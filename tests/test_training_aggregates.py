from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_strava.adapters.duckdb.aggregate_queries import (
    AggregateRequest,
    build_aggregate_query,
    query_training_aggregates,
    validate_aggregate_request,
)
from mcp_strava.adapters.duckdb.connection import open_fixture_db
from mcp_strava.adapters.duckdb.schema import create_schema
from mcp_strava.application.metric_registry import (
    METRIC_REGISTRY,
    SUPPORTED_AGGREGATE_BUCKETS,
    SUPPORTED_ROLLING_WINDOW_DAYS,
    metrics_for_aggregate_bundle,
)
from mcp_strava.types import dc_to_dict

EXPECTED_BUCKETS = ("day", "week", "month", "year", "all_time")
EXPECTED_WINDOWS = (7, 14, 28, 42, 90)
D42_ROW_KEYS = {
    "bucket_start",
    "bucket_end",
    "bucket_width",
    "metric_id",
    "unit",
    "calculation",
    "aggregation_mode",
    "denominator",
    "value",
    "quantiles",
    "distribution",
    "sample_size",
    "activity_count",
    "null_count",
    "excluded_count",
    "completeness_status",
    "missing_reasons",
    "metric_version_status",
    "materialized_at",
    "mirror_freshness",
    "read_model_freshness",
}


def _payloads(rows: list[object]) -> list[dict[str, object]]:
    return [dc_to_dict(row) for row in rows]


def _row(
    rows: list[dict[str, object]],
    metric_id: str,
    *,
    bucket_start: str | None = None,
    sport_type: str | None = None,
) -> dict[str, object]:
    matches = [row for row in rows if row["metric_id"] == metric_id]
    if bucket_start is not None:
        matches = [row for row in matches if row["bucket_start"] == bucket_start]
    if sport_type is not None:
        matches = [row for row in matches if row["sport_type"] == sport_type]
    assert len(matches) == 1, matches
    return matches[0]


def _insert_activity(
    conn,
    *,
    activity_id: int,
    day: str,
    sport_type: str,
    distance_m: float,
    moving_time_s: int,
    elapsed_time_s: int,
    elevation_gain_m: float,
    avg_hr: float | None,
    max_hr: float | None,
    kudos_count: int,
) -> None:
    summary = {
        "id": activity_id,
        "sport_type": sport_type,
        "start_date_local": f"{day}T07:00:00",
        "distance": distance_m,
        "moving_time": moving_time_s,
        "elapsed_time": elapsed_time_s,
        "total_elevation_gain": elevation_gain_m,
        "has_heartrate": avg_hr is not None,
        "average_heartrate": avg_hr,
        "max_heartrate": max_hr,
        "kudos_count": kudos_count,
    }
    conn.execute(
        """
        INSERT INTO activities (
            id, activity_day, date, name, sport_type, distance, moving_time,
            elapsed_time, total_elevation_gain, summary_json, detail_json, synced_at
        ) VALUES (?, CAST(? AS DATE), ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """,
        [
            activity_id,
            day,
            f"{day}T07:00:00",
            f"Workout {activity_id}",
            sport_type,
            distance_m,
            moving_time_s,
            elapsed_time_s,
            elevation_gain_m,
            json.dumps(summary),
            f"{day}T08:00:00",
        ],
    )


