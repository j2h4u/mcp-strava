from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tomllib

import duckdb
import pytest

from tests.test_sqlite_safety import _create_fixture_db


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


def test_phase7_deployment_runbook_documents_read_model_performance_gate() -> None:
    text = _read_text(_repo_root() / "docs" / "deployment.md")
    lowered = text.lower()

    assert "pinned pre-phase-7 backup" in lowered
    assert "user_version=7" in text
    assert "admin db-migrate --apply" in text
    assert "admin mirror-refresh --force" in text
    assert "just test" in text
    assert "just mcp-read-model-perf" in text
    assert "500 ms p95" in lowered
    for tool_name in (
        "get_fitness_state",
        "list_workouts",
        "get_workout_detail",
        "compare_periods",
        "project_fitness_state",
    ):
        assert tool_name in text


def test_phase8_deployment_runbook_documents_duckdb_cutover_and_rollback() -> None:
    text = _read_text(_repo_root() / "docs" / "deployment.md")
    lowered = text.lower()

    assert "phase 8 duckdb cutover validation" in lowered
    assert "pinned pre-phase-8 sqlite backup" in lowered
    assert "first accepted post-cutover refresh pass" in lowered
    assert "no active refresh lease" in lowered
    assert "mcp-strava:pre-phase-8" in text
    assert "/runtime/data/strava.duckdb" in text
    assert "/opt/docker/mcp-strava/data/strava.duckdb" in text
    assert "python -m mcp_strava admin duckdb-cutover" in text
    assert "--confirm-live-cutover" in text
    assert "just test" in text
    assert "just mcp-smoke-full" in text
    assert "just mcp-read-model-perf 20 2 100" in text
    assert "owner-process/HTTP validation" in text
    assert "get_training_aggregates" in text
    assert "docker compose -f deploy/docker-compose.yml exec -T mcp-strava python -c" in text
    assert "assert sys.version_info[:2] == (3, 14)" in text
    assert "Full Strava resync is not a rollback or validation mechanism" in text
    assert "Full Strava resync is not a rollback path" in text
    assert "mcp-read-model-perf samples=" not in text
    assert "mcp-read-model-perf warmup=" not in text
    assert "mcp-read-model-perf p95" not in text


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


