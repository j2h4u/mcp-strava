from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


CANONICAL_DUCKDB_RUNTIME_PATH = "/runtime/data/strava.duckdb"

D08_TABLES = (
    "activities",
    "streams",
    "stream_channels",
    "athlete_zones",
    "sync_log",
    "kudos",
    "refresh_state",
    "refresh_requests",
    "activity_source_state",
    "metric_dirty_activities",
    "activity_metric_facts",
    "daily_load_facts",
    "training_model_daily",
    "rolling_period_facts",
    "read_model_refresh_runs",
    "schema_migration_log",
)


def _create_v7_fixture(
    db_path: Path,
    *,
    active_lease: bool = False,
    invalid_activity_day: bool = False,
) -> None:
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
            activity_id INTEGER NOT NULL,
            time_offset INTEGER NOT NULL,
            heartrate INTEGER, velocity REAL, altitude REAL,
            cadence INTEGER, lat REAL, lng REAL, grade REAL,
            gap_speed REAL, gap_distance REAL, is_moving INTEGER,
            values_json TEXT,
            PRIMARY KEY (activity_id, time_offset)
        );
        CREATE TABLE stream_channels (
            activity_id INTEGER NOT NULL,
            channel_key TEXT NOT NULL,
            original_size INTEGER,
            resolution TEXT,
            series_type TEXT,
            fetched_at TEXT NOT NULL,
            batch_id TEXT,
            status TEXT NOT NULL,
            error TEXT,
            PRIMARY KEY (activity_id, channel_key)
        );
        CREATE TABLE athlete_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT,
            zones_json TEXT
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
        CREATE TABLE refresh_state (
            id INTEGER PRIMARY KEY,
            last_success_at TEXT,
            last_attempt_at TEXT,
            last_status TEXT,
            last_error_code TEXT,
            lease_owner TEXT,
            lease_expires_at TEXT,
            backoff_until TEXT,
            checkpoint_stage TEXT,
            checkpoint_cursor TEXT
        );
        CREATE TABLE refresh_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reason TEXT NOT NULL,
            requested_for_day TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            consumed_at TEXT
        );
        CREATE TABLE activity_source_state (
            activity_id INTEGER PRIMARY KEY,
            activity_day TEXT NOT NULL,
            summary_hash TEXT NOT NULL,
            detail_hash TEXT NOT NULL,
            streams_hash TEXT NOT NULL,
            channels_hash TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            source_revision INTEGER NOT NULL,
            changed_at TEXT NOT NULL
        );
        CREATE TABLE metric_dirty_activities (
            activity_id INTEGER NOT NULL,
            activity_day TEXT NOT NULL,
            metric_version INTEGER NOT NULL,
            source_revision INTEGER NOT NULL,
            reason TEXT NOT NULL,
            queued_at TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            PRIMARY KEY (activity_id, metric_version)
        );
        CREATE TABLE activity_metric_facts (
            activity_id INTEGER NOT NULL,
            activity_day TEXT NOT NULL,
            sport_type TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            source_revision INTEGER NOT NULL,
            metric_version INTEGER NOT NULL,
            computed_at TEXT NOT NULL,
            completeness_status TEXT NOT NULL,
            missing_reasons_json TEXT NOT NULL DEFAULT '[]',
            trimp REAL,
            zone1_seconds INTEGER NOT NULL DEFAULT 0,
            zone2_seconds INTEGER NOT NULL DEFAULT 0,
            zone3_seconds INTEGER NOT NULL DEFAULT 0,
            zone4_seconds INTEGER NOT NULL DEFAULT 0,
            zone5_seconds INTEGER NOT NULL DEFAULT 0,
            hr_recovery_pause_count INTEGER NOT NULL DEFAULT 0,
            hr_recovery_total_rest_sec INTEGER NOT NULL DEFAULT 0,
            hr_recovery_median_rate REAL,
            hr_recovery_best_rate REAL,
            hr_recovery_worst_rate REAL,
            hr_recovery_avg_rate REAL,
            vertical_speed_vmh INTEGER,
            vertical_speed_total_ascent_m REAL,
            vertical_speed_duration_hours REAL,
            cardiac_cost REAL,
            adjusted_cardiac_cost REAL,
            cardiac_drift_pct REAL,
            cardiac_drift_severity TEXT,
            cardiac_drift_significant INTEGER NOT NULL DEFAULT 0,
            cardiac_drift_quality TEXT,
            hrr_pct REAL,
            anomaly_count INTEGER NOT NULL DEFAULT 0,
            distance_m REAL,
            moving_time_s INTEGER,
            elapsed_time_s INTEGER,
            elevation_gain_m REAL,
            heartrate_sample_count INTEGER NOT NULL DEFAULT 0,
            stream_sample_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (activity_id, metric_version)
        );
        CREATE TABLE daily_load_facts (
            day TEXT NOT NULL,
            scope TEXT NOT NULL,
            sport_type TEXT NOT NULL,
            metric_version INTEGER NOT NULL,
            computed_at TEXT NOT NULL,
            completeness_status TEXT NOT NULL,
            missing_reasons_json TEXT NOT NULL DEFAULT '[]',
            activity_count INTEGER NOT NULL DEFAULT 0,
            stream_point_count INTEGER NOT NULL DEFAULT 0,
            heartrate_point_count INTEGER NOT NULL DEFAULT 0,
            observed_trimp REAL,
            effective_trimp REAL NOT NULL DEFAULT 0.0,
            distance_m REAL NOT NULL DEFAULT 0.0,
            moving_time_s INTEGER NOT NULL DEFAULT 0,
            elevation_gain_m REAL NOT NULL DEFAULT 0.0,
            zone4_seconds INTEGER NOT NULL DEFAULT 0,
            zone5_seconds INTEGER NOT NULL DEFAULT 0,
            high_zone_seconds INTEGER NOT NULL DEFAULT 0,
            anomaly_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, scope, sport_type, metric_version)
        );
        CREATE TABLE training_model_daily (
            day TEXT NOT NULL,
            scope TEXT NOT NULL,
            sport_type TEXT NOT NULL,
            metric_version INTEGER NOT NULL,
            computed_at TEXT NOT NULL,
            completeness_status TEXT NOT NULL,
            missing_reasons_json TEXT NOT NULL DEFAULT '[]',
            effective_trimp REAL NOT NULL DEFAULT 0.0,
            observed_trimp REAL,
            fitness REAL,
            fatigue REAL,
            form REAL,
            form_zone TEXT,
            acwr_zone TEXT,
            acwr REAL,
            load_7d REAL,
            load_28d REAL,
            load_42d REAL,
            input_days INTEGER NOT NULL DEFAULT 0,
            missing_days INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, scope, sport_type, metric_version)
        );
        CREATE TABLE rolling_period_facts (
            as_of_day TEXT NOT NULL,
            window_days INTEGER NOT NULL,
            scope TEXT NOT NULL,
            sport_type TEXT NOT NULL,
            metric_version INTEGER NOT NULL,
            computed_at TEXT NOT NULL,
            completeness_status TEXT NOT NULL,
            missing_reasons_json TEXT NOT NULL DEFAULT '[]',
            activity_count INTEGER NOT NULL DEFAULT 0,
            active_days INTEGER NOT NULL DEFAULT 0,
            rest_days INTEGER NOT NULL DEFAULT 0,
            observed_trimp REAL,
            effective_trimp REAL NOT NULL DEFAULT 0.0,
            distance_m REAL NOT NULL DEFAULT 0.0,
            moving_time_s INTEGER NOT NULL DEFAULT 0,
            elevation_gain_m REAL NOT NULL DEFAULT 0.0,
            high_zone_seconds INTEGER NOT NULL DEFAULT 0,
            anomaly_count INTEGER NOT NULL DEFAULT 0,
            fitness REAL,
            fatigue REAL,
            form REAL,
            form_zone TEXT,
            acwr_zone TEXT,
            acwr REAL,
            median_cardiac_cost REAL,
            median_adjusted_cardiac_cost REAL,
            median_hr_recovery REAL,
            median_cardiac_drift_pct REAL,
            PRIMARY KEY (as_of_day, window_days, scope, sport_type, metric_version)
        );
        CREATE TABLE read_model_refresh_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            metric_version INTEGER NOT NULL,
            trigger_reason TEXT,
            lease_owner TEXT,
            activities_considered INTEGER NOT NULL DEFAULT 0,
            activities_materialized INTEGER NOT NULL DEFAULT 0,
            daily_facts_materialized INTEGER NOT NULL DEFAULT 0,
            model_facts_materialized INTEGER NOT NULL DEFAULT 0,
            rolling_facts_materialized INTEGER NOT NULL DEFAULT 0,
            dirty_rows_claimed INTEGER NOT NULL DEFAULT 0,
            dirty_rows_cleared INTEGER NOT NULL DEFAULT 0,
            checkpoint_cursor TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        );
        CREATE TABLE schema_migration_log (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            checksum TEXT NOT NULL
        );
        PRAGMA user_version=7;
        """
    )
    source_day = "not-a-day" if invalid_activity_day else "2026-05-20"
    conn.execute(
        """
        INSERT INTO activities (
            id, date, name, sport_type, distance, moving_time, elapsed_time,
            total_elevation_gain, summary_json, detail_json, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            701,
            "2026-05-20T07:00:00Z",
            "DuckDB Fixture Run",
            "Run",
            10000.0,
            3600,
            3660,
            140.0,
            json.dumps({"id": 701, "kudos_count": 2}),
            json.dumps({"private_note": "not emitted by migration report"}),
            "2026-05-20T08:00:00Z",
        ),
    )
    conn.executemany(
        """
        INSERT INTO streams (
            activity_id, time_offset, heartrate, velocity, altitude, cadence,
            lat, lng, grade, gap_speed, gap_distance, is_moving, values_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (701, 0, 140, 2.9, 500.0, 82, 43.2, 76.9, 0.1, 3.0, 0.0, 1, json.dumps({"watts": 210})),
            (701, 1, 142, 3.0, 501.0, 83, 43.2001, 76.9001, 0.2, 3.1, 6.0, 1, json.dumps({"watts": 220})),
        ],
    )
    conn.executemany(
        """
        INSERT INTO stream_channels (
            activity_id, channel_key, original_size, resolution, series_type,
            fetched_at, batch_id, status, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (701, "heartrate", 2, "high", "time", "2026-05-20T08:00:00Z", "batch-1", "available", None),
            (701, "watts", None, None, None, "2026-05-20T08:00:00Z", "batch-1", "unavailable", None),
        ],
    )
    conn.execute("INSERT INTO athlete_zones (fetched_at, zones_json) VALUES (?, ?)", ("2026-05-20T00:00:00Z", "{}"))
    conn.execute(
        """
        INSERT INTO sync_log (
            timestamp, status, activities_seen, activities_new, streams_fetched,
            details_fetched, api_calls, error, kudos_fetched
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-05-20T08:00:00Z", "ok", 1, 1, 1, 1, 3, None, 2),
    )
    conn.executemany(
        "INSERT INTO kudos (activity_id, firstname, lastname, fetched_at) VALUES (?, ?, ?, ?)",
        [
            (701, "Ada", "Lovelace", "2026-05-20T08:00:00Z"),
            (701, "Grace", "Hopper", "2026-05-20T08:00:00Z"),
        ],
    )
    conn.execute(
        """
        INSERT INTO refresh_state (
            id, last_success_at, last_attempt_at, last_status, last_error_code,
            lease_owner, lease_expires_at, backoff_until, checkpoint_stage, checkpoint_cursor
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-20T08:00:00Z",
            "2026-05-20T08:00:00Z",
            "ok",
            None,
            "refresh-worker" if active_lease else None,
            "2026-05-20T08:30:00Z" if active_lease else None,
            None,
            None,
            None,
        ),
    )
    conn.execute(
        """
        INSERT INTO refresh_requests (reason, requested_for_day, requested_at, consumed_at)
        VALUES (?, ?, ?, ?)
        """,
        ("manual_test", "2026-05-20", "2026-05-20T09:00:00Z", None),
    )
    conn.execute(
        """
        INSERT INTO activity_source_state (
            activity_id, activity_day, summary_hash, detail_hash, streams_hash,
            channels_hash, source_hash, source_revision, changed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (701, source_day, "summary", "detail", "streams", "channels", "source", 1, "2026-05-20T08:00:00Z"),
    )
    conn.execute(
        """
        INSERT INTO metric_dirty_activities (
            activity_id, activity_day, metric_version, source_revision,
            reason, queued_at, attempt_count, last_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (701, source_day, 1, 1, "fixture", "2026-05-20T08:01:00Z", 0, None),
    )
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
            701, ?, 'Run', 'source', 1, 1, '2026-05-20T08:05:00Z',
            'complete', '[]', 120.5, 10, 20, 30, 40, 50,
            1, 60, 18.0, 25.0, 12.0, 17.5, 420, 140.0, 0.33,
            41.0, 39.5, 2.1, 'stable', 0, 'good', 66.0, 0,
            10000.0, 3600, 3660, 140.0, 2, 2
        )
        """,
        (source_day,),
    )
    conn.execute(
        """
        INSERT INTO daily_load_facts (
            day, scope, sport_type, metric_version, computed_at,
            completeness_status, missing_reasons_json, activity_count,
            stream_point_count, heartrate_point_count, observed_trimp,
            effective_trimp, distance_m, moving_time_s, elevation_gain_m,
            zone4_seconds, zone5_seconds, high_zone_seconds, anomaly_count
        ) VALUES (?, 'all', 'all', 1, '2026-05-20T08:10:00Z', 'complete', '[]', 1, 2, 2, 120.5, 120.5, 10000.0, 3600, 140.0, 40, 50, 90, 0)
        """,
        (source_day,),
    )
    conn.execute(
        """
        INSERT INTO training_model_daily (
            day, scope, sport_type, metric_version, computed_at,
            completeness_status, missing_reasons_json, effective_trimp,
            observed_trimp, fitness, fatigue, form, form_zone, acwr_zone,
            acwr, load_7d, load_28d, load_42d, input_days, missing_days
        ) VALUES (?, 'all', 'all', 1, '2026-05-20T08:15:00Z', 'complete', '[]', 120.5, 120.5, 42.0, 38.0, 4.0, 'normal', 'sweet_spot', 0.9, 120.5, 300.0, 500.0, 1, 0)
        """,
        (source_day,),
    )
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
        ) VALUES (?, 7, 'all', 'all', 1, '2026-05-20T08:20:00Z', 'complete', '[]', 1, 1, 6, 120.5, 120.5, 10000.0, 3600, 140.0, 90, 0, 42.0, 38.0, 4.0, 'normal', 'sweet_spot', 0.9, 41.0, 39.5, 18.0, 2.1)
        """,
        (source_day,),
    )
    conn.execute(
        """
        INSERT INTO read_model_refresh_runs (
            started_at, finished_at, status, metric_version, trigger_reason,
            lease_owner, activities_considered, activities_materialized,
            daily_facts_materialized, model_facts_materialized,
            rolling_facts_materialized, dirty_rows_claimed, dirty_rows_cleared,
            checkpoint_cursor, attempt_count, last_error
        ) VALUES (
            '2026-05-20T08:00:00Z', '2026-05-20T08:20:00Z', 'ok', 1,
            'fixture', 'pytest', 1, 1, 1, 1, 1, 1, 1, NULL, 1, NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO schema_migration_log (version, name, applied_at, checksum)
        VALUES (7, 'fixture_v7', '2026-05-20T08:00:00Z', 'checksum')
        """
    )
    conn.commit()
    conn.close()


