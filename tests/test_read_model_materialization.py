import sqlite3
from pathlib import Path

import pytest

from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from tests.test_sqlite_safety import _create_fixture_db


READ_MODEL_TABLES = {
    "activity_source_state",
    "metric_dirty_activities",
    "activity_metric_facts",
    "daily_load_facts",
    "training_model_daily",
    "rolling_period_facts",
    "read_model_refresh_runs",
}


REQUIRED_COLUMNS = {
    "activity_source_state": {
        "activity_id",
        "activity_day",
        "summary_hash",
        "detail_hash",
        "streams_hash",
        "channels_hash",
        "source_hash",
        "source_revision",
        "changed_at",
    },
    "metric_dirty_activities": {
        "activity_id",
        "activity_day",
        "metric_version",
        "source_revision",
        "reason",
        "queued_at",
        "attempt_count",
        "last_error",
    },
    "activity_metric_facts": {
        "activity_id",
        "activity_day",
        "sport_type",
        "source_hash",
        "source_revision",
        "metric_version",
        "computed_at",
        "completeness_status",
        "missing_reasons_json",
        "trimp",
        "zone1_seconds",
        "zone2_seconds",
        "zone3_seconds",
        "zone4_seconds",
        "zone5_seconds",
        "hr_recovery_median_rate",
        "vertical_speed_vmh",
        "cardiac_cost",
        "adjusted_cardiac_cost",
        "cardiac_drift_pct",
        "hrr_pct",
        "z5_seconds",
        "anomaly_count",
        "distance_m",
        "moving_time_s",
        "elevation_gain_m",
        "heartrate_sample_count",
        "stream_sample_count",
    },
    "daily_load_facts": {
        "day",
        "scope",
        "sport_type",
        "metric_version",
        "computed_at",
        "completeness_status",
        "missing_reasons_json",
        "activity_count",
        "stream_point_count",
        "heartrate_point_count",
        "observed_trimp",
        "effective_trimp",
        "distance_m",
        "moving_time_s",
        "elevation_gain_m",
        "high_zone_seconds",
        "anomaly_count",
    },
    "training_model_daily": {
        "day",
        "scope",
        "sport_type",
        "metric_version",
        "computed_at",
        "completeness_status",
        "missing_reasons_json",
        "effective_trimp",
        "fitness",
        "fatigue",
        "form",
        "atl",
        "ctl",
        "acwr",
    },
    "rolling_period_facts": {
        "as_of_day",
        "window_days",
        "scope",
        "sport_type",
        "metric_version",
        "computed_at",
        "completeness_status",
        "missing_reasons_json",
        "activity_count",
        "active_days",
        "observed_trimp",
        "effective_trimp",
        "distance_m",
        "moving_time_s",
        "elevation_gain_m",
        "fitness",
        "fatigue",
        "form",
    },
    "read_model_refresh_runs": {
        "id",
        "started_at",
        "finished_at",
        "status",
        "metric_version",
        "trigger_reason",
        "activities_considered",
        "activities_materialized",
        "dirty_rows_claimed",
        "dirty_rows_cleared",
        "checkpoint_cursor",
        "attempt_count",
        "last_error",
    },
}


REQUIRED_INDEXES = {
    "idx_activity_source_state_day",
    "idx_metric_dirty_lookup",
    "idx_activity_metric_day_sport_version",
    "idx_activity_metric_activity_version",
    "idx_daily_load_day_scope_sport_version",
    "idx_training_model_day_scope_sport_version",
    "idx_rolling_period_asof_window_scope_sport_version",
    "idx_activities_date_id",
    "idx_activities_sport_date_id",
}


SOURCE_TABLES = (
    "activities",
    "streams",
    "stream_channels",
    "athlete_zones",
    "sync_log",
    "kudos",
    "refresh_state",
    "refresh_requests",
)


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _index_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    return {str(row[0]) for row in rows}


