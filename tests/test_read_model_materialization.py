from pathlib import Path

import pytest

from mcp_strava.adapters.duckdb.read_model_materializer import materialize_read_model
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from tests._fixtures_duckdb import create_empty_fixture_db


def _create_duckdb_read_model_repo(tmp_path: Path) -> tuple[Path, DuckDBRepository]:
    fixture = tmp_path / "read-model.duckdb"
    create_empty_fixture_db(fixture)
    return fixture, DuckDBRepository.from_path(fixture)


def _seed_dirty_activity_with_streams(
    repo: DuckDBRepository,
    *,
    activity_id: int = 920,
    day: str = "2026-05-21",
) -> None:
    repo.upsert_activity_summary(
        activity_id=activity_id,
        date=f"{day}T06:00:00Z",
        name=f"Materialized {activity_id}",
        sport_type="Run",
        distance=6000.0,
        moving_time=1800,
        elapsed_time=1900,
        total_elevation_gain=120.0,
        summary_json=(
            '{"id":%d,"name":"Materialized","sport_type":"Run","start_date_local":"%sT06:00:00Z",'
            '"distance":6000,"moving_time":1800,"elapsed_time":1900,"total_elevation_gain":120,'
            '"average_heartrate":145,"max_heartrate":172,"has_heartrate":true}'
        )
        % (activity_id, day),
        synced_at=f"{day}T07:00:00Z",
    )
    repo.update_activity_detail(activity_id, '{"id": %d, "resource_state": 3}' % activity_id)
    rows = []
    for idx in range(180):
        rows.append(
            {
                "time_offset": idx * 10,
                "heartrate": 138 + (idx % 35),
                "velocity": 3.0 + ((idx % 4) * 0.02),
                "altitude": 500.0 + idx * 0.2,
                "cadence": 84,
                "lat": 43.2 + idx * 0.00001,
                "lng": 76.9 + idx * 0.00001,
                "grade": 1.0,
                "gap_speed": 3.1,
                "gap_distance": idx * 30.0,
                "is_moving": 1,
                "values_json": '{"distance": %.1f}' % (idx * 30.0),
            }
        )
    repo.replace_stream_rows_and_channel_metadata(
        activity_id,
        rows=rows,
        metadata=[
            {
                "channel_key": "heartrate",
                "original_size": len(rows),
                "resolution": "high",
                "series_type": "distance",
                "fetched_at": f"{day}T07:30:00Z",
                "batch_id": "materializer-test",
                "status": "available",
                "error": None,
            }
        ],
    )


def test_duckdb_materializer_writes_fact_tiers_and_clears_dirty_rows(tmp_path: Path) -> None:
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)
    with repo:
        _seed_dirty_activity_with_streams(repo)
        result = materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")

        activity_fact = repo.fetch_activity_metric_fact(920, metric_version=1)
        daily_facts = repo.fetch_daily_load_facts("2026-05-21", "2026-05-22", scope="all")
        model_fact = repo.fetch_latest_training_model_day(1, as_of_day="2026-05-24")
        rolling = repo.fetch_rolling_period_facts("2026-05-24", 7, scope="all")
        run_count = repo.conn.execute(
            "SELECT COUNT(*) FROM read_model_refresh_runs WHERE status = 'ok'"
        ).fetchone()[0]
        dirty = repo.dirty_activity_rows(activity_id=920)

    assert result["status"] == "ok"
    assert activity_fact is not None
    assert activity_fact["source_hash"]
    assert activity_fact["trimp"] > 0
    assert activity_fact["stream_sample_count"] == 180
    assert activity_fact["heartrate_sample_count"] == 180
    assert daily_facts and daily_facts[0]["activity_count"] == 1
    assert model_fact is not None and model_fact["fitness"] is not None
    assert rolling is not None and rolling["active_days"] >= 1
    assert run_count == 1
    assert dirty == []


def test_duckdb_materializer_rolls_back_facts_and_keeps_dirty_rows_on_failure(tmp_path: Path) -> None:
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)

    class FailingDailyFactRepo(DuckDBRepository):
        def upsert_daily_load_fact(self, *args, **kwargs):
            raise RuntimeError("daily fact failed")

    with repo:
        _seed_dirty_activity_with_streams(repo)
        failing_repo = FailingDailyFactRepo(repo.conn)

        with pytest.raises(RuntimeError, match="daily fact failed"):
            materialize_read_model(failing_repo, metric_version=1, now="2026-05-24T12:00:00")

        assert repo.dirty_activity_rows(activity_id=920)
        success_count = repo.conn.execute(
            "SELECT COUNT(*) FROM read_model_refresh_runs WHERE status = 'ok'"
        ).fetchone()[0]
        activity_fact_count = repo.conn.execute("SELECT COUNT(*) FROM activity_metric_facts").fetchone()[0]

    assert success_count == 0
    assert activity_fact_count == 0