def _insert_activity_fact(
    conn,
    *,
    activity_id: int,
    day: str,
    sport_type: str,
    metric_version: int,
    trimp: float,
    completeness_status: str,
    missing_reasons: list[str],
    cardiac_cost: float | None,
    vertical_ascent_m: float | None,
    vertical_duration_h: float | None,
    heartrate_sample_count: int,
    stream_sample_count: int,
    distance_m: float,
    moving_time_s: int,
    elapsed_time_s: int,
    elevation_gain_m: float,
    zone4_seconds: int = 40,
    zone5_seconds: int = 50,
    cardiac_drift_pct: float | None = 2.5,
    cardiac_drift_severity: str | None = "stable",
    cardiac_drift_significant: int = 0,
    cardiac_drift_quality: str | None = "good",
    hr_anomaly_count: int = 0,
) -> None:
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
            ?, CAST(? AS DATE), ?, ?, 1, ?, ?, ?, ?,
            ?, 10, 20, 30, ?, ?,
            1, 30, 18.0, 24.0, 8.0, 16.0, NULL, ?, ?,
            ?, ?, ?, ?, ?, ?, 65.0, ?,
            ?, ?, ?, ?, ?, ?
        )
        """,
        [
            activity_id,
            day,
            sport_type,
            f"hash-{activity_id}",
            metric_version,
            f"{day}T12:00:00",
            completeness_status,
            json.dumps(missing_reasons),
            trimp,
            zone4_seconds,
            zone5_seconds,
            vertical_ascent_m,
            vertical_duration_h,
            cardiac_cost,
            cardiac_cost - 1 if cardiac_cost is not None else None,
            cardiac_drift_pct,
            cardiac_drift_severity,
            cardiac_drift_significant,
            cardiac_drift_quality,
            hr_anomaly_count,
            distance_m,
            moving_time_s,
            elapsed_time_s,
            elevation_gain_m,
            heartrate_sample_count,
            stream_sample_count,
        ],
    )


def _insert_daily_fact(
    conn,
    day: str,
    *,
    metric_version: int,
    effective_trimp: float,
    activity_count: int,
    distance_m: float,
    moving_time_s: int,
    elevation_gain_m: float,
) -> None:
    conn.execute(
        """
        INSERT INTO daily_load_facts (
            day, scope, sport_type, metric_version, computed_at, completeness_status,
            missing_reasons_json, activity_count, stream_point_count, heartrate_point_count,
            observed_trimp, effective_trimp, distance_m, moving_time_s, elevation_gain_m,
            zone4_seconds, zone5_seconds, high_zone_seconds, anomaly_count
        ) VALUES (
            CAST(? AS DATE), 'all', 'all', ?, ?, 'complete', '[]', ?, 1, 1,
            ?, ?, ?, ?, ?, 0, 0, 0, 0
        )
        """,
        [
            day,
            metric_version,
            f"{day}T12:05:00",
            activity_count,
            effective_trimp,
            effective_trimp,
            distance_m,
            moving_time_s,
            elevation_gain_m,
        ],
    )


def _insert_model_fact(
    conn,
    day: str,
    *,
    metric_version: int,
    fitness: float,
    fatigue: float,
    form: float,
    form_zone: str,
) -> None:
    conn.execute(
        """
        INSERT INTO training_model_daily (
            day, scope, sport_type, metric_version, computed_at, completeness_status,
            missing_reasons_json, effective_trimp, observed_trimp, fitness, fatigue,
            form, form_zone, acwr_zone, acwr, load_7d, load_28d, load_42d,
            input_days, missing_days
        ) VALUES (
            CAST(? AS DATE), 'all', 'all', ?, ?, 'complete', '[]', 0.0, 0.0,
            ?, ?, ?, ?, 'sweet_spot', 1.1, 0.0, 0.0, 0.0, 1, 0
        )
        """,
        [day, metric_version, f"{day}T12:10:00", fitness, fatigue, form, form_zone],
    )


def _insert_rolling_facts(conn, as_of_day: str = "2026-05-21") -> None:
    for window_days in EXPECTED_WINDOWS:
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
                CAST(? AS DATE), ?, 'all', 'all', 1, ?, 'complete', '[]',
                ?, 2, ?, ?, ?, 21000.0, 7400, 350.0, 90, 0,
                30.0, 20.0, 10.0, 'fresh', 'sweet_spot', 1.1,
                50.0, 49.0, 18.0, 2.5
            )
            """,
            [
                as_of_day,
                window_days,
                f"{as_of_day}T12:20:00",
                window_days,
                max(0, window_days - 2),
                float(window_days),
                float(window_days),
            ],
        )


