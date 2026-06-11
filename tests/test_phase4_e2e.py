from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from mcp_strava.adapters.duckdb.refresh_state_store import RefreshStateStore
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from tests._fixtures_duckdb import create_empty_fixture_db


def _create_fixture_db(path: Path) -> None:
    create_empty_fixture_db(path)
    summary = {
        "id": 901,
        "name": "Fixture Run",
        "sport_type": "Run",
        "start_date_local": "2026-05-21T07:00:00",
        "distance": 5000.0,
        "moving_time": 1800,
        "elapsed_time": 1830,
        "total_elevation_gain": 30.0,
        "has_heartrate": True,
        "average_heartrate": 145.0,
        "max_heartrate": 165.0,
    }
    with DuckDBRepository.from_path(path) as repo:
        repo.conn.execute(
            """
            INSERT INTO activities (
                id, activity_day, name, sport_type, distance, moving_time,
                elapsed_time, total_elevation_gain, summary_json, detail_json, synced_at
            ) VALUES (?, CAST(? AS DATE), ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                901,
                "2026-05-21",
                "Fixture Run",
                "Run",
                5000.0,
                1800,
                1830,
                30.0,
                json.dumps(summary),
                None,
                "2026-05-21T08:00:00",
            ],
        )
        # Ensure refresh_state row id=1 exists, then mark a successful refresh.
        RefreshStateStore.from_connection(repo.conn).get_refresh_state()
        repo.conn.execute(
            """
            UPDATE refresh_state
            SET last_success_at = ?, last_attempt_at = ?, last_status = 'ok'
            WHERE id = 1
            """,
            ["2026-05-21T06:00:00", "2026-05-21T06:00:00"],
        )
        repo.conn.commit()


def test_phase4_cli_freshness_json_uses_fixture_duckdb_without_strava(tmp_path: Path) -> None:
    db_path = tmp_path / "phase4.duckdb"
    _create_fixture_db(db_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    env["MCP_STRAVA_DB_PATH"] = str(db_path)
    env["MCP_STRAVA_TOKEN_PATH"] = str(tmp_path / ".env")

    result = subprocess.run(
        [sys.executable, "-m", "mcp_strava", "freshness", "--json"],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload) == {"data", "freshness", "completeness", "warnings", "rationale"}
    assert payload["freshness"]["last_successful_refresh_at"] == "2026-05-21T06:00:00Z"
    assert payload["freshness"]["last_activity_at"] == "2026-05-21"
    assert payload["completeness"]["status"] == "complete"