def _row_counts(conn: sqlite3.Connection, tables: tuple[str, ...]) -> dict[str, int]:
    return {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in tables
        if table in _table_names(conn)
    }


def test_read_model_v5_migration_creates_required_tables_columns_and_indexes(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations

    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)

    report = run_migrations(fixture)

    with sqlite3.connect(fixture) as conn:
        assert report.user_version == 5
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert READ_MODEL_TABLES <= _table_names(conn)
        for table, required in REQUIRED_COLUMNS.items():
            assert required <= _column_names(conn, table), table
        assert REQUIRED_INDEXES <= _index_names(conn)


def test_read_model_v5_migration_is_idempotent_and_preserves_source_rows(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations

    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)
    run_migrations(fixture)

    with sqlite3.connect(fixture) as conn:
        before = _row_counts(conn, SOURCE_TABLES)

    first = run_migrations(fixture)
    second = run_migrations(fixture)

    with sqlite3.connect(fixture) as conn:
        after = _row_counts(conn, SOURCE_TABLES)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5

    assert first.user_version == 5
    assert second.user_version == 5
    assert after == before


def test_schema_inventory_reports_read_model_row_counts(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations, run_preflight

    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)
    run_migrations(fixture)

    report = run_preflight(fixture)

    assert report.user_version == 5
    for table in READ_MODEL_TABLES:
        assert report.row_counts[table] == 0


def _migrated_repo(tmp_path: Path) -> tuple[Path, SQLiteRepository]:
    from mcp_strava.adapters.sqlite.migrations import run_migrations

    fixture = tmp_path / "read-model.db"
    _create_fixture_db(fixture)
    run_migrations(fixture)
    return fixture, SQLiteRepository.from_path(fixture)


def _source_state(repo: SQLiteRepository, activity_id: int) -> sqlite3.Row | None:
    return repo.conn.execute(
        "SELECT * FROM activity_source_state WHERE activity_id = ?",
        (activity_id,),
    ).fetchone()


def _dirty_rows(repo: SQLiteRepository, activity_id: int | None = None) -> list[sqlite3.Row]:
    if activity_id is None:
        return repo.conn.execute(
            "SELECT * FROM metric_dirty_activities ORDER BY activity_id, metric_version"
        ).fetchall()
    return repo.conn.execute(
        """
        SELECT * FROM metric_dirty_activities
        WHERE activity_id = ?
        ORDER BY metric_version
        """,
        (activity_id,),
    ).fetchall()


def _upsert_summary(repo: SQLiteRepository, *, synced_at: str, distance: float = 1000.0) -> None:
    repo.upsert_activity_summary(
        activity_id=900,
        date="2026-05-21T06:00:00Z",
        name="Dirty Run",
        sport_type="Run",
        distance=distance,
        moving_time=600,
        elapsed_time=620,
        total_elevation_gain=10,
        summary_json='{"name":"Dirty Run","synced_at":"ignored"}',
        synced_at=synced_at,
    )


def test_summary_write_updates_source_state_and_dirty_queue_atomically(tmp_path: Path) -> None:
    _fixture, repo = _migrated_repo(tmp_path)
    with repo:
        _upsert_summary(repo, synced_at="2026-05-21T07:00:00Z")
        state = _source_state(repo, 900)
        dirty = _dirty_rows(repo, 900)

    assert state is not None
    assert state["activity_day"] == "2026-05-21"
    assert state["source_revision"] == 1
    assert state["source_hash"]
    assert len(dirty) == 1
    assert dirty[0]["activity_day"] == "2026-05-21"
    assert dirty[0]["metric_version"] == 1
    assert dirty[0]["reason"] == "source_changed"
    assert dirty[0]["attempt_count"] == 0
    assert dirty[0]["last_error"] is None


