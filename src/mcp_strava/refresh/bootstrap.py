"""Refresh runtime bootstrap and safe failure recording."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mcp_strava.adapters.duckdb.connection import MirrorConn
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.strava import SystemClock, SystemSleeper, _build_strava_transport
from mcp_strava.refresh.policy import RefreshPolicy
from mcp_strava.settings import Settings, get_settings


def _now_iso() -> str:
    # UTC-naive instant — refresh_state timestamps are read against the WR-02 UTC basis.
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


def ensure_runtime_refresh_schema(settings: Settings) -> None:
    del settings
    with MirrorConn() as conn:
        repo = DuckDBRepository.from_connection(conn)
        repo.get_refresh_state()
        repo.pending_refresh_requests()


def record_refresh_misconfigured(settings: Settings | None = None) -> None:
    """Record a safe refresh configuration failure for freshness surfaces."""
    settings = settings or get_settings()
    ensure_runtime_refresh_schema(settings)
    at = _now_iso()
    backoff_until = (datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)).isoformat()
    with MirrorConn() as conn:
        repo = DuckDBRepository.from_connection(conn)
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


def build_refresh_collaborators(settings: Settings | None = None):
    settings = settings or get_settings()
    clock = SystemClock()
    sleeper = SystemSleeper()
    transport = _build_strava_transport(settings, clock, sleeper)
    refresh_policy = RefreshPolicy.from_settings(settings)
    return settings, clock, sleeper, transport, refresh_policy
