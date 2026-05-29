"""Refresh runtime bootstrap and safe failure recording."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

from mcp_strava.adapters.strava import (
    FileTokenProvider,
    RateLimitPolicy,
    StravaTransport,
    TokenRefreshTransport,
)
from mcp_strava.db import DbConn, repository_from_connection
from mcp_strava.refresh.policy import RefreshPolicy
from mcp_strava.settings import Settings, get_settings


class RealClock:
    def now(self) -> float:
        return time.time()


class RealSleeper:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _now_iso() -> str:
    return datetime.now().isoformat()


def ensure_runtime_refresh_schema(settings: Settings) -> None:
    del settings
    with DbConn() as conn:
        repo = repository_from_connection(conn)
        repo.get_refresh_state()
        repo.pending_refresh_requests()


def record_refresh_misconfigured(settings: Settings | None = None) -> None:
    """Record a safe refresh configuration failure for freshness surfaces."""
    settings = settings or get_settings()
    ensure_runtime_refresh_schema(settings)
    at = _now_iso()
    backoff_until = (datetime.now() + timedelta(hours=1)).isoformat()
    with DbConn() as conn:
        repo = repository_from_connection(conn)
        repo.record_refresh_failure(at, "refresh_misconfigured", backoff_until)
        repo.append_sync_log(
            timestamp=at,
            status="error",
            activities_seen=None,
            activities_new=None,
            streams_fetched=None,
            details_fetched=None,
            api_calls=None,
            error="refresh_misconfigured",
            kudos_fetched=None,
        )


def _read_token_values(token_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not token_path.exists():
        return values
    for raw_line in token_path.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.lstrip().startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _required_strava_client(settings: Settings) -> tuple[str, str]:
    values = _read_token_values(settings.token_path)
    required = ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError(f"Missing Strava client settings: {', '.join(missing)}. Check {settings.token_path}")
    return values["STRAVA_CLIENT_ID"], values["STRAVA_CLIENT_SECRET"]


def build_refresh_collaborators(settings: Settings | None = None):
    settings = settings or get_settings()
    clock = RealClock()
    sleeper = RealSleeper()
    client_id, client_secret = _required_strava_client(settings)
    refresh_transport = TokenRefreshTransport(
        client_id=client_id,
        client_secret=client_secret,
        clock=clock,
        sleeper=sleeper,
    )
    token_provider = FileTokenProvider(settings.token_path, refresh_transport, clock)
    transport = StravaTransport(token_provider, RateLimitPolicy(), clock, sleeper)
    refresh_policy = RefreshPolicy.from_settings(settings)
    return settings, clock, sleeper, transport, refresh_policy