def test_source_hash_ignores_non_semantic_timestamps(tmp_path: Path) -> None:
    _fixture, repo = _migrated_repo(tmp_path)
    with repo:
        _upsert_summary(repo, synced_at="2026-05-21T07:00:00Z")
        first = _source_state(repo, 900)
        assert first is not None

        _upsert_summary(repo, synced_at="2026-05-21T08:30:00Z")
        second = _source_state(repo, 900)
        dirty = _dirty_rows(repo, 900)

    assert second is not None
    assert second["source_hash"] == first["source_hash"]
    assert second["source_revision"] == first["source_revision"]
    assert len(dirty) == 1


def test_semantic_summary_change_increments_revision_and_dedupes_dirty_queue(tmp_path: Path) -> None:
    _fixture, repo = _migrated_repo(tmp_path)
    with repo:
        _upsert_summary(repo, synced_at="2026-05-21T07:00:00Z")
        first = _source_state(repo, 900)
        repo.mark_dirty_activity_attempt_failed(900, "2026-05-21", 1, "boom")

        _upsert_summary(repo, synced_at="2026-05-21T08:00:00Z", distance=1200.0)
        second = _source_state(repo, 900)
        dirty = _dirty_rows(repo, 900)

    assert first is not None and second is not None
    assert second["source_revision"] == first["source_revision"] + 1
    assert len(dirty) == 1
    assert dirty[0]["source_revision"] == second["source_revision"]
    assert dirty[0]["attempt_count"] == 0
    assert dirty[0]["last_error"] is None


def test_detail_stream_replace_and_channel_merge_enqueue_dirty_work(tmp_path: Path) -> None:
    _fixture, repo = _migrated_repo(tmp_path)
    with repo:
        _upsert_summary(repo, synced_at="2026-05-21T07:00:00Z")
        state1 = _source_state(repo, 900)

        repo.update_activity_detail(900, '{"id":900,"description":"detail"}')
        state2 = _source_state(repo, 900)

        repo.replace_stream_rows_and_channel_metadata(
            900,
            rows=[
                {
                    "time_offset": 0,
                    "heartrate": 140,
                    "velocity": 3.1,
                    "altitude": 500.0,
                    "cadence": 84,
                    "lat": 43.2,
                    "lng": 76.9,
                    "grade": 1.0,
                    "gap_speed": 3.2,
                    "gap_distance": 10.0,
                    "is_moving": 1,
                    "values_json": '{"distance": 0.0}',
                }
            ],
            metadata=[
                {
                    "channel_key": "heartrate",
                    "original_size": 1,
                    "resolution": "high",
                    "series_type": "distance",
                    "fetched_at": "2026-05-21T07:30:00Z",
                    "batch_id": "batch-a",
                    "status": "available",
                    "error": None,
                }
            ],
        )
        state3 = _source_state(repo, 900)

        repo.merge_stream_channel_values(
            900,
            rows=[{"time_offset": 0, "values": {"watts": 210}}],
            metadata=[
                {
                    "channel_key": "watts",
                    "original_size": 1,
                    "resolution": "high",
                    "series_type": "distance",
                    "fetched_at": "2026-05-21T07:35:00Z",
                    "batch_id": "batch-b",
                    "status": "available",
                    "error": None,
                }
            ],
            missing_channel_keys=["temp"],
        )
        state4 = _source_state(repo, 900)
        dirty = _dirty_rows(repo, 900)

    assert state1 is not None and state2 is not None and state3 is not None and state4 is not None
    assert state2["source_revision"] == state1["source_revision"] + 1
    assert state3["source_revision"] == state2["source_revision"] + 1
    assert state4["source_revision"] == state3["source_revision"] + 1
    assert len(dirty) == 1
    assert dirty[0]["source_revision"] == state4["source_revision"]


