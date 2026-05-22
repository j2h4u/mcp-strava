"""Metric registry contract tests for Phase 05 plan 05-01."""

from mcp_strava.application.metric_registry import (
    EXCLUDED_INTERPRETATIONS,
    MCP_TOOL_IDS,
    METRIC_REGISTRY,
    metrics_for_tool,
)
import pytest


REQUIRED_METRIC_IDS = {
    "activity_id",
    "activity_date",
    "sport_type",
    "activity_name",
    "distance_km",
    "moving_time_min",
    "elapsed_time_min",
    "elevation_m",
    "start_time",
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
    "cardiac_drift_quality",
    "cardiac_drift_significant",
    "hrr_pct",
    "z5_seconds",
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
    "atl",
    "ctl",
    "acwr_history",
    "daily_avg_trimp_7d",
    "daily_avg_trimp_28d",
    "daily_avg_trimp_90d",
    "rolling_median_cc",
    "rolling_median_cc_adj",
    "rolling_median_epkm",
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
}

ALLOWED_SPORT_SCOPE = {"global", "per_sport", "both"}
ALLOWED_COMPARISON_MODE = {"sum", "avg", "median", "last", "min", "max", "trend", "distribution", "none"}
ALLOWED_TOOLS = {
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
}


def test_registry_covers_required_metric_ids():
    missing = REQUIRED_METRIC_IDS - set(METRIC_REGISTRY.keys())
    assert not missing, f"Missing required metric ids: {sorted(missing)}"


def test_registry_entries_have_required_metadata():
    for metric in METRIC_REGISTRY.values():
        assert metric.metric_id
        assert metric.unit
        assert metric.source
        assert metric.scope
        assert metric.sport_scope
        assert metric.comparison_mode
        assert metric.directionality
        assert metric.requirements
        assert metric.missing_reasons
        assert metric.exposed_in


def test_registry_entry_enums_and_tool_allowlist():
    for metric in METRIC_REGISTRY.values():
        assert metric.sport_scope in ALLOWED_SPORT_SCOPE
        assert metric.comparison_mode in ALLOWED_COMPARISON_MODE
        unknown_tools = set(metric.exposed_in) - ALLOWED_TOOLS
        assert not unknown_tools, f"{metric.metric_id} has unknown tool ids: {sorted(unknown_tools)}"

    assert set(MCP_TOOL_IDS) == ALLOWED_TOOLS


def test_excluded_interpretations_map_to_preserved_numeric_facts():
    required_exclusions = {
        "recommendation.action",
        "recommendation.intensity",
        "recommendation.confidence",
        "weekly_plan.on_track",
        "weekly_plan.plan_days.activity",
        "safety_warnings.text",
    }
    missing = required_exclusions - set(EXCLUDED_INTERPRETATIONS.keys())
    assert not missing, f"Missing interpretation exclusions: {sorted(missing)}"

    for key, exclusion in EXCLUDED_INTERPRETATIONS.items():
        assert exclusion.field == key
        assert exclusion.preserved_metric_ids, f"{key} must preserve at least one numeric/model input metric"


def test_unknown_tool_id_is_rejected():
    with pytest.raises(ValueError):
        metrics_for_tool("get_data_status")
