from __future__ import annotations

from pathlib import Path
import sys
import tomllib

import duckdb
import pytest

from tests._fixtures_duckdb import create_fixture_db


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_project_runtime_requires_python_314_and_duckdb_dependency() -> None:
    assert sys.version_info[:2] == (3, 14)
    assert duckdb.__version__.startswith("1.5.")

    pyproject = tomllib.loads(_read_text(_repo_root() / "pyproject.toml"))
    project = pyproject["project"]
    assert project["requires-python"] == ">=3.14"
    assert "duckdb>=1.5.3,<1.6" in project["dependencies"]


def test_dockerfile_source_contract() -> None:
    dockerfile = _repo_root() / "deploy" / "Dockerfile"
    if not dockerfile.exists():
        pytest.skip("Dockerfile added in Task 3")
    text = _read_text(dockerfile)
    assert "FROM python:3.14-slim" in text
    assert "groupadd --gid 1000 mcp" in text
    assert "useradd --uid 1000 --gid 1000" in text
    assert "USER 1000:1000" in text
    assert "MCP_STRAVA_RUNTIME_PROFILE=container" in text
    assert "MCP_STRAVA_HTTP_HOST=0.0.0.0" in text
    assert "MCP_STRAVA_ALLOW_CONTAINER_BIND=1" in text
    assert "EXPOSE 8080" in text
    assert 'ENTRYPOINT ["python", "-m", "mcp_strava.deploy.entrypoint"]' in text
    assert "mcp_strava.deploy.healthcheck" in text
    assert "/runtime/data/strava.duckdb" in text
    assert "/runtime/data/strava.db" not in text
    assert "COPY mcp-content /app/mcp-content" in text


def test_compose_source_contract() -> None:
    compose = _repo_root() / "deploy" / "docker-compose.yml"
    if not compose.exists():
        pytest.skip("compose added in Task 3")
    text = _read_text(compose)
    assert "mcp-strava:" in text
    assert "container_name: mcp-strava" in text
    assert "ports:" not in text
    assert 'expose: ["8080"]' in text or "expose:\n      - \"8080\"" in text
    assert "/opt/docker/mcp-strava:/runtime" in text
    assert "MCP_STRAVA_DB_PATH" in text and "/runtime/data/strava.duckdb" in text
    assert "/runtime/data/strava.db" not in text
    assert "MCP_STRAVA_TOKEN_PATH" in text and "/runtime/.env" in text
    assert "MCP_STRAVA_READ_MODEL_BATCH_SIZE" in text
    assert "mcp-backends" in text


def test_docker_smoke_and_perf_use_owner_process_http_path() -> None:
    root = _repo_root()
    justfile = _read_text(root / "Justfile")
    client_sources = "\n".join(
        _read_text(root / path)
        for path in (
            Path("src/mcp_strava/devtools/mcp_client/client.py"),
            Path("src/mcp_strava/devtools/mcp_client/cli.py"),
            Path("src/mcp_strava/deploy/smoke.py"),
        )
    )
    healthcheck = _read_text(root / "src/mcp_strava/deploy/healthcheck.py")

    assert "mcp-smoke-full" in justfile
    assert "mcp-read-model-perf" in justfile
    assert "--url http://127.0.0.1:8080/mcp" in justfile
    assert "p95_ms=\"100\"" in justfile
    for forbidden in ("duckdb.connect", "open_expected_duckdb", "validate_runtime_db"):
        assert forbidden not in client_sources
        assert forbidden not in healthcheck
    assert "HTTPConnection(\"127.0.0.1\"" in healthcheck
    assert "db_mode\") != \"duckdb-primary\"" in healthcheck


def test_dockerignore_contract() -> None:
    dockerignore = _repo_root() / "deploy" / ".dockerignore"
    if not dockerignore.exists():
        pytest.skip(".dockerignore added in Task 3")
    text = _read_text(dockerignore)
    assert ".env" in text
    assert "data/*.db" in text
    assert ".planning/config.json" in text


def test_deployment_runbook_documents_read_model_performance_gate() -> None:
    text = _read_text(_repo_root() / "docs" / "deployment.md")
    lowered = text.lower()

    assert "just test" in text
    assert "just mcp-read-model-perf" in text
    assert "500 ms" in lowered
    assert "get_fitness_state" in text
    assert "get_training_aggregates" in text


def test_preflight_main_missing_db_fails(tmp_path: Path) -> None:
    from mcp_strava.deploy.preflight import main as preflight_main

    rc = preflight_main(["--db", str(tmp_path / "missing.db"), "--quiet"])
    assert rc != 0
    assert not (tmp_path / "missing.db").exists()


def test_preflight_main_empty_file_fails(tmp_path: Path) -> None:
    from mcp_strava.deploy.preflight import main as preflight_main

    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    rc = preflight_main(["--db", str(empty), "--quiet"])
    assert rc != 0