def test_metadata_fetched_at_and_batch_id_do_not_change_source_hash(tmp_path: Path) -> None:
    _fixture, repo = _migrated_repo(tmp_path)
    with repo:
        _upsert_summary(repo, synced_at="2026-05-21T07:00:00Z")
        repo.upsert_stream_channel_metadata(
            activity_id=900,
            channel_key="distance",
            original_size=1,
            resolution="high",
            series_type="distance",
            fetched_at="2026-05-21T07:30:00Z",
            batch_id="batch-a",
            status="available",
            error=None,
        )
        first = _source_state(repo, 900)
        repo.upsert_stream_channel_metadata(
            activity_id=900,
            channel_key="distance",
            original_size=1,
            resolution="high",
            series_type="distance",
            fetched_at="2026-05-21T08:30:00Z",
            batch_id="batch-b",
            status="available",
            error=None,
        )
        second = _source_state(repo, 900)

    assert first is not None and second is not None
    assert second["source_hash"] == first["source_hash"]
    assert second["source_revision"] == first["source_revision"]


def test_metric_version_bump_queues_all_source_state_activities(tmp_path: Path) -> None:
    _fixture, repo = _migrated_repo(tmp_path)
    with repo:
        _upsert_summary(repo, synced_at="2026-05-21T07:00:00Z")
        repo.upsert_activity_summary(
            activity_id=901,
            date="2026-05-22T06:00:00Z",
            name="Second Dirty Run",
            sport_type="Run",
            distance=1000,
            moving_time=600,
            elapsed_time=620,
            total_elevation_gain=10,
            summary_json="{}",
            synced_at="2026-05-22T07:00:00Z",
        )
        queued = repo.enqueue_metric_version_recompute(2, "metric_version_changed", "2026-05-23T00:00:00Z")
        rows = _dirty_rows(repo)

    assert queued == 2
    assert {(row["activity_id"], row["metric_version"]) for row in rows} >= {
        (900, 2),
        (901, 2),
    }


def test_failed_dirty_enqueue_rolls_back_source_mutation_and_state(tmp_path: Path) -> None:
    _fixture, repo = _migrated_repo(tmp_path)

    class FailingDirtyRepo(SQLiteRepository):
        def enqueue_metric_dirty_activity(self, *args, **kwargs):
            raise RuntimeError("dirty enqueue failed")

    with repo:
        failing = FailingDirtyRepo(repo.conn)
        with pytest.raises(RuntimeError, match="dirty enqueue failed"):
            _upsert_summary(failing, synced_at="2026-05-21T07:00:00Z")

        activity = repo.activity_by_id(900)
        state = _source_state(repo, 900)
        dirty = _dirty_rows(repo, 900)

    assert activity is None
    assert state is None
    assert dirty == []


def _seed_dirty_activity_with_streams(repo: SQLiteRepository, *, activity_id: int = 920, day: str = "2026-05-21") -> None:
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


