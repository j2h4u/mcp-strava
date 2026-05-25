"""One-shot SQLite to DuckDB cutover migration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3

import duckdb

from mcp_strava.adapters.duckdb.schema import DUCKDB_TABLES, create_schema
from mcp_strava.adapters.sqlite.backup import create_pre_phase_8_backup


CANONICAL_DUCKDB_RUNTIME_PATH = "/runtime/data/strava.duckdb"


@dataclass(frozen=True)
class DuckDBCutoverReport:
    backup_path: Path | None
    duckdb_path: Path
    parity_ok: bool
    source_counts: dict[str, int] = field(default_factory=dict)
    target_counts: dict[str, int] = field(default_factory=dict)
    cast_failures: list[dict[str, object]] = field(default_factory=list)
    stream_point_count: int = 0
    stream_channel_status_counts: dict[str, int] = field(default_factory=dict)
    kudos_count: int = 0
    refresh_state: dict[str, object] = field(default_factory=dict)
    metric_versions: list[int] = field(default_factory=list)
    min_max_dates: dict[str, dict[str, str | None]] = field(default_factory=dict)
    rollback: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "backup_path": str(self.backup_path) if self.backup_path is not None else None,
            "duckdb_path": str(self.duckdb_path),
            "parity_ok": self.parity_ok,
            "source_counts": self.source_counts,
            "target_counts": self.target_counts,
            "cast_failures": self.cast_failures,
            "stream_point_count": self.stream_point_count,
            "stream_channel_status_counts": self.stream_channel_status_counts,
            "kudos_count": self.kudos_count,
            "refresh_state": self.refresh_state,
            "metric_versions": self.metric_versions,
            "min_max_dates": self.min_max_dates,
            "rollback": self.rollback,
        }


class DuckDBMigrationError(RuntimeError):
    def __init__(self, message: str, report: DuckDBCutoverReport | None = None) -> None:
        super().__init__(message)
        self.report = report


def _quote_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _read_refresh_state(sqlite_path: Path) -> dict[str, object]:
    with sqlite3.connect(sqlite_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM refresh_state WHERE id = 1").fetchone()
        return dict(row) if row is not None else {}


def _sqlite_counts(sqlite_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with sqlite3.connect(sqlite_path) as conn:
        for table in DUCKDB_TABLES:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            if row is not None:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return counts


def _ensure_sqlite_extension(conn) -> None:
    try:
        conn.execute("LOAD sqlite")
    except Exception as exc:  # pragma: no cover - depends on local DuckDB packaging
        raise DuckDBMigrationError(
            "DuckDB sqlite extension is unavailable; install/load sqlite support before migration"
        ) from exc
    rows = conn.execute(
        """
        SELECT extension_name, loaded, installed, aliases
        FROM duckdb_extensions()
        WHERE extension_name = 'sqlite_scanner'
           OR list_contains(aliases, 'sqlite')
        """
    ).fetchall()
    if not rows or not any(bool(row[1]) for row in rows):
        raise DuckDBMigrationError("DuckDB sqlite extension did not report as loaded")


def _attach_sqlite(conn, sqlite_path: Path) -> None:
    conn.execute(f"ATTACH {_quote_literal(sqlite_path)} AS sqlite_src (TYPE sqlite)")


def _detach_sqlite(conn) -> None:
    try:
        conn.execute("DETACH sqlite_src")
    except Exception:
        pass


def _date_cast_failures(conn) -> list[dict[str, object]]:
    checks = (
        ("activities", "date", "SUBSTR(date, 1, 10)"),
        ("activity_source_state", "activity_day", "activity_day"),
        ("metric_dirty_activities", "activity_day", "activity_day"),
        ("activity_metric_facts", "activity_day", "activity_day"),
        ("daily_load_facts", "day", "day"),
        ("training_model_daily", "day", "day"),
        ("rolling_period_facts", "as_of_day", "as_of_day"),
    )
    failures: list[dict[str, object]] = []
    for table, column, expression in checks:
        count = int(
            conn.execute(
                f"""
                SELECT COUNT(*)
                FROM sqlite_src.{table}
                WHERE {column} IS NOT NULL
                  AND TRY_CAST({expression} AS DATE) IS NULL
                """
            ).fetchone()[0]
        )
        if count:
            failures.append({"table": table, "column": column, "failing_value_count": count})
    return failures


def _insert_all_tables(conn) -> None:
    conn.execute(
        """
        INSERT INTO activities (
            id, activity_day, date, name, sport_type, distance, moving_time, elapsed_time,
            total_elevation_gain, summary_json, detail_json, synced_at
        )
        SELECT
            id, TRY_CAST(SUBSTR(date, 1, 10) AS DATE), date, name, sport_type,
            distance, moving_time, elapsed_time, total_elevation_gain,
            summary_json, detail_json, synced_at
        FROM sqlite_src.activities
        """
    )
    conn.execute(
        """
        INSERT INTO streams
        SELECT
            activity_id, time_offset, heartrate, velocity, altitude, cadence,
            lat, lng, grade, gap_speed, gap_distance, is_moving, values_json
        FROM sqlite_src.streams
        """
    )
    conn.execute(
        """
        INSERT INTO stream_channels
        SELECT activity_id, channel_key, original_size, resolution, series_type,
               fetched_at, batch_id, status, error
        FROM sqlite_src.stream_channels
        """
    )
    conn.execute("INSERT INTO athlete_zones SELECT id, fetched_at, zones_json FROM sqlite_src.athlete_zones")
    conn.execute(
        """
        INSERT INTO sync_log
        SELECT id, timestamp, status, activities_seen, activities_new, streams_fetched,
               details_fetched, api_calls, error, kudos_fetched
        FROM sqlite_src.sync_log
        """
    )
    conn.execute("INSERT INTO kudos SELECT activity_id, firstname, lastname, fetched_at FROM sqlite_src.kudos")
    conn.execute(
        """
        INSERT INTO refresh_state
        SELECT id, last_success_at, last_attempt_at, last_status, last_error_code,
               lease_owner, lease_expires_at, backoff_until, checkpoint_stage, checkpoint_cursor
        FROM sqlite_src.refresh_state
        """
    )
    conn.execute(
        """
        INSERT INTO refresh_requests
        SELECT id, reason, requested_for_day, requested_at, consumed_at
        FROM sqlite_src.refresh_requests
        """
    )
    conn.execute(
        """
        INSERT INTO activity_source_state
        SELECT activity_id, TRY_CAST(activity_day AS DATE), summary_hash, detail_hash,
               streams_hash, channels_hash, source_hash, source_revision, changed_at
        FROM sqlite_src.activity_source_state
        """
    )
    conn.execute(
        """
        INSERT INTO metric_dirty_activities
        SELECT activity_id, TRY_CAST(activity_day AS DATE), metric_version, source_revision,
               reason, queued_at, attempt_count, last_error
        FROM sqlite_src.metric_dirty_activities
        """
    )
    conn.execute(
        """
        INSERT INTO activity_metric_facts
        SELECT
            activity_id, TRY_CAST(activity_day AS DATE), sport_type, source_hash,
            source_revision, metric_version, computed_at, completeness_status,
            missing_reasons_json, trimp, zone1_seconds, zone2_seconds, zone3_seconds,
            zone4_seconds, zone5_seconds, hr_recovery_pause_count,
            hr_recovery_total_rest_sec, hr_recovery_median_rate, hr_recovery_best_rate,
            hr_recovery_worst_rate, hr_recovery_avg_rate, vertical_speed_vmh,
            vertical_speed_total_ascent_m, vertical_speed_duration_hours, cardiac_cost,
            adjusted_cardiac_cost, cardiac_drift_pct, cardiac_drift_severity,
            cardiac_drift_significant, cardiac_drift_quality, hrr_pct, anomaly_count,
            distance_m, moving_time_s, elapsed_time_s, elevation_gain_m,
            heartrate_sample_count, stream_sample_count
        FROM sqlite_src.activity_metric_facts
        """
    )
    conn.execute(
        """
        INSERT INTO daily_load_facts
        SELECT
            TRY_CAST(day AS DATE), scope, sport_type, metric_version, computed_at,
            completeness_status, missing_reasons_json, activity_count, stream_point_count,
            heartrate_point_count, observed_trimp, effective_trimp, distance_m,
            moving_time_s, elevation_gain_m, zone4_seconds, zone5_seconds,
            high_zone_seconds, anomaly_count
        FROM sqlite_src.daily_load_facts
        """
    )
    conn.execute(
        """
        INSERT INTO training_model_daily
        SELECT
            TRY_CAST(day AS DATE), scope, sport_type, metric_version, computed_at,
            completeness_status, missing_reasons_json, effective_trimp, observed_trimp,
            fitness, fatigue, form, form_zone, acwr_zone, acwr, load_7d, load_28d,
            load_42d, input_days, missing_days
        FROM sqlite_src.training_model_daily
        """
    )
    conn.execute(
        """
        INSERT INTO rolling_period_facts
        SELECT
            TRY_CAST(as_of_day AS DATE), window_days, scope, sport_type, metric_version,
            computed_at, completeness_status, missing_reasons_json, activity_count,
            active_days, rest_days, observed_trimp, effective_trimp, distance_m,
            moving_time_s, elevation_gain_m, high_zone_seconds, anomaly_count,
            fitness, fatigue, form, form_zone, acwr_zone, acwr, median_cardiac_cost,
            median_adjusted_cardiac_cost, median_hr_recovery, median_cardiac_drift_pct
        FROM sqlite_src.rolling_period_facts
        """
    )
    conn.execute(
        """
        INSERT INTO read_model_refresh_runs
        SELECT
            id, started_at, finished_at, status, metric_version, trigger_reason,
            lease_owner, activities_considered, activities_materialized,
            daily_facts_materialized, model_facts_materialized,
            rolling_facts_materialized, dirty_rows_claimed, dirty_rows_cleared,
            checkpoint_cursor, attempt_count, last_error
        FROM sqlite_src.read_model_refresh_runs
        """
    )
    conn.execute(
        """
        INSERT INTO schema_migration_log
        SELECT version, name, applied_at, checksum
        FROM sqlite_src.schema_migration_log
        """
    )


def _duckdb_counts(conn) -> dict[str, int]:
    return {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in DUCKDB_TABLES
    }


def _status_counts(conn) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM stream_channels
        GROUP BY status
        ORDER BY status
        """
    ).fetchall()
    return {str(status): int(count) for status, count in rows}


