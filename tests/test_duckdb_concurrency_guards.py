from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (_repo_root() / path).read_text(encoding="utf-8")


def _calls_named(tree: ast.AST, name: str) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == name:
                calls.append(node)
            elif isinstance(func, ast.Attribute) and func.attr == name:
                calls.append(node)
    return calls


def test_duckdb_service_does_not_launch_standalone_refresh_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_strava.deploy import service

    monkeypatch.setenv("MCP_STRAVA_DB_PATH", "/runtime/data/strava.duckdb")
    monkeypatch.setenv("MCP_STRAVA_REFRESH_WORKER_ENABLED", "1")

    specs = service._child_specs()

    commands = [" ".join(spec.command) for spec in specs]
    assert not any("mcp_strava.refresh.worker" in command for command in commands)


def test_service_state_records_single_owner_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_strava.deploy import service

    state_path = tmp_path / "supervisor.json"
    monkeypatch.setenv("MCP_STRAVA_SUPERVISOR_STATE_PATH", str(state_path))
    monkeypatch.setenv("MCP_STRAVA_DB_PATH", "/runtime/data/strava.duckdb")
    process = SimpleNamespace(pid=os.getpid())

    service._write_state([service.ChildProcess(name="mcp-http", process=process)])

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["owner"]["pid"] == os.getpid()
    assert payload["owner"]["db_mode"] == "duckdb-primary"
    assert payload["owner"]["connection_policy"] == "per-thread-connection"
    assert "refresh" not in payload.get("children", {})


def test_healthcheck_does_not_open_live_duckdb_via_preflight() -> None:
    tree = ast.parse(_source("src/mcp_strava/deploy/healthcheck.py"))
    forbidden_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "mcp_strava.deploy.preflight":
            forbidden_imports.extend(alias.name for alias in node.names if alias.name == "validate_runtime_db")

    assert forbidden_imports == []
    assert _calls_named(tree, "validate_runtime_db") == []


def test_healthcheck_accepts_owner_state_without_refresh_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from mcp_strava.deploy import healthcheck

    state_path = tmp_path / "supervisor.json"
    state_path.write_text(
        json.dumps({"owner": {"pid": os.getpid(), "db_mode": "duckdb-primary"}, "children": {}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MCP_STRAVA_SUPERVISOR_STATE_PATH", str(state_path))
    monkeypatch.setenv("MCP_STRAVA_DB_PATH", "/runtime/data/strava.duckdb")
    monkeypatch.setattr(healthcheck, "_validate_http", lambda: None)
    if hasattr(healthcheck, "validate_runtime_db"):
        monkeypatch.setattr(
            healthcheck,
            "validate_runtime_db",
            lambda *_args, **_kwargs: pytest.fail("healthcheck must not open live DuckDB directly"),
        )

    assert healthcheck.main() == 0


def test_standalone_refresh_worker_refuses_live_duckdb_runtime(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcp_strava.refresh import worker

    monkeypatch.setenv("MCP_STRAVA_RUNTIME_PROFILE", "container")
    monkeypatch.setenv("MCP_STRAVA_DB_PATH", "/runtime/data/strava.duckdb")
    monkeypatch.setattr(worker, "run_pending_once", lambda **_kwargs: pytest.fail("standalone worker must refuse first"))

    rc = worker.main(["--once"])

    captured = capsys.readouterr()
    assert rc != 0
    assert "owner process" in captured.err
