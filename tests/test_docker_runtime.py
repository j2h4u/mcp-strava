from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_sqlite_safety import _create_fixture_db


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dockerfile_source_contract() -> None:
    dockerfile = _repo_root() / "deploy" / "Dockerfile"
    if not dockerfile.exists():
        pytest.skip("Dockerfile added in Task 3")
    text = _read_text(dockerfile)
    assert "FROM python:3.13-slim" in text
    assert "USER 10001:10001" in text
    assert "MCP_STRAVA_RUNTIME_PROFILE=container" in text
    assert "MCP_STRAVA_HTTP_HOST=0.0.0.0" in text
    assert "MCP_STRAVA_ALLOW_CONTAINER_BIND=1" in text
    assert "EXPOSE 8080" in text
    assert 'ENTRYPOINT ["python", "-m", "mcp_strava.deploy.entrypoint"]' in text
    assert "python -m mcp_strava.deploy.preflight --db /data/strava.db --quick --quiet" in text


def test_compose_source_contract() -> None:
    compose = _repo_root() / "deploy" / "docker-compose.yml"
    if not compose.exists():
        pytest.skip("compose added in Task 3")
    text = _read_text(compose)
    assert "mcp-strava:" in text
    assert "container_name: mcp-strava" in text
    assert "ports:" not in text
    assert 'expose: ["8080"]' in text or "expose:\n      - \"8080\"" in text
    assert "/opt/docker/mcp-strava/data:/data" in text
    assert "MCP_STRAVA_DB_PATH=/data/strava.db" in text
    assert "/opt/docker/mcp-strava/.env" in text
    assert "mcp-backends" in text


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


def test_preflight_main_valid_db_passes(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations
    from mcp_strava.deploy.preflight import main as preflight_main

    db_path = tmp_path / "ok.db"
    _create_fixture_db(db_path)
    run_migrations(db_path)
    rc = preflight_main(["--db", str(db_path), "--quiet"])
    assert rc == 0


def test_preflight_quick_mode_passes_valid_db(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations
    from mcp_strava.deploy.preflight import main as preflight_main

    db_path = tmp_path / "quick.db"
    _create_fixture_db(db_path)
    run_migrations(db_path)
    rc = preflight_main(["--db", str(db_path), "--quick", "--quiet"])
    assert rc == 0


def test_entrypoint_runs_preflight_before_exec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from mcp_strava.deploy import entrypoint

    db_path = tmp_path / "ok.db"
    _create_fixture_db(db_path)

    calls: list[tuple[str, object]] = []

    def fake_validate(path: Path, *, quick: bool = False) -> None:
        calls.append(("validate", path))
        assert path == db_path
        assert quick is False

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

    def fake_validate(_path: Path, *, quick: bool = False) -> None:
        del quick
        raise RuntimeError("boom")

    def fake_execvp(program: str, argv: list[str]) -> None:
        del program, argv
        nonlocal exec_called
        exec_called = True

    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(tmp_path / "missing.db"))
    monkeypatch.setattr(entrypoint, "validate_runtime_db", fake_validate)
    monkeypatch.setattr(entrypoint.os, "execvp", fake_execvp)

    rc = entrypoint.main([])
    assert rc != 0
    assert exec_called is False


def test_prepare_runtime_backup_copy_and_live_env(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations
    from mcp_strava.deploy.prepare_runtime import prepare_runtime

    source_db = tmp_path / "source.db"
    _create_fixture_db(source_db)
    run_migrations(source_db)

    target_root = tmp_path / "runtime"
    target_data = target_root / "data"
    target_data.mkdir(parents=True, exist_ok=True)
    target_db = target_data / "strava.db"
    _create_fixture_db(target_db)
    run_migrations(target_db)

    result = prepare_runtime(source_db=source_db, target_root=target_root)
    assert Path(result["target_db"]) == target_db
    assert target_db.exists()

    backups = sorted((target_data / "backups").glob("strava-*.db"))
    assert backups

    live_env = target_root / "live.env"
    assert live_env.exists()
    text = live_env.read_text(encoding="utf-8")
    assert f"MCP_STRAVA_DB_PATH={target_root / 'data' / 'strava.db'}" in text
    assert f"MCP_STRAVA_TOKEN_PATH={target_root / '.env'}" in text
    assert oct(live_env.stat().st_mode & 0o777) in {"0o600", "0o640", "0o644"}


def test_prepare_runtime_refuses_env_overwrite_without_replace_flag(tmp_path: Path) -> None:
    from mcp_strava.deploy.prepare_runtime import prepare_runtime

    source_db = tmp_path / "source.db"
    _create_fixture_db(source_db)
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
    from mcp_strava.adapters.sqlite.migrations import run_migrations
    from mcp_strava.deploy.prepare_runtime import main as prepare_main

    source_db = tmp_path / "source.db"
    _create_fixture_db(source_db)
    run_migrations(source_db)
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

    source_db = tmp_path / "shared.db"
    _create_fixture_db(source_db)
    with pytest.raises(RuntimeError):
        prepare_runtime(source_db=source_db, target_root=source_db.parent)
