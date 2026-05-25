"""Fail-closed runtime DB validation for Docker startup and health checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mcp_strava.adapters.sqlite.connection import open_expected_mirror_db
from mcp_strava.adapters.sqlite.schema import READ_MODEL_TABLES_V6, read_user_version, validate_required_inventory

REQUIRED_RUNTIME_TABLES: tuple[str, ...] = (
    "activities",
    "streams",
    "athlete_zones",
    "sync_log",
    "kudos",
    "refresh_state",
    "refresh_requests",
)


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _stream_columns(conn) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(streams)").fetchall()}


def _validate_phase6_versioned_stream_inventory(conn) -> None:
    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0] or 0)
    columns = _stream_columns(conn)
    if user_version >= 4:
        if "latlng" in columns:
            raise RuntimeError("Phase 6 v4 runtime schema must not include streams.latlng")
        if "values_json" not in columns:
            raise RuntimeError("Phase 6 v4 runtime schema missing streams.values_json")
        return
    if user_version == 3:
        if "latlng" not in columns:
            raise RuntimeError("Phase 6 v3 intermediate schema must include streams.latlng before v4 migration")
        if "values_json" not in columns:
            raise RuntimeError("Phase 6 v3 intermediate schema missing streams.values_json")
        return
    raise RuntimeError(f"Unsupported runtime schema version for Phase 6: user_version={user_version}")


def _read_model_readiness(conn) -> dict[str, object]:
    version = read_user_version(conn)
    missing_tables = [table for table in READ_MODEL_TABLES_V6 if not _table_exists(conn, table)]
    schema_ready = version >= 6 and not missing_tables
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


def validate_runtime_db(path: Path, *, quick: bool = False) -> dict[str, object]:
    """Validate runtime DB structure.

    Runtime is expected to use `/opt/docker/mcp-strava/data/strava.db` after live
    cutover. The repository `data/strava.db` remains a development snapshot unless
    commands explicitly override paths.
    """
    if not path.exists():
        raise RuntimeError(f"Expected runtime DB does not exist: {path}")

    with open_expected_mirror_db(path) as conn:
        if quick:
            activity_count = int(conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0])
            return {"path": str(path), "quick": True, "activity_count": activity_count}

        validate_required_inventory(conn)
        _validate_phase6_versioned_stream_inventory(conn)
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
        for table in REQUIRED_RUNTIME_TABLES:
            if not _table_exists(conn, table):
                raise RuntimeError(f"Missing required runtime table: {table}")
        return {
            "path": str(path),
            "user_version": read_user_version(conn),
            "integrity_result": integrity,
            "read_model": _read_model_readiness(conn),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate runtime SQLite mirror.")
    parser.add_argument("--db", required=True, help="Path to runtime SQLite DB")
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
