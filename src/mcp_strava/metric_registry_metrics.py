"""Base metric registry assembled from domain metric definition modules."""

from __future__ import annotations

from mcp_strava.metric_registry_metrics_activity import ACTIVITY_METRICS
from mcp_strava.metric_registry_metrics_analytics import ANALYTICS_METRICS
from mcp_strava.metric_registry_metrics_report import REPORT_METRICS
from mcp_strava.metric_registry_metrics_stream import STREAM_METRICS
from mcp_strava.metric_registry_metrics_training import TRAINING_METRICS
from mcp_strava.types import MetricDefinition

_METRIC_GROUPS: tuple[dict[str, MetricDefinition], ...] = (
    ACTIVITY_METRICS,
    STREAM_METRICS,
    REPORT_METRICS,
    TRAINING_METRICS,
    ANALYTICS_METRICS,
)

_METRIC_ORDER: tuple[str, ...] = (
    "activity_id",
    "activity_date",
    "sport_type",
    "activity_name",
    "kudos_count",
    "kudos_names",
    "gear_id",
    "gear_name",
    "gear_distance_km",
    "gear_primary",
    "distance_km",
    "calories",
    "moving_time_min",
    "elapsed_time_min",
    "elevation_m",
    "start_time_local",
    "relative_time",
    "trimp",
    "avg_hr",
    "max_hr",
    "time_in_hr_zones_min",
    "hr_recovery_pauses",
    "hr_recovery_total_rest_sec",
    "hr_recovery_median_bpm_per_min",
    "hr_recovery_best_bpm_per_min",
    "hr_recovery_worst_bpm_per_min",
    "hr_recovery_avg_bpm_per_min",
    "vertical_speed_m_per_h",
    "vertical_ascent_m",
    "vertical_duration_h",
    "cardiac_cost",
    "cardiac_cost_adjusted",
    "cardiac_drift_pct",
    "cardiac_drift_severity",
    "cardiac_drift_significant",
    "cardiac_drift_quality",
    "hrr_pct",
    "hr_anomaly_count",
    "daily_trimp",
    "total_trimp_14d",
    "avg_trimp_per_day",
    "active_days",
    "rest_days",
    "weekly_trimp",
    "by_sport_trimp",
    "by_sport_distance_km",
    "by_sport_time_min",
    "by_sport_elevation_m",
    "fitness",
    "fatigue",
    "form",
    "form_zone",
    "banister_history",
    "acwr",
    "acwr_zone",
    "acwr_history",
    "daily_avg_trimp_7d",
    "daily_avg_trimp_28d",
    "daily_avg_trimp_90d",
    "rolling_median_cc",
    "rolling_median_cc_adj",
    "rolling_median_epkm",
    "rolling_median_hr_recovery",
    "rolling_median_cardiac_drift_pct",
    "volume_7d",
    "volume_28d",
    "load_trend_pct",
    "efficiency_trend_pct",
    "run_90d_median_cc_trend_pct",
    "activity_streak_days",
    "rest_streak_days",
    "last_hike_days_ago",
    "progressive_load_bonus",
    "progressive_cc_trends",
    "projected_daily_trimp",
    "projected_fitness",
    "projected_fatigue",
    "projected_form",
    "target_date_form",
    "post_weekend_monday_form",
    "activity_template_trimp",
)

_ALL_METRICS: dict[str, MetricDefinition] = {}
for _group in _METRIC_GROUPS:
    _ALL_METRICS.update(_group)

METRIC_REGISTRY: dict[str, MetricDefinition] = {metric_id: _ALL_METRICS[metric_id] for metric_id in _METRIC_ORDER}
