"""Supervisor state file management for the single-owner DuckDB runtime."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

from mcp_strava.deploy.runtime_options import refresh_worker_enabled, supervisor_state_path

DUCKDB_OWNER_CONNECTION_POLICY = "per-thread-connection"


@dataclass(frozen=True)
class ChildSpec:
    name: str
    command: list[str]


@dataclass
class ChildProcess:
    name: str
    process: subprocess.Popen


def child_specs() -> list[ChildSpec]:
    """The single-owner DuckDB runtime spawns no child processes."""
    return []


def write_state(children: list[ChildProcess]) -> None:
    state_path = supervisor_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "owner": {
            "pid": os.getpid(),
            "db_mode": "duckdb-primary",
            "refresh_scheduler": "in-process" if refresh_worker_enabled() else "disabled",
            "connection_policy": DUCKDB_OWNER_CONNECTION_POLICY,
        },
        "children": {child.name: {"pid": child.process.pid} for child in children if child.name != "refresh"},
    }
    tmp_path = state_path.with_name(f".{state_path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    tmp_path.replace(state_path)


def remove_state() -> None:
    path = supervisor_state_path()
    if path.exists():
        path.unlink()
