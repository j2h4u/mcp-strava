"""Database layer — connection management, auth, zones, TRIMP queries."""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

from mcp_strava.adapters.duckdb.connection import open_expected_mirror_db
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.strava import (
    FileTokenProvider,
    RateLimitPolicy,
    StravaTransport,
    StravaUnavailable,
    TokenRefreshTransport,
)
from mcp_strava.settings import get_settings


def _db_path() -> str:
    return str(get_settings().database_path)


def _env_path() -> str:
    return str(get_settings().token_path)


def _open_storage_connection(path: str | Path):
    return open_expected_mirror_db(path)


# --- DB ---

class DbConn:
    """Context manager for primary storage connections — auto-closes on exit."""

    def __enter__(self):
        self.conn = _open_storage_connection(_db_path())
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()


# --- Thread-local read connection reuse ---
#
# Opening a fresh DuckDB connection per request costs ~25 ms (catalog attach),
# which dominated warm read latency. Read services reuse one connection per
# (thread, db path) instead. DuckDB caches the database instance by path within
# a process, so a persistent reader coexists with the refresh writer exactly as
# the previous open-per-call readers did — only the connection lifetime changes,
# not the in-process RLock or MVCC behaviour. Each FastMCP worker thread keeps
# its own connection, matching the single-owner / per-thread-connection model.

_thread_state = threading.local()


def _thread_read_connections() -> dict[str, object]:
    connections = getattr(_thread_state, "read_connections", None)
    if connections is None:
        connections = {}
        _thread_state.read_connections = connections
    return connections


class ReadConn:
    """Thread-local reused read connection — opened once per (thread, db path).

    Not closed on normal exit, so repeated reads avoid connect/close overhead.
    On an error inside the ``with`` block the connection is evicted and closed
    so the next call reopens a clean one (a poisoned cached connection is a
    worse failure mode than the churn this removes). Use
    ``reset_thread_connections()`` for shutdown and per-test isolation.
    """

    def __enter__(self):
        self._path = _db_path()
        connections = _thread_read_connections()
        conn = connections.get(self._path)
        if conn is None:
            conn = _open_storage_connection(self._path)
            connections[self._path] = conn
        return conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            conn = _thread_read_connections().pop(self._path, None)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        return False


def reset_thread_connections() -> None:
    """Close and clear this thread's cached read connections (tests, shutdown)."""
    connections = getattr(_thread_state, "read_connections", None)
    if not connections:
        return
    for conn in list(connections.values()):
        try:
            conn.close()
        except Exception:
            pass
    connections.clear()



def init_db(conn):
    # Runtime paths do not run schema-changing DDL; migration owns schema creation.
    del conn
    check = _open_storage_connection(_db_path())
    check.close()


def repository_from_connection(conn):
    return DuckDBRepository.from_connection(conn)


def repository_from_path(db_path: str | Path, *, expected_mirror: bool = False):
    return DuckDBRepository.from_path(db_path, expected_mirror=expected_mirror)


# --- Auth ---

class _RealClock:
    def now(self) -> float:
        return datetime.now().timestamp()


class _RealSleeper:
    def sleep(self, seconds: float) -> None:
        import time
        time.sleep(seconds)


class _CompatTokenProvider:
    def __init__(self, token: str | None, token_path: Path, clock, sleeper) -> None:
        self._token = token
        self._token_path = token_path
        self._clock = clock
        self._sleeper = sleeper
        self._delegate = None

    def access_token(self) -> str:
        if self._token:
            return self._token
        return self._file_provider().access_token()

    def refresh(self) -> str:
        self._token = self._file_provider().refresh()
        return self._token

    def _file_provider(self) -> FileTokenProvider:
        if self._delegate is None:
            values = _read_token_values(self._token_path)
            required = ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET")
            missing = [key for key in required if not values.get(key)]
            if missing:
                raise RuntimeError(
                    f"Missing env vars for Strava auth: {', '.join(missing)}. "
                    f"Check {self._token_path}"
                )
            refresh_transport = TokenRefreshTransport(
                client_id=values["STRAVA_CLIENT_ID"],
                client_secret=values["STRAVA_CLIENT_SECRET"],
                clock=self._clock,
                sleeper=self._sleeper,
            )
            self._delegate = FileTokenProvider(self._token_path, refresh_transport, self._clock)
        return self._delegate


def _read_token_values(token_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not token_path.exists():
        return values
    for raw_line in token_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _build_token_provider(token: str | None = None) -> _CompatTokenProvider:
    settings = get_settings()
    clock = _RealClock()
    sleeper = _RealSleeper()
    return _CompatTokenProvider(token, settings.token_path, clock, sleeper)


def _build_transport(token: str | None = None) -> StravaTransport:
    clock = _RealClock()
    sleeper = _RealSleeper()
    token_provider = _CompatTokenProvider(token, Path(_env_path()), clock, sleeper)
    return StravaTransport(token_provider, RateLimitPolicy(), clock, sleeper)


def refresh_token():
    try:
        return _build_token_provider().refresh()
    except StravaUnavailable as exc:
        raise RuntimeError(f"Strava OAuth token refresh failed: {exc.reason}") from exc


def api_request(path, token=None):
    """Strava API request. Returns (data, rate_headers) tuple.
    rate_headers contains usage_15min, usage_daily, limit_15min from X-RateLimit-* headers."""
    try:
        response = _build_transport(token).fetch(path)
    except StravaUnavailable as exc:
        if exc.reason == "rate_limited":
            return {"_rate_limited": True, "_retry_after": None}, {}
        raise RuntimeError(f"Strava API request failed: {exc.reason}") from exc
    return response.data, response.rate_info.as_dict()


# --- HR Zones ---

def get_zones():
    """Get cached zones or fetch from Strava."""
    with DbConn() as conn:
        repo = repository_from_connection(conn)
        zones_json = repo.latest_athlete_zones()
        if zones_json is not None:
            return json.loads(zones_json)
    data, _rate_info = api_request('/athlete/zones')
    zones = [{'min': z['min'], 'max': z['max'] if z['max'] != -1 else 300}
             for z in data['heart_rate']['zones']]
    with DbConn() as conn:
        repo = repository_from_connection(conn)
        repo.insert_athlete_zones(datetime.now().isoformat(), json.dumps(zones))
    return zones


# --- TRIMP History ---

def get_daily_trimp_history(conn, days=None, sport_filter=None):
    """Return dict {date_str: trimp} for last N days (0 for rest days).
    days=None: use all available history (needed for Banister warmup).
    sport_filter='training': exclude non-training activities (Walk) from TRIMP.
                           Prevents daily walking from creating false fatigue signals.
    """
    from mcp_strava.hr_zones import get_zone_model
    repo = repository_from_connection(conn)
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d') if days is not None else None
    athlete = get_settings().athlete
    if athlete.hr_rest is None:
        raise RuntimeError(
            "MCP_STRAVA_HR_REST is not set — cannot compute HR zones. "
            "Set MCP_STRAVA_HR_REST to the athlete's resting heart rate."
        )
    hr_max = repo.max_heartrate()
    if hr_max is None:
        return {}
    bounds = get_zone_model(athlete.hr_zone_model).zone_bounds(
        hr_max=int(hr_max), hr_rest=athlete.hr_rest
    )
    return repo.observed_trimp_history(bounds=bounds, since_day=since, sport_filter=sport_filter)