def _metric_versions(conn) -> list[int]:
    rows = conn.execute(
        """
        SELECT DISTINCT metric_version
        FROM (
            SELECT metric_version FROM metric_dirty_activities
            UNION ALL SELECT metric_version FROM activity_metric_facts
            UNION ALL SELECT metric_version FROM daily_load_facts
            UNION ALL SELECT metric_version FROM training_model_daily
            UNION ALL SELECT metric_version FROM rolling_period_facts
            UNION ALL SELECT metric_version FROM read_model_refresh_runs
        )
        ORDER BY metric_version
        """
    ).fetchall()
    return [int(row[0]) for row in rows if row[0] is not None]


def _min_max_dates(conn) -> dict[str, dict[str, str | None]]:
    specs = {
        "activities": "activity_day",
        "activity_metric_facts": "activity_day",
        "daily_load_facts": "day",
        "training_model_daily": "day",
        "rolling_period_facts": "as_of_day",
    }
    result: dict[str, dict[str, str | None]] = {}
    for table, column in specs.items():
        row = conn.execute(f"SELECT MIN({column}), MAX({column}) FROM {table}").fetchone()
        result[table] = {
            "min": str(row[0]) if row and row[0] is not None else None,
            "max": str(row[1]) if row and row[1] is not None else None,
        }
    return result