def _sqlite_counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in D08_TABLES
        }


def _duckdb_counts(path: Path) -> dict[str, int]:
    import duckdb

    with duckdb.connect(database=str(path), read_only=True) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in D08_TABLES
        }


def _duckdb_column_types(path: Path, table: str) -> dict[str, str]:
    import duckdb

    with duckdb.connect(database=str(path), read_only=True) as conn:
        rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    return {str(row[1]): str(row[2]).upper() for row in rows}


def test_duckdb_cutover_migrates_v7_fixture_with_parity_dates_and_rollback(tmp_path: Path) -> None:
    from mcp_strava.adapters.duckdb.migrations import run_duckdb_cutover

    source = tmp_path / "source.db"
    target = tmp_path / "strava.duckdb"
    backups = tmp_path / "backups"
    _create_v7_fixture(source)
    source_counts = _sqlite_counts(source)

    report = run_duckdb_cutover(
        source_sqlite_path=source,
        target_duckdb_path=target,
        backup_dir=backups,
        now="2026-05-25T12:00:00Z",
        owner="pytest",
    )

    assert target.exists()
    assert report.duckdb_path == target
    assert Path(report.backup_path).name.startswith("strava-pre-phase-8-")
    assert report.parity_ok is True
    assert report.cast_failures == []
    assert report.source_counts == source_counts
    assert report.target_counts == source_counts
    assert _duckdb_counts(target) == source_counts
    assert report.stream_point_count == 2
    assert report.stream_channel_status_counts == {"available": 1, "unavailable": 1}
    assert report.kudos_count == 2
    assert report.refresh_state["last_status"] == "ok"
    assert report.refresh_state["lease_owner"] is None
    assert report.metric_versions == [1]
    assert report.min_max_dates["activities"] == {"min": "2026-05-20", "max": "2026-05-20"}
    assert "strava-pre-phase-8" in report.rollback["sqlite_backup_path"]
    assert "full Strava resync" not in json.dumps(report.rollback).lower()

    assert _duckdb_column_types(target, "activities")["activity_day"] == "DATE"
    assert _duckdb_column_types(target, "activity_source_state")["activity_day"] == "DATE"
    assert _duckdb_column_types(target, "activity_metric_facts")["activity_day"] == "DATE"
    assert _duckdb_column_types(target, "daily_load_facts")["day"] == "DATE"
    assert _duckdb_column_types(target, "training_model_daily")["day"] == "DATE"
    assert _duckdb_column_types(target, "rolling_period_facts")["as_of_day"] == "DATE"