def test_duckdb_preflight_missing_or_corrupt_file_fails_closed(tmp_path: Path) -> None:
    from mcp_strava.deploy.preflight import main as preflight_main

    missing = tmp_path / "missing.duckdb"
    assert preflight_main(["--db", str(missing), "--quiet"]) != 0
    assert not missing.exists()

    corrupt = tmp_path / "corrupt.duckdb"
    corrupt.write_text("not a duckdb file", encoding="utf-8")
    assert preflight_main(["--db", str(corrupt), "--quiet"]) != 0


def test_preflight_main_valid_duckdb_passes(tmp_path: Path) -> None:
    from mcp_strava.deploy.preflight import main as preflight_main

    db_path = tmp_path / "ok.duckdb"
    create_fixture_db(db_path)
    rc = preflight_main(["--db", str(db_path), "--quiet"])
    assert rc == 0


def test_preflight_quick_mode_passes_valid_duckdb(tmp_path: Path) -> None:
    from mcp_strava.deploy.preflight import main as preflight_main

    db_path = tmp_path / "quick.duckdb"
    create_fixture_db(db_path)
    rc = preflight_main(["--db", str(db_path), "--quick", "--quiet"])
    assert rc == 0


def test_runtime_path_references_stay_in_deploy_surface() -> None:
    root = _repo_root()
    offenders: list[str] = []
    for py_file in (root / "src" / "mcp_strava").rglob("*.py"):
        rel = py_file.relative_to(root).as_posix()
        if rel.startswith("src/mcp_strava/deploy/"):
            continue
        if "/opt/docker/mcp-strava" in _read_text(py_file):
            offenders.append(rel)
    assert offenders == []


def test_entrypoint_runs_preflight_before_exec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from mcp_strava.deploy import entrypoint

    db_path = tmp_path / "ok.duckdb"
    create_fixture_db(db_path)

    calls: list[tuple[str, object]] = []

    def fake_validate(path: Path, *, quick: bool = False, allow_active_refresh_lease: bool = False) -> None:
        calls.append(("validate", path))
        assert path == db_path
        assert quick is False
        assert allow_active_refresh_lease is True

    def fake_execvp(program: str, argv: list[str]) -> None:
        calls.append(("execvp", (program, argv)))
        raise SystemExit(0)

    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(db_path))
    monkeypatch.setattr(entrypoint, "validate_runtime_db", fake_validate)
    monkeypatch.setattr(entrypoint.os, "execvp", fake_execvp)

    with pytest.raises(SystemExit):
        entrypoint.main([])

    assert calls[0][0] == "validate"
    assert calls[1][0] == "execvp"


def test_entrypoint_exits_without_exec_when_preflight_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from mcp_strava.deploy import entrypoint

    exec_called = False

    def fake_validate(_path: Path, *, quick: bool = False, allow_active_refresh_lease: bool = False) -> None:
        del quick, allow_active_refresh_lease
        raise RuntimeError("boom")

    def fake_execvp(program: str, argv: list[str]) -> None:
        del program, argv
        nonlocal exec_called
        exec_called = True

    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(tmp_path / "missing.duckdb"))
    monkeypatch.setattr(entrypoint, "validate_runtime_db", fake_validate)
    monkeypatch.setattr(entrypoint.os, "execvp", fake_execvp)

    rc = entrypoint.main([])
    assert rc != 0
    assert exec_called is False


def test_duckdb_preflight_blocks_active_refresh_lease_by_default(
    tmp_path: Path,
) -> None:
    from mcp_strava.adapters.duckdb.schema import create_schema
    from mcp_strava.deploy.preflight import validate_runtime_db

    db_path = tmp_path / "active.duckdb"

    conn = duckdb.connect(str(db_path))
    create_schema(conn)
    conn.execute(
        """
        INSERT INTO refresh_state (id, lease_owner, lease_expires_at)
        VALUES (1, 'refresh-worker', '2099-01-01T00:00:00')
        """
    )
    conn.close()

    with pytest.raises(RuntimeError, match="active refresh lease"):
        validate_runtime_db(db_path)


def test_entrypoint_allows_active_duckdb_refresh_lease_before_owner_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from mcp_strava.adapters.duckdb.schema import create_schema
    from mcp_strava.deploy import entrypoint

    db_path = tmp_path / "active.duckdb"

    conn = duckdb.connect(str(db_path))
    create_schema(conn)
    conn.execute(
        """
        INSERT INTO refresh_state (id, lease_owner, lease_expires_at)
        VALUES (1, 'refresh-worker', '2099-01-01T00:00:00')
        """
    )
    conn.close()

    exec_called = False

    def fake_execvp(program: str, argv: list[str]) -> None:
        del program, argv
        nonlocal exec_called
        exec_called = True
        raise SystemExit(0)

    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(db_path))
    monkeypatch.setattr(entrypoint.os, "execvp", fake_execvp)

    with pytest.raises(SystemExit):
        entrypoint.main([])

    assert exec_called is True


