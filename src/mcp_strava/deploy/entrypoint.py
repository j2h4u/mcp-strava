"""Container entrypoint that validates runtime DB before starting the service."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp_strava.adapters.duckdb.migrations import run_duckdb_cutover
from mcp_strava.adapters.sqlite.migrations import latest_migration_version, run_migrations
from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.adapters.sqlite.schema import read_user_version
from mcp_strava.deploy.preflight import validate_runtime_db


def _needs_migration(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    if db_path.suffix.lower() == ".duckdb":
        return False
    latest_version = latest_migration_version()
    with SQLiteRepository.from_path(db_path, expected_mirror=True) as repo:
        current_version = read_user_version(repo.conn)
    return current_version < latest_version


def _sqlite_source_for_duckdb_target(db_path: Path) -> Path:
    return db_path.with_suffix(".db")


def _prepare_duckdb_target_if_missing(db_path: Path) -> None:
    if db_path.suffix.lower() != ".duckdb" or db_path.exists():
        return

    source_sqlite = _sqlite_source_for_duckdb_target(db_path)
    if not source_sqlite.exists():
        return

    if _needs_migration(source_sqlite):
        run_migrations(source_sqlite)

    report = run_duckdb_cutover(
        source_sqlite_path=source_sqlite,
        target_duckdb_path=db_path,
        backup_dir=db_path.parent / "backups",
        now=None,
        owner="entrypoint",
    )
    print(
        "entrypoint duckdb cutover prepared: "
        f"source={source_sqlite} target={db_path} backup={report.backup_path}",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    del argv
    db_path = Path(os.environ["MCP_STRAVA_DB_PATH"])
    try:
        _prepare_duckdb_target_if_missing(db_path)
        if _needs_migration(db_path):
            run_migrations(db_path)
        validate_runtime_db(db_path, quick=False)
    except Exception as exc:
        print(f"entrypoint preflight failed: {exc}", file=sys.stderr)
        return 1

    os.execvp(
        sys.executable,
        [sys.executable, "-m", "mcp_strava.deploy.service"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
