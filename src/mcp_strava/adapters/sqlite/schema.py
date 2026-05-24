"""Schema inventory and preflight/post-check helpers."""

from dataclasses import dataclass
from pathlib import Path
import sqlite3


BASE_TABLES_V1: tuple[str, ...] = ("activities", "streams", "athlete_zones", "sync_log", "kudos")
REFRESH_TABLES_V2: tuple[str, ...] = ("refresh_state", "refresh_requests")
READ_MODEL_TABLES_V5: tuple[str, ...] = (
    "activity_source_state",
    "metric_dirty_activities",
    "activity_metric_facts",
    "daily_load_facts",
    "training_model_daily",
    "rolling_period_facts",
    "read_model_refresh_runs",
)

REQUIRED_TABLES_BY_VERSION: dict[int, tuple[str, ...]] = {
    1: BASE_TABLES_V1,
    2: BASE_TABLES_V1 + REFRESH_TABLES_V2,
    3: BASE_TABLES_V1 + REFRESH_TABLES_V2 + ("stream_channels",),
    # Reserved for 06-03 canonical GPS cleanup; latlng removal is intentional here.
    4: BASE_TABLES_V1 + REFRESH_TABLES_V2 + ("stream_channels",),
    5: BASE_TABLES_V1 + REFRESH_TABLES_V2 + ("stream_channels",) + READ_MODEL_TABLES_V5,
}

REQUIRED_COLUMNS_BY_VERSION: dict[int, dict[str, tuple[str, ...]]] = {
    1: {
        "activities": (
            "id",
            "date",
            "name",
            "sport_type",
            "distance",
            "moving_time",
            "elapsed_time",
            "total_elevation_gain",
            "summary_json",
            "detail_json",
            "synced_at",
        ),
        "streams": (
            "activity_id",
            "time_offset",
            "heartrate",
            "velocity",
            "altitude",
            "cadence",
            "lat",
            "lng",
            "grade",
            "gap_speed",
            "gap_distance",
            "is_moving",
            "latlng",
        ),
        "athlete_zones": ("id", "fetched_at", "zones_json"),
        "sync_log": (
            "id",
            "timestamp",
            "status",
            "activities_seen",
            "activities_new",
            "streams_fetched",
            "details_fetched",
            "api_calls",
            "error",
            "kudos_fetched",
        ),
        "kudos": ("activity_id", "firstname", "lastname", "fetched_at"),
    },
    2: {
        "refresh_state": (
            "id",
            "last_success_at",
            "last_attempt_at",
            "last_status",
            "last_error_code",
            "lease_owner",
            "lease_expires_at",
            "backoff_until",
            "checkpoint_stage",
            "checkpoint_cursor",
        ),
        "refresh_requests": ("id", "reason", "requested_for_day", "requested_at", "consumed_at"),
    },
    3: {
        "streams": (
            "activity_id",
            "time_offset",
            "heartrate",
            "velocity",
            "altitude",
            "cadence",
            "lat",
            "lng",
            "grade",
            "gap_speed",
            "gap_distance",
            "is_moving",
            "latlng",
            "values_json",
        ),
        "stream_channels": (
            "activity_id",
            "channel_key",
            "original_size",
            "resolution",
            "series_type",
            "fetched_at",
            "batch_id",
            "status",
            "error",
        ),
    },
    4: {
        "streams": (
            "activity_id",
            "time_offset",
            "heartrate",
            "velocity",
            "altitude",
            "cadence",
            "lat",
            "lng",
            "grade",
            "gap_speed",
            "gap_distance",
            "is_moving",
            "values_json",
        ),
    },
    5: {
        "activity_source_state": (
            "activity_id",
            "activity_day",
            "summary_hash",
            "detail_hash",
            "streams_hash",
            "channels_hash",
            "source_hash",
            "source_revision",
            "changed_at",
        ),
        "metric_dirty_activities": (
            "activity_id",
            "activity_day",
            "metric_version",
            "source_revision",
            "reason",
            "queued_at",
            "attempt_count",
            "last_error",
        ),
        "activity_metric_facts": (
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
            "hr_recovery_best_rate",
            "hr_recovery_worst_rate",
            "hr_recovery_avg_rate",
            "vertical_speed_vmh",
            "vertical_speed_total_ascent_m",
            "vertical_speed_duration_hours",
            "cardiac_cost",
            "adjusted_cardiac_cost",
            "cardiac_drift_pct",
            "cardiac_drift_severity",
            "hrr_pct",
            "z5_seconds",
            "anomaly_count",
            "distance_m",
            "moving_time_s",
            "elapsed_time_s",
            "elevation_gain_m",
            "heartrate_sample_count",
            "stream_sample_count",
        ),
        "daily_load_facts": (
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
            "zone4_seconds",
            "zone5_seconds",
            "high_zone_seconds",
            "anomaly_count",
        ),
        "training_model_daily": (
            "day",
            "scope",
            "sport_type",
            "metric_version",
            "computed_at",
            "completeness_status",
            "missing_reasons_json",
            "effective_trimp",
            "observed_trimp",
            "fitness",
            "fatigue",
            "form",
            "form_zone",
            "atl",
            "ctl",
            "acwr",
            "load_7d",
            "load_28d",
            "load_42d",
            "input_days",
            "missing_days",
        ),
        "rolling_period_facts": (
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
            "rest_days",
            "observed_trimp",
            "effective_trimp",
            "distance_m",
            "moving_time_s",
            "elevation_gain_m",
            "high_zone_seconds",
            "anomaly_count",
            "fitness",
            "fatigue",
            "form",
            "atl",
            "ctl",
            "acwr",
            "median_cardiac_cost",
            "median_adjusted_cardiac_cost",
            "median_hr_recovery",
            "median_cardiac_drift_pct",
        ),
        "read_model_refresh_runs": (
            "id",
            "started_at",
            "finished_at",
            "status",
            "metric_version",
            "trigger_reason",
            "lease_owner",
            "activities_considered",
            "activities_materialized",
            "daily_facts_materialized",
            "model_facts_materialized",
            "rolling_facts_materialized",
            "dirty_rows_claimed",
            "dirty_rows_cleared",
            "checkpoint_cursor",
            "attempt_count",
            "last_error",
        ),
    },
}

