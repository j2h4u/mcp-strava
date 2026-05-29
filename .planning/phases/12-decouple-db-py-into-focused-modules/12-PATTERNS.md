# Phase 12 — Pattern Map

**Mapped:** 2026-05-30
**Purpose:** For each file created/modified, the closest existing analog + concrete excerpts so executors replicate established conventions instead of inventing.

> This phase is move/delete, not greenfield. "Analog" usually means "the code being moved" or "an adjacent module in the same package."

---

## NEW: `src/mcp_strava/adapters/strava/clock.py` (D-07)

**Role:** Real implementations of the `Clock`/`Sleeper` ports (rename of `db.py::_RealClock`/`_RealSleeper` → `SystemClock`/`SystemSleeper`).
**Data flow:** Injected into `StravaTransport`/`StravaClient` for retry/rate-limit timing.

**Closest analog — `refresh/bootstrap.py` (the already-public, canonical pair):**
```python
import time

class RealClock:
    def now(self) -> float:
        return time.time()

class RealSleeper:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
```

**Port contract being implemented — `adapters/strava/types.py`:**
```python
class Clock(Protocol):
    def now(self) -> float: ...

class Sleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...
```

**Convergence note:** `db.py::_RealClock.now()` uses `datetime.now().timestamp()`; `bootstrap.py::RealClock.now()` uses `time.time()`. Both return wall-clock epoch seconds — **pick `time.time()`** (cleaner, matches the existing public impl). After creating `SystemClock`/`SystemSleeper` in `clock.py`, update `bootstrap.py` to import them (delete its local `RealClock`/`RealSleeper`), and update the `sync.py` re-exports (`__all__` lists `RealClock`/`RealSleeper`) + `cli.py` consumers (L20-21, L281-282) to the new names. This is a rename rippling through 3 consumers, not new behavior.

---

## NEW: `src/mcp_strava/adapters/strava/client.py` (D-08)

**Role:** `StravaClient` facade — owns transport construction + `(data, rate_headers)` contract + error mapping + `refresh_token()`.
**Data flow:** settings → token provider chain → `StravaTransport` → `(data, rate_info.as_dict())`; consumers are `cli.py` (`api_request`, `refresh_token`) and (post-deletion) the security-guard test literals.

**Closest analog #1 — construction chain in `refresh/bootstrap.py::build_refresh_collaborators` (replicate this wiring, source creds from settings):**
```python
def build_refresh_collaborators(settings=None):
    settings = settings or get_settings()
    clock = RealClock()            # → SystemClock
    sleeper = RealSleeper()        # → SystemSleeper
    client_id, client_secret = _required_strava_client(settings)
    refresh_transport = TokenRefreshTransport(
        client_id=client_id, client_secret=client_secret, clock=clock, sleeper=sleeper,
    )
    token_provider = FileTokenProvider(settings.token_path, refresh_transport, clock)
    transport = StravaTransport(token_provider, RateLimitPolicy(), clock, sleeper)
    ...
```

**Closest analog #2 — the error-mapping + return contract being relocated from `db.py`:**
```python
def api_request(path, token=None):
    """Returns (data, rate_headers)."""
    try:
        response = _build_transport(token).fetch(path)
    except StravaUnavailable as exc:
        if exc.reason == "rate_limited":
            return {"_rate_limited": True, "_retry_after": None}, {}
        raise RuntimeError(f"Strava API request failed: {exc.reason}") from exc
    return response.data, response.rate_info.as_dict()

def refresh_token():
    try:
        return _build_token_provider().refresh()
    except StravaUnavailable as exc:
        raise RuntimeError(f"Strava OAuth token refresh failed: {exc.reason}") from exc
```

**Replication rules:**
- Source `client_id`/`client_secret` from **settings** (D-06), not a new `.env` parser. Delete `db.py::_read_token_values` and `db.py::_CompatTokenProvider` (D-05); `bootstrap.py` also has a `_read_token_values`/`_required_strava_client` that should consume settings once D-06 lands.
- Preserve the exact `StravaUnavailable.reason == "rate_limited"` sentinel branch and the `RuntimeError(f"...: {exc.reason}")` messages verbatim (behavior parity, GP-04).
- **Security:** never include `client_secret` in any `StravaClient` exception message — current code only surfaces `exc.reason`. Keep it that way (RESEARCH Security Domain, T-12-02).

