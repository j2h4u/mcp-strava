import sqlite3
from pathlib import Path

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
