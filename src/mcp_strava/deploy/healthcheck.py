"""Container health check for the mcp-strava owner service."""

from __future__ import annotations

import json
import os
import sys
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from typing import cast

from mcp_strava.refresh.health import check_refresh_health


def _state_path() -> Path:
    raw_path = os.environ.get("MCP_STRAVA_SUPERVISOR_STATE_PATH")
    return Path(raw_path) if raw_path else Path("/tmp/mcp-strava-supervisor.json")


def _pid_alive(pid: int) -> bool:
    return Path(f"/proc/{pid}").exists()


def _validate_owner_and_children() -> None:
    path = _state_path()
    if not path.exists():
        raise RuntimeError("supervisor state file is missing")
    payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(payload, dict):
        raise RuntimeError("supervisor state file is malformed")
    owner = payload.get("owner")
    if not isinstance(owner, dict) or not isinstance(owner.get("pid"), int):
        raise RuntimeError("supervisor owner process is missing")
    if owner.get("db_mode") != "duckdb-primary":
        raise RuntimeError("supervisor owner process is not in DuckDB primary mode")
    if not _pid_alive(owner["pid"]):
        raise RuntimeError("supervisor owner process is not running")

    children = payload.get("children")
    if not isinstance(children, dict):
        raise RuntimeError("supervisor state file is malformed")
    for name, child in children.items():
        if not isinstance(child, dict) or not isinstance(child.get("pid"), int):
            raise RuntimeError(f"supervisor child is missing: {name}")
        if not _pid_alive(child["pid"]):
            raise RuntimeError(f"supervisor child is not running: {name}")


def _validate_http() -> None:
    port = int(os.environ.get("MCP_STRAVA_HTTP_PORT", "8080"))
    connection = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", "/mcp", headers={"Accept": "text/event-stream"})
        response = connection.getresponse()
        if response.status >= 400:
            raise RuntimeError(f"MCP HTTP health returned {response.status}")
    except (OSError, HTTPException) as exc:
        raise RuntimeError("MCP HTTP health request failed") from exc
    finally:
        connection.close()


def main() -> int:
    try:
        _validate_owner_and_children()
        _validate_http()
        check_refresh_health()
    except Exception as exc:
        print(f"healthcheck failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
