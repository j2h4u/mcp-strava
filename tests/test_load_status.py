from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.db import get_daily_trimp_history
from mcp_strava.training import calc_banister, calc_banister_series, calc_weekly_plan, ewma


def _create_fixture_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
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
        """
    )
    conn.commit()
    conn.close()


def _insert_activity(conn: sqlite3.Connection, activity_id: int, day: str, sport_type: str = "Run") -> None:
    conn.execute(
        """
        INSERT INTO activities (
            id, date, name, sport_type, distance, moving_time, elapsed_time,
            total_elevation_gain, summary_json, detail_json, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            activity_id,
            f"{day}T06:00:00Z",
            f"act-{activity_id}",
            sport_type,
            1000.0,
            600,
            620,
            5.0,
            "{}",
            None,
            f"{day}T07:00:00Z",
        ),
    )


def _insert_stream(conn: sqlite3.Connection, activity_id: int, t: int, hr: int | None, vel: float = 3.0) -> None:
    conn.execute(
        """
        INSERT INTO streams (
            activity_id, time_offset, heartrate, velocity, altitude,
            cadence, lat, lng, grade, gap_speed, gap_distance, is_moving, latlng
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            activity_id,
            t,
            hr,
            vel,
            100.0,
            85,
            None,
            None,
            0.0,
            vel,
            1.0,
            1,
            "[43.2,76.9]",
        ),
    )


def test_daily_load_contract_statuses_and_phase2_numeric_mapping(tmp_path: Path) -> None:
    fixture = tmp_path / "load-status.db"
    _create_fixture_db(fixture)

    rest_day = "2026-05-16"
    unknown_day = "2026-05-17"
    partial_day = "2026-05-18"
    observed_day = "2026-05-19"

    conn = sqlite3.connect(fixture)
    conn.row_factory = sqlite3.Row
    _insert_activity(conn, 101, unknown_day)
    _insert_activity(conn, 102, partial_day)
    _insert_activity(conn, 103, observed_day)

    _insert_stream(conn, 102, 0, None)
    _insert_stream(conn, 102, 1, None)
    _insert_stream(conn, 103, 0, 150)
    _insert_stream(conn, 103, 1, 150)
    conn.commit()
    conn.close()

    with SQLiteRepository.from_path(fixture) as repo:
        points = repo.daily_load_points_between(rest_day, observed_day, sport_filter="training")

    by_day = {p.date: p for p in points}
    assert by_day[rest_day].status == "REST"
    assert by_day[unknown_day].status == "UNKNOWN"
    assert by_day[partial_day].status == "PARTIAL"
    assert by_day[observed_day].status == "OBSERVED"

    assert by_day[unknown_day].status != "REST"
    assert by_day[partial_day].status != "REST"

    for day_key in (rest_day, unknown_day, partial_day):
        assert by_day[day_key].effective_trimp == 0.0
        assert by_day[day_key].observed_trimp is None

    assert by_day[observed_day].observed_trimp == by_day[observed_day].effective_trimp
    assert by_day[observed_day].effective_trimp > 0


def test_effective_trimp_series_keeps_training_numeric_parity(tmp_path: Path) -> None:
    fixture = tmp_path / "load-parity.db"
    _create_fixture_db(fixture)

    conn = sqlite3.connect(fixture)
    conn.row_factory = sqlite3.Row
    _insert_activity(conn, 201, "2026-05-17")
    _insert_activity(conn, 202, "2026-05-18")
    _insert_activity(conn, 203, "2026-05-19")
    _insert_activity(conn, 204, "2026-05-20")
    _insert_stream(conn, 202, 0, 145)
    _insert_stream(conn, 202, 1, 145)
    _insert_stream(conn, 203, 0, None)
    _insert_stream(conn, 203, 1, None)
    _insert_stream(conn, 204, 0, 155)
    _insert_stream(conn, 204, 1, 155)
    conn.commit()

    legacy_observed = get_daily_trimp_history(conn, sport_filter="training")
    conn.close()

    with SQLiteRepository.from_path(fixture) as repo:
        points = repo.daily_load_points_between("2026-05-16", "2026-05-20", sport_filter="training")
        effective_series = repo.effective_trimp_history("2026-05-16", "2026-05-20", sport_filter="training")

    today_str = "2026-05-20"
    effective_from_points = {p.date: p.effective_trimp for p in points}
    observed_only_from_points = {
        p.date: p.observed_trimp
        for p in points
        if p.status == "OBSERVED" and p.observed_trimp is not None
    }

    assert effective_series == effective_from_points
    assert observed_only_from_points == legacy_observed

    assert calc_banister(effective_series, today_str) == calc_banister(legacy_observed, today_str)
    effective_series_tail = calc_banister_series(effective_series, today_str)[-1]
    legacy_series_tail = calc_banister_series(legacy_observed, today_str)[-1]
    assert effective_series_tail == legacy_series_tail
    assert ewma(effective_series, 7, today_str)[today_str] == ewma(legacy_observed, 7, today_str)[today_str]
    assert ewma(effective_series, 28, today_str)[today_str] == ewma(legacy_observed, 28, today_str)[today_str]
    assert ewma(effective_series, 42, today_str)[today_str] == ewma(legacy_observed, 42, today_str)[today_str]

    plan_effective = calc_weekly_plan(effective_series, today_str)
    plan_legacy = calc_weekly_plan(legacy_observed, today_str)
    assert [d.trimp for d in plan_effective.completed_days] == [d.trimp for d in plan_legacy.completed_days]


def test_load_status_fixture_uses_temp_db_only(tmp_path: Path) -> None:
    fixture = tmp_path / "load.db"
    _create_fixture_db(fixture)
    resolved = fixture.resolve()
    assert "/data/strava.db" not in str(resolved)
    assert "/opt/docker/mcp-strava" not in str(resolved)
