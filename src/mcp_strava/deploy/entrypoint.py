"""Container entrypoint that validates runtime DB before starting the service."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb

from mcp_strava.deploy.preflight import validate_runtime_db


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        db_path = Path(os.environ["MCP_STRAVA_DB_PATH"])
        validate_runtime_db(
            db_path,
            quick=False,
            allow_active_refresh_lease=db_path.suffix.lower() == ".duckdb",
        )
    except (KeyError, OSError, RuntimeError, duckdb.Error) as exc:
        print(f"entrypoint preflight failed: {exc}", file=sys.stderr)
        return 1

    os.execvp(
        sys.executable,
        [sys.executable, "-m", "mcp_strava.deploy.service"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