def test_active_refresh_lease_blocks_cutover_before_final_duckdb_path(tmp_path: Path) -> None:
    from mcp_strava.adapters.duckdb.migrations import DuckDBMigrationError, run_duckdb_cutover

    source = tmp_path / "source.db"
    target = tmp_path / "strava.duckdb"
    _create_v7_fixture(source, active_lease=True)

    with pytest.raises(DuckDBMigrationError, match="active refresh lease") as exc_info:
        run_duckdb_cutover(
            source_sqlite_path=source,
            target_duckdb_path=target,
            backup_dir=tmp_path / "backups",
            now="2026-05-25T12:00:00Z",
            owner="pytest",
        )

    assert not target.exists()
    assert exc_info.value.report is not None
    assert exc_info.value.report.parity_ok is False
    assert exc_info.value.report.refresh_state["lease_owner"] == "refresh-worker"


def test_invalid_required_date_cast_reports_table_column_and_count(tmp_path: Path) -> None:
    from mcp_strava.adapters.duckdb.migrations import DuckDBMigrationError, run_duckdb_cutover

    source = tmp_path / "source.db"
    target = tmp_path / "strava.duckdb"
    _create_v7_fixture(source, invalid_activity_day=True)

    with pytest.raises(DuckDBMigrationError, match="cast failure") as exc_info:
        run_duckdb_cutover(
            source_sqlite_path=source,
            target_duckdb_path=target,
            backup_dir=tmp_path / "backups",
            now="2026-05-25T12:00:00Z",
            owner="pytest",
        )

    report = exc_info.value.report
    assert report is not None
    assert report.parity_ok is False
    assert not target.exists()
    assert {
        "table": "activity_metric_facts",
        "column": "activity_day",
        "failing_value_count": 1,
    } in report.cast_failures


