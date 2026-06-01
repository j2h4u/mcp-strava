"""Container service entrypoint for the single-owner DuckDB MCP runtime.

The runtime is DuckDB-only: one owner process serves MCP HTTP and runs the
mirror-refresh scheduler in-process. No separate child processes are spawned.
"""

from __future__ import annotations

import threading

from mcp_strava.deploy.refresh_scheduler import require_hr_config_for_worker, start_refresh_scheduler
from mcp_strava.deploy.supervisor_state import remove_state, write_state
from mcp_strava.interfaces import mcp_http


def _run_duckdb_owner_service() -> int:
    require_hr_config_for_worker()
    stop_event = threading.Event()
    refresh_thread = start_refresh_scheduler(stop_event)

    write_state([])
    try:
        return mcp_http.main([])
    finally:
        stop_event.set()
        if refresh_thread is not None:
            refresh_thread.join(timeout=5)
        remove_state()


def main(argv: list[str] | None = None) -> int:
    del argv
    return _run_duckdb_owner_service()


if __name__ == "__main__":
    raise SystemExit(main())
