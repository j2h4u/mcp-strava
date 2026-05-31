from __future__ import annotations

import json
from pathlib import Path

from mcp_strava.adapters.duckdb.connection import open_fixture_db
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.duckdb.schema import create_schema
from mcp_strava.metric_registry import MATERIALIZED_ROLLING_WINDOW_DAYS

READ_MODEL_METADATA_KEYS = {
    "status",
    "last_materialized_at",
    "dirty_count",
    "oldest_dirty_day",
    "metric_versions_present",
    "stale_reason",
}


def _insert_activity(conn, activity_id: int, day: str, *, sport_type: str, with_hr: bool) -> None:
    avg_hr = 145.0 if with_hr else None
    max_hr = 165.0 if with_hr else None
    summary = {
        "id": activity_id,
        "name": f"Workout {activity_id}",
        "sport_type": sport_type,
        "start_date_local": f"{day}T07:00:00",
        "distance": 5000.0,
        "moving_time": 1800,
        "elapsed_time": 1830,
        "total_elevation_gain": 30.0,
        "has_heartrate": with_hr,
        "average_heartrate": avg_hr,
        "max_heartrate": max_hr,
        "kudos_count": 2 if activity_id == 701 else 0,
    }
    conn.execute(
        """
        INSERT INTO activities (
            id, activity_day, date, name, sport_type, distance, moving_time, elapsed_time,
            total_elevation_gain, summary_json, detail_json, synced_at
        ) VALUES (?, CAST(? AS DATE), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            activity_id,
            day,
            f"{day}T07:00:00",
            f"Workout {activity_id}",
            sport_type,
            5000.0,
            1800,
            1830,
            30.0,
            json.dumps(summary),
            None,
            f"{day}T08:00:00",
        ],
    )


def _insert_activity_fact(conn, values: dict[str, object]) -> None:
    conn.execute(
        """
        INSERT INTO activity_metric_facts (
            activity_id, activity_day, sport_type, source_hash, source_revision,
            metric_version, computed_at, completeness_status, missing_reasons_json,
            trimp, zone1_seconds, zone2_seconds, zone3_seconds, zone4_seconds, zone5_seconds,
            hr_recovery_pause_count, hr_recovery_total_rest_sec,
            hr_recovery_median_rate, hr_recovery_best_rate, hr_recovery_worst_rate,
            hr_recovery_avg_rate, vertical_speed_vmh, vertical_speed_total_ascent_m,
            vertical_speed_duration_hours, cardiac_cost, adjusted_cardiac_cost,
            cardiac_drift_pct, cardiac_drift_severity, cardiac_drift_significant,
            cardiac_drift_quality, hrr_pct, anomaly_count, distance_m, moving_time_s,
            elapsed_time_s, elevation_gain_m, heartrate_sample_count, stream_sample_count
        ) VALUES (
            ?, CAST(? AS DATE), ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            values["activity_id"],
            values["activity_day"],
            values["sport_type"],
            values["source_hash"],
            values["source_revision"],
            values["metric_version"],
            values["computed_at"],
            values["completeness_status"],
            values["missing_reasons_json"],
            values["trimp"],
            values["zone1_seconds"],
            values["zone2_seconds"],
            values["zone3_seconds"],
            values["zone4_seconds"],
            values["zone5_seconds"],
            values["hr_recovery_pause_count"],
            values["hr_recovery_total_rest_sec"],
            values["hr_recovery_median_rate"],
            values["hr_recovery_best_rate"],
            values["hr_recovery_worst_rate"],
            values["hr_recovery_avg_rate"],
            values["vertical_speed_vmh"],
            values["vertical_speed_total_ascent_m"],
            values["vertical_speed_duration_hours"],
            values["cardiac_cost"],
            values["adjusted_cardiac_cost"],
            values["cardiac_drift_pct"],
            values["cardiac_drift_severity"],
            values["cardiac_drift_significant"],
            values["cardiac_drift_quality"],
            values["hrr_pct"],
            values["anomaly_count"],
            values["distance_m"],
            values["moving_time_s"],
            values["elapsed_time_s"],
            values["elevation_gain_m"],
            values["heartrate_sample_count"],
            values["stream_sample_count"],
        ],
    )


