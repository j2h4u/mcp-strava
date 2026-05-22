"""Container entrypoint that validates runtime DB before starting the service."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp_strava.deploy.preflight import validate_runtime_db


def main(argv: list[str] | None = None) -> int:
    del argv
    db_path = Path(os.environ["MCP_STRAVA_DB_PATH"])
    try:
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