REQUIRED_INDEXES_BY_VERSION: dict[int, dict[str, dict[str, object]]] = {
    1: {
        "idx_streams_act": {"table": "streams", "columns": ("activity_id",), "partial": False},
    },
    2: {
        "idx_refresh_requests_dedupe": {
            "table": "refresh_requests",
            "columns": ("reason", "requested_for_day"),
            "partial": True,
        },
    },
    3: {
        "idx_stream_channels_activity": {
            "table": "stream_channels",
            "columns": ("activity_id",),
            "partial": False,
        }
    },
    4: {},
    5: {
        "idx_activity_source_state_day": {
            "table": "activity_source_state",
            "columns": ("activity_day",),
            "partial": False,
        },
        "idx_metric_dirty_lookup": {
            "table": "metric_dirty_activities",
            "columns": ("metric_version", "activity_day", "activity_id"),
            "partial": False,
        },
        "idx_activity_metric_day_sport_version": {
            "table": "activity_metric_facts",
            "columns": ("activity_day", "sport_type", "metric_version"),
            "partial": False,
        },
        "idx_activity_metric_activity_version": {
            "table": "activity_metric_facts",
            "columns": ("activity_id", "metric_version"),
            "partial": False,
        },
        "idx_daily_load_day_scope_sport_version": {
            "table": "daily_load_facts",
            "columns": ("day", "scope", "sport_type", "metric_version"),
            "partial": False,
        },
        "idx_training_model_day_scope_sport_version": {
            "table": "training_model_daily",
            "columns": ("day", "scope", "sport_type", "metric_version"),
            "partial": False,
        },
        "idx_rolling_period_asof_window_scope_sport_version": {
            "table": "rolling_period_facts",
            "columns": ("as_of_day", "window_days", "scope", "sport_type", "metric_version"),
            "partial": False,
        },
        "idx_activities_date_id": {
            "table": "activities",
            "columns": ("date", "id"),
            "partial": False,
        },
        "idx_activities_sport_date_id": {
            "table": "activities",
            "columns": ("sport_type", "date", "id"),
            "partial": False,
        },
    },
}