def test_preflight_main_valid_db_passes(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations
    from mcp_strava.deploy.preflight import main as preflight_main

    db_path = tmp_path / "ok.db"
    _create_fixture_db(db_path)
    run_migrations(db_path)
    rc = preflight_main(["--db", str(db_path), "--quiet"])
    assert rc == 0


def test_validate_runtime_db_reports_v6_read_model_readiness_without_requiring_current_facts(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations
    from mcp_strava.deploy.preflight import validate_runtime_db

    db_path = tmp_path / "read-model-ready.db"
    _create_fixture_db(db_path)
    run_migrations(db_path)

    report = validate_runtime_db(db_path)

    assert report["user_version"] == 7
    assert report["read_model"]["schema_ready"] is True
    assert report["read_model"]["missing_tables"] == []
    assert report["read_model"]["facts_current"] is False
    assert report["read_model"]["dirty_count"] == 42


def test_validate_runtime_db_fails_when_v6_read_model_tables_are_missing(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations
    from mcp_strava.deploy.preflight import validate_runtime_db

    db_path = tmp_path / "read-model-broken.db"
    _create_fixture_db(db_path)
    run_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE activity_metric_facts")
        conn.commit()

    with pytest.raises(RuntimeError, match="activity_metric_facts"):
        validate_runtime_db(db_path)


def test_preflight_quick_mode_passes_valid_db(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations
    from mcp_strava.deploy.preflight import main as preflight_main

    db_path = tmp_path / "quick.db"
    _create_fixture_db(db_path)
    run_migrations(db_path)
    rc = preflight_main(["--db", str(db_path), "--quick", "--quiet"])
    assert rc == 0


def test_phase6_preflight_accepts_v3_intermediate_and_v4_final(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import create_lossless_stream_inventory_v3, run_migrations
    from mcp_strava.deploy.preflight import main as preflight_main
    from tests.test_full_fidelity_mirror import _create_v2_fixture

    v3_path = tmp_path / "v3.db"
    _create_v2_fixture(v3_path)
    with sqlite3.connect(v3_path) as conn:
        create_lossless_stream_inventory_v3(conn)
        conn.execute("PRAGMA user_version=3")
        conn.commit()
    assert preflight_main(["--db", str(v3_path), "--quiet"]) == 0

    v4_path = tmp_path / "v4.db"
    _create_v2_fixture(v4_path)
    run_migrations(v4_path)
    assert preflight_main(["--db", str(v4_path), "--quiet"]) == 0


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

    db_path = tmp_path / "ok.db"
    _create_fixture_db(db_path)

    calls: list[tuple[str, object]] = []

    def fake_validate(path: Path, *, quick: bool = False, allow_active_refresh_lease: bool = False) -> None:
        calls.append(("validate", path))
        assert path == db_path
        assert quick is False
        assert allow_active_refresh_lease is False

    def fake_needs_migration(path: Path) -> bool:
        calls.append(("needs_migration", path))
        return False

    def fake_execvp(program: str, argv: list[str]) -> None:
        calls.append(("execvp", (program, argv)))
        raise SystemExit(0)

    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(db_path))
    monkeypatch.setattr(entrypoint, "_needs_migration", fake_needs_migration)
    monkeypatch.setattr(entrypoint, "validate_runtime_db", fake_validate)
    monkeypatch.setattr(entrypoint.os, "execvp", fake_execvp)

    with pytest.raises(SystemExit):
        entrypoint.main([])

    assert calls[0][0] == "needs_migration"
    assert calls[1][0] == "validate"
    assert calls[2][0] == "execvp"


def test_entrypoint_runs_migration_before_preflight_when_needed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from mcp_strava.deploy import entrypoint

    db_path = tmp_path / "old.db"
    _create_fixture_db(db_path)
    calls: list[str] = []

    def fake_needs_migration(path: Path) -> bool:
        assert path == db_path
        calls.append("needs_migration")
        return True

    def fake_run_migrations(path: Path) -> None:
        assert path == db_path
        calls.append("run_migrations")

    def fake_validate(path: Path, *, quick: bool = False, allow_active_refresh_lease: bool = False) -> None:
        assert path == db_path
        assert quick is False
        assert allow_active_refresh_lease is False
        calls.append("validate")

    def fake_execvp(program: str, argv: list[str]) -> None:
        del program, argv
        calls.append("execvp")
        raise SystemExit(0)

    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(db_path))
    monkeypatch.setattr(entrypoint, "_needs_migration", fake_needs_migration)
    monkeypatch.setattr(entrypoint, "run_migrations", fake_run_migrations)
    monkeypatch.setattr(entrypoint, "validate_runtime_db", fake_validate)
    monkeypatch.setattr(entrypoint.os, "execvp", fake_execvp)

    with pytest.raises(SystemExit):
        entrypoint.main([])

    assert calls == ["needs_migration", "run_migrations", "validate", "execvp"]


def test_entrypoint_auto_cutover_prepares_missing_duckdb_from_sibling_sqlite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from mcp_strava.deploy import entrypoint

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sqlite_path = data_dir / "strava.db"
    sqlite_path.write_bytes(b"sqlite placeholder")
    duckdb_path = data_dir / "strava.duckdb"
    calls: list[tuple[str, object]] = []

    class Report:
        backup_path = data_dir / "backups" / "strava.db"

    def fake_needs_migration(path: Path) -> bool:
        calls.append(("needs_migration", path))
        return False

    def fake_cutover(**kwargs: object) -> Report:
        calls.append(("cutover", kwargs))
        assert kwargs["source_sqlite_path"] == sqlite_path
        assert kwargs["target_duckdb_path"] == duckdb_path
        assert kwargs["backup_dir"] == data_dir / "backups"
        assert kwargs["owner"] == "entrypoint"
        duckdb_path.write_bytes(b"duckdb placeholder")
        return Report()

    def fake_validate(path: Path, *, quick: bool = False, allow_active_refresh_lease: bool = False) -> None:
        calls.append(("validate", path))
        assert path == duckdb_path
        assert quick is False
        assert allow_active_refresh_lease is True

    def fake_execvp(program: str, argv: list[str]) -> None:
        del program, argv
        calls.append(("execvp", duckdb_path.exists()))
        raise SystemExit(0)

    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(duckdb_path))
    monkeypatch.setattr(entrypoint, "_needs_migration", fake_needs_migration)
    monkeypatch.setattr(entrypoint, "run_duckdb_cutover", fake_cutover)
    monkeypatch.setattr(entrypoint, "validate_runtime_db", fake_validate)
    monkeypatch.setattr(entrypoint.os, "execvp", fake_execvp)

    with pytest.raises(SystemExit):
        entrypoint.main([])

    assert calls == [
        ("needs_migration", sqlite_path),
        (
            "cutover",
            {
                "source_sqlite_path": sqlite_path,
                "target_duckdb_path": duckdb_path,
                "backup_dir": data_dir / "backups",
                "now": None,
                "owner": "entrypoint",
            },
        ),
        ("needs_migration", duckdb_path),
        ("validate", duckdb_path),
        ("execvp", True),
    ]


def test_entrypoint_missing_duckdb_without_sibling_sqlite_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from mcp_strava.deploy import entrypoint

    duckdb_path = tmp_path / "data" / "strava.duckdb"
    cutover_called = False

    def fake_cutover(**_kwargs: object) -> None:
        nonlocal cutover_called
        cutover_called = True

    def fake_validate(path: Path, *, quick: bool = False, allow_active_refresh_lease: bool = False) -> None:
        del quick, allow_active_refresh_lease
        raise RuntimeError(f"missing {path}")

    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(duckdb_path))
    monkeypatch.setattr(entrypoint, "run_duckdb_cutover", fake_cutover)
    monkeypatch.setattr(entrypoint, "validate_runtime_db", fake_validate)
    monkeypatch.setattr(entrypoint.os, "execvp", lambda *_args: pytest.fail("must not exec"))

    rc = entrypoint.main([])

    assert rc != 0
    assert cutover_called is False
    assert not duckdb_path.exists()


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

    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(tmp_path / "missing.db"))
    monkeypatch.setattr(entrypoint, "_needs_migration", lambda _path: False)
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
    import duckdb

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
    import duckdb

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
    monkeypatch.setattr(entrypoint, "_needs_migration", lambda _path: False)
    monkeypatch.setattr(entrypoint.os, "execvp", fake_execvp)

    with pytest.raises(SystemExit):
        entrypoint.main([])

    assert exec_called is True


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
