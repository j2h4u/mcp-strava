"""Fail-closed runtime DB validation for Docker startup and health checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mcp_strava.adapters.sqlite.connection import open_expected_mirror_db
from mcp_strava.adapters.sqlite.schema import validate_required_inventory

REQUIRED_RUNTIME_TABLES: tuple[str, ...] = (
    "activities",
    "streams",
    "athlete_zones",
    "sync_log",
    "kudos",
    "refresh_state",
    "refresh_requests",
)


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


def validate_runtime_db(path: Path, *, quick: bool = False) -> None:
    """Validate runtime DB structure.

    Runtime is expected to use `/opt/docker/mcp-strava/data/strava.db` after live
    cutover. The repository `data/strava.db` remains a development snapshot unless
    commands explicitly override paths.
    """
    if not path.exists():
        raise RuntimeError(f"Expected runtime DB does not exist: {path}")

    with open_expected_mirror_db(path) as conn:
        if quick:
            conn.execute("SELECT COUNT(*) FROM activities").fetchone()
            return

        validate_required_inventory(conn)
        _validate_phase6_versioned_stream_inventory(conn)
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
        for table in REQUIRED_RUNTIME_TABLES:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if exists is None:
                raise RuntimeError(f"Missing required runtime table: {table}")


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
