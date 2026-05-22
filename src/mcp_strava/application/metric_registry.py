"""Metric registry contract for MCP metric exposure."""

from __future__ import annotations

from mcp_strava.types import ExcludedInterpretation, MetricDefinition

MCP_TOOL_IDS = (
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
)

_DEFAULT_REQUIREMENTS = ["metric_available_from_local_mirror"]
_DEFAULT_MISSING_REASONS = ["not_available_in_source", "insufficient_samples"]


def _metric(
    metric_id: str,
    label: str,
    unit: str,
    source: str,
    scope: str,
    sport_scope: str,
    comparison_mode: str,
    directionality: str,
    exposed_in: list[str],
    description: str = "",
    requirements: list[str] | None = None,
    missing_reasons: list[str] | None = None,
) -> MetricDefinition:
    return MetricDefinition(
        metric_id=metric_id,
        label=label,
        unit=unit,
        source=source,
        scope=scope,
        sport_scope=sport_scope,
        comparison_mode=comparison_mode,
        directionality=directionality,
        requirements=list(requirements or _DEFAULT_REQUIREMENTS),
        missing_reasons=list(missing_reasons or _DEFAULT_MISSING_REASONS),
        exposed_in=exposed_in,
        description=description,
    )


METRIC_REGISTRY: dict[str, MetricDefinition] = {
    "activity_id": _metric("activity_id", "Activity ID", "id", "activity", "activity", "both", "none", "neutral", ["list_workouts", "get_workout_detail"]),
    "activity_date": _metric("activity_date", "Activity Date", "date", "activity", "activity", "both", "none", "neutral", ["list_workouts", "get_workout_detail"]),
    "sport_type": _metric("sport_type", "Sport Type", "category", "activity", "activity", "both", "distribution", "neutral", ["list_workouts", "get_workout_detail", "compare_periods"]),
    "activity_name": _metric("activity_name", "Activity Name", "text", "activity", "activity", "both", "none", "neutral", ["list_workouts", "get_workout_detail"]),
    "distance_km": _metric("distance_km", "Distance", "km", "activity", "activity", "both", "sum", "higher_is_more", ["list_workouts", "get_workout_detail", "compare_periods"]),
    "moving_time_min": _metric("moving_time_min", "Moving Time", "minutes", "activity", "activity", "both", "sum", "higher_is_more", ["list_workouts", "get_workout_detail", "compare_periods"]),
    "elapsed_time_min": _metric("elapsed_time_min", "Elapsed Time", "minutes", "activity", "activity", "both", "sum", "higher_is_more", ["list_workouts", "get_workout_detail", "compare_periods"]),
    "elevation_m": _metric("elevation_m", "Elevation Gain", "m", "activity", "activity", "both", "sum", "higher_is_more", ["list_workouts", "get_workout_detail", "compare_periods"]),
    "start_time": _metric("start_time", "Start Time", "time", "activity", "activity", "both", "none", "neutral", ["list_workouts", "get_workout_detail"]),
    "trimp": _metric("trimp", "TRIMP", "trimp", "activity", "activity", "global", "sum", "higher_is_more", ["list_workouts", "get_workout_detail", "compare_periods"]),
    "avg_hr": _metric("avg_hr", "Average Heart Rate", "bpm", "activity", "activity", "per_sport", "avg", "context", ["list_workouts", "get_workout_detail", "compare_periods"]),
    "max_hr": _metric("max_hr", "Max Heart Rate", "bpm", "activity", "activity", "per_sport", "max", "higher_is_more", ["list_workouts", "get_workout_detail", "compare_periods"]),
    "time_in_hr_zones_min": _metric("time_in_hr_zones_min", "Time In HR Zones", "minutes", "activity", "activity", "both", "distribution", "context", ["get_workout_detail", "compare_periods"]),
    "hr_recovery_pauses": _metric("hr_recovery_pauses", "HR Recovery Pauses", "count", "metrics", "activity", "per_sport", "sum", "context", ["get_workout_detail", "compare_periods"]),
    "hr_recovery_total_rest_sec": _metric("hr_recovery_total_rest_sec", "HR Recovery Rest Time", "seconds", "metrics", "activity", "per_sport", "sum", "context", ["get_workout_detail", "compare_periods"]),
    "hr_recovery_median_bpm_per_min": _metric("hr_recovery_median_bpm_per_min", "HR Recovery Median", "bpm_per_min", "metrics", "activity", "per_sport", "median", "higher_is_better", ["get_workout_detail", "compare_periods"]),
    "hr_recovery_best_bpm_per_min": _metric("hr_recovery_best_bpm_per_min", "HR Recovery Best", "bpm_per_min", "metrics", "activity", "per_sport", "max", "higher_is_better", ["get_workout_detail", "compare_periods"]),
    "hr_recovery_worst_bpm_per_min": _metric("hr_recovery_worst_bpm_per_min", "HR Recovery Worst", "bpm_per_min", "metrics", "activity", "per_sport", "min", "higher_is_worse", ["get_workout_detail", "compare_periods"]),
    "hr_recovery_avg_bpm_per_min": _metric("hr_recovery_avg_bpm_per_min", "HR Recovery Average", "bpm_per_min", "metrics", "activity", "per_sport", "avg", "higher_is_better", ["get_workout_detail", "compare_periods"]),
    "vertical_speed_m_per_h": _metric("vertical_speed_m_per_h", "Vertical Speed", "m_per_hour", "metrics", "activity", "per_sport", "median", "higher_is_more", ["get_workout_detail", "compare_periods"]),
    "vertical_ascent_m": _metric("vertical_ascent_m", "Vertical Ascent", "m", "metrics", "activity", "both", "sum", "higher_is_more", ["get_workout_detail", "compare_periods"]),
    "vertical_duration_h": _metric("vertical_duration_h", "Vertical Duration", "hours", "metrics", "activity", "both", "sum", "higher_is_more", ["get_workout_detail", "compare_periods"]),
    "cardiac_cost": _metric("cardiac_cost", "Cardiac Cost", "ratio", "metrics", "activity", "per_sport", "median", "lower_is_better", ["get_workout_detail", "compare_periods"]),
    "cardiac_cost_adjusted": _metric("cardiac_cost_adjusted", "Cardiac Cost Adjusted", "ratio", "analytics", "activity", "per_sport", "median", "lower_is_better", ["get_workout_detail", "compare_periods"]),
    "cardiac_drift_pct": _metric("cardiac_drift_pct", "Cardiac Drift", "percent", "metrics", "activity", "per_sport", "median", "lower_is_better", ["get_workout_detail", "compare_periods"]),
    "cardiac_drift_severity": _metric("cardiac_drift_severity", "Cardiac Drift Severity", "category", "metrics", "activity", "per_sport", "distribution", "context", ["get_workout_detail", "compare_periods"]),
    "cardiac_drift_quality": _metric("cardiac_drift_quality", "Cardiac Drift Quality", "category", "metrics", "activity", "per_sport", "distribution", "context", ["get_workout_detail", "compare_periods"]),
    "cardiac_drift_significant": _metric("cardiac_drift_significant", "Cardiac Drift Significant", "count", "metrics", "activity", "per_sport", "sum", "higher_is_worse", ["get_workout_detail", "compare_periods"]),
    "hrr_pct": _metric("hrr_pct", "HRR Percent", "percent", "metrics", "activity", "per_sport", "median", "lower_is_easier", ["get_workout_detail", "compare_periods"]),
    "z5_seconds": _metric("z5_seconds", "Z5 Seconds", "seconds", "metrics", "activity", "both", "sum", "higher_is_more", ["get_workout_detail", "compare_periods"]),
    "hr_anomaly_count": _metric("hr_anomaly_count", "HR Anomaly Count", "count", "metrics", "activity", "both", "sum", "higher_is_worse", ["get_workout_detail", "compare_periods"]),
    "daily_trimp": _metric("daily_trimp", "Daily TRIMP", "trimp", "report", "period", "global", "sum", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "total_trimp_14d": _metric("total_trimp_14d", "Total TRIMP 14d", "trimp", "report", "period", "global", "sum", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "avg_trimp_per_day": _metric("avg_trimp_per_day", "Average TRIMP Per Day", "trimp", "report", "period", "global", "avg", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "active_days": _metric("active_days", "Active Days", "count", "report", "period", "global", "sum", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "rest_days": _metric("rest_days", "Rest Days", "count", "report", "period", "global", "sum", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "weekly_trimp": _metric("weekly_trimp", "Weekly TRIMP", "trimp", "report", "period", "global", "sum", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "by_sport_trimp": _metric("by_sport_trimp", "TRIMP By Sport", "trimp", "report", "period", "both", "distribution", "context", ["get_fitness_state", "compare_periods"]),
    "by_sport_distance_km": _metric("by_sport_distance_km", "Distance By Sport", "km", "report", "period", "both", "distribution", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "by_sport_time_min": _metric("by_sport_time_min", "Time By Sport", "minutes", "report", "period", "both", "distribution", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "by_sport_elevation_m": _metric("by_sport_elevation_m", "Elevation By Sport", "m", "report", "period", "both", "distribution", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "fitness": _metric("fitness", "Fitness", "model_units", "training", "model", "global", "last", "higher_is_more", ["get_fitness_state", "compare_periods", "project_fitness_state"]),
    "fatigue": _metric("fatigue", "Fatigue", "model_units", "training", "model", "global", "last", "higher_is_more", ["get_fitness_state", "compare_periods", "project_fitness_state"]),
    "form": _metric("form", "Form", "model_units", "training", "model", "global", "last", "higher_is_more", ["get_fitness_state", "compare_periods", "project_fitness_state"]),
    "form_zone": _metric("form_zone", "Form Zone", "category", "training", "model", "global", "distribution", "context", ["get_fitness_state", "project_fitness_state"]),
    "banister_history": _metric("banister_history", "Banister History", "model_units", "training", "period", "global", "trend", "context", ["get_fitness_state", "compare_periods"]),
    "acwr": _metric("acwr", "ACWR", "ratio", "report", "model", "global", "last", "context", ["get_fitness_state", "compare_periods"]),
    "acwr_zone": _metric("acwr_zone", "ACWR Zone", "category", "report", "model", "global", "distribution", "context", ["get_fitness_state", "compare_periods"]),
    "atl": _metric("atl", "ATL", "model_units", "report", "model", "global", "last", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "ctl": _metric("ctl", "CTL", "model_units", "report", "model", "global", "last", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "acwr_history": _metric("acwr_history", "ACWR History", "ratio", "report", "period", "global", "trend", "context", ["get_fitness_state", "compare_periods"]),
    "daily_avg_trimp_7d": _metric("daily_avg_trimp_7d", "Daily Average TRIMP 7d", "trimp", "analytics", "period", "global", "avg", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "daily_avg_trimp_28d": _metric("daily_avg_trimp_28d", "Daily Average TRIMP 28d", "trimp", "analytics", "period", "global", "avg", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "daily_avg_trimp_90d": _metric("daily_avg_trimp_90d", "Daily Average TRIMP 90d", "trimp", "analytics", "period", "global", "avg", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "rolling_median_cc": _metric("rolling_median_cc", "Rolling Median Cardiac Cost", "ratio", "analytics", "period", "per_sport", "median", "lower_is_better", ["get_fitness_state", "compare_periods"]),
    "rolling_median_cc_adj": _metric("rolling_median_cc_adj", "Rolling Median Adjusted Cardiac Cost", "ratio", "analytics", "period", "per_sport", "median", "lower_is_better", ["get_fitness_state", "compare_periods"]),
    "rolling_median_epkm": _metric("rolling_median_epkm", "Rolling Median Elevation Per KM", "m", "analytics", "period", "per_sport", "median", "context", ["get_fitness_state", "compare_periods"]),
    "volume_7d": _metric("volume_7d", "Volume 7d", "count", "analytics", "period", "both", "sum", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "volume_28d": _metric("volume_28d", "Volume 28d", "count", "analytics", "period", "both", "sum", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "load_trend_pct": _metric("load_trend_pct", "Load Trend", "percent", "analytics", "period", "global", "trend", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "efficiency_trend_pct": _metric("efficiency_trend_pct", "Efficiency Trend", "percent", "analytics", "period", "per_sport", "trend", "lower_is_better", ["get_fitness_state", "compare_periods"]),
    "run_90d_median_cc_trend_pct": _metric("run_90d_median_cc_trend_pct", "Run 90d Median CC Trend", "percent", "analytics", "period", "per_sport", "trend", "lower_is_better", ["get_fitness_state", "compare_periods"]),
    "activity_streak_days": _metric("activity_streak_days", "Activity Streak", "count", "analytics", "period", "global", "last", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "rest_streak_days": _metric("rest_streak_days", "Rest Streak", "count", "analytics", "period", "global", "last", "higher_is_more", ["get_fitness_state", "compare_periods"]),
    "last_hike_days_ago": _metric("last_hike_days_ago", "Last Hike Days Ago", "count", "analytics", "period", "global", "last", "lower_is_recent", ["get_fitness_state", "compare_periods"]),
    "progressive_load_bonus": _metric("progressive_load_bonus", "Progressive Load Bonus", "ratio", "training", "model", "global", "last", "higher_is_more", ["get_fitness_state", "project_fitness_state"]),
    "progressive_cc_trends": _metric("progressive_cc_trends", "Progressive CC Trends", "percent", "training", "model", "per_sport", "trend", "lower_is_better", ["get_fitness_state", "project_fitness_state"]),
    "projected_daily_trimp": _metric("projected_daily_trimp", "Projected Daily TRIMP", "trimp", "training", "projection", "global", "distribution", "context", ["project_fitness_state"]),
    "projected_fitness": _metric("projected_fitness", "Projected Fitness", "model_units", "training", "projection", "global", "last", "higher_is_more", ["project_fitness_state"]),
    "projected_fatigue": _metric("projected_fatigue", "Projected Fatigue", "model_units", "training", "projection", "global", "last", "higher_is_more", ["project_fitness_state"]),
    "projected_form": _metric("projected_form", "Projected Form", "model_units", "training", "projection", "global", "last", "higher_is_more", ["project_fitness_state"]),
    "target_date_form": _metric("target_date_form", "Target Date Form", "model_units", "training", "projection", "global", "last", "higher_is_more", ["project_fitness_state"]),
    "post_weekend_monday_form": _metric("post_weekend_monday_form", "Post Weekend Monday Form", "model_units", "training", "projection", "global", "distribution", "higher_is_more", ["project_fitness_state"]),
    "activity_template_trimp": _metric("activity_template_trimp", "Activity Template TRIMP", "trimp", "training", "projection", "global", "distribution", "context", ["project_fitness_state"]),
}


EXCLUDED_INTERPRETATIONS: dict[str, ExcludedInterpretation] = {
    "recommendation.action": ExcludedInterpretation(
        field="recommendation.action",
        reason="interpretation_label_not_metric",
        preserved_metric_ids=["form", "weekly_trimp", "active_days"],
    ),
    "recommendation.intensity": ExcludedInterpretation(
        field="recommendation.intensity",
        reason="interpretation_label_not_metric",
        preserved_metric_ids=["form", "weekly_trimp", "yesterday_trimp" if "yesterday_trimp" in METRIC_REGISTRY else "daily_trimp"],
    ),
    "recommendation.confidence": ExcludedInterpretation(
        field="recommendation.confidence",
        reason="interpretation_label_not_metric",
        preserved_metric_ids=["active_days", "rest_days"],
    ),
    "weekly_plan.on_track": ExcludedInterpretation(
        field="weekly_plan.on_track",
        reason="derived_boolean_judgment_not_metric",
        preserved_metric_ids=["target_date_form", "form"],
    ),
    "weekly_plan.plan_days.activity": ExcludedInterpretation(
        field="weekly_plan.plan_days.activity",
        reason="nl_activity_label_not_metric",
        preserved_metric_ids=["projected_daily_trimp", "activity_template_trimp"],
    ),
    "safety_warnings.text": ExcludedInterpretation(
        field="safety_warnings.text",
        reason="natural_language_warning_not_metric",
        preserved_metric_ids=["z5_seconds", "hr_anomaly_count", "cardiac_drift_significant"],
    ),
}


def metric_definition(metric_id: str) -> MetricDefinition:
    return METRIC_REGISTRY[metric_id]


def metrics_for_tool(tool_id: str) -> list[MetricDefinition]:
    if tool_id not in MCP_TOOL_IDS:
        raise ValueError(f"Unknown MCP tool id: {tool_id}")
    return sorted(
        [metric for metric in METRIC_REGISTRY.values() if tool_id in metric.exposed_in],
        key=lambda metric: metric.metric_id,
    )


def comparable_metrics(scope: str | None = None, sport_scope: str | None = None) -> list[MetricDefinition]:
    metrics = [metric for metric in METRIC_REGISTRY.values() if metric.comparison_mode != "none"]
    if scope is not None:
        metrics = [metric for metric in metrics if metric.scope == scope]
    if sport_scope is not None:
        metrics = [metric for metric in metrics if metric.sport_scope == sport_scope]
    return sorted(metrics, key=lambda metric: metric.metric_id)


def metric_catalog_payload() -> dict[str, object]:
    return {
        "tool_ids": list(MCP_TOOL_IDS),
        "metrics": [
            {
                "metric_id": metric.metric_id,
                "label": metric.label,
                "unit": metric.unit,
                "source": metric.source,
                "scope": metric.scope,
                "sport_scope": metric.sport_scope,
                "comparison_mode": metric.comparison_mode,
                "directionality": metric.directionality,
                "requirements": metric.requirements,
                "missing_reasons": metric.missing_reasons,
                "exposed_in": metric.exposed_in,
                "description": metric.description,
            }
            for metric in sorted(METRIC_REGISTRY.values(), key=lambda metric: metric.metric_id)
        ],
        "excluded_interpretations": {
            key: {
                "field": value.field,
                "reason": value.reason,
                "preserved_metric_ids": value.preserved_metric_ids,
            }
            for key, value in EXCLUDED_INTERPRETATIONS.items()
        },
    }
