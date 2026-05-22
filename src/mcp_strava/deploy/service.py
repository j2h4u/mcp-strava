"""Container supervisor for MCP HTTP and mirror refresh processes."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_DEFAULT_STATE_PATH = Path("/tmp/mcp-strava-supervisor.json")


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
    specs: list[ChildSpec] = []
    if _refresh_worker_enabled():
        specs.append(
            ChildSpec(
                name="refresh",
                command=[sys.executable, "-m", "mcp_strava.refresh.worker"],
            )
        )
    specs.append(
        ChildSpec(
            name="mcp-http",
            command=[sys.executable, "-m", "mcp_strava.interfaces.mcp_http"],
        )
    )
    return specs


def _start_children(specs: list[ChildSpec]) -> list[ChildProcess]:
    children: list[ChildProcess] = []
    for spec in specs:
        process = subprocess.Popen(spec.command)
        children.append(ChildProcess(name=spec.name, process=process))
        _emit("service_child_started", name=spec.name, pid=process.pid)
    return children


def _write_state(children: list[ChildProcess]) -> None:
    state_path = _state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "children": {
            child.name: {"pid": child.process.pid}
            for child in children
        }
    }
    tmp_path = state_path.with_name(f".{state_path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    tmp_path.replace(state_path)


def _terminate_children(children: list[ChildProcess], *, timeout_seconds: float = 10.0) -> None:
    running = [child for child in children if child.process.poll() is None]
    for child in running:
        child.process.terminate()
    deadline = time.monotonic() + timeout_seconds
    for child in running:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            child.process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            child.process.kill()
            child.process.wait()


def _remove_state() -> None:
    path = _state_path()
    if path.exists():
        path.unlink()


def main(argv: list[str] | None = None) -> int:
    del argv
    stop_requested = False

    def _request_stop(signum, frame) -> None:
        del frame
        nonlocal stop_requested
        stop_requested = True
        _emit("service_shutdown_requested", signal=signum)

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    children = _start_children(_child_specs())
    _write_state(children)
    try:
        while True:
            if stop_requested:
                _terminate_children(children)
                return 0
            for child in children:
                returncode = child.process.poll()
                if returncode is not None:
                    _emit("service_child_exited", name=child.name, returncode=returncode)
                    _terminate_children(children)
                    return returncode if returncode != 0 else 1
            time.sleep(1)
    finally:
        _remove_state()


if __name__ == "__main__":
    raise SystemExit(main())
