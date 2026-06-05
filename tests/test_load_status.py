from __future__ import annotations

from pathlib import Path

from mcp_strava.adapters.duckdb.daily_load_queries import daily_load_points_between, effective_trimp_history
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.hr_zones import zone_bounds as _zone_bounds
from mcp_strava.training import calc_banister, calc_banister_series, ewma
from tests._fixtures_duckdb import create_empty_fixture_db

# Use the canonical historical bounds (hr_rest=53, hr_max=191) for test fixtures.
_TEST_BOUNDS = _zone_bounds(191, 53)


def _insert_activity(conn, activity_id: int, day: str, sport_type: str = "Run") -> None:
    conn.execute(
        """
        INSERT INTO activities (
            id, activity_day, date, name, sport_type, distance, moving_time,
            elapsed_time, total_elevation_gain, summary_json, detail_json, synced_at
        ) VALUES (?, CAST(? AS DATE), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            activity_id,
            day,
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
        ],
    )


def _insert_stream(conn, activity_id: int, t: int, hr: int | None, vel: float = 3.0) -> None:
    conn.execute(
        """
        INSERT INTO streams (
            activity_id, time_offset, heartrate, velocity, altitude,
            cadence, lat, lng, grade, gap_speed, gap_distance, is_moving, values_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
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
        ],
    )


def test_daily_load_contract_statuses_and_phase2_numeric_mapping(tmp_path: Path) -> None:
    fixture = tmp_path / "load-status.duckdb"
    create_empty_fixture_db(fixture)

    rest_day = "2026-05-16"
    unknown_day = "2026-05-17"
    partial_day = "2026-05-18"
    observed_day = "2026-05-19"

    with DuckDBRepository.from_path(fixture) as repo:
        _insert_activity(repo.conn, 101, unknown_day)
        _insert_activity(repo.conn, 102, partial_day)
        _insert_activity(repo.conn, 103, observed_day)

        _insert_stream(repo.conn, 102, 0, None)
        _insert_stream(repo.conn, 102, 1, None)
        _insert_stream(repo.conn, 103, 0, 150)
        _insert_stream(repo.conn, 103, 1, 150)

        points = daily_load_points_between(repo, rest_day, observed_day, bounds=_TEST_BOUNDS, sport_filter="training")

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


def test_effective_trimp_series_matches_daily_load_points(tmp_path: Path) -> None:
    fixture = tmp_path / "load-parity.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        _insert_activity(repo.conn, 201, "2026-05-17")
        _insert_activity(repo.conn, 202, "2026-05-18")
        _insert_activity(repo.conn, 203, "2026-05-19")
        _insert_activity(repo.conn, 204, "2026-05-20")
        _insert_stream(repo.conn, 202, 0, 145)
        _insert_stream(repo.conn, 202, 1, 145)
        _insert_stream(repo.conn, 203, 0, None)
        _insert_stream(repo.conn, 203, 1, None)
        _insert_stream(repo.conn, 204, 0, 155)
        _insert_stream(repo.conn, 204, 1, 155)

        points = daily_load_points_between(
            repo, "2026-05-16", "2026-05-20", bounds=_TEST_BOUNDS, sport_filter="training"
        )
        effective_series = effective_trimp_history(
            repo, "2026-05-16", "2026-05-20", bounds=_TEST_BOUNDS, sport_filter="training"
        )

    today_str = "2026-05-20"
    effective_from_points = {p.date: p.effective_trimp for p in points}

    assert effective_series == effective_from_points

    # Banister/EWMA/weekly-plan computations are well-defined over the effective series.
    banister = calc_banister(effective_series, today_str)
    assert banister is not None
    series_tail = calc_banister_series(effective_series, today_str)[-1]
    assert series_tail is not None
    assert ewma(effective_series, 7, today_str)[today_str] >= 0
    assert ewma(effective_series, 28, today_str)[today_str] >= 0
    assert ewma(effective_series, 42, today_str)[today_str] >= 0


def test_load_status_fixture_uses_temp_db_only(tmp_path: Path) -> None:
    fixture = tmp_path / "load.duckdb"
    create_empty_fixture_db(fixture)
    resolved = fixture.resolve()
    assert "/data/strava.db" not in str(resolved)
    assert "/opt/docker/mcp-strava" not in str(resolved)
