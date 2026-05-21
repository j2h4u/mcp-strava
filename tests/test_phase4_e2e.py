from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from mcp_strava.adapters.sqlite.migrations import run_migrations


def _create_fixture_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            date TEXT, name TEXT, sport_type TEXT,
            distance REAL, moving_time INTEGER, elapsed_time INTEGER,
            total_elevation_gain REAL,
            summary_json TEXT, detail_json TEXT, synced_at TEXT
        );
        CREATE TABLE streams (
            activity_id INTEGER, time_offset INTEGER,
            heartrate INTEGER, velocity REAL, altitude REAL,
            cadence INTEGER, lat REAL, lng REAL, grade REAL,
            gap_speed REAL, gap_distance REAL, is_moving INTEGER, latlng TEXT,
            PRIMARY KEY (activity_id, time_offset)
        );
        CREATE INDEX idx_streams_act ON streams(activity_id);
        CREATE TABLE athlete_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT, zones_json TEXT
        );
        CREATE TABLE sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            activities_seen INTEGER,
            activities_new INTEGER,
            streams_fetched INTEGER,
            details_fetched INTEGER,
            api_calls INTEGER,
            error TEXT,
            kudos_fetched INTEGER
        );
        CREATE TABLE kudos (
            activity_id INTEGER NOT NULL,
            firstname TEXT NOT NULL DEFAULT '',
            lastname TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (activity_id, firstname, lastname)
        );
        PRAGMA user_version=1;
        """
    )
    conn.execute(
        """
        INSERT INTO activities (
            id, date, name, sport_type, distance, moving_time, elapsed_time,
            total_elevation_gain, summary_json, detail_json, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            901,
            "2026-05-21T07:00:00",
            "Fixture Run",
            "Run",
            5000.0,
            1800,
            1830,
            30.0,
            json.dumps(
                {
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
            ),
            None,
            "2026-05-21T08:00:00",
        ),
    )
    conn.commit()
    conn.close()
    run_migrations(path)
    migrated = sqlite3.connect(path)
    migrated.execute(
        """
        UPDATE refresh_state
        SET last_success_at = ?, last_attempt_at = ?, last_status = 'ok'
        WHERE id = 1
        """,
        ("2026-05-21T06:00:00", "2026-05-21T06:00:00"),
    )
    migrated.commit()
    migrated.close()


def test_phase4_cli_freshness_json_uses_fixture_sqlite_without_strava(tmp_path: Path) -> None:
    db_path = tmp_path / "phase4.db"
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
    assert payload["freshness"]["last_successful_refresh_at"] == "2026-05-21T06:00:00"
    assert payload["freshness"]["last_activity_at"] == "2026-05-21T07:00:00"
    assert payload["completeness"]["status"] == "complete"
