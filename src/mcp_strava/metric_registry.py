"""Core metric registry contract.

The registry inventories every Strava-sourced, calculated, or deliberately
derived metric. MCP tools expose filtered subsets through ``exposed_in``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from mcp_strava.types import ExcludedInterpretation, MetricDefinition, StatusFactDefinition

MCP_TOOL_IDS = (
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
    "get_training_aggregates",
)

AGGREGATE_MODES = (
    "sum",
    "calendar_average",
    "weighted_average",
    "ratio_of_sums",
    "quantile",
    "last_state",
    "distribution",
    "kudos_count",
)
SUPPORTED_AGGREGATE_BUCKETS = ("day", "week", "month", "year", "all_time")
SUPPORTED_AGGREGATE_SCOPES = ("global", "per_sport", "both")
SUPPORTED_ROLLING_WINDOW_DAYS = (7, 14, 28, 42, 90)
MATERIALIZED_ROLLING_WINDOW_DAYS = SUPPORTED_ROLLING_WINDOW_DAYS
DEFAULT_AGGREGATE_QUANTILES = ("p25", "median", "p75")

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

_DEFAULT_REQUIREMENTS = ["metric_available_from_local_mirror"]
_DEFAULT_MISSING_REASONS = ["not_available_in_source", "insufficient_samples"]
_CALCULATION_BY_METRIC_ID = {
    "activity_id": "Direct Strava activity id stored in activities.id.",
    "activity_date": "Local activity day derived from the stored Strava activity start date.",
    "sport_type": "Direct Strava sport_type stored on the activity row.",
    "activity_name": "Direct Strava activity name stored on the activity row.",
    "kudos_count": "Strava summary_json.kudos_count for the activity, defaulting to 0 when Strava omitted it.",
    "kudos_names": "Names stored from the Strava kudos endpoint for the activity, grouped by activity_id and formatted from firstname and lastname.",
    "gear_id": "Strava gear id copied from the activity summary or detail payload when mirrored for an activity.",
    "gear_name": "Gear or shoe display name copied from the detailed Strava gear payload when it is mirrored for an activity.",
    "gear_distance_km": "Total mirrored Strava gear distance in meters divided by 1000 when the detailed gear payload provides distance.",
    "gear_primary": "Boolean primary-gear flag copied from the detailed Strava gear payload when Strava marks a shoe as primary.",
    "distance_km": "Activity distance_m from the mirror divided by 1000.",
    "calories": "Strava's reported calories (kcal) per activity, summed over the period.",
    "moving_time_min": "Activity moving_time_s from the mirror divided by 60.",
    "elapsed_time_min": "Activity elapsed_time_s from the mirror divided by 60.",
    "elevation_m": "Activity total elevation gain in meters from the mirrored Strava activity.",
    "start_time": "HH:MM extracted from summary_json.start_date_local when Strava provided it.",
    "trimp": "Per-activity TRIMP = sum(seconds in each HR zone * zone weight) / 60 using the configured HR zone model and athlete resting HR.",
    "avg_hr": "Strava summary_json.average_heartrate for the activity.",
    "max_hr": "Strava summary_json.max_heartrate rounded to an integer bpm.",
    "time_in_hr_zones_min": "Counts stream heartrate samples in the five configured HR zones and divides seconds by 60.",
    "hr_recovery_pauses": "Count of detected rest pauses from HR recovery analysis; pauses are >= Config.Metrics.MIN_PAUSE_SEC with velocity < Config.Thresholds.VEL_STOP.",
    "hr_recovery_total_rest_sec": "Total seconds across detected HR recovery rest pauses.",
    "hr_recovery_median_bpm_per_min": "Median HR drop rate across detected rest pauses, in bpm per minute.",
    "hr_recovery_best_bpm_per_min": "Maximum HR drop rate across detected rest pauses, in bpm per minute.",
    "hr_recovery_worst_bpm_per_min": "Minimum HR drop rate across detected rest pauses, in bpm per minute.",
    "hr_recovery_avg_bpm_per_min": "Arithmetic mean HR drop rate across detected rest pauses, in bpm per minute.",
    "vertical_speed_m_per_h": "Positive altitude gain from altitude stream divided by elapsed stream duration in hours.",
    "vertical_ascent_m": "Sum of positive altitude deltas from the altitude stream.",
    "vertical_duration_h": "Elapsed stream duration used for vertical speed, computed from the last stream time_offset / 3600.",
    "cardiac_cost": "Average stream heartrate divided by average stream velocity for points above Config.Thresholds.VEL_MOVING.",
    "cardiac_cost_adjusted": "Elevation-adjusted cardiac cost = cardiac_cost - Config.Efficiency.CC_ELEV_COEFF * elevation_gain_m_per_km.",
    "cardiac_drift_pct": "Jenks-clusters moving stream velocity into pace bands, compares early vs late median HR inside bands, and returns weighted HR drift percent.",
    "cardiac_drift_severity": "Cardiac drift severity label from the Jenks-based algorithm: stable, borderline, moderate, significant, or severe.",
    "cardiac_drift_significant": "Boolean activity flag materialized as 1 when the cardiac drift algorithm marks the drift significant, otherwise 0.",
    "cardiac_drift_quality": "Cardiac drift algorithm quality label based on clustered data duration: good, fair, or low.",
    "hrr_pct": "(median_hr - athlete_hr_rest) / (observed_hr_max - athlete_hr_rest) * 100, using MCP_STRAVA_HR_REST.",
    "hr_anomaly_count": "Count of consecutive stream heartrate jumps greater than 30 bpm.",
    "daily_trimp": "Daily effective TRIMP series from daily_load_facts, using observed TRIMP on complete HR days and 0 for rest or unknown days.",
    "total_trimp_14d": "Sum of effective_trimp over the 14-day rolling window ending at the query day.",
    "avg_trimp_per_day": "total_trimp_14d divided by 14.",
    "active_days": "Count of days with activity_count > 0 in the 14-day rolling window.",
    "rest_days": "Count of days with activity_count = 0 in the 14-day rolling window.",
    "weekly_trimp": "Sum of effective_trimp over the 7-day rolling window ending at the query day.",
    "by_sport_trimp": "Period TRIMP grouped by sport from enriched activity/report rows.",
    "by_sport_distance_km": "Period distance grouped by sport from mirrored activity distance_m divided by 1000.",
    "by_sport_time_min": "Period moving time grouped by sport from mirrored moving_time_s divided by 60.",
    "by_sport_elevation_m": "Period elevation gain grouped by sport from mirrored elevation_gain_m.",
    "fitness": "Banister long-term fitness EWMA of daily effective_trimp using Config.Model.Banister.TAU_FITNESS.",
    "fatigue": "Banister short-term fatigue EWMA of daily effective_trimp using Config.Model.Banister.TAU_FATIGUE.",
    "form": "Banister form = fitness - fatigue.",
    "form_zone": "Agent-friendly form category: tired when form < -5, normal when -5 <= form < 10, fresh when form >= 10.",
    "banister_history": "Daily Banister time series of fitness, fatigue, form, form_zone, and TRIMP for recent/report windows.",
    "acwr": "Acute:chronic workload ratio stored as fatigue / fitness when fitness > 0.",
    "acwr_zone": "Agent-friendly ACWR category: sweet_spot for 0.8-1.3, caution up to Config.Thresholds.ACWR_DANGER, danger above it, undertrained below 0.8.",
    "acwr_history": "Daily ACWR time series with the fatigue and fitness inputs used for each point.",
    "daily_avg_trimp_7d": "7-day rolling effective_trimp sum divided by 7.",
    "daily_avg_trimp_28d": "28-day rolling effective_trimp sum divided by 28.",
    "daily_avg_trimp_90d": "90-day rolling effective_trimp sum divided by 90.",
    "rolling_median_cc": "Rolling median cardiac_cost from materialized activity_metric_facts for the selected window.",
    "rolling_median_cc_adj": "Rolling median cardiac_cost_adjusted from materialized activity_metric_facts for the selected window.",
    "rolling_median_epkm": "Rolling median elevation gain per kilometer from per-activity analytics rows.",
    "rolling_median_hr_recovery": "Rolling median hr_recovery_median_bpm_per_min from materialized activity_metric_facts for the selected window.",
    "rolling_median_cardiac_drift_pct": "Rolling median cardiac_drift_pct from materialized activity_metric_facts for the selected window.",
    "volume_7d": "Activity count over the 7-day rolling window.",
    "volume_28d": "Activity count over the 28-day rolling window.",
    "load_trend_pct": "Percent change of rolling daily TRIMP load between the current window and the previous equally sized window.",
    "efficiency_trend_pct": "Percent change of per-sport rolling cardiac efficiency metrics, especially median cardiac cost.",
    "run_90d_median_cc_trend_pct": "Percent change of 90-day running median cardiac cost versus the previous 90-day running window.",
    "activity_streak_days": "Count of consecutive recent days with at least one activity.",
    "rest_streak_days": "Count of consecutive recent days without activity.",
    "last_hike_days_ago": "Days since the latest mirrored Hike activity.",
    "progressive_load_bonus": "Progressive-overload scalar from 21-day quality trends; positive when quality improves, negative when fatigue signals worsen.",
    "progressive_cc_trends": "Per-sport cardiac-cost trend bundle used by the progressive signal calculation.",
    "projected_daily_trimp": "Scenario input TRIMP for each projected day: rest=0, easy=Config.Plan.TRIMP_EASY, maintain=recent weekday pattern, custom=user input.",
    "projected_fitness": "Forward-simulated Banister fitness from current baseline and projected_daily_trimp.",
    "projected_fatigue": "Forward-simulated Banister fatigue from current baseline and projected_daily_trimp.",
    "projected_form": "Forward-simulated projected_fitness - projected_fatigue.",
    "target_date_form": "The final projected_form value on the requested target_date for a scenario.",
    "post_weekend_monday_form": "When target_date is Friday-Sunday, forward-simulates rest days after target_date and reports the following Monday form.",
    "activity_template_trimp": "Scenario template TRIMP value, currently Config.Plan.TRIMP_EASY for the easy scenario.",
}


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
    calculation: str | None = None,
    requirements: list[str] | None = None,
    missing_reasons: list[str] | None = None,
) -> MetricDefinition:
    calculation_text = calculation or _CALCULATION_BY_METRIC_ID.get(metric_id, "")
    if not calculation_text:
        raise ValueError(f"Missing calculation description for metric: {metric_id}")
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
        calculation=calculation_text,
        description=description,
    )


METRIC_REGISTRY: dict[str, MetricDefinition] = {
    "activity_id": _metric(
        "activity_id",
        "Activity ID",
        "id",
        "activity",
        "activity",
        "both",
        "none",
        "neutral",
        ["list_workouts", "get_workout_detail"],
    ),
    "activity_date": _metric(
        "activity_date",
        "Activity Date",
        "date",
        "activity",
        "activity",
        "both",
        "none",
        "neutral",
        ["list_workouts", "get_workout_detail"],
    ),
    "sport_type": _metric(
        "sport_type",
        "Sport Type",
        "category",
        "activity",
        "activity",
        "both",
        "distribution",
        "neutral",
        ["list_workouts", "get_workout_detail"],
    ),
    "activity_name": _metric(
        "activity_name",
        "Activity Name",
        "text",
        "activity",
        "activity",
        "both",
        "none",
        "neutral",
        ["list_workouts", "get_workout_detail"],
    ),
    "kudos_count": _metric(
        "kudos_count",
        "Kudos Count",
        "count",
        "activity",
        "activity",
        "both",
        "none",
        "context",
        ["list_workouts", "get_workout_detail"],
    ),
    "kudos_names": _metric(
        "kudos_names",
        "Kudos Names",
        "text_list",
        "activity",
        "activity",
        "both",
        "none",
        "context",
        ["get_workout_detail"],
    ),
    "gear_id": _metric(
        "gear_id", "Gear ID", "id", "activity", "activity", "both", "none", "context", ["get_workout_detail"]
    ),
    "gear_name": _metric(
        "gear_name", "Gear Name", "text", "activity", "activity", "both", "none", "context", ["get_workout_detail"]
    ),
    "gear_distance_km": _metric(
        "gear_distance_km",
        "Gear Distance",
        "km",
        "activity",
        "activity",
        "both",
        "none",
        "context",
        ["get_workout_detail"],
    ),
    "gear_primary": _metric(
        "gear_primary",
        "Primary Gear",
        "boolean",
        "activity",
        "activity",
        "both",
        "none",
        "context",
        ["get_workout_detail"],
    ),
    "distance_km": _metric(
        "distance_km",
        "Distance",
        "km",
        "activity",
        "activity",
        "both",
        "sum",
        "higher_is_more",
        ["list_workouts", "get_workout_detail", "compare_periods"],
    ),
    # Raw kcal passthrough; mirrors distance_km (sum metric). Aggregate metadata
    # in _AGGREGATE_METADATA_BY_METRIC_ID, fact column in the activity_metric_facts
    # _fact_table block, value source activity_metric_facts.calories_kcal.
    # Aggregate/digest-only (weekly/monthly digest + period comparison) — NOT a
    # per-workout row metric, so exposed_in omits list_workouts/get_workout_detail
    # (those tool payloads are hand-built and would have to emit it). Digest and
    # compare exposure come from AGGREGATE_METRIC_BUNDLES membership below.
    "calories": _metric(
        "calories",
        "Calories",
        "kcal",
        "activity",
        "activity",
        "both",
        "sum",
        "higher_is_more",
        ["compare_periods"],
    ),
    "moving_time_min": _metric(
        "moving_time_min",
        "Moving Time",
        "minutes",
        "activity",
        "activity",
        "both",
        "sum",
        "higher_is_more",
        ["list_workouts", "get_workout_detail", "compare_periods"],
    ),
    "elapsed_time_min": _metric(
        "elapsed_time_min",
        "Elapsed Time",
        "minutes",
        "activity",
        "activity",
        "both",
        "sum",
        "higher_is_more",
        ["get_workout_detail", "compare_periods"],
    ),
    "elevation_m": _metric(
        "elevation_m",
        "Elevation Gain",
        "m",
        "activity",
        "activity",
        "both",
        "sum",
        "higher_is_more",
        ["list_workouts", "get_workout_detail", "compare_periods"],
    ),
    "start_time": _metric(
        "start_time", "Start Time", "time", "activity", "activity", "both", "none", "neutral", ["get_workout_detail"]
    ),
    "trimp": _metric(
        "trimp",
        "TRIMP",
        "trimp",
        "activity",
        "activity",
        "global",
        "sum",
        "higher_is_more",
        ["list_workouts", "get_workout_detail", "compare_periods"],
    ),
    "avg_hr": _metric(
        "avg_hr",
        "Average Heart Rate",
        "bpm",
        "activity",
        "activity",
        "per_sport",
        "avg",
        "context",
        ["list_workouts", "get_workout_detail", "compare_periods"],
    ),
    "max_hr": _metric(
        "max_hr",
        "Max Heart Rate",
        "bpm",
        "activity",
        "activity",
        "per_sport",
        "max",
        "higher_is_more",
        ["list_workouts", "get_workout_detail", "compare_periods"],
    ),
    "time_in_hr_zones_min": _metric(
        "time_in_hr_zones_min",
        "Time In HR Zones",
        "minutes",
        "activity",
        "activity",
        "both",
        "distribution",
        "context",
        ["get_workout_detail", "compare_periods"],
    ),
    "hr_recovery_pauses": _metric(
        "hr_recovery_pauses",
        "HR Recovery Pauses",
        "count",
        "metrics",
        "activity",
        "per_sport",
        "sum",
        "context",
        ["get_workout_detail", "compare_periods"],
    ),
    "hr_recovery_total_rest_sec": _metric(
        "hr_recovery_total_rest_sec",
        "HR Recovery Rest Time",
        "seconds",
        "metrics",
        "activity",
        "per_sport",
        "sum",
        "context",
        ["get_workout_detail", "compare_periods"],
    ),
    "hr_recovery_median_bpm_per_min": _metric(
        "hr_recovery_median_bpm_per_min",
        "HR Recovery Median",
        "bpm_per_min",
        "metrics",
        "activity",
        "per_sport",
        "median",
        "higher_is_better",
        ["get_workout_detail", "compare_periods"],
    ),
    "hr_recovery_best_bpm_per_min": _metric(
        "hr_recovery_best_bpm_per_min",
        "HR Recovery Best",
        "bpm_per_min",
        "metrics",
        "activity",
        "per_sport",
        "max",
        "higher_is_better",
        ["get_workout_detail", "compare_periods"],
    ),
    "hr_recovery_worst_bpm_per_min": _metric(
        "hr_recovery_worst_bpm_per_min",
        "HR Recovery Worst",
        "bpm_per_min",
        "metrics",
        "activity",
        "per_sport",
        "min",
        "higher_is_worse",
        ["get_workout_detail", "compare_periods"],
    ),
    "hr_recovery_avg_bpm_per_min": _metric(
        "hr_recovery_avg_bpm_per_min",
        "HR Recovery Average",
        "bpm_per_min",
        "metrics",
        "activity",
        "per_sport",
        "avg",
        "higher_is_better",
        ["get_workout_detail", "compare_periods"],
    ),
    "vertical_speed_m_per_h": _metric(
        "vertical_speed_m_per_h",
        "Vertical Speed",
        "m_per_hour",
        "metrics",
        "activity",
        "per_sport",
        "median",
        "higher_is_more",
        ["get_workout_detail", "compare_periods"],
    ),
    "vertical_ascent_m": _metric(
        "vertical_ascent_m",
        "Vertical Ascent",
        "m",
        "metrics",
        "activity",
        "both",
        "sum",
        "higher_is_more",
        ["get_workout_detail", "compare_periods"],
    ),
    "vertical_duration_h": _metric(
        "vertical_duration_h",
        "Vertical Duration",
        "hours",
        "metrics",
        "activity",
        "both",
        "sum",
        "higher_is_more",
        ["get_workout_detail", "compare_periods"],
    ),
    "cardiac_cost": _metric(
        "cardiac_cost",
        "Cardiac Cost",
        "ratio",
        "metrics",
        "activity",
        "per_sport",
        "median",
        "lower_is_better",
        ["get_workout_detail", "compare_periods"],
    ),
    "cardiac_cost_adjusted": _metric(
        "cardiac_cost_adjusted",
        "Cardiac Cost Adjusted",
        "ratio",
        "metrics",
        "activity",
        "per_sport",
        "median",
        "lower_is_better",
        ["get_workout_detail", "compare_periods"],
    ),
    "cardiac_drift_pct": _metric(
        "cardiac_drift_pct",
        "Cardiac Drift",
        "percent",
        "metrics",
        "activity",
        "per_sport",
        "median",
        "lower_is_better",
        ["get_workout_detail", "compare_periods"],
    ),
    "cardiac_drift_severity": _metric(
        "cardiac_drift_severity",
        "Cardiac Drift Severity",
        "category",
        "metrics",
        "activity",
        "per_sport",
        "distribution",
        "context",
        ["get_workout_detail"],
    ),
    "cardiac_drift_significant": _metric(
        "cardiac_drift_significant",
        "Cardiac Drift Significant",
        "count",
        "metrics",
        "activity",
        "per_sport",
        "sum",
        "higher_is_worse",
        ["get_workout_detail", "compare_periods"],
    ),
    "cardiac_drift_quality": _metric(
        "cardiac_drift_quality",
        "Cardiac Drift Quality",
        "category",
        "metrics",
        "activity",
        "per_sport",
        "distribution",
        "context",
        ["get_workout_detail"],
    ),
    "hrr_pct": _metric(
        "hrr_pct",
        "HRR Percent",
        "percent",
        "metrics",
        "activity",
        "per_sport",
        "median",
        "lower_is_easier",
        ["get_workout_detail", "compare_periods"],
    ),
    "hr_anomaly_count": _metric(
        "hr_anomaly_count",
        "HR Anomaly Count",
        "count",
        "metrics",
        "activity",
        "both",
        "sum",
        "higher_is_worse",
        ["get_workout_detail", "compare_periods"],
    ),
    "daily_trimp": _metric(
        "daily_trimp", "Daily TRIMP", "trimp", "report", "period", "global", "sum", "higher_is_more", []
    ),
    "total_trimp_14d": _metric(
        "total_trimp_14d",
        "Total TRIMP 14d",
        "trimp",
        "report",
        "period",
        "global",
        "sum",
        "higher_is_more",
        ["get_fitness_state", "compare_periods"],
    ),
    "avg_trimp_per_day": _metric(
        "avg_trimp_per_day",
        "Average TRIMP Per Day",
        "trimp",
        "report",
        "period",
        "global",
        "avg",
        "higher_is_more",
        ["get_fitness_state", "compare_periods"],
    ),
    "active_days": _metric(
        "active_days",
        "Active Days",
        "count",
        "report",
        "period",
        "global",
        "sum",
        "higher_is_more",
        ["get_fitness_state", "compare_periods"],
    ),
    "rest_days": _metric(
        "rest_days",
        "Rest Days",
        "count",
        "report",
        "period",
        "global",
        "sum",
        "higher_is_more",
        ["get_fitness_state", "compare_periods"],
    ),
    "weekly_trimp": _metric(
        "weekly_trimp",
        "Weekly TRIMP",
        "trimp",
        "report",
        "period",
        "global",
        "sum",
        "higher_is_more",
        ["get_fitness_state", "compare_periods"],
    ),
    "by_sport_trimp": _metric(
        "by_sport_trimp", "TRIMP By Sport", "trimp", "report", "period", "both", "distribution", "context", []
    ),
    "by_sport_distance_km": _metric(
        "by_sport_distance_km",
        "Distance By Sport",
        "km",
        "report",
        "period",
        "both",
        "distribution",
        "higher_is_more",
        [],
    ),
    "by_sport_time_min": _metric(
        "by_sport_time_min",
        "Time By Sport",
        "minutes",
        "report",
        "period",
        "both",
        "distribution",
        "higher_is_more",
        [],
    ),
    "by_sport_elevation_m": _metric(
        "by_sport_elevation_m",
        "Elevation By Sport",
        "m",
        "report",
        "period",
        "both",
        "distribution",
        "higher_is_more",
        [],
    ),
    "fitness": _metric(
        "fitness",
        "Fitness",
        "model_units",
        "training",
        "model",
        "global",
        "last",
        "higher_is_more",
        ["get_fitness_state", "compare_periods"],
    ),
    "fatigue": _metric(
        "fatigue",
        "Fatigue",
        "model_units",
        "training",
        "model",
        "global",
        "last",
        "higher_is_more",
        ["get_fitness_state", "compare_periods"],
    ),
    "form": _metric(
        "form",
        "Form",
        "model_units",
        "training",
        "model",
        "global",
        "last",
        "higher_is_more",
        ["get_fitness_state", "compare_periods"],
    ),
    "form_zone": _metric(
        "form_zone", "Form Zone", "category", "training", "model", "global", "none", "context", ["get_fitness_state"]
    ),
    "banister_history": _metric(
        "banister_history", "Banister History", "model_units", "training", "period", "global", "trend", "context", []
    ),
    "acwr": _metric(
        "acwr",
        "ACWR",
        "ratio",
        "report",
        "model",
        "global",
        "last",
        "context",
        ["get_fitness_state", "compare_periods"],
    ),
    "acwr_zone": _metric(
        "acwr_zone", "ACWR Zone", "category", "report", "model", "global", "none", "context", ["get_fitness_state"]
    ),
    "acwr_history": _metric(
        "acwr_history", "ACWR History", "ratio", "report", "period", "global", "trend", "context", []
    ),
    "daily_avg_trimp_7d": _metric(
        "daily_avg_trimp_7d",
        "Daily Average TRIMP 7d",
        "trimp",
        "analytics",
        "period",
        "global",
        "avg",
        "higher_is_more",
        ["get_fitness_state", "compare_periods"],
    ),
    "daily_avg_trimp_28d": _metric(
        "daily_avg_trimp_28d",
        "Daily Average TRIMP 28d",
        "trimp",
        "analytics",
        "period",
        "global",
        "avg",
        "higher_is_more",
        ["get_fitness_state", "compare_periods"],
    ),
    "daily_avg_trimp_90d": _metric(
        "daily_avg_trimp_90d",
        "Daily Average TRIMP 90d",
        "trimp",
        "analytics",
        "period",
        "global",
        "avg",
        "higher_is_more",
        ["get_fitness_state", "compare_periods"],
    ),
    "rolling_median_cc": _metric(
        "rolling_median_cc",
        "Rolling Median Cardiac Cost",
        "ratio",
        "analytics",
        "period",
        "per_sport",
        "median",
        "lower_is_better",
        ["get_fitness_state", "compare_periods"],
    ),
    "rolling_median_cc_adj": _metric(
        "rolling_median_cc_adj",
        "Rolling Median Adjusted Cardiac Cost",
        "ratio",
        "analytics",
        "period",
        "per_sport",
        "median",
        "lower_is_better",
        ["get_fitness_state", "compare_periods"],
    ),
    "rolling_median_epkm": _metric(
        "rolling_median_epkm",
        "Rolling Median Elevation Per KM",
        "m_per_km",
        "analytics",
        "period",
        "per_sport",
        "median",
        "context",
        [],
    ),
    "rolling_median_hr_recovery": _metric(
        "rolling_median_hr_recovery",
        "Rolling Median HR Recovery",
        "bpm_per_min",
        "analytics",
        "period",
        "per_sport",
        "median",
        "higher_is_better",
        ["get_fitness_state", "compare_periods"],
    ),
    "rolling_median_cardiac_drift_pct": _metric(
        "rolling_median_cardiac_drift_pct",
        "Rolling Median Cardiac Drift",
        "percent",
        "analytics",
        "period",
        "per_sport",
        "median",
        "lower_is_better",
        ["get_fitness_state", "compare_periods"],
    ),
    "volume_7d": _metric(
        "volume_7d",
        "Volume 7d",
        "count",
        "analytics",
        "period",
        "global",
        "sum",
        "higher_is_more",
        ["get_fitness_state", "compare_periods"],
    ),
    "volume_28d": _metric(
        "volume_28d",
        "Volume 28d",
        "count",
        "analytics",
        "period",
        "global",
        "sum",
        "higher_is_more",
        ["get_fitness_state", "compare_periods"],
    ),
    "load_trend_pct": _metric(
        "load_trend_pct", "Load Trend", "percent", "analytics", "period", "global", "trend", "higher_is_more", []
    ),
    "efficiency_trend_pct": _metric(
        "efficiency_trend_pct",
        "Efficiency Trend",
        "percent",
        "analytics",
        "period",
        "per_sport",
        "trend",
        "lower_is_better",
        [],
    ),
    "run_90d_median_cc_trend_pct": _metric(
        "run_90d_median_cc_trend_pct",
        "Run 90d Median CC Trend",
        "percent",
        "analytics",
        "period",
        "per_sport",
        "trend",
        "lower_is_better",
        [],
    ),
    "activity_streak_days": _metric(
        "activity_streak_days",
        "Activity Streak",
        "count",
        "analytics",
        "period",
        "global",
        "last",
        "higher_is_more",
        [],
    ),
    "rest_streak_days": _metric(
        "rest_streak_days", "Rest Streak", "count", "analytics", "period", "global", "last", "higher_is_more", []
    ),
    "last_hike_days_ago": _metric(
        "last_hike_days_ago",
        "Last Hike Days Ago",
        "count",
        "analytics",
        "period",
        "global",
        "last",
        "lower_is_recent",
        [],
    ),
    "progressive_load_bonus": _metric(
        "progressive_load_bonus",
        "Progressive Load Bonus",
        "ratio",
        "training",
        "model",
        "global",
        "last",
        "higher_is_more",
        [],
    ),
    "progressive_cc_trends": _metric(
        "progressive_cc_trends",
        "Progressive CC Trends",
        "percent",
        "training",
        "model",
        "per_sport",
        "trend",
        "lower_is_better",
        [],
    ),
    "projected_daily_trimp": _metric(
        "projected_daily_trimp",
        "Projected Daily TRIMP",
        "trimp",
        "training",
        "projection",
        "global",
        "distribution",
        "context",
        ["project_fitness_state"],
    ),
    "projected_fitness": _metric(
        "projected_fitness",
        "Projected Fitness",
        "model_units",
        "training",
        "projection",
        "global",
        "last",
        "higher_is_more",
        ["project_fitness_state"],
    ),
    "projected_fatigue": _metric(
        "projected_fatigue",
        "Projected Fatigue",
        "model_units",
        "training",
        "projection",
        "global",
        "last",
        "higher_is_more",
        ["project_fitness_state"],
    ),
    "projected_form": _metric(
        "projected_form",
        "Projected Form",
        "model_units",
        "training",
        "projection",
        "global",
        "last",
        "higher_is_more",
        ["project_fitness_state"],
    ),
    "target_date_form": _metric(
        "target_date_form",
        "Target Date Form",
        "model_units",
        "training",
        "projection",
        "global",
        "last",
        "higher_is_more",
        ["project_fitness_state"],
    ),
    "post_weekend_monday_form": _metric(
        "post_weekend_monday_form",
        "Post Weekend Monday Form",
        "model_units",
        "training",
        "projection",
        "global",
        "distribution",
        "higher_is_more",
        ["project_fitness_state"],
    ),
    "activity_template_trimp": _metric(
        "activity_template_trimp",
        "Activity Template TRIMP",
        "trimp",
        "training",
        "projection",
        "global",
        "distribution",
        "context",
        ["project_fitness_state"],
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


def _fact_column(
    table_name: str,
    column_name: str,
    role: str,
    metric_ids: tuple[str, ...] = (),
    description: str = "",
) -> FactColumnDefinition:
    if role not in FACT_COLUMN_ROLES:
        raise ValueError(f"Unknown fact column role: {role}")
    return FactColumnDefinition(
        table_name=table_name,
        column_name=column_name,
        role=role,
        metric_ids=metric_ids,
        description=description,
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


def _validate_fact_column_registry() -> None:
    unknown_tables = set(MATERIALIZED_FACT_COLUMN_REGISTRY) - set(MATERIALIZED_FACT_TABLES)
    if unknown_tables:
        raise ValueError(f"Unknown materialized fact tables: {sorted(unknown_tables)}")
    missing_tables = set(MATERIALIZED_FACT_TABLES) - set(MATERIALIZED_FACT_COLUMN_REGISTRY)
    if missing_tables:
        raise ValueError(f"Missing materialized fact table registries: {sorted(missing_tables)}")

    for table_name, columns in MATERIALIZED_FACT_COLUMN_REGISTRY.items():
        for column_name, definition in columns.items():
            if definition.table_name != table_name or definition.column_name != column_name:
                raise ValueError(f"Fact column key mismatch: {table_name}.{column_name}")
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


def _status_fact(
    code: str,
    metric_id: str,
    *,
    threshold: dict[str, Any],
    window: dict[str, Any],
    evidence_keys: list[str],
    completeness_reasons: list[str],
    calculation: str,
    materialized_from: str,
) -> StatusFactDefinition:
    if metric_id not in METRIC_REGISTRY:
        raise ValueError(f"Unknown status fact metric id: {metric_id}")
    return StatusFactDefinition(
        code=code,
        metric_id=metric_id,
        threshold=dict(threshold),
        window=dict(window),
        evidence_keys=list(evidence_keys),
        completeness_reasons=list(completeness_reasons),
        calculation=calculation,
        materialized_from=materialized_from,
    )


STATUS_FACT_REGISTRY: dict[str, StatusFactDefinition] = {
    "stale_mirror_data": _status_fact(
        "stale_mirror_data",
        "activity_date",
        threshold={"max_age_days": 1},
        window={"lookback_days": 1},
        evidence_keys=["last_success_at", "age_days", "threshold_days"],
        completeness_reasons=["refresh_state_missing", "last_success_missing"],
        calculation="Active when the latest mirror refresh success is older than the registered freshness age.",
        materialized_from="refresh_state",
    ),
    "stale_read_model_facts": _status_fact(
        "stale_read_model_facts",
        "fitness",
        threshold={"max_age_days": 1, "dirty_count": 0},
        window={"lookback_days": 1},
        evidence_keys=["last_materialized_at", "age_days", "dirty_count"],
        completeness_reasons=["read_model_run_missing", "read_model_unavailable"],
        calculation="Active when read-model materialization is older than the registered age or dirty rows remain.",
        materialized_from="read_model_refresh_runs,metric_dirty_activities",
    ),
    "missing_hr": _status_fact(
        "missing_hr",
        "avg_hr",
        threshold={"heartrate_sample_count": 1},
        window={"lookback_days": 14},
        evidence_keys=["activity_count", "activity_ids"],
        completeness_reasons=["no_activity_facts"],
        calculation="Active when recent materialized activity facts include activities with zero heart-rate samples.",
        materialized_from="activity_metric_facts",
    ),
    "missing_streams": _status_fact(
        "missing_streams",
        "time_in_hr_zones_min",
        threshold={"stream_sample_count": 1},
        window={"lookback_days": 14},
        evidence_keys=["activity_count", "activity_ids"],
        completeness_reasons=["no_activity_facts"],
        calculation="Active when recent materialized activity facts include activities with zero stream samples.",
        materialized_from="activity_metric_facts",
    ),
    "excessive_z5_exposure": _status_fact(
        "excessive_z5_exposure",
        "time_in_hr_zones_min",
        threshold={"zone5_seconds": 300, "z5_lower_bound_bpm": 177},
        window={"lookback_days": 7},
        evidence_keys=["activity_id", "activity_day", "zone5_seconds", "z5_lower_bound_bpm"],
        completeness_reasons=["no_activity_facts", "missing_hr"],
        calculation="Active when a recent materialized activity has zone5_seconds above the registered Z5 duration threshold.",
        materialized_from="activity_metric_facts",
    ),
    "hr_anomaly_burst": _status_fact(
        "hr_anomaly_burst",
        "hr_anomaly_count",
        threshold={"hr_anomaly_count": 3, "jump_bpm": 30},
        window={"lookback_days": 7},
        evidence_keys=["activity_id", "activity_day", "hr_anomaly_count", "jump_bpm"],
        completeness_reasons=["no_activity_facts", "missing_hr"],
        calculation="Active when a recent materialized activity has at least the registered count of 30 bpm heart-rate jumps.",
        materialized_from="activity_metric_facts",
    ),
    "cardiac_drift_significant_quality": _status_fact(
        "cardiac_drift_significant_quality",
        "cardiac_drift_significant",
        threshold={"cardiac_drift_significant": 1, "quality": ["good", "fair"]},
        window={"lookback_days": 7},
        evidence_keys=["activity_id", "activity_day", "cardiac_drift_significant", "cardiac_drift_quality"],
        completeness_reasons=["no_activity_facts", "missing_streams"],
        calculation="Active when a recent materialized activity is significant for cardiac drift and quality is good or fair.",
        materialized_from="activity_metric_facts",
    ),
    "consecutive_high_load_hikes": _status_fact(
        "consecutive_high_load_hikes",
        "trimp",
        threshold={"combined_trimp": 800, "consecutive_days": 2},
        window={"lookback_days": 7},
        evidence_keys=["hike_days", "combined_trimp"],
        completeness_reasons=["insufficient_hike_history", "no_activity_facts"],
        calculation="Active when two consecutive Hike days in the local read model have combined TRIMP above the registered threshold.",
        materialized_from="activity_metric_facts",
    ),
    "running_volume_jump": _status_fact(
        "running_volume_jump",
        "distance_km",
        threshold={"caution_pct": 10, "high_pct": 15},
        window={"week_start": "monday", "comparison": "previous_week"},
        evidence_keys=["current_week_distance_km", "previous_week_distance_km", "increase_pct"],
        completeness_reasons=["no_previous_running_week", "no_current_running_week"],
        calculation="Active when current Monday-start running distance exceeds previous week distance by a registered percentage threshold.",
        materialized_from="activity_metric_facts",
    ),
}


def materialized_fact_column_names(table_name: str) -> frozenset[str]:
    if table_name not in MATERIALIZED_FACT_COLUMN_REGISTRY:
        raise ValueError(f"Unknown materialized fact table: {table_name}")
    return frozenset(MATERIALIZED_FACT_COLUMN_REGISTRY[table_name])


def aggregate_query_allowed_columns() -> frozenset[str]:
    columns: set[str] = set(AGGREGATE_QUERY_PROJECTION_COLUMNS)
    for table in MATERIALIZED_FACT_COLUMN_REGISTRY.values():
        columns.update(
            column_name for column_name, definition in table.items() if definition.role in {"metric", "dependency"}
        )
    return frozenset(columns)


EXCLUDED_INTERPRETATIONS: dict[str, ExcludedInterpretation] = {
    "recommendation.action": ExcludedInterpretation(
        field="recommendation.action",
        reason="interpretation_label_not_metric",
        preserved_metric_ids=["form", "weekly_trimp", "active_days"],
    ),
    "recommendation.intensity": ExcludedInterpretation(
        field="recommendation.intensity",
        reason="interpretation_label_not_metric",
        preserved_metric_ids=["form", "weekly_trimp", "active_days"],
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
        preserved_metric_ids=["time_in_hr_zones_min", "hr_anomaly_count", "cardiac_drift_significant"],
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


def metrics_for_aggregate_bundle(bundle_id: str) -> tuple[str, ...]:
    if bundle_id not in AGGREGATE_METRIC_BUNDLES:
        raise ValueError(f"Unknown aggregate bundle id: {bundle_id}")
    return AGGREGATE_METRIC_BUNDLES[bundle_id]


def comparable_metrics(scope: str | None = None, sport_scope: str | None = None) -> list[MetricDefinition]:
    metrics = [metric for metric in METRIC_REGISTRY.values() if metric.comparison_mode != "none"]
    if scope is not None:
        metrics = [metric for metric in metrics if metric.scope == scope]
    if sport_scope is not None:
        metrics = [metric for metric in metrics if metric.sport_scope == sport_scope]
    return sorted(metrics, key=lambda metric: metric.metric_id)


def metric_catalog_payload() -> dict[str, Any]:
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
                "calculation": metric.calculation,
                "description": metric.description,
                "aggregate_mode": metric.aggregate_mode,
                "aggregate_source": metric.aggregate_source,
                "denominator": metric.denominator,
                "weight_column": metric.weight_column,
                "numerator_column": metric.numerator_column,
                "denominator_column": metric.denominator_column,
                "value_column": metric.value_column,
                "sample_size_column": metric.sample_size_column,
                "supported_buckets": metric.supported_buckets,
                "supported_scopes": metric.supported_scopes,
                "bundle_ids": metric.bundle_ids,
                "quantiles": metric.quantiles,
                "metric_version_policy": metric.metric_version_policy,
                "rolling_window_days": metric.rolling_window_days,
                "fixed_rolling_window": metric.fixed_rolling_window,
            }
            for metric in sorted(METRIC_REGISTRY.values(), key=lambda metric: metric.metric_id)
        ],
        "aggregate": {
            "modes": list(AGGREGATE_MODES),
            "buckets": list(SUPPORTED_AGGREGATE_BUCKETS),
            "scopes": list(SUPPORTED_AGGREGATE_SCOPES),
            "rolling_window_days": list(SUPPORTED_ROLLING_WINDOW_DAYS),
            "materialized_rolling_window_days": list(MATERIALIZED_ROLLING_WINDOW_DAYS),
            "bundles": {
                bundle_id: list(metric_ids) for bundle_id, metric_ids in sorted(AGGREGATE_METRIC_BUNDLES.items())
            },
        },
        "status_facts": [
            {
                "code": definition.code,
                "metric_id": definition.metric_id,
                "threshold": definition.threshold,
                "window": definition.window,
                "evidence_keys": definition.evidence_keys,
                "completeness_reasons": definition.completeness_reasons,
                "calculation": definition.calculation,
                "materialized_from": definition.materialized_from,
            }
            for definition in STATUS_FACT_REGISTRY.values()
        ],
        "materialized_fact_columns": {
            table_name: [
                {
                    "column_name": column.column_name,
                    "role": column.role,
                    "metric_ids": list(column.metric_ids),
                    "description": column.description,
                }
                for column in columns.values()
            ]
            for table_name, columns in MATERIALIZED_FACT_COLUMN_REGISTRY.items()
        },
        "aggregate_query_columns": sorted(aggregate_query_allowed_columns()),
        "excluded_interpretations": {
            key: {
                "field": value.field,
                "reason": value.reason,
                "preserved_metric_ids": value.preserved_metric_ids,
            }
            for key, value in EXCLUDED_INTERPRETATIONS.items()
        },
    }
