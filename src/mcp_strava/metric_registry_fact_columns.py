"""Materialized fact-column registry and SQL metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass

from mcp_strava.metric_registry_metrics import METRIC_REGISTRY

FACT_COLUMN_ROLES = ("dimension", "metric", "dependency", "provenance")
MATERIALIZED_FACT_TABLES = (
    "activity_metric_facts",
    "daily_load_facts",
    "training_model_daily",
    "rolling_period_facts",
)


@dataclass(frozen=True)
class FactColumnDefinition:
    """Registry entry for a materialized analytic fact-table column."""

    table_name: str
    column_name: str
    role: str
    metric_ids: tuple[str, ...] = ()
    description: str = ""
    sql_type: str = ""
    nullable: bool = True
    default_sql: str | None = None


_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SUPPORTED_FACT_SQL_TYPES = frozenset({"BIGINT", "DOUBLE", "VARCHAR", "DATE"})
_SUPPORTED_FACT_DEFAULT_SQL = frozenset({"0", "0.0", "'[]'"})


def _sql(sql_type: str, *, nullable: bool = True, default_sql: str | None = None) -> tuple[str, bool, str | None]:
    return sql_type, nullable, default_sql


_MATERIALIZED_FACT_COLUMN_SQL_METADATA: dict[str, dict[str, tuple[str, bool, str | None]]] = {
    "activity_metric_facts": {
        "activity_id": _sql("BIGINT", nullable=False),
        "activity_day": _sql("DATE", nullable=False),
        "sport_type": _sql("VARCHAR", nullable=False),
        "source_hash": _sql("VARCHAR", nullable=False),
        "source_revision": _sql("BIGINT", nullable=False),
        "metric_version": _sql("BIGINT", nullable=False),
        "computed_at": _sql("VARCHAR", nullable=False),
        "completeness_status": _sql("VARCHAR", nullable=False),
        "missing_reasons_json": _sql("VARCHAR", nullable=False, default_sql="'[]'"),
        "trimp": _sql("DOUBLE"),
        "zone1_seconds": _sql("BIGINT", nullable=False, default_sql="0"),
        "zone2_seconds": _sql("BIGINT", nullable=False, default_sql="0"),
        "zone3_seconds": _sql("BIGINT", nullable=False, default_sql="0"),
        "zone4_seconds": _sql("BIGINT", nullable=False, default_sql="0"),
        "zone5_seconds": _sql("BIGINT", nullable=False, default_sql="0"),
        "hr_recovery_pause_count": _sql("BIGINT", nullable=False, default_sql="0"),
        "hr_recovery_total_rest_sec": _sql("BIGINT", nullable=False, default_sql="0"),
        "hr_recovery_median_rate": _sql("DOUBLE"),
        "hr_recovery_best_rate": _sql("DOUBLE"),
        "hr_recovery_worst_rate": _sql("DOUBLE"),
        "hr_recovery_avg_rate": _sql("DOUBLE"),
        "vertical_speed_vmh": _sql("BIGINT"),
        "vertical_speed_total_ascent_m": _sql("DOUBLE"),
        "vertical_speed_duration_hours": _sql("DOUBLE"),
        "cardiac_cost": _sql("DOUBLE"),
        "adjusted_cardiac_cost": _sql("DOUBLE"),
        "cardiac_drift_pct": _sql("DOUBLE"),
        "cardiac_drift_severity": _sql("VARCHAR"),
        "cardiac_drift_significant": _sql("BIGINT", nullable=False, default_sql="0"),
        "cardiac_drift_quality": _sql("VARCHAR"),
        "hrr_pct": _sql("DOUBLE"),
        "anomaly_count": _sql("BIGINT", nullable=False, default_sql="0"),
        "distance_m": _sql("DOUBLE"),
        "calories_kcal": _sql("DOUBLE"),
        "moving_time_s": _sql("BIGINT"),
        "elapsed_time_s": _sql("BIGINT"),
        "elevation_gain_m": _sql("DOUBLE"),
        "heartrate_sample_count": _sql("BIGINT", nullable=False, default_sql="0"),
        "stream_sample_count": _sql("BIGINT", nullable=False, default_sql="0"),
        "observed_min_hr": _sql("BIGINT"),
        "observed_max_hr": _sql("BIGINT"),
        "hr_zone_model": _sql("VARCHAR"),
        "hr_max_used": _sql("BIGINT"),
        "hr_rest_used": _sql("BIGINT"),
        "start_time_local": _sql("VARCHAR"),
    },
    "daily_load_facts": {
        "day": _sql("DATE", nullable=False),
        "scope": _sql("VARCHAR", nullable=False),
        "sport_type": _sql("VARCHAR", nullable=False),
        "metric_version": _sql("BIGINT", nullable=False),
        "computed_at": _sql("VARCHAR", nullable=False),
        "completeness_status": _sql("VARCHAR", nullable=False),
        "missing_reasons_json": _sql("VARCHAR", nullable=False, default_sql="'[]'"),
        "activity_count": _sql("BIGINT", nullable=False, default_sql="0"),
        "stream_point_count": _sql("BIGINT", nullable=False, default_sql="0"),
        "heartrate_point_count": _sql("BIGINT", nullable=False, default_sql="0"),
        "observed_trimp": _sql("DOUBLE"),
        "effective_trimp": _sql("DOUBLE", nullable=False, default_sql="0.0"),
        "distance_m": _sql("DOUBLE", nullable=False, default_sql="0.0"),
        "moving_time_s": _sql("BIGINT", nullable=False, default_sql="0"),
        "elevation_gain_m": _sql("DOUBLE", nullable=False, default_sql="0.0"),
        "zone4_seconds": _sql("BIGINT", nullable=False, default_sql="0"),
        "zone5_seconds": _sql("BIGINT", nullable=False, default_sql="0"),
        "high_zone_seconds": _sql("BIGINT", nullable=False, default_sql="0"),
        "anomaly_count": _sql("BIGINT", nullable=False, default_sql="0"),
    },
    "training_model_daily": {
        "day": _sql("DATE", nullable=False),
        "scope": _sql("VARCHAR", nullable=False),
        "sport_type": _sql("VARCHAR", nullable=False),
        "metric_version": _sql("BIGINT", nullable=False),
        "computed_at": _sql("VARCHAR", nullable=False),
        "completeness_status": _sql("VARCHAR", nullable=False),
        "missing_reasons_json": _sql("VARCHAR", nullable=False, default_sql="'[]'"),
        "effective_trimp": _sql("DOUBLE", nullable=False, default_sql="0.0"),
        "observed_trimp": _sql("DOUBLE"),
        "fitness": _sql("DOUBLE"),
        "fatigue": _sql("DOUBLE"),
        "form": _sql("DOUBLE"),
        "form_zone": _sql("VARCHAR"),
        "acwr_zone": _sql("VARCHAR"),
        "acwr": _sql("DOUBLE"),
        "load_7d": _sql("DOUBLE"),
        "load_28d": _sql("DOUBLE"),
        "load_42d": _sql("DOUBLE"),
        "input_days": _sql("BIGINT", nullable=False, default_sql="0"),
        "missing_days": _sql("BIGINT", nullable=False, default_sql="0"),
    },
    "rolling_period_facts": {
        "as_of_day": _sql("DATE", nullable=False),
        "window_days": _sql("BIGINT", nullable=False),
        "scope": _sql("VARCHAR", nullable=False),
        "sport_type": _sql("VARCHAR", nullable=False),
        "metric_version": _sql("BIGINT", nullable=False),
        "computed_at": _sql("VARCHAR", nullable=False),
        "completeness_status": _sql("VARCHAR", nullable=False),
        "missing_reasons_json": _sql("VARCHAR", nullable=False, default_sql="'[]'"),
        "activity_count": _sql("BIGINT", nullable=False, default_sql="0"),
        "active_days": _sql("BIGINT", nullable=False, default_sql="0"),
        "rest_days": _sql("BIGINT", nullable=False, default_sql="0"),
        "observed_trimp": _sql("DOUBLE"),
        "effective_trimp": _sql("DOUBLE", nullable=False, default_sql="0.0"),
        "distance_m": _sql("DOUBLE", nullable=False, default_sql="0.0"),
        "moving_time_s": _sql("BIGINT", nullable=False, default_sql="0"),
        "elevation_gain_m": _sql("DOUBLE", nullable=False, default_sql="0.0"),
        "high_zone_seconds": _sql("BIGINT", nullable=False, default_sql="0"),
        "anomaly_count": _sql("BIGINT", nullable=False, default_sql="0"),
        "fitness": _sql("DOUBLE"),
        "fatigue": _sql("DOUBLE"),
        "form": _sql("DOUBLE"),
        "form_zone": _sql("VARCHAR"),
        "acwr_zone": _sql("VARCHAR"),
        "acwr": _sql("DOUBLE"),
        "median_cardiac_cost": _sql("DOUBLE"),
        "median_adjusted_cardiac_cost": _sql("DOUBLE"),
        "median_hr_recovery": _sql("DOUBLE"),
        "median_cardiac_drift_pct": _sql("DOUBLE"),
    },
}


def _fact_column(
    table_name: str,
    column_name: str,
    role: str,
    metric_ids: tuple[str, ...] = (),
    description: str = "",
) -> FactColumnDefinition:
    if role not in FACT_COLUMN_ROLES:
        raise ValueError(f"Unknown fact column role: {role}")
    sql_type, nullable, default_sql = _MATERIALIZED_FACT_COLUMN_SQL_METADATA.get(table_name, {}).get(
        column_name, ("", True, None)
    )
    return FactColumnDefinition(
        table_name=table_name,
        column_name=column_name,
        role=role,
        metric_ids=metric_ids,
        description=description,
        sql_type=sql_type,
        nullable=nullable,
        default_sql=default_sql,
    )


def _fact_table(
    table_name: str, columns: tuple[tuple[str, str, tuple[str, ...], str], ...]
) -> dict[str, FactColumnDefinition]:
    return {
        column_name: _fact_column(table_name, column_name, role, metric_ids, description)
        for column_name, role, metric_ids, description in columns
    }


MATERIALIZED_FACT_COLUMN_REGISTRY: dict[str, dict[str, FactColumnDefinition]] = {
    "activity_metric_facts": _fact_table(
        "activity_metric_facts",
        (
            ("activity_id", "dimension", ("activity_id",), "Activity identity for the materialized row."),
            ("activity_day", "dimension", ("activity_date",), "Activity day used for period and rolling filters."),
            ("sport_type", "dimension", ("sport_type",), "Sport dimension used for per-sport aggregates."),
            ("source_hash", "provenance", (), "Source mirror hash used to decide whether facts are stale."),
            ("source_revision", "provenance", (), "Monotonic source revision copied from activity_source_state."),
            ("metric_version", "provenance", (), "Read-model metric formula version."),
            ("computed_at", "provenance", (), "Timestamp when this fact row was materialized."),
            ("completeness_status", "provenance", (), "Completeness state for the source data behind this row."),
            ("missing_reasons_json", "provenance", (), "Machine-readable missing-data reasons for the row."),
            ("trimp", "metric", ("trimp",), "Per-activity TRIMP."),
            ("zone1_seconds", "dependency", ("time_in_hr_zones_min", "trimp"), "Heart-rate zone 1 seconds."),
            ("zone2_seconds", "dependency", ("time_in_hr_zones_min", "trimp"), "Heart-rate zone 2 seconds."),
            ("zone3_seconds", "dependency", ("time_in_hr_zones_min", "trimp"), "Heart-rate zone 3 seconds."),
            ("zone4_seconds", "dependency", ("time_in_hr_zones_min", "trimp"), "Heart-rate zone 4 seconds."),
            ("zone5_seconds", "dependency", ("time_in_hr_zones_min", "trimp"), "Heart-rate zone 5 seconds."),
            ("hr_recovery_pause_count", "metric", ("hr_recovery_pauses",), "Detected HR recovery pause count."),
            (
                "hr_recovery_total_rest_sec",
                "metric",
                ("hr_recovery_total_rest_sec",),
                "Total detected HR recovery rest seconds.",
            ),
            ("hr_recovery_median_rate", "metric", ("hr_recovery_median_bpm_per_min",), "Median HR recovery rate."),
            ("hr_recovery_best_rate", "metric", ("hr_recovery_best_bpm_per_min",), "Best HR recovery rate."),
            ("hr_recovery_worst_rate", "metric", ("hr_recovery_worst_bpm_per_min",), "Worst HR recovery rate."),
            ("hr_recovery_avg_rate", "metric", ("hr_recovery_avg_bpm_per_min",), "Average HR recovery rate."),
            ("vertical_speed_vmh", "metric", ("vertical_speed_m_per_h",), "Vertical speed in meters per hour."),
            (
                "vertical_speed_total_ascent_m",
                "metric",
                ("vertical_ascent_m",),
                "Positive vertical ascent used by vertical metrics.",
            ),
            (
                "vertical_speed_duration_hours",
                "metric",
                ("vertical_duration_h",),
                "Duration denominator used by vertical speed.",
            ),
            ("cardiac_cost", "metric", ("cardiac_cost",), "Per-activity cardiac cost."),
            ("adjusted_cardiac_cost", "metric", ("cardiac_cost_adjusted",), "Elevation-adjusted cardiac cost."),
            ("cardiac_drift_pct", "metric", ("cardiac_drift_pct",), "Cardiac drift percent."),
            ("cardiac_drift_severity", "metric", ("cardiac_drift_severity",), "Cardiac drift severity category."),
            ("cardiac_drift_significant", "metric", ("cardiac_drift_significant",), "Cardiac drift significant flag."),
            ("cardiac_drift_quality", "metric", ("cardiac_drift_quality",), "Cardiac drift quality category."),
            ("hrr_pct", "metric", ("hrr_pct",), "Heart-rate reserve percent."),
            ("anomaly_count", "metric", ("hr_anomaly_count",), "Heart-rate anomaly count."),
            ("distance_m", "metric", ("distance_km",), "Mirrored distance in meters."),
            ("calories_kcal", "metric", ("calories",), "Strava-reported calories in kcal (from detail_json)."),
            ("moving_time_s", "metric", ("moving_time_min",), "Mirrored moving time in seconds."),
            ("elapsed_time_s", "metric", ("elapsed_time_min",), "Mirrored elapsed time in seconds."),
            ("elevation_gain_m", "metric", ("elevation_m",), "Mirrored elevation gain in meters."),
            ("heartrate_sample_count", "dependency", ("avg_hr", "max_hr"), "Heart-rate sample denominator."),
            ("stream_sample_count", "dependency", (), "Stream sample count used for completeness checks."),
            ("observed_min_hr", "provenance", (), "Minimum heartrate sample observed in the activity streams."),
            ("observed_max_hr", "provenance", (), "Maximum heartrate sample observed in the activity streams."),
            ("hr_zone_model", "provenance", (), "HR zone model identifier used when computing zone seconds and TRIMP."),
            (
                "hr_max_used",
                "provenance",
                (),
                "Running max heartrate to date used as hr_max for zone bound computation.",
            ),
            (
                "hr_rest_used",
                "provenance",
                (),
                "Athlete resting HR from MCP_STRAVA_HR_REST used for zone bound computation.",
            ),
            (
                "start_time_local",
                "metric",
                ("start_time_local",),
                "Local time-of-day (HH:MM) the activity started, parsed from "
                "summary_json.start_date_local (fromisoformat + strftime, not a string slice).",
            ),
        ),
    ),
    "daily_load_facts": _fact_table(
        "daily_load_facts",
        (
            ("day", "dimension", ("activity_date",), "Calendar day."),
            ("scope", "dimension", (), "Aggregate scope discriminator."),
            ("sport_type", "dimension", ("sport_type",), "Sport dimension."),
            ("metric_version", "provenance", (), "Read-model metric formula version."),
            ("computed_at", "provenance", (), "Timestamp when this fact row was materialized."),
            ("completeness_status", "provenance", (), "Daily completeness state."),
            ("missing_reasons_json", "provenance", (), "Daily missing-data reasons."),
            (
                "activity_count",
                "dependency",
                ("active_days", "rest_days", "volume_7d", "volume_28d"),
                "Activity count for the day.",
            ),
            ("stream_point_count", "dependency", (), "Daily stream sample count."),
            ("heartrate_point_count", "dependency", ("avg_hr", "max_hr"), "Daily heart-rate sample count."),
            ("observed_trimp", "dependency", ("daily_trimp", "trimp"), "Observed daily TRIMP before rest-day fill."),
            (
                "effective_trimp",
                "metric",
                ("daily_trimp", "weekly_trimp", "total_trimp_14d", "avg_trimp_per_day"),
                "Effective daily load used by training model and rollups.",
            ),
            ("distance_m", "metric", ("distance_km",), "Daily distance in meters."),
            ("moving_time_s", "metric", ("moving_time_min",), "Daily moving time in seconds."),
            ("elevation_gain_m", "metric", ("elevation_m",), "Daily elevation gain in meters."),
            ("zone4_seconds", "dependency", ("time_in_hr_zones_min",), "Daily HR zone 4 seconds."),
            ("zone5_seconds", "dependency", ("time_in_hr_zones_min",), "Daily HR zone 5 seconds."),
            ("high_zone_seconds", "dependency", ("time_in_hr_zones_min",), "Daily zone 4 plus zone 5 seconds."),
            ("anomaly_count", "metric", ("hr_anomaly_count",), "Daily heart-rate anomaly count."),
        ),
    ),
    "training_model_daily": _fact_table(
        "training_model_daily",
        (
            ("day", "dimension", ("activity_date",), "Calendar day for model state."),
            ("scope", "dimension", (), "Aggregate scope discriminator."),
            ("sport_type", "dimension", ("sport_type",), "Sport dimension."),
            ("metric_version", "provenance", (), "Read-model metric formula version."),
            ("computed_at", "provenance", (), "Timestamp when this fact row was materialized."),
            ("completeness_status", "provenance", (), "Training-model completeness state."),
            ("missing_reasons_json", "provenance", (), "Training-model missing-data reasons."),
            (
                "effective_trimp",
                "dependency",
                ("fitness", "fatigue", "form", "acwr"),
                "Daily load input to the training model.",
            ),
            (
                "observed_trimp",
                "dependency",
                ("fitness", "fatigue", "form", "acwr"),
                "Observed daily load retained beside effective load.",
            ),
            ("fitness", "metric", ("fitness",), "Banister long-term fitness state."),
            ("fatigue", "metric", ("fatigue",), "Banister short-term fatigue state."),
            ("form", "metric", ("form",), "Fitness minus fatigue."),
            ("form_zone", "metric", ("form_zone",), "Agent-friendly form category."),
            ("acwr_zone", "metric", ("acwr_zone",), "Agent-friendly ACWR category."),
            ("acwr", "metric", ("acwr",), "Acute chronic workload ratio."),
            ("load_7d", "dependency", ("fatigue",), "Short-horizon model load retained for model provenance."),
            ("load_28d", "dependency", (), "Medium-horizon model load slot retained for model provenance."),
            ("load_42d", "dependency", ("fitness",), "Long-horizon model load retained for model provenance."),
            ("input_days", "provenance", (), "Number of input days used for model materialization."),
            ("missing_days", "provenance", (), "Number of missing model input days."),
        ),
    ),
    "rolling_period_facts": _fact_table(
        "rolling_period_facts",
        (
            ("as_of_day", "dimension", ("activity_date",), "Inclusive rolling-window end day."),
            ("window_days", "dimension", (), "Rolling window width in days."),
            ("scope", "dimension", (), "Aggregate scope discriminator."),
            ("sport_type", "dimension", ("sport_type",), "Sport dimension."),
            ("metric_version", "provenance", (), "Read-model metric formula version."),
            ("computed_at", "provenance", (), "Timestamp when this fact row was materialized."),
            ("completeness_status", "provenance", (), "Rolling-window completeness state."),
            ("missing_reasons_json", "provenance", (), "Rolling-window missing-data reasons."),
            ("activity_count", "metric", ("volume_7d", "volume_28d"), "Activity count in the rolling window."),
            ("active_days", "metric", ("active_days",), "Active days in the rolling window."),
            ("rest_days", "metric", ("rest_days",), "Rest days in the rolling window."),
            ("observed_trimp", "dependency", ("trimp",), "Observed TRIMP sum in the rolling window."),
            (
                "effective_trimp",
                "metric",
                (
                    "weekly_trimp",
                    "total_trimp_14d",
                    "avg_trimp_per_day",
                    "daily_avg_trimp_7d",
                    "daily_avg_trimp_28d",
                    "daily_avg_trimp_90d",
                ),
                "Effective TRIMP sum in the rolling window.",
            ),
            ("distance_m", "metric", ("distance_km",), "Distance sum in meters."),
            ("moving_time_s", "metric", ("moving_time_min",), "Moving-time sum in seconds."),
            ("elevation_gain_m", "metric", ("elevation_m",), "Elevation-gain sum in meters."),
            (
                "high_zone_seconds",
                "dependency",
                ("time_in_hr_zones_min",),
                "High HR-zone seconds in the rolling window.",
            ),
            ("anomaly_count", "metric", ("hr_anomaly_count",), "Heart-rate anomaly count in the rolling window."),
            ("fitness", "metric", ("fitness",), "Latest fitness state at the rolling as-of day."),
            ("fatigue", "metric", ("fatigue",), "Latest fatigue state at the rolling as-of day."),
            ("form", "metric", ("form",), "Latest form state at the rolling as-of day."),
            ("form_zone", "metric", ("form_zone",), "Latest form-zone state at the rolling as-of day."),
            ("acwr_zone", "metric", ("acwr_zone",), "Latest ACWR-zone state at the rolling as-of day."),
            ("acwr", "metric", ("acwr",), "Latest ACWR at the rolling as-of day."),
            ("median_cardiac_cost", "metric", ("rolling_median_cc",), "Rolling median cardiac cost."),
            (
                "median_adjusted_cardiac_cost",
                "metric",
                ("rolling_median_cc_adj",),
                "Rolling median adjusted cardiac cost.",
            ),
            ("median_hr_recovery", "metric", ("rolling_median_hr_recovery",), "Rolling median HR recovery."),
            (
                "median_cardiac_drift_pct",
                "metric",
                ("rolling_median_cardiac_drift_pct",),
                "Rolling median cardiac drift percent.",
            ),
        ),
    ),
}

AGGREGATE_QUERY_PROJECTION_COLUMNS: dict[str, FactColumnDefinition] = {
    "activity_sample_count": _fact_column(
        "v_activity_aggregate_facts",
        "activity_sample_count",
        "dependency",
        ("trimp",),
        "View-level count of rows with activity metric samples.",
    ),
    "active_day_count": _fact_column(
        "v_daily_aggregate_facts",
        "active_day_count",
        "dependency",
        ("active_days",),
        "View-level active-day indicator.",
    ),
    "rest_day_count": _fact_column(
        "v_daily_aggregate_facts",
        "rest_day_count",
        "dependency",
        ("rest_days",),
        "View-level rest-day indicator.",
    ),
    "calendar_days": _fact_column(
        "aggregate_query",
        "calendar_days",
        "dependency",
        ("avg_trimp_per_day", "daily_avg_trimp_7d", "daily_avg_trimp_28d", "daily_avg_trimp_90d"),
        "Calendar-day denominator projected by daily or rolling views.",
    ),
    "calendar_day_count": _fact_column(
        "aggregate_query",
        "calendar_day_count",
        "dependency",
        (),
        "Calendar-day sample-size projection.",
    ),
    "model_day_count": _fact_column(
        "v_training_model_state_facts",
        "model_day_count",
        "dependency",
        ("fitness", "fatigue", "form", "acwr"),
        "Training-model row count projection.",
    ),
    "rolling_sample_count": _fact_column(
        "v_rolling_aggregate_facts",
        "rolling_sample_count",
        "dependency",
        (
            "rolling_median_cc",
            "rolling_median_cc_adj",
            "rolling_median_hr_recovery",
            "rolling_median_cardiac_drift_pct",
        ),
        "Rolling-window sample-size projection.",
    ),
    "avg_hr": _fact_column(
        "v_activity_aggregate_facts",
        "avg_hr",
        "metric",
        ("avg_hr",),
        "View projection from activity summary_json.average_heartrate.",
    ),
    "max_hr": _fact_column(
        "v_activity_aggregate_facts",
        "max_hr",
        "metric",
        ("max_hr",),
        "View projection from activity summary_json.max_heartrate.",
    ),
    "kudos_count": _fact_column(
        "v_activity_aggregate_facts",
        "kudos_count",
        "metric",
        ("kudos_count",),
        "View projection from activity summary_json.kudos_count.",
    ),
    "sport_type": _fact_column(
        "v_activity_aggregate_facts",
        "sport_type",
        "dimension",
        ("sport_type",),
        "View projection used for sport-type distribution aggregates.",
    ),
    "daily_avg_trimp_7d": _fact_column(
        "v_rolling_aggregate_facts",
        "daily_avg_trimp_7d",
        "metric",
        ("daily_avg_trimp_7d",),
        "View projection from rolling effective_trimp divided by window_days.",
    ),
    "daily_avg_trimp_28d": _fact_column(
        "v_rolling_aggregate_facts",
        "daily_avg_trimp_28d",
        "metric",
        ("daily_avg_trimp_28d",),
        "View projection from rolling effective_trimp divided by window_days.",
    ),
    "daily_avg_trimp_90d": _fact_column(
        "v_rolling_aggregate_facts",
        "daily_avg_trimp_90d",
        "metric",
        ("daily_avg_trimp_90d",),
        "View projection from rolling effective_trimp divided by window_days.",
    ),
    "activity_streak_days": _fact_column(
        "v_historical_context_facts",
        "activity_streak_days",
        "metric",
        ("activity_streak_days",),
        "View-derived consecutive active-day count ending at each local day.",
    ),
    "rest_streak_days": _fact_column(
        "v_historical_context_facts",
        "rest_streak_days",
        "metric",
        ("rest_streak_days",),
        "View-derived consecutive rest-day count ending at each local day.",
    ),
    "last_hike_days_ago": _fact_column(
        "v_historical_context_facts",
        "last_hike_days_ago",
        "metric",
        ("last_hike_days_ago",),
        "View-derived day difference from the latest mirrored Hike activity.",
    ),
}


def _validate_sql_identifier(identifier: str) -> None:
    if not _SQL_IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")


def _validate_fact_column_sql_metadata(definition: FactColumnDefinition) -> None:
    _validate_sql_identifier(definition.table_name)
    _validate_sql_identifier(definition.column_name)
    if not definition.sql_type:
        raise ValueError(f"{definition.table_name}.{definition.column_name} missing sql_type")
    if definition.sql_type not in _SUPPORTED_FACT_SQL_TYPES:
        raise ValueError(
            f"{definition.table_name}.{definition.column_name} has unsupported sql_type: {definition.sql_type}"
        )
    if definition.default_sql is not None and definition.default_sql not in _SUPPORTED_FACT_DEFAULT_SQL:
        raise ValueError(
            f"{definition.table_name}.{definition.column_name} has unsafe default_sql: {definition.default_sql}"
        )


def _validate_fact_column_registry() -> None:
    unknown_tables = set(MATERIALIZED_FACT_COLUMN_REGISTRY) - set(MATERIALIZED_FACT_TABLES)
    if unknown_tables:
        raise ValueError(f"Unknown materialized fact tables: {sorted(unknown_tables)}")
    missing_tables = set(MATERIALIZED_FACT_TABLES) - set(MATERIALIZED_FACT_COLUMN_REGISTRY)
    if missing_tables:
        raise ValueError(f"Missing materialized fact table registries: {sorted(missing_tables)}")
    unknown_metadata_tables = set(_MATERIALIZED_FACT_COLUMN_SQL_METADATA) - set(MATERIALIZED_FACT_COLUMN_REGISTRY)
    if unknown_metadata_tables:
        raise ValueError(f"Unknown materialized fact SQL metadata tables: {sorted(unknown_metadata_tables)}")

    for table_name, columns in MATERIALIZED_FACT_COLUMN_REGISTRY.items():
        metadata_columns = set(_MATERIALIZED_FACT_COLUMN_SQL_METADATA.get(table_name, {}))
        unknown_metadata_columns = metadata_columns - set(columns)
        if unknown_metadata_columns:
            raise ValueError(f"{table_name} has SQL metadata for unknown columns: {sorted(unknown_metadata_columns)}")
        for column_name, definition in columns.items():
            if definition.table_name != table_name or definition.column_name != column_name:
                raise ValueError(f"Fact column key mismatch: {table_name}.{column_name}")
            _validate_fact_column_sql_metadata(definition)
            unknown_metric_ids = set(definition.metric_ids) - set(METRIC_REGISTRY)
            if unknown_metric_ids:
                raise ValueError(f"{table_name}.{column_name} references unknown metrics: {sorted(unknown_metric_ids)}")

    for column_name, definition in AGGREGATE_QUERY_PROJECTION_COLUMNS.items():
        if definition.column_name != column_name:
            raise ValueError(f"Aggregate projection key mismatch: {column_name}")
        unknown_metric_ids = set(definition.metric_ids) - set(METRIC_REGISTRY)
        if unknown_metric_ids:
            raise ValueError(f"{column_name} references unknown metrics: {sorted(unknown_metric_ids)}")


_validate_fact_column_registry()


def materialized_fact_column_names(table_name: str) -> frozenset[str]:
    if table_name not in MATERIALIZED_FACT_COLUMN_REGISTRY:
        raise ValueError(f"Unknown materialized fact table: {table_name}")
    return frozenset(MATERIALIZED_FACT_COLUMN_REGISTRY[table_name])


def materialized_fact_column_definition(table_name: str, column_name: str) -> FactColumnDefinition:
    if table_name not in MATERIALIZED_FACT_COLUMN_REGISTRY:
        raise ValueError(f"Unknown materialized fact table: {table_name}")
    if column_name not in MATERIALIZED_FACT_COLUMN_REGISTRY[table_name]:
        raise ValueError(f"Unknown materialized fact column: {table_name}.{column_name}")
    return MATERIALIZED_FACT_COLUMN_REGISTRY[table_name][column_name]


def materialized_fact_column_definition_sql(table_name: str, column_name: str) -> str:
    definition = materialized_fact_column_definition(table_name, column_name)
    parts = [definition.column_name, definition.sql_type]
    if not definition.nullable:
        parts.append("NOT NULL")
    if definition.default_sql is not None:
        parts.extend(("DEFAULT", definition.default_sql))
    return " ".join(parts)


def activity_metric_facts_table_sql() -> str:
    columns = [
        f"    {materialized_fact_column_definition_sql('activity_metric_facts', column_name)}"
        for column_name in MATERIALIZED_FACT_COLUMN_REGISTRY["activity_metric_facts"]
    ]
    columns.append("    PRIMARY KEY (activity_id, metric_version)")
    return "CREATE TABLE activity_metric_facts (\n" + ",\n".join(columns) + "\n);"


def aggregate_query_allowed_columns() -> frozenset[str]:
    columns: set[str] = set(AGGREGATE_QUERY_PROJECTION_COLUMNS)
    for table in MATERIALIZED_FACT_COLUMN_REGISTRY.values():
        columns.update(
            column_name for column_name, definition in table.items() if definition.role in {"metric", "dependency"}
        )
    return frozenset(columns)
