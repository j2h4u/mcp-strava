"""Fail-closed runtime DB validation for Docker startup."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from mcp_strava.adapters.duckdb.connection import open_expected_mirror_db as open_expected_duckdb
from mcp_strava.adapters.duckdb.schema import DUCKDB_TABLES

REQUIRED_RUNTIME_TABLES: tuple[str, ...] = (
    "activities",
    "streams",
    "athlete_zones",
    "sync_log",
    "kudos",
    "refresh_state",
    "refresh_requests",
)


def _duckdb_table_exists(conn, table: str) -> bool:
    return conn.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_name = ?
        LIMIT 1
        """,
        [table],
    ).fetchone() is not None


def _duckdb_read_model_readiness(conn) -> dict[str, object]:
    missing_tables = [
        table
        for table in (
            "activity_source_state",
            "metric_dirty_activities",
            "activity_metric_facts",
            "daily_load_facts",
            "training_model_daily",
            "rolling_period_facts",
            "read_model_refresh_runs",
        )
        if not _duckdb_table_exists(conn, table)
    ]
    schema_ready = not missing_tables
    dirty_count = None
    activity_fact_count = None
    ok_run_count = None
    if schema_ready:
        dirty_count = int(conn.execute("SELECT COUNT(*) FROM metric_dirty_activities").fetchone()[0])
        activity_fact_count = int(conn.execute("SELECT COUNT(*) FROM activity_metric_facts").fetchone()[0])
        ok_run_count = int(
            conn.execute("SELECT COUNT(*) FROM read_model_refresh_runs WHERE status = 'ok'").fetchone()[0]
        )
    return {
        "schema_ready": schema_ready,
        "missing_tables": missing_tables,
        "dirty_count": dirty_count,
        "activity_fact_count": activity_fact_count,
        "ok_run_count": ok_run_count,
        "facts_current": bool(schema_ready and dirty_count == 0 and activity_fact_count and ok_run_count),
    }


def _duckdb_refresh_state(conn) -> dict[str, object]:
    row = conn.execute(
        """
        SELECT lease_owner, lease_expires_at, last_status, checkpoint_stage
        FROM refresh_state
        WHERE id = 1
        """
    ).fetchone()
    if row is None:
        return {
            "lease_owner": None,
            "lease_expires_at": None,
            "last_status": None,
            "checkpoint_stage": None,
        }
    columns = ("lease_owner", "lease_expires_at", "last_status", "checkpoint_stage")
    return dict(zip(columns, row, strict=False))


def _lease_active(refresh_state: dict[str, object]) -> bool:
    owner = refresh_state.get("lease_owner")
    expires_at = refresh_state.get("lease_expires_at")
    if owner is None:
        return False
    if expires_at is None:
        return True
    try:
        return datetime.fromisoformat(str(expires_at)) > datetime.now()
    except ValueError:
        return True


def _validate_duckdb_runtime_db(
    path: Path,
    *,
    quick: bool = False,
    allow_active_refresh_lease: bool = False,
) -> dict[str, object]:
    with open_expected_duckdb(path) as conn:
        missing = [table for table in DUCKDB_TABLES if not _duckdb_table_exists(conn, table)]
        if missing:
            raise RuntimeError(f"Missing required DuckDB runtime table: {missing[0]}")
        refresh_state = _duckdb_refresh_state(conn)
        if _lease_active(refresh_state) and not allow_active_refresh_lease:
            raise RuntimeError(f"active refresh lease blocks DuckDB startup: {refresh_state.get('lease_owner')}")
        activity_count = int(conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0])
        if quick:
            return {
                "path": str(path),
                "quick": True,
                "storage": "duckdb",
                "activity_count": activity_count,
            }
        return {
            "path": str(path),
            "storage": "duckdb",
            "activity_count": activity_count,
            "read_model": _duckdb_read_model_readiness(conn),
            "refresh_state": refresh_state,
        }


def validate_runtime_db(
    path: Path,
    *,
    quick: bool = False,
    allow_active_refresh_lease: bool = False,
) -> dict[str, object]:
    """Validate runtime DB structure.

    DuckDB runtime validation is an offline startup gate. Live health checks use
    the owner process and HTTP readiness path instead of opening the live DB.
    """
    if not path.exists():
        raise RuntimeError(f"Expected runtime DB does not exist: {path}")
    if path.suffix.lower() != ".duckdb":
        raise RuntimeError(f"Runtime DB must be DuckDB: {path}")
    return _validate_duckdb_runtime_db(
        path,
        quick=quick,
        allow_active_refresh_lease=allow_active_refresh_lease,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate runtime mirror DB")
    parser.add_argument("--db", required=True, help="Path to runtime DB")
    parser.add_argument("--quick", action="store_true", help="Run lightweight health check")
    parser.add_argument("--quiet", action="store_true", help="Suppress success output")
    args = parser.parse_args(argv)

    try:
        validate_runtime_db(Path(args.db), quick=args.quick)
    except Exception as exc:
        if not args.quiet:
            print(f"preflight failed: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print("preflight ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
