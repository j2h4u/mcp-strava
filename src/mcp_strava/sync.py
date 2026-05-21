"""Refresh runtime compatibility entrypoints."""

from __future__ import annotations

import time
from pathlib import Path

import mcp_strava.refresh.runtime as refresh_runtime
from mcp_strava.adapters.sqlite.migrations import run_preflight
from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.adapters.strava import (
    FileTokenProvider,
    RateLimitPolicy,
    StravaTransport,
    TokenRefreshTransport,
)
from mcp_strava.db import DbConn
from mcp_strava.refresh import RefreshPolicy
from mcp_strava.settings import Settings, get_settings


class RealClock:
    def now(self) -> float:
        return time.time()


class RealSleeper:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


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
        raise RuntimeError(
            f"Missing Strava client settings: {', '.join(missing)}. "
            f"Check {settings.token_path}"
        )
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


def ensure_refresh_schema(preflight_report) -> None:
    row_counts = getattr(preflight_report, "row_counts", {})
    if "refresh_state" not in row_counts or "refresh_requests" not in row_counts:
        raise RuntimeError(
            "Refresh metadata schema is missing. Run `python -m mcp_strava db-migrate` "
            "before sync, backfill, or db-refresh."
        )


def sync_activities(quick: bool = False):
    """Run the standard refresh runtime behind the legacy sync entrypoint."""
    settings = get_settings()
    ensure_refresh_schema(run_preflight(settings.database_path))
    _, clock, sleeper, transport, refresh_policy = build_refresh_collaborators(settings)
    with DbConn() as conn:
        repo = SQLiteRepository.from_connection(conn)
        return refresh_runtime.run_once(
            repo,
            transport,
            refresh_policy,
            clock,
            sleeper,
            force=quick,
            mode="quick" if quick else "daily",
        )


def backfill_activities(since: str | None = None):
    """Run the backfill refresh runtime behind the legacy backfill entrypoint."""
    settings = get_settings()
    ensure_refresh_schema(run_preflight(settings.database_path))
    _, clock, sleeper, transport, refresh_policy = build_refresh_collaborators(settings)
    with DbConn() as conn:
        repo = SQLiteRepository.from_connection(conn)
        return refresh_runtime.run_backfill(
            repo,
            transport,
            refresh_policy,
            clock,
            sleeper,
            since=since,
            owner="refresh-backfill",
        )
