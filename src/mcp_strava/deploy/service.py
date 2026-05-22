"""Container service runtime for HTTP MCP plus internal mirror refresh."""

from __future__ import annotations

import os
from threading import Thread

from mcp_strava.interfaces.mcp_http import main as run_mcp_http
from mcp_strava.refresh.worker import run_forever as run_refresh_worker

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _refresh_worker_enabled() -> bool:
    raw_value = os.environ.get("MCP_STRAVA_REFRESH_WORKER_ENABLED")
    if raw_value is None:
        return True
    normalized = raw_value.strip().lower()
    if normalized in _FALSE_VALUES:
        return False
    return normalized in _TRUE_VALUES


def _start_refresh_worker() -> Thread | None:
    if not _refresh_worker_enabled():
        return None
    thread = Thread(target=run_refresh_worker, name="mcp-strava-refresh", daemon=True)
    thread.start()
    return thread


def main(argv: list[str] | None = None) -> int:
    _start_refresh_worker()
    return run_mcp_http(argv)


if __name__ == "__main__":
    raise SystemExit(main())
