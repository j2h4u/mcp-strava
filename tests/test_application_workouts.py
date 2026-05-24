from __future__ import annotations

import json
import sqlite3
import urllib.request
from datetime import datetime
from pathlib import Path

import pytest

from mcp_strava.adapters.sqlite.migrations import run_migrations
from mcp_strava.types import ServiceEnvelope


@pytest.fixture(autouse=True)
def forbid_live_network_and_reset_cache(monkeypatch):
    def _blocked(*args, **kwargs):
        raise RuntimeError("live network forbidden")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)

    import mcp_strava.metrics as metrics

    metrics._hr_max_cache = None
    yield
    metrics._hr_max_cache = None


def _create_base_db(path: Path) -> sqlite3.Connection:
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
    opened = sqlite3.connect(path)
    opened.row_factory = sqlite3.Row
    return opened


def _insert_activity(conn: sqlite3.Connection, activity_id: int, day: str, *, with_hr: bool = True) -> None:
    avg_hr = 145.0 if with_hr else None
    max_hr = 165.0 if with_hr else None
    summary = {
        "id": activity_id,
        "name": f"Workout {activity_id}",
        "sport_type": "Run",
        "start_date_local": f"{day}T07:00:00",
        "distance": 5000.0,
        "moving_time": 1800,
        "elapsed_time": 1830,
        "total_elevation_gain": 30.0,
        "has_heartrate": with_hr,
        "average_heartrate": avg_hr,
        "max_heartrate": max_hr,
    }
    conn.execute(
        """
        INSERT INTO activities (
            id, date, name, sport_type, distance, moving_time, elapsed_time,
            total_elevation_gain, summary_json, detail_json, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            activity_id,
            f"{day}T07:00:00",
            f"Workout {activity_id}",
            "Run",
            5000.0,
            1800,
            1830,
            30.0,
            json.dumps(summary),
            None,
            f"{day}T08:00:00",
        ),
    )


def _insert_streams(conn: sqlite3.Connection, activity_id: int, *, with_hr: bool = True) -> None:
    for second in range(130):
        conn.execute(
            """
            INSERT INTO streams (
                activity_id, time_offset, heartrate, velocity, altitude,
                cadence, lat, lng, grade, gap_speed, gap_distance, is_moving
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity_id,
                second,
                145 if with_hr else None,
                3.0,
                100.0 + second * 0.01,
                85,
                None,
                None,
                0.0,
                3.0,
                float(second),
                1,
            ),
        )


def _fixture_conn(path: Path) -> sqlite3.Connection:
    conn = _create_base_db(path)
    _insert_activity(conn, 701, "2026-05-20", with_hr=True)
    _insert_streams(conn, 701, with_hr=True)
    _insert_activity(conn, 702, "2026-05-21", with_hr=True)
    _insert_streams(conn, 702, with_hr=True)
    _insert_activity(conn, 703, "2026-05-19", with_hr=False)
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


def test_recent_workouts_service_returns_compact_local_rows(tmp_path: Path) -> None:
    from mcp_strava.application.workouts import get_recent_workouts_service

    conn = _fixture_conn(tmp_path / "recent.db")
    try:
        envelope = get_recent_workouts_service(
            limit=2,
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    assert isinstance(envelope, ServiceEnvelope)
    assert [item["id"] for item in envelope.data] == [702, 701]
    assert envelope.data[0]["distance_km"] == 5.0
    assert envelope.data[0]["moving_time_min"] == 30.0
    assert envelope.data[0]["avg_hr"] == 145.0
    assert envelope.freshness.last_successful_refresh_at == "2026-05-21T06:00:00"


def test_workout_analytics_service_preserves_enriched_activity_fields(tmp_path: Path) -> None:
    from mcp_strava.application.workouts import get_workout_analytics_service

    conn = _fixture_conn(tmp_path / "analytics.db")
    try:
        envelope = get_workout_analytics_service(
            activity_id=701,
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    assert isinstance(envelope, ServiceEnvelope)
    enriched = envelope.data
    for field in (
        "id",
        "date",
        "name",
        "sport_type",
        "distance_km",
        "moving_time_min",
        "elapsed_time_min",
        "elevation_m",
        "trimp",
        "avg_hr",
        "max_hr",
        "zone_minutes",
        "hr_recovery",
        "vertical_speed",
        "cc",
        "cardiac_drift",
        "hrr_pct",
        "start_time",
    ):
        assert hasattr(enriched, field)
    assert enriched.id == 701
    assert enriched.avg_hr == 145.0
    assert envelope.completeness.status in {"complete", "partial"}


def test_workout_analytics_latest_uses_newest_activity(tmp_path: Path) -> None:
    from mcp_strava.application.workouts import get_workout_analytics_service

    conn = _fixture_conn(tmp_path / "latest.db")
    try:
        envelope = get_workout_analytics_service(
            activity_id="latest",
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    assert envelope.data.id == 702


def test_workout_analytics_not_found_returns_unavailable_envelope(tmp_path: Path) -> None:
    from mcp_strava.application.workouts import get_workout_analytics_service

    conn = _fixture_conn(tmp_path / "missing.db")
    try:
        envelope = get_workout_analytics_service(
            activity_id=999999,
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    assert envelope.data is None
    assert envelope.completeness.status == "unavailable"
    assert "workout_not_found" in {warning.code for warning in envelope.warnings}


def test_workout_analytics_missing_hr_and_streams_are_factual_metadata(tmp_path: Path) -> None:
    from mcp_strava.application.workouts import get_workout_analytics_service

    conn = _fixture_conn(tmp_path / "partial.db")
    try:
        envelope = get_workout_analytics_service(
            activity_id=703,
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    assert envelope.data.avg_hr is None
    assert envelope.completeness.status == "partial"
    assert {"missing_hr", "missing_streams", "metric_unavailable"} & set(envelope.completeness.missing)