def _insert_sport_rolling_fact(
    conn,
    *,
    as_of_day: str,
    window_days: int,
    sport_type: str,
    median_cardiac_cost: float,
) -> None:
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
            CAST(? AS DATE), ?, 'sport', ?, 1, ?, 'complete', '[]',
            1, 1, 0, 20.0, 20.0, 5000.0, 1800, 50.0, 30, 0,
            30.0, 20.0, 10.0, 'fresh', 'sweet_spot', 1.1,
            ?, ?, 18.0, 2.5
        )
        """,
        [
            as_of_day,
            window_days,
            sport_type,
            f"{as_of_day}T12:30:00",
            median_cardiac_cost,
            median_cardiac_cost,
        ],
    )


def _aggregate_fixture(path: Path) -> Path:
    conn = open_fixture_db(path)
    create_schema(conn)
    activities = [
        (
            101,
            "2026-05-05",
            "Run",
            10000.0,
            3600,
            3700,
            100.0,
            140.0,
            170.0,
            2,
            1,
            100.0,
            "complete",
            [],
            40.0,
            200.0,
            1.0,
            100,
            100,
        ),
        (
            102,
            "2026-05-12",
            "Run",
            5000.0,
            1800,
            1900,
            50.0,
            160.0,
            180.0,
            0,
            1,
            80.0,
            "partial",
            ["missing_streams"],
            50.0,
            300.0,
            2.0,
            300,
            0,
        ),
        (
            103,
            "2026-05-13",
            "Run",
            6000.0,
            2000,
            2100,
            200.0,
            150.0,
            175.0,
            1,
            2,
            70.0,
            "complete",
            [],
            60.0,
            100.0,
            1.0,
            200,
            200,
        ),
        (
            104,
            "2026-05-20",
            "Hike",
            8000.0,
            7200,
            7500,
            500.0,
            None,
            None,
            3,
            1,
            60.0,
            "partial",
            ["missing_hr"],
            None,
            500.0,
            2.0,
            0,
            0,
        ),
        (
            105,
            "2026-06-01",
            "Run",
            9999.0,
            999,
            999,
            9.0,
            190.0,
            200.0,
            9,
            1,
            999.0,
            "complete",
            [],
            99.0,
            99.0,
            1.0,
            99,
            99,
        ),
    ]
    for (
        activity_id,
        day,
        sport_type,
        distance_m,
        moving_time_s,
        elapsed_time_s,
        elevation_gain_m,
        avg_hr,
        max_hr,
        kudos_count,
        metric_version,
        trimp,
        completeness_status,
        missing_reasons,
        cardiac_cost,
        vertical_ascent_m,
        vertical_duration_h,
        heartrate_sample_count,
        stream_sample_count,
    ) in activities:
        _insert_activity(
            conn,
            activity_id=activity_id,
            day=day,
            sport_type=sport_type,
            distance_m=distance_m,
            moving_time_s=moving_time_s,
            elapsed_time_s=elapsed_time_s,
            elevation_gain_m=elevation_gain_m,
            avg_hr=avg_hr,
            max_hr=max_hr,
            kudos_count=kudos_count,
        )
        _insert_activity_fact(
            conn,
            activity_id=activity_id,
            day=day,
            sport_type=sport_type,
            metric_version=metric_version,
            trimp=trimp,
            completeness_status=completeness_status,
            missing_reasons=missing_reasons,
            cardiac_cost=cardiac_cost,
            vertical_ascent_m=vertical_ascent_m,
            vertical_duration_h=vertical_duration_h,
            heartrate_sample_count=heartrate_sample_count,
            stream_sample_count=stream_sample_count,
            distance_m=distance_m,
            moving_time_s=moving_time_s,
            elapsed_time_s=elapsed_time_s,
            elevation_gain_m=elevation_gain_m,
        )
        _insert_daily_fact(
            conn,
            day,
            metric_version=metric_version,
            effective_trimp=trimp,
            activity_count=1,
            distance_m=distance_m,
            moving_time_s=moving_time_s,
            elevation_gain_m=elevation_gain_m,
        )
    _insert_model_fact(conn, "2026-05-05", metric_version=1, fitness=10.0, fatigue=8.0, form=2.0, form_zone="normal")
    _insert_model_fact(conn, "2026-05-13", metric_version=2, fitness=30.0, fatigue=22.0, form=8.0, form_zone="fresh")
    _insert_model_fact(conn, "2026-05-20", metric_version=1, fitness=40.0, fatigue=32.0, form=8.0, form_zone="fresh")
    _insert_rolling_facts(conn)
    conn.execute(
        """
        INSERT INTO read_model_refresh_runs (
            id, started_at, finished_at, status, metric_version, trigger_reason,
            activities_considered, activities_materialized, daily_facts_materialized,
            model_facts_materialized, rolling_facts_materialized,
            dirty_rows_claimed, dirty_rows_cleared, attempt_count
        ) VALUES (
            1, '2026-05-21T12:00:00', '2026-05-21T12:30:00', 'ok', 1, 'test',
            5, 5, 5, 3, 5, 0, 0, 1
        )
        """
    )
    conn.execute(
        """
        INSERT INTO refresh_state (
            id, last_success_at, last_attempt_at, last_status
        ) VALUES (1, '2026-05-21T13:00:00', '2026-05-21T13:00:00', 'ok')
        """
    )
    conn.close()
    return path


def _phase9_status_fixture(path: Path) -> Path:
    conn = open_fixture_db(path)
    create_schema(conn)
    activities = [
        (201, "2026-05-11", "Run", 10000.0, 3600, 3700, 100.0, 140.0, 170.0, 100.0, 50, 0, 0, "good"),
        (202, "2026-05-18", "Run", 7000.0, 2500, 2600, 70.0, 145.0, 172.0, 90.0, 50, 0, 0, "good"),
        (203, "2026-05-20", "Run", 6000.0, 2200, 2300, 80.0, 155.0, 182.0, 95.0, 360, 4, 1, "good"),
        (204, "2026-05-19", "Hike", 9000.0, 7200, 7400, 500.0, 135.0, 168.0, 420.0, 50, 0, 0, "fair"),
        (205, "2026-05-20", "Hike", 8500.0, 7000, 7200, 480.0, 138.0, 170.0, 430.0, 50, 0, 0, "fair"),
    ]
    for (
        activity_id,
        day,
        sport_type,
        distance_m,
        moving_time_s,
        elapsed_time_s,
        elevation_gain_m,
        avg_hr,
        max_hr,
        trimp,
        zone5_seconds,
        hr_anomaly_count,
        cardiac_drift_significant,
        cardiac_drift_quality,
    ) in activities:
        _insert_activity(
            conn,
            activity_id=activity_id,
            day=day,
            sport_type=sport_type,
            distance_m=distance_m,
            moving_time_s=moving_time_s,
            elapsed_time_s=elapsed_time_s,
            elevation_gain_m=elevation_gain_m,
            avg_hr=avg_hr,
            max_hr=max_hr,
            kudos_count=1,
        )
        _insert_activity_fact(
            conn,
            activity_id=activity_id,
            day=day,
            sport_type=sport_type,
            metric_version=1,
            trimp=trimp,
            completeness_status="complete",
            missing_reasons=[],
            cardiac_cost=45.0,
            vertical_ascent_m=elevation_gain_m,
            vertical_duration_h=2.0,
            heartrate_sample_count=200,
            stream_sample_count=200,
            distance_m=distance_m,
            moving_time_s=moving_time_s,
            elapsed_time_s=elapsed_time_s,
            elevation_gain_m=elevation_gain_m,
            zone5_seconds=zone5_seconds,
            hr_anomaly_count=hr_anomaly_count,
            cardiac_drift_significant=cardiac_drift_significant,
            cardiac_drift_quality=cardiac_drift_quality,
        )
    conn.execute(
        """
        INSERT INTO read_model_refresh_runs (
            id, started_at, finished_at, status, metric_version, trigger_reason,
            activities_considered, activities_materialized, daily_facts_materialized,
            model_facts_materialized, rolling_facts_materialized,
            dirty_rows_claimed, dirty_rows_cleared, attempt_count
        ) VALUES (
            1, '2026-05-20T12:00:00', '2026-05-20T12:30:00', 'ok', 1, 'test',
            5, 5, 0, 0, 0, 0, 0, 1
        )
        """
    )
    conn.execute(
        """
        INSERT INTO refresh_state (
            id, last_success_at, last_attempt_at, last_status
        ) VALUES (1, '2026-05-20T13:00:00', '2026-05-20T13:00:00', 'ok')
        """
    )
    conn.close()
    return path


@pytest.mark.parametrize("bucket", EXPECTED_BUCKETS)
def test_supported_buckets_return_factual_half_open_bounds(tmp_path: Path, bucket: str) -> None:
    assert tuple(SUPPORTED_AGGREGATE_BUCKETS) == EXPECTED_BUCKETS
    db_path = _aggregate_fixture(tmp_path / f"{bucket}.duckdb")

    conn = open_fixture_db(db_path)
    rows = _payloads(
        query_training_aggregates(
            conn,
            AggregateRequest(
                metric_ids=("trimp",),
                bucket=bucket,
                start_day="2026-05-01",
                end_day_exclusive="2026-06-01",
                scope="global",
            ),
        )
    )
    conn.close()

    assert rows
    assert all(D42_ROW_KEYS <= set(row) for row in rows)
    assert all(row["bucket_width"] == bucket for row in rows)
    assert not any(row["bucket_start"] == "2026-06-01" for row in rows)
    first = rows[0]
    expected_first_bounds = {
        "day": ("2026-05-05", "2026-05-06"),
        "week": ("2026-05-04", "2026-05-11"),
        "month": ("2026-05-01", "2026-06-01"),
        "year": ("2026-01-01", "2027-01-01"),
        "all_time": ("2026-05-01", "2026-06-01"),
    }
    assert (first["bucket_start"], first["bucket_end"]) == expected_first_bounds[bucket]


def test_all_time_defaults_start_and_honors_exclusive_end(tmp_path: Path) -> None:
    db_path = _aggregate_fixture(tmp_path / "all-time.duckdb")
    conn = open_fixture_db(db_path)

    default_start = _payloads(
        query_training_aggregates(
            conn,
            AggregateRequest(
                metric_ids=("trimp",),
                bucket="all_time",
                start_day=None,
                end_day_exclusive="2026-05-15",
                scope="global",
            ),
        )
    )
    explicit_start = _payloads(
        query_training_aggregates(
            conn,
            AggregateRequest(
                metric_ids=("trimp",),
                bucket="all_time",
                start_day="2026-05-01",
                end_day_exclusive="2026-05-15",
                scope="global",
            ),
        )
    )
    conn.close()

    assert default_start[0]["bucket_start"] == "2026-05-05"
    assert default_start[0]["bucket_end"] == "2026-05-15"
    assert default_start[0]["value"] == pytest.approx(250.0)
    assert explicit_start[0]["bucket_start"] == "2026-05-01"
    assert explicit_start[0]["value"] == pytest.approx(250.0)


def test_week_buckets_start_on_monday(tmp_path: Path) -> None:
    db_path = _aggregate_fixture(tmp_path / "week.duckdb")
    conn = open_fixture_db(db_path)
    rows = _payloads(
        query_training_aggregates(
            conn,
            AggregateRequest(
                metric_ids=("trimp",),
                bucket="week",
                start_day="2026-05-01",
                end_day_exclusive="2026-06-01",
                scope="global",
            ),
        )
    )
    conn.close()

    assert [row["bucket_start"] for row in rows] == ["2026-05-04", "2026-05-11", "2026-05-18"]
    assert rows[0]["bucket_end"] == "2026-05-11"


def test_registry_aggregate_modes_return_expected_values(tmp_path: Path) -> None:
    db_path = _aggregate_fixture(tmp_path / "modes.duckdb")
    conn = open_fixture_db(db_path)

    global_rows = _payloads(
        query_training_aggregates(
            conn,
            AggregateRequest(
                metric_ids=("distance_km", "avg_trimp_per_day", "fitness", "form_zone", "kudos_count"),
                bucket="all_time",
                start_day="2026-05-05",
                end_day_exclusive="2026-06-01",
                scope="global",
            ),
        )
    )
    run_rows = _payloads(
        query_training_aggregates(
            conn,
            AggregateRequest(
                metric_ids=("avg_hr", "vertical_speed_m_per_h", "cardiac_cost"),
                bucket="all_time",
                start_day="2026-05-05",
                end_day_exclusive="2026-06-01",
                scope="per_sport",
                sport_filter="Run",
            ),
        )
    )
    conn.close()

    rows = global_rows + run_rows
    assert {row["aggregation_mode"] for row in rows} == {
        "sum",
        "calendar_average",
        "weighted_average",
        "ratio_of_sums",
        "quantile",
        "last_state",
        "distribution",
        "kudos_count",
    }
    assert _row(rows, "distance_km")["value"] == pytest.approx(29.0)
    assert _row(rows, "avg_trimp_per_day")["value"] == pytest.approx(310.0 / 27.0)
    assert _row(rows, "avg_hr", sport_type="Run")["value"] == pytest.approx((140 * 100 + 160 * 300 + 150 * 200) / 600)
    assert _row(rows, "vertical_speed_m_per_h", sport_type="Run")["value"] == pytest.approx(600.0 / 4.0)
    assert _row(rows, "cardiac_cost", sport_type="Run")["quantiles"] == {"p25": 45.0, "median": 50.0, "p75": 55.0}
    assert _row(rows, "cardiac_cost", sport_type="Run")["value"] == pytest.approx(50.0)
    assert _row(rows, "fitness")["value"] == pytest.approx(40.0)
    assert _row(rows, "form_zone")["distribution"] == {"fresh": 2, "normal": 1}
    assert _row(rows, "kudos_count")["value"] == pytest.approx(6.0)


def test_missing_denominators_and_mixed_versions_are_explicit(tmp_path: Path) -> None:
    db_path = _aggregate_fixture(tmp_path / "coverage.duckdb")
    conn = open_fixture_db(db_path)

    hike_hr = _payloads(
        query_training_aggregates(
            conn,
            AggregateRequest(
                metric_ids=("avg_hr",),
                bucket="all_time",
                start_day="2026-05-01",
                end_day_exclusive="2026-06-01",
                scope="per_sport",
                sport_filter="Hike",
            ),
        )
    )
    mixed = _payloads(
        query_training_aggregates(
            conn,
            AggregateRequest(
                metric_ids=("trimp",),
                bucket="month",
                start_day="2026-05-01",
                end_day_exclusive="2026-06-01",
                scope="global",
            ),
        )
    )
    conn.close()

    assert hike_hr[0]["value"] is None
    assert hike_hr[0]["completeness_status"] == "unavailable"
    assert hike_hr[0]["excluded_count"] == 1
    assert set(hike_hr[0]["missing_reasons"]) >= {"missing_denominator", "missing_hr"}
    assert mixed[0]["metric_version_status"] == "mixed_degraded"
    assert mixed[0]["completeness_status"] == "partial"


def test_bundles_sport_scope_empty_buckets_and_rolling_windows(tmp_path: Path) -> None:
    assert tuple(SUPPORTED_ROLLING_WINDOW_DAYS) == EXPECTED_WINDOWS
    db_path = _aggregate_fixture(tmp_path / "bundle-empty-rolling.duckdb")
    conn = open_fixture_db(db_path)

    bundle_rows = _payloads(
        query_training_aggregates(
            conn,
            AggregateRequest(
                metric_ids=(),
                bundle_id="sport_efficiency",
                bucket="all_time",
                start_day="2026-05-05",
                end_day_exclusive="2026-06-01",
                scope="per_sport",
                sport_filter="Run",
            ),
        )
    )
    empty_rows = _payloads(
        query_training_aggregates(
            conn,
            AggregateRequest(
                metric_ids=("trimp",),
                bucket="day",
                start_day="2026-05-05",
                end_day_exclusive="2026-05-08",
                scope="global",
                include_empty_buckets=True,
            ),
        )
    )
    rolling_widths = []
    for window_days in EXPECTED_WINDOWS:
        rows = _payloads(
            query_training_aggregates(
                conn,
                AggregateRequest(
                    metric_ids=("rolling_median_cc",),
                    bucket="all_time",
                    start_day=None,
                    end_day_exclusive="2026-05-22",
                    scope="per_sport",
                    as_of_day="2026-05-21",
                    window_days=window_days,
                ),
            )
        )
        rolling_widths.append(rows[0]["bucket_width"])
    conn.close()

    assert {row["metric_id"] for row in bundle_rows} == set(metrics_for_aggregate_bundle("sport_efficiency"))
    assert {row["sport_type"] for row in bundle_rows} == {"Run"}
    assert [(row["bucket_start"], row["value"]) for row in empty_rows] == [
        ("2026-05-05", 100.0),
        ("2026-05-06", None),
        ("2026-05-07", None),
    ]
    assert rolling_widths == [f"rolling_{window_days}d" for window_days in EXPECTED_WINDOWS]


def test_phase9_product_bundles_handle_mixed_scopes_and_historical_context(tmp_path: Path) -> None:
    db_path = _aggregate_fixture(tmp_path / "phase9-bundles.duckdb")
    conn = open_fixture_db(db_path)

    try:
        for bundle_id in ("daily_brief", "weekly_digest", "historical_facts"):
            metric_ids = metrics_for_aggregate_bundle(bundle_id)
            assert set(metric_ids).issubset(METRIC_REGISTRY)
            assert all(METRIC_REGISTRY[metric_id].aggregate_mode for metric_id in metric_ids)
            rows = _payloads(
                query_training_aggregates(
                    conn,
                    AggregateRequest(
                        metric_ids=(),
                        bundle_id=bundle_id,
                        bucket="all_time",
                        start_day=None,
                        end_day_exclusive="2026-05-22",
                        scope="both",
                    ),
                )
            )
            assert rows, bundle_id
            assert {row["metric_id"] for row in rows}.issuperset(metric_ids)

        historical_rows = _payloads(
            query_training_aggregates(
                conn,
                AggregateRequest(
                    metric_ids=("activity_streak_days", "rest_streak_days", "last_hike_days_ago"),
                    bucket="all_time",
                    start_day=None,
                    end_day_exclusive="2026-05-22",
                    scope="global",
                ),
            )
        )
    finally:
        conn.close()

    assert {row["metric_id"] for row in historical_rows} == {
        "activity_streak_days",
        "rest_streak_days",
        "last_hike_days_ago",
    }
    for metric_id in ("activity_streak_days", "rest_streak_days", "last_hike_days_ago"):
        row = _row(historical_rows, metric_id)
        assert row["completeness_status"] != "unavailable"
        assert row["value"] is not None

    request = AggregateRequest(
        metric_ids=("activity_streak_days",),
        bucket="all_time",
        start_day=None,
        end_day_exclusive="2026-05-22",
        scope="global",
    )
    query = build_aggregate_query(METRIC_REGISTRY["activity_streak_days"], request)
    assert "v_historical_context_facts" in query.statement
    assert "training_model_daily.activity_streak_days" not in query.statement


def test_phase9_status_fact_queries_return_fixture_evidence(tmp_path: Path) -> None:
    from mcp_strava.adapters.duckdb.aggregate_queries import query_status_facts
    from mcp_strava.application.metric_registry import STATUS_FACT_REGISTRY

    db_path = _phase9_status_fixture(tmp_path / "phase9-status.duckdb")
    conn = open_fixture_db(db_path)
    try:
        rows = _payloads(query_status_facts(conn, as_of_day="2026-05-20"))
    finally:
        conn.close()

    by_code = {row["code"]: row for row in rows}
    expected_active = {
        "excessive_z5_exposure": {"zone5_seconds", "z5_lower_bound_bpm", "activity_id"},
        "hr_anomaly_burst": {"hr_anomaly_count", "activity_id"},
        "cardiac_drift_significant_quality": {"cardiac_drift_significant", "cardiac_drift_quality", "activity_id"},
        "consecutive_high_load_hikes": {"combined_trimp", "hike_days"},
        "running_volume_jump": {"current_week_distance_km", "previous_week_distance_km", "increase_pct"},
    }
    assert set(STATUS_FACT_REGISTRY).issubset(by_code)
    for code, evidence_keys in expected_active.items():
        row = by_code[code]
        assert row["status"] != "unavailable"
        assert evidence_keys <= set(row["evidence"])
        assert row["threshold"] == STATUS_FACT_REGISTRY[code].threshold
        assert row["window"] == STATUS_FACT_REGISTRY[code].window
        assert row["calculation"] == STATUS_FACT_REGISTRY[code].calculation
        assert row["completeness"]["status"] == "complete"
        assert row["materialized_from"] == STATUS_FACT_REGISTRY[code].materialized_from


def test_fixed_rolling_metrics_filter_to_their_declared_window(tmp_path: Path) -> None:
    db_path = _aggregate_fixture(tmp_path / "fixed-rolling-window.duckdb")
    conn = open_fixture_db(db_path)

    try:
        rows = _payloads(
            query_training_aggregates(
                conn,
                AggregateRequest(
                    metric_ids=("volume_7d",),
                    bucket="week",
                    start_day="2026-05-18",
                    end_day_exclusive="2026-05-25",
                    scope="global",
                ),
            )
        )
        with pytest.raises(ValueError, match="requires rolling window 7"):
            query_training_aggregates(
                conn,
                AggregateRequest(
                    metric_ids=("volume_7d",),
                    bucket="all_time",
                    start_day=None,
                    end_day_exclusive="2026-05-22",
                    as_of_day="2026-05-21",
                    window_days=14,
                ),
            )
    finally:
        conn.close()

    assert len(rows) == 1
    assert rows[0]["value"] == 7.0
    assert rows[0]["aggregation_mode"] == "last_state"


def test_product_parameter_rejections_happen_before_query_execution(tmp_path: Path) -> None:
    db_path = _aggregate_fixture(tmp_path / "validation.duckdb")
    conn = open_fixture_db(db_path)

    invalid_requests = [
        AggregateRequest(metric_ids=("trimp",), bucket="hour", start_day="2026-05-01", end_day_exclusive="2026-06-01"),
        AggregateRequest(
            metric_ids=("does_not_exist",), bucket="day", start_day="2026-05-01", end_day_exclusive="2026-06-01"
        ),
        AggregateRequest(
            metric_ids=(),
            bundle_id="gear_efficiency",
            bucket="day",
            start_day="2026-05-01",
            end_day_exclusive="2026-06-01",
        ),
        AggregateRequest(
            metric_ids=("trimp",), bucket="day", start_day="2026-05-01", end_day_exclusive="2026-06-01", scope="gear"
        ),
        AggregateRequest(
            metric_ids=("avg_hr",),
            bucket="day",
            start_day="2026-05-01",
            end_day_exclusive="2026-06-01",
            scope="per_sport",
            sport_filter="Unicycle",
        ),
        AggregateRequest(
            metric_ids=("volume_7d",),
            bucket="all_time",
            start_day=None,
            end_day_exclusive="2026-05-22",
            as_of_day="2026-05-21",
            window_days=13,
        ),
    ]
    for request in invalid_requests:
        with pytest.raises(ValueError):
            query_training_aggregates(conn, request)

    for forbidden_field in ("raw_sql", "sql", "table_name", "column_name", "query_plan", "gear_id"):
        with pytest.raises(TypeError):
            AggregateRequest(
                metric_ids=("trimp",),
                bucket="day",
                start_day="2026-05-01",
                end_day_exclusive="2026-06-01",
                **{forbidden_field: "not-supported"},
            )
    conn.close()


def test_validation_accepts_exact_rolling_window_allowlist() -> None:
    for window_days in EXPECTED_WINDOWS:
        validate_aggregate_request(
            AggregateRequest(
                metric_ids=("rolling_median_cc",),
                bucket="all_time",
                start_day=None,
                end_day_exclusive="2026-05-22",
                scope="per_sport",
                as_of_day="2026-05-21",
                window_days=window_days,
            )
        )


def test_per_sport_rolling_aggregates_use_stored_sport_rows(tmp_path: Path) -> None:
    db_path = _aggregate_fixture(tmp_path / "rolling-sport-scope.duckdb")
    conn = open_fixture_db(db_path)
    _insert_sport_rolling_fact(
        conn,
        as_of_day="2026-05-21",
        window_days=90,
        sport_type="Run",
        median_cardiac_cost=44.0,
    )
    _insert_sport_rolling_fact(
        conn,
        as_of_day="2026-05-21",
        window_days=90,
        sport_type="Hike",
        median_cardiac_cost=77.0,
    )

    run_rows = _payloads(
        query_training_aggregates(
            conn,
            AggregateRequest(
                metric_ids=("rolling_median_cc",),
                bucket="all_time",
                start_day=None,
                end_day_exclusive="2026-05-22",
                scope="per_sport",
                sport_filter="Run",
                as_of_day="2026-05-21",
                window_days=90,
            ),
        )
    )
    hike_rows = _payloads(
        query_training_aggregates(
            conn,
            AggregateRequest(
                metric_ids=("rolling_median_cc",),
                bucket="all_time",
                start_day=None,
                end_day_exclusive="2026-05-22",
                scope="per_sport",
                sport_filter="Hike",
                as_of_day="2026-05-21",
                window_days=90,
            ),
        )
    )
    conn.close()

    assert [(row["sport_type"], row["value"]) for row in run_rows] == [("Run", 44.0)]
    assert [(row["sport_type"], row["value"]) for row in hike_rows] == [("Hike", 77.0)]


def _walk_no_forbidden_product_terms(obj) -> None:
    forbidden = {
        "sql",
        "query_plan",
        "table",
        "raw_streams",
        "token",
        "kudos_names",
        "gear",
        "sync_log",
        "recommendation",
        "should",
        "ready",
        "rest",
        "train",
    }
    if isinstance(obj, dict):
        for key, value in obj.items():
            lowered = str(key).lower()
            assert lowered not in forbidden
            _walk_no_forbidden_product_terms(value)
    elif isinstance(obj, list):
        for value in obj:
            _walk_no_forbidden_product_terms(value)
    elif isinstance(obj, str):
        lowered = obj.lower()
        assert not any(term in lowered for term in forbidden)


def test_aggregate_service_returns_factual_envelope_rows_with_freshness(tmp_path: Path) -> None:
    from datetime import datetime

    from mcp_strava.application.aggregate_services import (
        AggregateServiceRequest,
        get_training_aggregates_service,
    )

    db_path = _aggregate_fixture(tmp_path / "service.duckdb")
    conn = open_fixture_db(db_path)
    envelope = get_training_aggregates_service(
        AggregateServiceRequest(
            metric_ids=("distance_km", "avg_trimp_per_day", "fitness", "form_zone", "kudos_count"),
            bucket="all_time",
            start_day="2026-05-05",
            end_day_exclusive="2026-06-01",
            scope="global",
        ),
        now=datetime(2026, 6, 2, 8, 0, 0),
        signal_first_use=False,
        connection=conn,
    )
    payload = dc_to_dict(envelope)
    conn.close()

    assert set(payload) == {"data", "freshness", "completeness", "warnings", "rationale"}
    assert payload["completeness"]["coverage"]["read_model"]["status"] == "current"
    assert payload["data"]["request"]["bucket"] == "all_time"
    assert payload["data"]["request"]["scope"] == "global"
    assert len(payload["data"]["rows"]) == 5
    for row in payload["data"]["rows"]:
        assert D42_ROW_KEYS <= set(row)
        assert isinstance(row["mirror_freshness"], dict)
        assert isinstance(row["read_model_freshness"], dict)
        assert row["read_model_freshness"]["status"] == "current"
    _walk_no_forbidden_product_terms(payload)


def test_aggregate_service_adds_product_bundle_sections_only_for_scenario_bundles(tmp_path: Path) -> None:
    from datetime import datetime

    from mcp_strava.application.aggregate_services import (
        AggregateServiceRequest,
        get_training_aggregates_service,
    )

    db_path = _aggregate_fixture(tmp_path / "scenario-bundle-service.duckdb")
    conn = open_fixture_db(db_path)
    try:
        for bundle_id in ("daily_brief", "weekly_digest", "historical_facts"):
            payload = dc_to_dict(
                get_training_aggregates_service(
                    AggregateServiceRequest(
                        metric_ids=(),
                        bundle_id=bundle_id,
                        bucket="all_time",
                        start_day=None,
                        end_day_exclusive="2026-05-22",
                        scope="both",
                    ),
                    now=datetime(2026, 5, 21, 9, 0, 0),
                    signal_first_use=False,
                    connection=conn,
                )
            )
            assert payload["data"]["rows"]
            assert payload["data"]["bundle"]["bundle_id"] == bundle_id
            assert payload["data"]["bundle"]["sections"]
            completeness = payload["data"]["bundle"]["bundle_completeness"]
            assert set(completeness) >= {
                "requested_metrics",
                "included_metrics",
                "unavailable_metrics",
                "skipped_metrics",
                "scope_incompatible_metrics",
            }
            assert set(completeness["requested_metrics"]) == set(metrics_for_aggregate_bundle(bundle_id))

        plain_payload = dc_to_dict(
            get_training_aggregates_service(
                AggregateServiceRequest(
                    metric_ids=(),
                    bundle_id="sport_efficiency",
                    bucket="all_time",
                    start_day="2026-05-05",
                    end_day_exclusive="2026-06-01",
                    scope="per_sport",
                    sport_filter="Run",
                ),
                now=datetime(2026, 5, 21, 9, 0, 0),
                signal_first_use=False,
                connection=conn,
            )
        )
    finally:
        conn.close()

    assert "rows" in plain_payload["data"]
    assert "bundle" not in plain_payload["data"]


def test_aggregate_service_validates_product_parameters_before_query_execution() -> None:
    from mcp_strava.application.aggregate_services import (
        AggregateServiceRequest,
        get_training_aggregates_service,
    )

    class ExplodingConnection:
        def execute(self, *_args, **_kwargs):  # pragma: no cover - fails if validation regresses
            raise AssertionError("query execution should not happen for invalid product parameters")

    invalid_requests = [
        AggregateServiceRequest(
            metric_ids=("trimp",), bucket="hour", start_day="2026-05-01", end_day_exclusive="2026-06-01"
        ),
        AggregateServiceRequest(
            metric_ids=("missing_metric",), bucket="day", start_day="2026-05-01", end_day_exclusive="2026-06-01"
        ),
        AggregateServiceRequest(
            metric_ids=(),
            bundle_id="gear_efficiency",
            bucket="day",
            start_day="2026-05-01",
            end_day_exclusive="2026-06-01",
        ),
        AggregateServiceRequest(
            metric_ids=("trimp",), bucket="day", start_day="2026-05-01", end_day_exclusive="2026-06-01", scope="gear"
        ),
        AggregateServiceRequest(
            metric_ids=("avg_hr",),
            bucket="day",
            start_day="2026-05-01",
            end_day_exclusive="2026-06-01",
            scope="per_sport",
            sport_filter="Unicycle",
        ),
        AggregateServiceRequest(
            metric_ids=("volume_7d",),
            bucket="all_time",
            start_day=None,
            end_day_exclusive="2026-05-22",
            as_of_day="2026-05-21",
            window_days=13,
        ),
    ]
    for request in invalid_requests:
        with pytest.raises(ValueError):
            get_training_aggregates_service(request, connection=ExplodingConnection())

    with pytest.raises(TypeError):
        AggregateServiceRequest(
            metric_ids=("trimp",),
            bucket="day",
            start_day="2026-05-01",
            end_day_exclusive="2026-06-01",
            gear_id="shoe-1",
        )
