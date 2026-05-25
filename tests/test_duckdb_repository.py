from pathlib import Path

import pytest

from mcp_strava.adapters.duckdb.connection import open_expected_mirror_db, open_fixture_db
from mcp_strava.adapters.duckdb.schema import create_schema


def _create_duckdb_fixture(path: Path) -> None:
    conn = open_fixture_db(path)
    try:
        create_schema(conn)
    finally:
        conn.close()


def _activity_fact_values(activity_id: int = 100) -> dict[str, object]:
    return {
        "activity_id": activity_id,
        "activity_day": "2026-05-21",
        "sport_type": "Run",
        "source_hash": "hash-a",
        "source_revision": 1,
        "metric_version": 1,
        "computed_at": "2026-05-24T12:00:00",
        "completeness_status": "complete",
        "missing_reasons_json": "[]",
        "trimp": 42.5,
        "zone1_seconds": 10,
        "zone2_seconds": 20,
        "zone3_seconds": 30,
        "zone4_seconds": 40,
        "zone5_seconds": 50,
        "hr_recovery_pause_count": 0,
        "hr_recovery_total_rest_sec": 0,
        "hr_recovery_median_rate": None,
        "hr_recovery_best_rate": None,
        "hr_recovery_worst_rate": None,
        "hr_recovery_avg_rate": None,
        "vertical_speed_vmh": None,
        "vertical_speed_total_ascent_m": None,
        "vertical_speed_duration_hours": None,
        "cardiac_cost": 48.2,
        "adjusted_cardiac_cost": 47.8,
        "cardiac_drift_pct": None,
        "cardiac_drift_severity": None,
        "cardiac_drift_significant": 0,
        "cardiac_drift_quality": None,
        "hrr_pct": None,
        "anomaly_count": 0,
        "distance_m": 6000.0,
        "moving_time_s": 1800,
        "elapsed_time_s": 1900,
        "elevation_gain_m": 120.0,
        "heartrate_sample_count": 180,
        "stream_sample_count": 180,
    }


def test_expected_duckdb_open_fails_closed_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Expected DuckDB mirror does not exist"):
        open_expected_mirror_db(tmp_path / "missing.duckdb")


def test_duckdb_repository_has_no_generic_sql_surface() -> None:
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository

    forbidden = {"execute", "executemany", "query", "raw_sql", "run_sql"}
    assert forbidden.isdisjoint(DuckDBRepository.__dict__)


