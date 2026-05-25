"""Container entrypoint that validates runtime DB before starting the service."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp_strava.adapters.sqlite.migrations import latest_migration_version, run_migrations
from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.adapters.sqlite.schema import read_user_version
from mcp_strava.deploy.preflight import validate_runtime_db


def _needs_migration(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    latest_version = latest_migration_version()
    with SQLiteRepository.from_path(db_path, expected_mirror=True) as repo:
        current_version = read_user_version(repo.conn)
    return current_version < latest_version


def main(argv: list[str] | None = None) -> int:
    del argv
    db_path = Path(os.environ["MCP_STRAVA_DB_PATH"])
    try:
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
