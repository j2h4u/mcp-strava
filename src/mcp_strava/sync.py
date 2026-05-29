"""Refresh runtime entrypoints."""

from __future__ import annotations

import mcp_strava.refresh.runtime as refresh_runtime
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.db import DbConn
from mcp_strava.refresh.bootstrap import (
    RealClock,
    RealSleeper,
    build_refresh_collaborators,
    ensure_runtime_refresh_schema,
)
from mcp_strava.settings import get_settings

__all__ = [
    "RealClock",
    "RealSleeper",
    "backfill_activities",
    "build_refresh_collaborators",
    "sync_activities",
]


def sync_activities(quick: bool = False):
    """Run the standard refresh runtime."""
    settings = get_settings()
    ensure_runtime_refresh_schema(settings)
    _, clock, sleeper, transport, refresh_policy = build_refresh_collaborators(settings)
    with DbConn() as conn:
        repo = DuckDBRepository.from_connection(conn)
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
    """Run the backfill refresh runtime."""
    settings = get_settings()
    ensure_runtime_refresh_schema(settings)
    _, clock, sleeper, transport, refresh_policy = build_refresh_collaborators(settings)
    with DbConn() as conn:
        repo = DuckDBRepository.from_connection(conn)
        return refresh_runtime.run_catchup(
            repo,
            transport,
            refresh_policy,
            clock,
            sleeper,
            since=since,
            owner="refresh-backfill",
        )