def _refresh_state_from_duckdb(conn) -> dict[str, object]:
    row = conn.execute("SELECT * FROM refresh_state WHERE id = 1").fetchone()
    if row is None:
        return {}
    columns = [item[0] for item in conn.description]
    return dict(zip(columns, row, strict=False))


def _rollback_metadata(backup_path: Path | None, duckdb_path: Path) -> dict[str, object]:
    return {
        "sqlite_backup_path": str(backup_path) if backup_path is not None else None,
        "duckdb_path": str(duckdb_path),
        "instructions": [
            "stop the DuckDB runtime",
            "restore or repoint runtime config to the pinned SQLite backup",
            "run storage preflight and Docker/MCP smoke checks before accepting rollback",
        ],
    }


def _empty_report(
    *,
    backup_path: Path | None,
    duckdb_path: Path,
    source_counts: dict[str, int] | None = None,
    refresh_state: dict[str, object] | None = None,
    cast_failures: list[dict[str, object]] | None = None,
) -> DuckDBCutoverReport:
    return DuckDBCutoverReport(
        backup_path=backup_path,
        duckdb_path=duckdb_path,
        parity_ok=False,
        source_counts=source_counts or {},
        cast_failures=cast_failures or [],
        refresh_state=refresh_state or {},
        rollback=_rollback_metadata(backup_path, duckdb_path),
    )