def test_duckdb_repository_refresh_source_dirty_and_status_roundtrip(tmp_path: Path) -> None:
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository

    fixture = tmp_path / "strava.duckdb"
    _create_duckdb_fixture(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        state = repo.get_refresh_state()
        assert state.id == 1
        assert repo.acquire_refresh_lease("owner-a", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")
        assert not repo.acquire_refresh_lease("owner-b", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")
        repo.release_refresh_lease("owner-a")
        assert repo.acquire_refresh_lease("owner-b", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")
        repo.release_refresh_lease("owner-b")

        assert repo.enqueue_refresh_request("first_use_of_day", "2026-05-21")
        assert not repo.enqueue_refresh_request("first_use_of_day", "2026-05-21")
        assert len(repo.pending_refresh_requests()) == 1
        assert repo.mark_refresh_requests_consumed("2026-05-21T12:00:00Z") == 1

        repo.upsert_activity_summary(
            activity_id=100,
            date="2026-05-21T06:00:00Z",
            name="DuckDB Run",
            sport_type="Run",
            distance=6000.0,
            moving_time=1800,
            elapsed_time=1900,
            total_elevation_gain=120.0,
            summary_json='{"id":100,"name":"DuckDB Run","synced_at":"ignored"}',
            synced_at="2026-05-21T07:00:00Z",
        )
        source = repo.source_state_for_activity(100)
        dirty = repo.dirty_activity_rows()

        assert source is not None
        assert source["activity_day"] == "2026-05-21"
        assert source["source_revision"] == 1
        assert len(dirty) == 1
        assert dirty[0]["reason"] == "source_changed"
        assert repo.read_model_status(metric_version=1)["status"] == "stale"


def test_duckdb_repository_fact_upserts_queries_and_dirty_clear(tmp_path: Path) -> None:
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository

    fixture = tmp_path / "strava.duckdb"
    _create_duckdb_fixture(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        repo.upsert_activity_summary(
            activity_id=100,
            date="2026-05-21T06:00:00Z",
            name="DuckDB Run",
            sport_type="Run",
            distance=6000.0,
            moving_time=1800,
            elapsed_time=1900,
            total_elevation_gain=120.0,
            summary_json="{}",
            synced_at="2026-05-21T07:00:00Z",
        )
        dirty = repo.dirty_activity_rows_for_materialization(metric_version=1)
        assert dirty

        repo.upsert_activity_metric_fact(_activity_fact_values())
        repo.upsert_daily_load_fact(
            {
                "day": "2026-05-21",
                "scope": "all",
                "sport_type": "all",
                "metric_version": 1,
                "computed_at": "2026-05-24T12:00:00",
                "completeness_status": "complete",
                "missing_reasons_json": "[]",
                "activity_count": 1,
                "stream_point_count": 180,
                "heartrate_point_count": 180,
                "observed_trimp": 42.5,
                "effective_trimp": 42.5,
                "distance_m": 6000.0,
                "moving_time_s": 1800,
                "elevation_gain_m": 120.0,
                "zone4_seconds": 40,
                "zone5_seconds": 50,
                "high_zone_seconds": 90,
                "anomaly_count": 0,
            }
        )
        repo.upsert_training_model_daily_fact(
            {
                "day": "2026-05-21",
                "scope": "all",
                "sport_type": "all",
                "metric_version": 1,
                "computed_at": "2026-05-24T12:00:00",
                "completeness_status": "complete",
                "missing_reasons_json": "[]",
                "effective_trimp": 42.5,
                "observed_trimp": 42.5,
                "fitness": 10.0,
                "fatigue": 12.0,
                "form": -2.0,
                "form_zone": "normal",
                "acwr_zone": "sweet_spot",
                "acwr": 1.2,
                "load_7d": 12.0,
                "load_28d": None,
                "load_42d": 10.0,
                "input_days": 1,
                "missing_days": 0,
            }
        )
        repo.upsert_rolling_period_fact(
            {
                "as_of_day": "2026-05-21",
                "window_days": 7,
                "scope": "all",
                "sport_type": "all",
                "metric_version": 1,
                "computed_at": "2026-05-24T12:00:00",
                "completeness_status": "complete",
                "missing_reasons_json": "[]",
                "activity_count": 1,
                "active_days": 1,
                "rest_days": 6,
                "observed_trimp": 42.5,
                "effective_trimp": 42.5,
                "distance_m": 6000.0,
                "moving_time_s": 1800,
                "elevation_gain_m": 120.0,
                "high_zone_seconds": 90,
                "anomaly_count": 0,
                "fitness": 10.0,
                "fatigue": 12.0,
                "form": -2.0,
                "form_zone": "normal",
                "acwr_zone": "sweet_spot",
                "acwr": 1.2,
                "median_cardiac_cost": 48.2,
                "median_adjusted_cardiac_cost": 47.8,
                "median_hr_recovery": None,
                "median_cardiac_drift_pct": None,
            }
        )
        repo.record_read_model_refresh_run(
            {
                "started_at": "2026-05-24T12:00:00",
                "finished_at": "2026-05-24T12:00:00",
                "status": "ok",
                "metric_version": 1,
                "trigger_reason": "test",
                "activities_considered": 1,
                "activities_materialized": 1,
                "daily_facts_materialized": 1,
                "model_facts_materialized": 1,
                "rolling_facts_materialized": 1,
                "dirty_rows_claimed": 1,
                "dirty_rows_cleared": 1,
                "attempt_count": 1,
                "last_error": None,
            }
        )
        cleared = repo.clear_dirty_activity_rows(dirty)
        repo.conn.commit()

        assert cleared == 1
        assert repo.fetch_activity_metric_fact(100, metric_version=1)["trimp"] == 42.5
        assert len(repo.fetch_daily_load_facts("2026-05-21", "2026-05-22", scope="all")) == 1
        assert repo.fetch_latest_training_model_day(1, as_of_day="2026-05-21")["fitness"] == 10.0
        assert repo.fetch_rolling_period_facts("2026-05-21", 7, scope="all")["active_days"] == 1
        rolling_by_window = repo.fetch_rolling_period_facts_by_windows("2026-05-21", (7, 14), scope="all")
        assert sorted(rolling_by_window) == [7]
        assert rolling_by_window[7]["active_days"] == 1
        assert repo.read_model_status(metric_version=1)["status"] == "current"