def _activity_fact(
    *,
    activity_id: int,
    day: str,
    sport_type: str,
    completeness_status: str,
    missing_reasons: list[str],
    trimp: float,
    cardiac_cost: float | None,
    adjusted_cardiac_cost: float | None,
    stream_sample_count: int,
    heartrate_sample_count: int,
) -> dict[str, object]:
    return {
        "activity_id": activity_id,
        "activity_day": day,
        "sport_type": sport_type,
        "source_hash": f"hash-{activity_id}",
        "source_revision": 1,
        "metric_version": 1,
        "computed_at": "2026-05-21T06:00:00",
        "completeness_status": completeness_status,
        "missing_reasons_json": json.dumps(missing_reasons),
        "trimp": trimp,
        "zone1_seconds": 120,
        "zone2_seconds": 240,
        "zone3_seconds": 360,
        "zone4_seconds": 180,
        "zone5_seconds": 30,
        "hr_recovery_pause_count": 1 if cardiac_cost is not None else 0,
        "hr_recovery_total_rest_sec": 45 if cardiac_cost is not None else 0,
        "hr_recovery_median_rate": 18.0 if cardiac_cost is not None else None,
        "hr_recovery_best_rate": 28.0 if cardiac_cost is not None else None,
        "hr_recovery_worst_rate": 8.0 if cardiac_cost is not None else None,
        "hr_recovery_avg_rate": 17.0 if cardiac_cost is not None else None,
        "vertical_speed_vmh": 420 if sport_type == "Run" else 300,
        "vertical_speed_total_ascent_m": 130.0 if sport_type == "Run" else 500.0,
        "vertical_speed_duration_hours": 0.6 if sport_type == "Run" else 1.7,
        "cardiac_cost": cardiac_cost,
        "adjusted_cardiac_cost": adjusted_cardiac_cost,
        "cardiac_drift_pct": 2.5 if cardiac_cost is not None else None,
        "cardiac_drift_severity": "stable" if cardiac_cost is not None else None,
        "cardiac_drift_significant": 0,
        "cardiac_drift_quality": "good" if cardiac_cost is not None else None,
        "hrr_pct": 68.0 if cardiac_cost is not None else None,
        "anomaly_count": 1 if completeness_status == "partial" else 0,
        "distance_m": 5000.0 if sport_type == "Run" else 9000.0,
        "moving_time_s": 1800 if sport_type == "Run" else 7200,
        "elapsed_time_s": 1830 if sport_type == "Run" else 7500,
        "elevation_gain_m": 30.0 if sport_type == "Run" else 500.0,
        "heartrate_sample_count": heartrate_sample_count,
        "stream_sample_count": stream_sample_count,
    }