def run_duckdb_cutover(
    source_sqlite_path: str | Path,
    target_duckdb_path: str | Path,
    backup_dir: str | Path,
    now: str | None,
    owner: str,
) -> DuckDBCutoverReport:
    """Migrate a stopped SQLite mirror into a typed DuckDB primary file.

    The canonical live target for Docker/runtime use is
    `/runtime/data/strava.duckdb`. This helper intentionally reads SQLite only
    during the cutover path and leaves the produced DuckDB file unattached.
    """

    _ = (now, owner)
    source_path = Path(source_sqlite_path)
    target_path = Path(target_duckdb_path)
    backups_path = Path(backup_dir)
    if not source_path.exists():
        raise DuckDBMigrationError(f"Source SQLite mirror does not exist: {source_path}")

    refresh_state = _read_refresh_state(source_path)
    if refresh_state.get("lease_owner"):
        report = _empty_report(
            backup_path=None,
            duckdb_path=target_path,
            source_counts=_sqlite_counts(source_path),
            refresh_state=refresh_state,
        )
        raise DuckDBMigrationError("active refresh lease blocks DuckDB cutover", report)

    backup_path = create_pre_phase_8_backup(source_path, backups_dir=backups_path)
    source_counts = _sqlite_counts(backup_path)
    tmp_path = target_path.with_name(f"{target_path.name}.tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(database=str(tmp_path), read_only=False)
    try:
        _ensure_sqlite_extension(conn)
        _attach_sqlite(conn, backup_path)
        cast_failures = _date_cast_failures(conn)
        if cast_failures:
            report = _empty_report(
                backup_path=backup_path,
                duckdb_path=target_path,
                source_counts=source_counts,
                refresh_state=refresh_state,
                cast_failures=cast_failures,
            )
            raise DuckDBMigrationError("cast failure during DuckDB cutover", report)

        create_schema(conn)
        _insert_all_tables(conn)
        _detach_sqlite(conn)
        target_counts = _duckdb_counts(conn)
        parity_ok = source_counts == target_counts
        report = DuckDBCutoverReport(
            backup_path=backup_path,
            duckdb_path=target_path,
            parity_ok=parity_ok,
            source_counts=source_counts,
            target_counts=target_counts,
            cast_failures=[],
            stream_point_count=int(conn.execute("SELECT COUNT(*) FROM streams").fetchone()[0]),
            stream_channel_status_counts=_status_counts(conn),
            kudos_count=int(conn.execute("SELECT COUNT(*) FROM kudos").fetchone()[0]),
            refresh_state=_refresh_state_from_duckdb(conn),
            metric_versions=_metric_versions(conn),
            min_max_dates=_min_max_dates(conn),
            rollback=_rollback_metadata(backup_path, target_path),
        )
        if not parity_ok:
            raise DuckDBMigrationError("row-count parity failed during DuckDB cutover", report)
    except DuckDBMigrationError:
        conn.close()
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        conn.close()
        tmp_path.unlink(missing_ok=True)
        raise DuckDBMigrationError(f"DuckDB cutover failed: {exc}") from exc
    else:
        conn.close()
        tmp_path.replace(target_path)
        return report
    finally:
        if tmp_path.exists() and not target_path.exists():
            tmp_path.unlink(missing_ok=True)
