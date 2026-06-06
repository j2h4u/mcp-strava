"""Aggregate metric bundles and aggregate metadata decoration."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from mcp_strava.metric_registry_metrics import METRIC_REGISTRY
from mcp_strava.metric_registry_shared import (
    AGGREGATE_MODES,
    DEFAULT_AGGREGATE_QUANTILES,
    SUPPORTED_AGGREGATE_BUCKETS,
    SUPPORTED_AGGREGATE_SCOPES,
    SUPPORTED_ROLLING_WINDOW_DAYS,
)

AGGREGATE_METRIC_BUNDLES: dict[str, tuple[str, ...]] = {
    "daily_brief": (
        "fitness",
        "fatigue",
        "form",
        "form_zone",
        "acwr",
        "acwr_zone",
        "weekly_trimp",
        "total_trimp_14d",
        "avg_trimp_per_day",
        "active_days",
        "rest_days",
        "daily_avg_trimp_7d",
        "rolling_median_cc",
        "rolling_median_hr_recovery",
        "kudos_count",
    ),
    "weekly_digest": (
        "trimp",
        "distance_km",
        "calories",
        "moving_time_min",
        "elapsed_time_min",
        "elevation_m",
        "active_days",
        "weekly_trimp",
        "volume_7d",
        "avg_hr",
        "max_hr",
        "cardiac_cost",
        "cardiac_cost_adjusted",
        "cardiac_drift_pct",
        "hrr_pct",
    ),
    "monthly_digest": (
        "trimp",
        "distance_km",
        "calories",
        "moving_time_min",
        "elevation_m",
        "active_days",
        "volume_28d",
        "daily_avg_trimp_28d",
        "daily_avg_trimp_90d",
        "fitness",
        "fatigue",
        "form",
    ),
    "period_comparison": (
        "trimp",
        "distance_km",
        "calories",
        "moving_time_min",
        "elapsed_time_min",
        "elevation_m",
        "active_days",
        "rest_days",
        "fitness",
        "fatigue",
        "form",
        "acwr",
        "avg_hr",
        "max_hr",
        "hr_recovery_median_bpm_per_min",
        "vertical_speed_m_per_h",
        "cardiac_cost",
        "cardiac_cost_adjusted",
        "cardiac_drift_pct",
        "hrr_pct",
        "cardiac_drift_significant",
        "time_in_hr_zones_min",
    ),
    "sport_efficiency": (
        "avg_hr",
        "hr_recovery_median_bpm_per_min",
        "vertical_speed_m_per_h",
        "cardiac_cost",
        "cardiac_cost_adjusted",
        "cardiac_drift_pct",
        "hrr_pct",
        "rolling_median_cc",
        "rolling_median_cc_adj",
        "rolling_median_hr_recovery",
        "rolling_median_cardiac_drift_pct",
    ),
    "historical_facts": (
        "sport_type",
        "form_zone",
        "acwr_zone",
        "cardiac_drift_severity",
        "cardiac_drift_quality",
        "kudos_count",
        "active_days",
        "activity_streak_days",
        "rest_streak_days",
        "last_hike_days_ago",
    ),
}


def _agg(
    mode: str,
    source: str,
    *,
    denominator: str | None = None,
    weight_column: str | None = None,
    numerator_column: str | None = None,
    denominator_column: str | None = None,
    value_column: str | None = None,
    sample_size_column: str = "activity_count",
    supported_buckets: tuple[str, ...] = SUPPORTED_AGGREGATE_BUCKETS,
    supported_scopes: tuple[str, ...] = ("both",),
    quantiles: tuple[str, ...] = (),
    metric_version_policy: str = "mixed_degraded",
    rolling_window_days: int | None = None,
    fixed_rolling_window: bool = False,
) -> dict[str, Any]:
    if mode not in AGGREGATE_MODES:
        raise ValueError(f"Unknown aggregate mode: {mode}")
    unknown_buckets = set(supported_buckets) - set(SUPPORTED_AGGREGATE_BUCKETS)
    if unknown_buckets:
        raise ValueError(f"Unknown aggregate buckets: {sorted(unknown_buckets)}")
    unknown_scopes = set(supported_scopes) - set(SUPPORTED_AGGREGATE_SCOPES)
    if unknown_scopes:
        raise ValueError(f"Unknown aggregate scopes: {sorted(unknown_scopes)}")
    if rolling_window_days is not None and rolling_window_days not in SUPPORTED_ROLLING_WINDOW_DAYS:
        raise ValueError(f"Unknown rolling window days: {rolling_window_days}")
    return {
        "aggregate_mode": mode,
        "aggregate_source": source,
        "denominator": denominator,
        "weight_column": weight_column,
        "numerator_column": numerator_column,
        "denominator_column": denominator_column,
        "value_column": value_column,
        "sample_size_column": sample_size_column,
        "supported_buckets": list(supported_buckets),
        "supported_scopes": list(supported_scopes),
        "quantiles": list(quantiles),
        "metric_version_policy": metric_version_policy,
        "rolling_window_days": rolling_window_days,
        "fixed_rolling_window": fixed_rolling_window,
    }


_AGGREGATE_METADATA_BY_METRIC_ID: dict[str, dict[str, Any]] = {
    "sport_type": _agg(
        "distribution",
        "activity_summary_fact",
        denominator="activity_count",
        value_column="sport_type",
        sample_size_column="activity_count",
        supported_scopes=("both",),
        metric_version_policy="mixed_allowed",
    ),
    "kudos_count": _agg(
        "kudos_count",
        "social_fact",
        denominator="activity_count",
        value_column="kudos_count",
        sample_size_column="activity_count",
        supported_scopes=("both",),
        metric_version_policy="mixed_allowed",
    ),
    "distance_km": _agg(
        "sum",
        "activity_summary_fact",
        denominator="distance_m",
        value_column="distance_m",
        sample_size_column="activity_count",
        supported_scopes=("both",),
    ),
    # value_column has no unit conversion (kcal stays kcal), so unlike distance_km
    # it needs NO _METRIC_VALUE_EXPRESSIONS entry — the aggregate sums calories_kcal
    # directly (same as trimp). Reads v_activity_aggregate_facts.calories_kcal.
    "calories": _agg(
        "sum",
        "activity_summary_fact",
        denominator="calories_kcal",
        value_column="calories_kcal",
        sample_size_column="activity_count",
        supported_scopes=("both",),
    ),
    "moving_time_min": _agg(
        "sum",
        "activity_summary_fact",
        denominator="moving_time_s",
        value_column="moving_time_s",
        sample_size_column="activity_count",
        supported_scopes=("both",),
    ),
    "elapsed_time_min": _agg(
        "sum",
        "activity_summary_fact",
        denominator="elapsed_time_s",
        value_column="elapsed_time_s",
        sample_size_column="activity_count",
        supported_scopes=("both",),
    ),
    "elevation_m": _agg(
        "sum",
        "activity_summary_fact",
        denominator="elevation_gain_m",
        value_column="elevation_gain_m",
        sample_size_column="activity_count",
        supported_scopes=("both",),
    ),
    "trimp": _agg(
        "sum",
        "activity_metric_fact",
        denominator="trimp",
        value_column="trimp",
        sample_size_column="activity_count",
        supported_scopes=("global",),
    ),
    "avg_hr": _agg(
        "weighted_average",
        "activity_summary_fact",
        denominator="heartrate_sample_count",
        weight_column="heartrate_sample_count",
        denominator_column="heartrate_sample_count",
        value_column="avg_hr",
        sample_size_column="heartrate_sample_count",
        supported_scopes=("per_sport",),
    ),
    "max_hr": _agg(
        "quantile",
        "activity_summary_fact",
        denominator="heartrate_sample_count",
        weight_column="heartrate_sample_count",
        denominator_column="heartrate_sample_count",
        value_column="max_hr",
        sample_size_column="heartrate_sample_count",
        supported_scopes=("per_sport",),
        quantiles=DEFAULT_AGGREGATE_QUANTILES,
    ),
    "time_in_hr_zones_min": _agg(
        "distribution",
        "activity_metric_fact",
        denominator="heartrate_sample_count",
        value_column="hr_zone_seconds",
        sample_size_column="heartrate_sample_count",
        supported_scopes=("both",),
    ),
    "hr_recovery_median_bpm_per_min": _agg(
        "quantile",
        "activity_metric_fact",
        denominator="activity_sample_count",
        value_column="hr_recovery_median_rate",
        sample_size_column="activity_sample_count",
        supported_scopes=("per_sport",),
        quantiles=DEFAULT_AGGREGATE_QUANTILES,
    ),
    "vertical_speed_m_per_h": _agg(
        "ratio_of_sums",
        "activity_metric_fact",
        denominator="vertical_speed_duration_hours",
        numerator_column="vertical_speed_total_ascent_m",
        denominator_column="vertical_speed_duration_hours",
        value_column="vertical_speed_vmh",
        sample_size_column="activity_sample_count",
        supported_scopes=("per_sport",),
    ),
    "cardiac_cost": _agg(
        "quantile",
        "activity_metric_fact",
        denominator="activity_sample_count",
        value_column="cardiac_cost",
        sample_size_column="activity_sample_count",
        supported_scopes=("per_sport",),
        quantiles=DEFAULT_AGGREGATE_QUANTILES,
    ),
    "cardiac_cost_adjusted": _agg(
        "quantile",
        "activity_metric_fact",
        denominator="activity_sample_count",
        value_column="adjusted_cardiac_cost",
        sample_size_column="activity_sample_count",
        supported_scopes=("per_sport",),
        quantiles=DEFAULT_AGGREGATE_QUANTILES,
    ),
    "cardiac_drift_pct": _agg(
        "quantile",
        "activity_metric_fact",
        denominator="activity_sample_count",
        value_column="cardiac_drift_pct",
        sample_size_column="activity_sample_count",
        supported_scopes=("per_sport",),
        quantiles=DEFAULT_AGGREGATE_QUANTILES,
    ),
    "cardiac_drift_severity": _agg(
        "distribution",
        "activity_metric_fact",
        denominator="activity_count",
        value_column="cardiac_drift_severity",
        sample_size_column="activity_count",
        supported_scopes=("per_sport",),
    ),
    "cardiac_drift_significant": _agg(
        "sum",
        "activity_metric_fact",
        denominator="cardiac_drift_significant",
        value_column="cardiac_drift_significant",
        sample_size_column="activity_count",
        supported_scopes=("per_sport",),
    ),
    "cardiac_drift_quality": _agg(
        "distribution",
        "activity_metric_fact",
        denominator="activity_count",
        value_column="cardiac_drift_quality",
        sample_size_column="activity_count",
        supported_scopes=("per_sport",),
    ),
    "hrr_pct": _agg(
        "quantile",
        "activity_metric_fact",
        denominator="activity_sample_count",
        value_column="hrr_pct",
        sample_size_column="activity_sample_count",
        supported_scopes=("per_sport",),
        quantiles=DEFAULT_AGGREGATE_QUANTILES,
    ),
    "total_trimp_14d": _agg(
        "sum",
        "daily_load_fact",
        denominator="effective_trimp",
        value_column="effective_trimp",
        sample_size_column="calendar_day_count",
        supported_scopes=("global",),
    ),
    "avg_trimp_per_day": _agg(
        "calendar_average",
        "daily_load_fact",
        denominator="calendar_days",
        denominator_column="calendar_days",
        value_column="effective_trimp",
        sample_size_column="calendar_day_count",
        supported_scopes=("global",),
    ),
    "active_days": _agg(
        "sum",
        "daily_load_fact",
        denominator="active_day_count",
        value_column="active_day_count",
        sample_size_column="calendar_day_count",
        supported_scopes=("global",),
    ),
    "rest_days": _agg(
        "sum",
        "daily_load_fact",
        denominator="rest_day_count",
        value_column="rest_day_count",
        sample_size_column="calendar_day_count",
        supported_scopes=("global",),
    ),
    "weekly_trimp": _agg(
        "sum",
        "daily_load_fact",
        denominator="effective_trimp",
        value_column="effective_trimp",
        sample_size_column="calendar_day_count",
        supported_scopes=("global",),
    ),
    "fitness": _agg(
        "last_state",
        "training_model_fact",
        denominator="latest_day",
        value_column="fitness",
        sample_size_column="model_day_count",
        supported_scopes=("global",),
    ),
    "fatigue": _agg(
        "last_state",
        "training_model_fact",
        denominator="latest_day",
        value_column="fatigue",
        sample_size_column="model_day_count",
        supported_scopes=("global",),
    ),
    "form": _agg(
        "last_state",
        "training_model_fact",
        denominator="latest_day",
        value_column="form",
        sample_size_column="model_day_count",
        supported_scopes=("global",),
    ),
    "form_zone": _agg(
        "distribution",
        "training_model_fact",
        denominator="model_day_count",
        value_column="form_zone",
        sample_size_column="model_day_count",
        supported_scopes=("global",),
    ),
    "acwr": _agg(
        "last_state",
        "training_model_fact",
        denominator="latest_day",
        value_column="acwr",
        sample_size_column="model_day_count",
        supported_scopes=("global",),
    ),
    "acwr_zone": _agg(
        "distribution",
        "training_model_fact",
        denominator="model_day_count",
        value_column="acwr_zone",
        sample_size_column="model_day_count",
        supported_scopes=("global",),
    ),
    "daily_avg_trimp_7d": _agg(
        "calendar_average",
        "rolling_period_fact",
        denominator="calendar_days",
        denominator_column="calendar_days",
        value_column="daily_avg_trimp_7d",
        sample_size_column="calendar_day_count",
        supported_scopes=("global",),
        rolling_window_days=7,
        fixed_rolling_window=True,
    ),
    "daily_avg_trimp_28d": _agg(
        "calendar_average",
        "rolling_period_fact",
        denominator="calendar_days",
        denominator_column="calendar_days",
        value_column="daily_avg_trimp_28d",
        sample_size_column="calendar_day_count",
        supported_scopes=("global",),
        rolling_window_days=28,
        fixed_rolling_window=True,
    ),
    "daily_avg_trimp_90d": _agg(
        "calendar_average",
        "rolling_period_fact",
        denominator="calendar_days",
        denominator_column="calendar_days",
        value_column="daily_avg_trimp_90d",
        sample_size_column="calendar_day_count",
        supported_scopes=("global",),
        rolling_window_days=90,
        fixed_rolling_window=True,
    ),
    "rolling_median_cc": _agg(
        "quantile",
        "rolling_period_fact",
        denominator="rolling_sample_count",
        value_column="median_cardiac_cost",
        sample_size_column="rolling_sample_count",
        supported_scopes=("per_sport",),
        quantiles=DEFAULT_AGGREGATE_QUANTILES,
        rolling_window_days=90,
    ),
    "rolling_median_cc_adj": _agg(
        "quantile",
        "rolling_period_fact",
        denominator="rolling_sample_count",
        value_column="median_adjusted_cardiac_cost",
        sample_size_column="rolling_sample_count",
        supported_scopes=("per_sport",),
        quantiles=DEFAULT_AGGREGATE_QUANTILES,
        rolling_window_days=90,
    ),
    "rolling_median_hr_recovery": _agg(
        "quantile",
        "rolling_period_fact",
        denominator="rolling_sample_count",
        value_column="median_hr_recovery",
        sample_size_column="rolling_sample_count",
        supported_scopes=("per_sport",),
        quantiles=DEFAULT_AGGREGATE_QUANTILES,
        rolling_window_days=90,
    ),
    "rolling_median_cardiac_drift_pct": _agg(
        "quantile",
        "rolling_period_fact",
        denominator="rolling_sample_count",
        value_column="median_cardiac_drift_pct",
        sample_size_column="rolling_sample_count",
        supported_scopes=("per_sport",),
        quantiles=DEFAULT_AGGREGATE_QUANTILES,
        rolling_window_days=90,
    ),
    "volume_7d": _agg(
        "last_state",
        "rolling_period_fact",
        denominator="latest_day",
        value_column="activity_count",
        sample_size_column="calendar_day_count",
        supported_scopes=("global",),
        rolling_window_days=7,
        fixed_rolling_window=True,
    ),
    "volume_28d": _agg(
        "last_state",
        "rolling_period_fact",
        denominator="latest_day",
        value_column="activity_count",
        sample_size_column="calendar_day_count",
        supported_scopes=("global",),
        rolling_window_days=28,
        fixed_rolling_window=True,
    ),
    "activity_streak_days": _agg(
        "last_state",
        "historical_fact",
        denominator="latest_day",
        value_column="activity_streak_days",
        sample_size_column="calendar_day_count",
        supported_scopes=("global",),
        metric_version_policy="mixed_allowed",
    ),
    "rest_streak_days": _agg(
        "last_state",
        "historical_fact",
        denominator="latest_day",
        value_column="rest_streak_days",
        sample_size_column="calendar_day_count",
        supported_scopes=("global",),
        metric_version_policy="mixed_allowed",
    ),
    "last_hike_days_ago": _agg(
        "last_state",
        "historical_fact",
        denominator="latest_day",
        value_column="last_hike_days_ago",
        sample_size_column="calendar_day_count",
        supported_scopes=("global",),
        metric_version_policy="mixed_allowed",
    ),
}


def _bundle_ids_by_metric_id(metric_id: str) -> list[str]:
    return [bundle_id for bundle_id, metric_ids in AGGREGATE_METRIC_BUNDLES.items() if metric_id in metric_ids]


def _apply_aggregate_metadata() -> None:
    known_metric_ids = set(METRIC_REGISTRY)
    for bundle_id, metric_ids in AGGREGATE_METRIC_BUNDLES.items():
        unknown = set(metric_ids) - known_metric_ids
        if unknown:
            raise ValueError(f"{bundle_id} has unknown metric ids: {sorted(unknown)}")
        missing_metadata = set(metric_ids) - set(_AGGREGATE_METADATA_BY_METRIC_ID)
        if missing_metadata:
            raise ValueError(f"{bundle_id} has metrics without aggregate metadata: {sorted(missing_metadata)}")

    for metric_id, metadata in _AGGREGATE_METADATA_BY_METRIC_ID.items():
        if metric_id not in METRIC_REGISTRY:
            raise ValueError(f"Unknown aggregate metric id: {metric_id}")
        exposed_in = list(METRIC_REGISTRY[metric_id].exposed_in)
        if "get_training_aggregates" not in exposed_in:
            exposed_in.append("get_training_aggregates")
        METRIC_REGISTRY[metric_id] = replace(
            METRIC_REGISTRY[metric_id],
            bundle_ids=_bundle_ids_by_metric_id(metric_id),
            exposed_in=exposed_in,
            **metadata,
        )


_apply_aggregate_metadata()


def _apply_compare_periods_exposure() -> None:
    compare_metrics = set(AGGREGATE_METRIC_BUNDLES["period_comparison"])
    for metric_id, metric in tuple(METRIC_REGISTRY.items()):
        exposed_in = [tool_id for tool_id in metric.exposed_in if tool_id != "compare_periods"]
        if metric_id in compare_metrics and metric.comparison_mode != "none":
            exposed_in.append("compare_periods")
        METRIC_REGISTRY[metric_id] = replace(metric, exposed_in=exposed_in)


_apply_compare_periods_exposure()
