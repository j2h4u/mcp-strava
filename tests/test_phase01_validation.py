import os
import sqlite3
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from mcp_strava.db import DbConn
from mcp_strava.settings import reset_settings_cache


def test_found01_pyproject_package_contract() -> None:
    with open('pyproject.toml', 'rb') as fh:
        data = tomllib.load(fh)

    assert data['project']['name'] == 'mcp-strava'
    assert data['project']['requires-python'] == '>=3.13'
    assert data['tool']['setuptools']['package-dir'] == {'': 'src'}
    assert data['tool']['setuptools']['packages']['find']['where'] == ['src']
    assert 'scripts' not in data['project']


def test_found01_module_entrypoint_usage_contract() -> None:
    env = os.environ.copy()
    env['PYTHONPATH'] = 'src'

    result = subprocess.run(
        [sys.executable, '-m', 'mcp_strava'],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 1
    assert 'Usage: python -m mcp_strava <command> [args]' in combined


def test_found02_dbconn_fails_closed_for_missing_expected_db(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / 'missing-expected.db'
    monkeypatch.setenv('MCP_STRAVA_DB_PATH', str(db_path))
    reset_settings_cache()

    try:
        with pytest.raises(Exception):
            with DbConn():
                pass
    finally:
        reset_settings_cache()

    assert not db_path.exists()


def test_found02_explicit_fixture_creation_path_is_available(tmp_path: Path) -> None:
    db_path = tmp_path / 'fixture-created.db'
    from mcp_strava.adapters.sqlite.connection import create_empty_mirror

    create_empty_mirror(db_path)
    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone()
    assert row is None


def test_found03_just_test_routes_to_pytest() -> None:
    justfile = Path('Justfile').read_text(encoding='utf-8')
    assert 'python3 -m pytest' in justfile
    assert 'scripts/run_tests.py' not in justfile
