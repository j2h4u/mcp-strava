"""Refresh runtime compatibility entrypoints."""

from __future__ import annotations

from types import SimpleNamespace

import mcp_strava.refresh.runtime as refresh_runtime
from mcp_strava.adapters.duckdb.connection import open_expected_mirror_db
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.duckdb.schema import DUCKDB_TABLES
from mcp_strava.refresh.bootstrap import (
    RealClock,
    RealSleeper,
    build_refresh_collaborators,
    ensure_refresh_schema,
)
from mcp_strava.db import DbConn
from mcp_strava.settings import get_settings


__all__ = [
    "RealClock",
    "RealSleeper",
    "backfill_activities",
    "build_refresh_collaborators",
    "ensure_refresh_schema",
    "sync_activities",
]


def run_preflight(db_path):
    conn = open_expected_mirror_db(db_path, read_only=True)
    try:
        present = {
            row[0]
            for row in conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                """
            ).fetchall()
        }
        row_counts = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in DUCKDB_TABLES
            if table in present
        }
        return SimpleNamespace(row_counts=row_counts)
    finally:
        conn.close()


def sync_activities(quick: bool = False):
    """Run the standard refresh runtime behind the legacy sync entrypoint."""
    settings = get_settings()
    ensure_refresh_schema(run_preflight(settings.database_path))
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
    """Run the backfill refresh runtime behind the legacy backfill entrypoint."""
    settings = get_settings()
    ensure_refresh_schema(run_preflight(settings.database_path))
    _, clock, sleeper, transport, refresh_policy = build_refresh_collaborators(settings)
    with DbConn() as conn:
        repo = DuckDBRepository.from_connection(conn)
        return refresh_runtime.run_backfill(
            repo,
            transport,
            refresh_policy,
            clock,
            sleeper,
            since=since,
            owner="refresh-backfill",
        )
