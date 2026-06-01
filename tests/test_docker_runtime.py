from __future__ import annotations

import sys
import tomllib
from pathlib import Path

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


def test_entrypoint_exits_without_exec_when_preflight_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


def _fake_settings(hr_rest: int | None):
    from types import SimpleNamespace

    return SimpleNamespace(athlete=SimpleNamespace(hr_rest=hr_rest))


def test_owner_startup_fails_fast_when_worker_enabled_and_hr_rest_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Eager guard: an enabled refresh worker without HR_REST aborts at startup,
    not lazily on the first materialization pass."""
    from mcp_strava.deploy import refresh_scheduler

    monkeypatch.setenv("MCP_STRAVA_REFRESH_WORKER_ENABLED", "1")
    monkeypatch.setattr("mcp_strava.settings.get_settings", lambda: _fake_settings(None))
    with pytest.raises(RuntimeError, match="MCP_STRAVA_HR_REST"):
        refresh_scheduler.require_hr_config_for_worker()


def test_owner_startup_allows_unset_hr_rest_when_worker_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A read-only runtime (worker disabled) does not need HR_REST."""
    from mcp_strava.deploy import refresh_scheduler

    monkeypatch.setenv("MCP_STRAVA_REFRESH_WORKER_ENABLED", "0")
    monkeypatch.setattr("mcp_strava.settings.get_settings", lambda: _fake_settings(None))
    refresh_scheduler.require_hr_config_for_worker()  # must not raise


def test_owner_startup_passes_when_hr_rest_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_strava.deploy import refresh_scheduler

    monkeypatch.setenv("MCP_STRAVA_REFRESH_WORKER_ENABLED", "1")
    monkeypatch.setattr("mcp_strava.settings.get_settings", lambda: _fake_settings(53))
    refresh_scheduler.require_hr_config_for_worker()  # must not raise


def test_lease_active_uses_utc_and_tolerates_aware_timestamps() -> None:
    """_lease_active compares in UTC and never mixes aware/naive datetimes.

    Panel SRE finding: lease timestamps are written naive-UTC, but the check
    compared against datetime.now() (naive-local) — a host-offset skew — and an
    aware ISO string would raise TypeError (not caught by `except ValueError`),
    crashing preflight. The fix normalises to naive-UTC on both sides.
    """
    from datetime import UTC, datetime, timedelta

    from mcp_strava.deploy.preflight import _lease_active

    now_utc = datetime.now(UTC).replace(tzinfo=None)
    future = (now_utc + timedelta(minutes=5)).isoformat()
    past = (now_utc - timedelta(minutes=5)).isoformat()
    aware_future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()  # carries +00:00

    assert _lease_active({"lease_owner": "w", "lease_expires_at": future}) is True
    assert _lease_active({"lease_owner": "w", "lease_expires_at": past}) is False
    # Aware (offset-carrying) timestamp must not raise TypeError and stays active.
    assert _lease_active({"lease_owner": "w", "lease_expires_at": aware_future}) is True
    # Owner/expiry edge cases.
    assert _lease_active({"lease_owner": None, "lease_expires_at": future}) is False
    assert _lease_active({"lease_owner": "w", "lease_expires_at": None}) is True
    assert _lease_active({"lease_owner": "w", "lease_expires_at": "not-a-date"}) is True
