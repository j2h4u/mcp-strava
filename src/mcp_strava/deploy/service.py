"""Container service process for the single-owner DuckDB MCP runtime.

The runtime is DuckDB-only: one owner process serves MCP HTTP and runs the
mirror-refresh scheduler in-process. No separate child processes are spawned.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from mcp_strava.interfaces import mcp_http
from mcp_strava.refresh import worker as refresh_worker

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_DEFAULT_STATE_PATH = Path("/tmp/mcp-strava-supervisor.json")
DUCKDB_OWNER_CONNECTION_POLICY = "per-thread-connection"


@dataclass(frozen=True)
class ChildSpec:
    name: str
    command: list[str]


@dataclass
class ChildProcess:
    name: str
    process: subprocess.Popen


def _emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def _refresh_worker_enabled() -> bool:
    raw_value = os.environ.get("MCP_STRAVA_REFRESH_WORKER_ENABLED")
    if raw_value is None:
        return True
    normalized = raw_value.strip().lower()
    if normalized in _FALSE_VALUES:
        return False
    return normalized in _TRUE_VALUES


def _state_path() -> Path:
    raw_path = os.environ.get("MCP_STRAVA_SUPERVISOR_STATE_PATH")
    return Path(raw_path) if raw_path else _DEFAULT_STATE_PATH


def _child_specs() -> list[ChildSpec]:
    """The single-owner DuckDB runtime spawns no child processes."""
    return []


def _write_state(children: list[ChildProcess]) -> None:
    state_path = _state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "owner": {
            "pid": os.getpid(),
            "db_mode": "duckdb-primary",
            "refresh_scheduler": "in-process" if _refresh_worker_enabled() else "disabled",
            "connection_policy": DUCKDB_OWNER_CONNECTION_POLICY,
        },
        "children": {
            child.name: {"pid": child.process.pid}
            for child in children
            if child.name != "refresh"
        },
    }
    tmp_path = state_path.with_name(f".{state_path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    tmp_path.replace(state_path)


def _remove_state() -> None:
    path = _state_path()
    if path.exists():
        path.unlink()


def _run_duckdb_owner_service() -> int:
    stop_event = threading.Event()
    refresh_thread: threading.Thread | None = None
    if _refresh_worker_enabled():
        refresh_thread = threading.Thread(
            target=refresh_worker.run_forever,
            kwargs={"stop_event": stop_event, "emit_start": True},
            name="mcp-strava-refresh",
            daemon=True,
        )
        refresh_thread.start()
        _emit("service_refresh_scheduler_started", mode="in-process")

    _write_state([])
    try:
        return mcp_http.main([])
    finally:
        stop_event.set()
        if refresh_thread is not None:
            refresh_thread.join(timeout=5)
        _remove_state()


def main(argv: list[str] | None = None) -> int:
    del argv
    return _run_duckdb_owner_service()


if __name__ == "__main__":
    raise SystemExit(main())