def test_pre_phase_8_backup_is_pinned_outside_ordinary_retention(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.backup import create_pre_phase_8_backup, enforce_backup_retention

    source = tmp_path / "source.db"
    _create_v7_fixture(source)
    backups = tmp_path / "backups"
    pinned = create_pre_phase_8_backup(source, backups_dir=backups)

    for idx in range(8):
        (backups / f"strava-20260520T12000{idx}Z.db").write_bytes(b"x")

    kept = enforce_backup_retention(backups, keep=5)

    assert pinned.exists()
    assert pinned in kept
    assert pinned.name.startswith("strava-pre-phase-8-")
    regular = [path for path in kept if "pre-phase-" not in path.name]
    assert len(regular) == 5


def test_migration_tests_use_temp_paths_only(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    _create_v7_fixture(source)
    resolved = str(source.resolve())

    assert "data/strava.db" not in resolved
    assert "/opt/docker/mcp-strava" not in resolved
    assert CANONICAL_DUCKDB_RUNTIME_PATH not in resolved


def test_canonical_live_duckdb_runtime_path_is_documented() -> None:
    from mcp_strava.adapters.duckdb.migrations import CANONICAL_DUCKDB_RUNTIME_PATH as implemented_path

    assert implemented_path == CANONICAL_DUCKDB_RUNTIME_PATH