---

## MODIFIED: `src/mcp_strava/adapters/duckdb/connection.py` (D-01, D-02, D-03)

**Role:** Receives `MirrorConn` (renamed `DbConn`), `ReadConn`, `_thread_state`, `_thread_read_connections`, `reset_thread_connections`, `_db_path`, `_open_storage_connection`. (`init_db` is DEAD — delete, do not relocate.)
**Data flow:** `MirrorConn`/`ReadConn` context managers → `open_expected_mirror_db` (already in this file).

**Closest analog — this file already owns the open-policy the helpers depend on:**
```python
def open_expected_mirror_db(path, read_only=False):
    db_path = Path(path)
    if not db_path.exists():
        raise RuntimeError(f"Expected DuckDB mirror does not exist: {db_path}")
    return _connect_or_translate_lock(db_path, read_only=read_only)
```

**Verbatim-move unit (D-02 — move all four together, single edit):**
```python
_thread_state = threading.local()

def _thread_read_connections() -> dict[str, object]: ...
class ReadConn: ...               # evict-on-error in __exit__ — preserve exactly
def reset_thread_connections() -> None: ...
```

**Replication rules:**
- Rename `DbConn` → `MirrorConn` (D-03). `_db_path()` currently does `str(get_settings().database_path)` — keep that; `_open_storage_connection` is `open_expected_mirror_db(path)` — collapse to a direct call once co-located (Claude's discretion on internal tidy).
- Keep `_thread_state`/`ReadConn`/`reset_thread_connections` co-located so the conftest reset hook and the read path share one `threading.local()` (RESEARCH Pitfall 1).

---

## MODIFIED: `src/mcp_strava/settings.py` (D-06)

**Role:** Add `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` resolution alongside `token_path`.

**Closest analog — the existing `resolve(...)` + `_KEYS` + dataclass pattern in this file:**
```python
_KEYS = { "MCP_STRAVA_DB_PATH", "MCP_STRAVA_TOKEN_PATH", ... }   # add STRAVA_CLIENT_ID/SECRET

def resolve(key: str, default: str) -> str:
    if key in env_map: return env_map[key]
    if key in file_values: return file_values[key]
    return default
```

**Replication rules:**
- Follow the established `resolve("KEY", default)` idiom and add the keys to `_KEYS` (so the cache key includes them and `.env`-file resolution works). Decide whether to surface via a new dataclass field (e.g., `StravaAuthSettings`) or top-level `Settings` fields — match the existing `frozen=True` dataclass style. These creds are required (no safe default) so resolution should fail-fast when missing, mirroring `bootstrap.py::_required_strava_client` and `AthleteSettings.hr_rest`'s fail-fast convention.

---

## MODIFIED: callers (mechanical import swaps)

**Analog = the import line itself.** Each is a one-line repoint:
- `application/{aggregate_services,metric_services,product_facts,freshness,mirror_coverage}.py`, `cli.py`, `sync.py`, `refresh/{bootstrap,worker}.py`: `from mcp_strava.db import ...` → new homes; `repository_from_connection/path` → `DuckDBRepository.from_connection/from_path` (D-04).
- Tests `conftest.py`, `test_metric_services.py`, `test_repository_boundary.py`, `test_smoke.py`, `test_phase01_validation.py`: repoint imports AND monkeypatch-by-path targets (`db._db_path`, `db.open_expected_mirror_db`, `db.api_request`, `db.refresh_token`) to the new module objects.
- `test_security_guards.py`: update literal guard strings `mcp_strava.db.api_request`/`refresh_token` → new facade path; remove/retarget the now-vacuous `init_db` DDL guards (RESEARCH Open Question 1).

---

## PATTERN MAPPING COMPLETE

Files mapped: 2 new (`clock.py`, `client.py`), 2 modified-with-additions (`connection.py`, `settings.py`), ~14 caller/test edits (mechanical). No new external patterns required — every analog is in-repo.