def test_materializer_writes_all_fact_tiers_and_clears_dirty_rows(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.read_model_materializer import materialize_read_model

    _fixture, repo = _migrated_repo(tmp_path)
    with repo:
        _seed_dirty_activity_with_streams(repo)
        result = materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")

        activity_fact = repo.conn.execute("SELECT * FROM activity_metric_facts WHERE activity_id = 920").fetchone()
        daily_fact = repo.conn.execute("SELECT * FROM daily_load_facts WHERE day = '2026-05-21'").fetchone()
        model_fact = repo.conn.execute("SELECT * FROM training_model_daily WHERE day = '2026-05-24'").fetchone()
        rolling_windows = repo.conn.execute(
            "SELECT window_days FROM rolling_period_facts WHERE as_of_day = '2026-05-24' ORDER BY window_days"
        ).fetchall()
        run = repo.conn.execute("SELECT * FROM read_model_refresh_runs ORDER BY id DESC LIMIT 1").fetchone()
        dirty = _dirty_rows(repo, 920)

    assert result["status"] == "ok"
    assert activity_fact is not None
    assert activity_fact["source_hash"]
    assert activity_fact["source_revision"] >= 1
    assert activity_fact["metric_version"] == 1
    assert activity_fact["computed_at"] == "2026-05-24T12:00:00"
    assert activity_fact["completeness_status"] == "complete"
    assert activity_fact["missing_reasons_json"] == "[]"
    assert activity_fact["trimp"] > 0
    assert activity_fact["stream_sample_count"] == 180
    assert activity_fact["heartrate_sample_count"] == 180
    assert activity_fact["distance_m"] == 6000.0
    assert activity_fact["moving_time_s"] == 1800
    assert daily_fact is not None
    assert daily_fact["activity_count"] == 1
    assert daily_fact["observed_trimp"] > 0
    assert model_fact is not None
    assert model_fact["fitness"] is not None
    assert [row["window_days"] for row in rolling_windows] == [7, 14, 28, 90]
    assert run is not None and run["status"] == "ok"
    assert dirty == []


def test_materializer_is_idempotent_for_same_dirty_set(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.read_model_materializer import materialize_read_model

    _fixture, repo = _migrated_repo(tmp_path)
    with repo:
        _seed_dirty_activity_with_streams(repo)
        materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")
        repo.enqueue_metric_version_recompute(1, "retry_same_version", "2026-05-24T12:01:00")
        materialize_read_model(repo, metric_version=1, now="2026-05-24T12:02:00")

        activity_count = repo.conn.execute("SELECT COUNT(*) FROM activity_metric_facts").fetchone()[0]
        daily_count = repo.conn.execute("SELECT COUNT(*) FROM daily_load_facts").fetchone()[0]
        model_count = repo.conn.execute("SELECT COUNT(*) FROM training_model_daily").fetchone()[0]
        rolling_count = repo.conn.execute("SELECT COUNT(*) FROM rolling_period_facts").fetchone()[0]

    assert activity_count == 1
    assert daily_count == 4
    assert model_count == 4
    assert rolling_count == 4


def test_materializer_writes_new_metric_versions_without_deleting_old_facts(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.read_model_materializer import materialize_read_model

    _fixture, repo = _migrated_repo(tmp_path)
    with repo:
        _seed_dirty_activity_with_streams(repo)
        materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")
        repo.enqueue_metric_version_recompute(2, "metric_version_changed", "2026-05-24T12:05:00")
        materialize_read_model(repo, metric_version=2, now="2026-05-24T12:06:00")

        versions = repo.conn.execute(
            "SELECT metric_version FROM activity_metric_facts WHERE activity_id = 920 ORDER BY metric_version"
        ).fetchall()

    assert [row["metric_version"] for row in versions] == [1, 2]


def test_materializer_failure_keeps_dirty_rows_and_does_not_mark_success(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.read_model_materializer import materialize_read_model

    _fixture, repo = _migrated_repo(tmp_path)

    class FailingDailyFactRepo(SQLiteRepository):
        def upsert_daily_load_fact(self, *args, **kwargs):
            raise RuntimeError("daily fact failed")

    with repo:
        _seed_dirty_activity_with_streams(repo)
        failing_repo = FailingDailyFactRepo(repo.conn)
        assert failing_repo.acquire_refresh_lease("materializer-test", "2026-05-24T12:15:00", "2026-05-24T12:00:00")

        def renew_lease() -> None:
            assert failing_repo.renew_refresh_lease("materializer-test", "2026-05-24T12:20:00")

        with pytest.raises(RuntimeError, match="daily fact failed"):
            materialize_read_model(
                failing_repo,
                metric_version=1,
                now="2026-05-24T12:00:00",
                renew_lease=renew_lease,
            )

        assert _dirty_rows(repo, 920)
        success_count = repo.conn.execute(
            "SELECT COUNT(*) FROM read_model_refresh_runs WHERE status = 'ok'"
        ).fetchone()[0]
        activity_fact_count = repo.conn.execute("SELECT COUNT(*) FROM activity_metric_facts").fetchone()[0]

    assert success_count == 0
    assert activity_fact_count == 0