def test_prepare_runtime_backup_copy_and_live_env(tmp_path: Path) -> None:
    from mcp_strava.deploy.prepare_runtime import prepare_runtime

    source_db = tmp_path / "source.duckdb"
    create_fixture_db(source_db)

    target_root = tmp_path / "runtime"
    target_data = target_root / "data"
    target_data.mkdir(parents=True, exist_ok=True)
    target_db = target_data / "strava.duckdb"
    create_fixture_db(target_db)

    result = prepare_runtime(source_db=source_db, target_root=target_root)
    assert Path(result["target_db"]) == target_db
    assert target_db.exists()

    backups = sorted((target_data / "backups").glob("strava-*.duckdb"))
    assert backups

    live_env = target_root / "live.env"
    assert live_env.exists()
    text = live_env.read_text(encoding="utf-8")
    assert f"MCP_STRAVA_DB_PATH={target_root / 'data' / 'strava.duckdb'}" in text
    assert f"MCP_STRAVA_TOKEN_PATH={target_root / '.env'}" in text
    assert oct(live_env.stat().st_mode & 0o777) in {"0o600", "0o640", "0o644"}


def test_prepare_runtime_refuses_env_overwrite_without_replace_flag(tmp_path: Path) -> None:
    from mcp_strava.deploy.prepare_runtime import prepare_runtime

    source_db = tmp_path / "source.duckdb"
    create_fixture_db(source_db)
    source_env = tmp_path / "source.env"
    source_env.write_text("STRAVA_CLIENT_ID=abc\n", encoding="utf-8")

    target_root = tmp_path / "runtime"
    target_root.mkdir(parents=True, exist_ok=True)
    (target_root / ".env").write_text("EXISTING=1\n", encoding="utf-8")

    with pytest.raises(RuntimeError):
        prepare_runtime(
            source_db=source_db,
            target_root=target_root,
            copy_env=True,
            source_env=source_env,
        )


def test_prepare_runtime_never_prints_env_contents(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcp_strava.deploy.prepare_runtime import main as prepare_main

    source_db = tmp_path / "source.duckdb"
    create_fixture_db(source_db)
    source_env = tmp_path / "source.env"
    source_env.write_text("STRAVA_CLIENT_SECRET=top-secret\n", encoding="utf-8")

    rc = prepare_main(
        [
            "--source-db",
            str(source_db),
            "--target-root",
            str(tmp_path / "runtime"),
            "--copy-env",
            "--source-env",
            str(source_env),
        ]
    )
    assert rc == 0
    output = capsys.readouterr()
    assert "top-secret" not in output.out
    assert "top-secret" not in output.err


def test_prepare_runtime_refuses_same_source_and_target_path(tmp_path: Path) -> None:
    from mcp_strava.deploy.prepare_runtime import prepare_runtime

    source_db = tmp_path / "data" / "strava.duckdb"
    source_db.parent.mkdir(parents=True, exist_ok=True)
    create_fixture_db(source_db)
    with pytest.raises(RuntimeError):
        prepare_runtime(source_db=source_db, target_root=source_db.parent.parent)


def _fake_settings(hr_rest: int | None):
    from types import SimpleNamespace

    return SimpleNamespace(athlete=SimpleNamespace(hr_rest=hr_rest))


def test_owner_startup_fails_fast_when_worker_enabled_and_hr_rest_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Eager guard: an enabled refresh worker without HR_REST aborts at startup,
    not lazily on the first materialization pass."""
    from mcp_strava.deploy import service

    monkeypatch.setenv("MCP_STRAVA_REFRESH_WORKER_ENABLED", "1")
    monkeypatch.setattr("mcp_strava.settings.get_settings", lambda: _fake_settings(None))
    with pytest.raises(RuntimeError, match="MCP_STRAVA_HR_REST"):
        service._require_hr_config_for_worker()


def test_owner_startup_allows_unset_hr_rest_when_worker_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A read-only runtime (worker disabled) does not need HR_REST."""
    from mcp_strava.deploy import service

    monkeypatch.setenv("MCP_STRAVA_REFRESH_WORKER_ENABLED", "0")
    monkeypatch.setattr("mcp_strava.settings.get_settings", lambda: _fake_settings(None))
    service._require_hr_config_for_worker()  # must not raise


def test_owner_startup_passes_when_hr_rest_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_strava.deploy import service

    monkeypatch.setenv("MCP_STRAVA_REFRESH_WORKER_ENABLED", "1")
    monkeypatch.setattr("mcp_strava.settings.get_settings", lambda: _fake_settings(53))
    service._require_hr_config_for_worker()  # must not raise
