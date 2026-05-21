from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from mcp_strava.adapters.sqlite.migrations import run_migrations
from mcp_strava.types import ServiceEnvelope, dc_to_dict


ALLOWED_WARNING_CODES = {
    "mirror_stale",
    "last_activity_old",
    "missing_hr",
    "missing_streams",
    "missing_details",
    "metric_unavailable",
    "empty_weekly_history",
    "insufficient_history",
}


@pytest.fixture(autouse=True)
def reset_metric_cache():
    import mcp_strava.metrics as metrics

    metrics._hr_max_cache = None
    yield
    metrics._hr_max_cache = None


def _create_base_db(path: Path) -> None:
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
    conn.commit()
    conn.close()
    run_migrations(path)


def _insert_activity_with_streams(path: Path) -> sqlite3.Connection:
    _create_base_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    summary = {
        "id": 701,
        "name": "Fixture Run",
        "sport_type": "Run",
        "start_date_local": "2026-05-20T07:15:00",
        "distance": 5000.0,
        "moving_time": 1800,
        "elapsed_time": 1830,
        "total_elevation_gain": 30.0,
        "has_heartrate": True,
        "average_heartrate": 145.0,
        "max_heartrate": 165.0,
    }
    conn.execute(
        """
        INSERT INTO activities (
            id, date, name, sport_type, distance, moving_time, elapsed_time,
            total_elevation_gain, summary_json, detail_json, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            701,
            "2026-05-20T07:15:00",
            "Fixture Run",
            "Run",
            5000.0,
            1800,
            1830,
            30.0,
            json.dumps(summary),
            None,
            "2026-05-20T08:00:00",
        ),
    )
    for second in range(130):
        conn.execute(
            """
            INSERT INTO streams (
                activity_id, time_offset, heartrate, velocity, altitude,
                cadence, lat, lng, grade, gap_speed, gap_distance, is_moving, latlng
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                701,
                second,
                145,
                3.0,
                100.0 + second * 0.01,
                85,
                None,
                None,
                0.0,
                3.0,
                float(second),
                1,
                "[43.2,76.9]",
            ),
        )
    conn.execute(
        """
        UPDATE refresh_state
        SET last_success_at = ?, last_attempt_at = ?, last_status = 'ok'
        WHERE id = 1
        """,
        ("2026-05-21T06:00:00", "2026-05-21T06:00:00"),
    )
    conn.commit()
    return conn


def _warning_codes(envelope: ServiceEnvelope) -> set[str]:
    return {warning.code for warning in envelope.warnings}


def test_daily_report_service_returns_envelope_with_existing_report_data(tmp_path: Path) -> None:
    from mcp_strava.application.reports import get_daily_report_service

    conn = _insert_activity_with_streams(tmp_path / "daily.db")
    try:
        envelope = get_daily_report_service(
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    assert isinstance(envelope, ServiceEnvelope)
    assert envelope.data.today == "2026-05-21"
    assert envelope.data.activities_14d
    assert envelope.data.activities_14d[0].id == 701
    assert envelope.freshness.last_successful_refresh_at == "2026-05-21T06:00:00"
    assert envelope.completeness.status in {"complete", "partial"}
    assert _warning_codes(envelope) <= ALLOWED_WARNING_CODES


def test_weekly_summary_service_returns_envelope_and_json_safe_payload(tmp_path: Path) -> None:
    from mcp_strava.application.reports import get_weekly_summary_service

    conn = _insert_activity_with_streams(tmp_path / "weekly.db")
    try:
        envelope = get_weekly_summary_service(
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    payload = dc_to_dict(envelope)

    assert isinstance(envelope, ServiceEnvelope)
    assert payload["data"]["period"]["today"] == "2026-05-21"
    assert "current_state" in payload["data"]
    assert "trends" in payload["data"]
    assert payload["freshness"]["last_successful_refresh_at"] == "2026-05-21T06:00:00"
    assert set(payload) == {"data", "freshness", "completeness", "warnings", "rationale"}
    assert _warning_codes(envelope) <= ALLOWED_WARNING_CODES


def test_weekly_summary_service_marks_empty_history_insufficient(tmp_path: Path) -> None:
    from mcp_strava.application.reports import get_weekly_summary_service

    db_path = tmp_path / "empty-weekly.db"
    _create_base_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        envelope = get_weekly_summary_service(
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    assert envelope.data is None
    assert envelope.completeness.status == "insufficient"
    assert "insufficient_history" in envelope.completeness.missing
    assert "insufficient_history" in _warning_codes(envelope)