def _repo_with_facts(path: Path) -> DuckDBRepository:
    conn = open_fixture_db(path)
    create_schema(conn)
    _insert_activity(conn, 701, "2026-05-20", sport_type="Run", with_hr=True)
    _insert_activity(conn, 702, "2026-05-21", sport_type="Run", with_hr=True)
    _insert_activity(conn, 703, "2026-05-19", sport_type="Hike", with_hr=False)
    conn.executemany(
        "INSERT INTO kudos (activity_id, firstname, lastname, fetched_at) VALUES (?, ?, ?, ?)",
        [
            (701, "Ada", "Lovelace", "2026-05-21T06:01:00"),
            (701, "Grace", "Hopper", "2026-05-21T06:01:00"),
        ],
    )
    for values in (
        _activity_fact(
            activity_id=701,
            day="2026-05-20",
            sport_type="Run",
            completeness_status="complete",
            missing_reasons=[],
            trimp=105.0,
            cardiac_cost=44.0,
            adjusted_cardiac_cost=41.3,
            stream_sample_count=130,
            heartrate_sample_count=130,
        ),
        _activity_fact(
            activity_id=702,
            day="2026-05-21",
            sport_type="Run",
            completeness_status="partial",
            missing_reasons=["missing_streams"],
            trimp=88.0,
            cardiac_cost=None,
            adjusted_cardiac_cost=None,
            stream_sample_count=0,
            heartrate_sample_count=130,
        ),
        _activity_fact(
            activity_id=703,
            day="2026-05-19",
            sport_type="Hike",
            completeness_status="partial",
            missing_reasons=["missing_hr"],
            trimp=75.0,
            cardiac_cost=None,
            adjusted_cardiac_cost=None,
            stream_sample_count=0,
            heartrate_sample_count=0,
        ),
    ):
        _insert_activity_fact(conn, values)
    conn.executemany(
        """
        INSERT INTO daily_load_facts (
            day, scope, sport_type, metric_version, computed_at,
            completeness_status, missing_reasons_json, activity_count,
            stream_point_count, heartrate_point_count, observed_trimp,
            effective_trimp, distance_m, moving_time_s, elevation_gain_m,
            zone4_seconds, zone5_seconds, high_zone_seconds, anomaly_count
        ) VALUES (CAST(? AS DATE), 'all', 'all', 1, '2026-05-21T06:10:00',
                  'complete', '[]', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("2026-05-19", 1, 0, 0, 75.0, 75.0, 9000.0, 7200, 500.0, 0, 0, 0, 0),
            ("2026-05-20", 1, 130, 130, 105.0, 105.0, 5000.0, 1800, 30.0, 180, 30, 210, 0),
            ("2026-05-21", 1, 0, 130, 88.0, 88.0, 5000.0, 1800, 30.0, 120, 0, 120, 1),
        ],
    )
    conn.execute(
        """
        INSERT INTO training_model_daily (
            day, scope, sport_type, metric_version, computed_at,
            completeness_status, missing_reasons_json, effective_trimp,
            observed_trimp, fitness, fatigue, form,
            form_zone, acwr_zone, acwr, load_7d, load_28d, load_42d, input_days, missing_days
        ) VALUES (
            DATE '2026-05-21', 'all', 'all', 1, '2026-05-21T06:15:00',
            'complete', '[]', 88.0, 88.0, 42.0, 37.0, 5.0,
            'normal', 'sweet_spot', 0.881, 180.0, 268.0, 370.0, 3, 0
        )
        """
    )
    rolling_inputs = {
        7: (268.0, 3, 4),
        14: (268.0, 3, 11),
        28: (268.0, 3, 25),
        42: (268.0, 3, 39),
        90: (268.0, 3, 87),
    }
    for window in MATERIALIZED_ROLLING_WINDOW_DAYS:
        effective, active, rest = rolling_inputs[window]
        conn.execute(
            """
            INSERT INTO rolling_period_facts (
                as_of_day, window_days, scope, sport_type, metric_version,
                computed_at, completeness_status, missing_reasons_json,
                activity_count, active_days, rest_days, observed_trimp,
                effective_trimp, distance_m, moving_time_s, elevation_gain_m,
                high_zone_seconds, anomaly_count, fitness, fatigue, form, form_zone,
                acwr_zone, acwr, median_cardiac_cost, median_adjusted_cardiac_cost,
                median_hr_recovery, median_cardiac_drift_pct
            ) VALUES (
                DATE '2026-05-21', ?, 'all', 'all', 1, '2026-05-21T06:20:00',
                'complete', '[]', 3, ?, ?, ?, ?, 19000.0, 10800,
                560.0, 330, 1, 42.0, 37.0, 5.0, 'normal',
                'sweet_spot', 0.881, 44.0, 41.3, 18.0, 2.5
            )
            """,
            [window, active, rest, effective, effective],
        )
    conn.execute(
        """
        INSERT INTO read_model_refresh_runs (
            id, started_at, finished_at, status, metric_version, trigger_reason,
            activities_considered, activities_materialized, daily_facts_materialized,
            model_facts_materialized, rolling_facts_materialized,
            dirty_rows_claimed, dirty_rows_cleared, attempt_count
        ) VALUES (
            1, '2026-05-21T06:00:00', '2026-05-21T06:20:00', 'ok', 1,
            'test', 3, 3, 3, 1, 5, 3, 3, 1
        )
        """
    )
    conn.execute(
        """
        INSERT INTO refresh_state (id, last_success_at, last_attempt_at, last_status)
        VALUES (1, '2026-05-21T06:30:00', '2026-05-21T06:30:00', 'ok')
        """
    )
    conn.commit()
    return DuckDBRepository.from_connection(conn)


def test_read_model_status_reports_metadata_fields(tmp_path: Path) -> None:
    repo = _repo_with_facts(tmp_path / "status.duckdb")
    with repo:
        repo.enqueue_metric_dirty_activity(
            activity_id=702,
            activity_day="2026-05-21",
            metric_version=1,
            source_revision=2,
            reason="test_dirty",
            queued_at="2026-05-21T07:00:00",
        )
        status = repo.read_model_status(metric_version=1)

    assert READ_MODEL_METADATA_KEYS <= set(status)
    assert status["status"] == "stale"
    assert status["last_materialized_at"] == "2026-05-21T06:20:00"
    assert status["dirty_count"] == 1
    assert status["oldest_dirty_day"] == "2026-05-21"
    assert status["metric_versions_present"] == [1]
    assert status["stale_reason"] == "dirty_queue_not_empty"


def test_activity_metric_fact_queries_return_facts_and_joined_activity_context(tmp_path: Path) -> None:
    repo = _repo_with_facts(tmp_path / "activity-facts.duckdb")
    with repo:
        rows = repo.fetch_activity_metric_facts("2026-05-19", "2026-05-22", metric_version=1)
        single = repo.fetch_activity_metric_fact(701, metric_version=1)

    assert [row["activity_id"] for row in rows] == [702, 701, 703]
    assert single is not None
    assert single["activity_name"] == "Workout 701"
    assert single["cardiac_cost"] == 44.0
    assert single["stream_sample_count"] == 130


def test_read_model_queries_fail_soft_when_schema_missing(tmp_path: Path) -> None:
    path = tmp_path / "empty.duckdb"
    conn = open_fixture_db(path)
    repo = DuckDBRepository.from_connection(conn)
    with repo:
        assert repo.read_model_status(metric_version=1)["status"] == "unavailable"
        assert repo.fetch_activity_metric_facts("2026-05-01", "2026-05-22") == []
        assert repo.fetch_latest_training_model_day(1) is None