@dataclass(frozen=True)
class PreflightReport:
    path: Path
    user_version: int
    row_counts: dict[str, int]
    integrity_result: str


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _columns_for_table(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _index_rows(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row | tuple]:
    return conn.execute(f"PRAGMA index_list({table})").fetchall()


def _index_columns(conn: sqlite3.Connection, index: str) -> tuple[str, ...]:
    rows = conn.execute(f"PRAGMA index_info({index})").fetchall()
    return tuple(row[2] for row in rows)


def read_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def set_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version={int(version)}")


def integrity_check(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0]) if row else "unknown"


def _effective_inventory_version(version: int) -> int:
    if version <= 1:
        return 1
    if version in REQUIRED_TABLES_BY_VERSION:
        return version
    return max(REQUIRED_TABLES_BY_VERSION)


def _required_columns_for_version(version: int) -> dict[str, tuple[str, ...]]:
    required: dict[str, tuple[str, ...]] = {}
    effective = _effective_inventory_version(version)
    for v in sorted(REQUIRED_COLUMNS_BY_VERSION):
        if v <= effective:
            required.update(REQUIRED_COLUMNS_BY_VERSION[v])
    return required


def _required_indexes_for_version(version: int) -> dict[str, dict[str, object]]:
    required: dict[str, dict[str, object]] = {}
    effective = _effective_inventory_version(version)
    for v in sorted(REQUIRED_INDEXES_BY_VERSION):
        if v <= effective:
            required.update(REQUIRED_INDEXES_BY_VERSION[v])
    return required


def row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    table_names = set(BASE_TABLES_V1 + REFRESH_TABLES_V2 + ("stream_channels",) + READ_MODEL_TABLES_V5)
    for table in sorted(table_names):
        if _table_exists(conn, table):
            counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return counts


def validate_required_inventory(conn: sqlite3.Connection) -> None:
    version = read_user_version(conn)
    effective = _effective_inventory_version(version)
    required_tables = REQUIRED_TABLES_BY_VERSION[effective]

    for table in required_tables:
        if not _table_exists(conn, table):
            raise RuntimeError(f"Missing required table: {table}")

    required_columns = _required_columns_for_version(version)
    for table in required_tables:
        required = required_columns.get(table, ())
        actual = _columns_for_table(conn, table)
        missing = [col for col in required if col not in actual]
        if missing:
            raise RuntimeError(f"Missing required columns in {table}: {', '.join(missing)}")

    required_indexes = _required_indexes_for_version(version)
    for idx, spec in required_indexes.items():
        table = str(spec["table"])
        rows = _index_rows(conn, table)
        matching = [row for row in rows if row[1] == idx]
        if not matching:
            raise RuntimeError(f"Missing required index: {idx}")
        actual_cols = _index_columns(conn, idx)
        expected_cols = tuple(spec["columns"])
        if actual_cols != expected_cols:
            raise RuntimeError(f"Invalid index columns for {idx}: {actual_cols} != {expected_cols}")
        if spec.get("partial") and len(matching[0]) >= 5 and int(matching[0][4]) != 1:
            raise RuntimeError(f"Required index is not partial: {idx}")


def run_preflight_checks(db_path: str | Path) -> PreflightReport:
    path = Path(db_path)
    if not path.exists():
        raise RuntimeError(f"Expected mirror does not exist: {path}")

    conn = sqlite3.connect(str(path), check_same_thread=False)
    try:
        validate_required_inventory(conn)
        integrity = integrity_check(conn)
        if integrity.lower() != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
        return PreflightReport(
            path=path,
            user_version=read_user_version(conn),
            row_counts=row_counts(conn),
            integrity_result=integrity,
        )
    finally:
        conn.close()
