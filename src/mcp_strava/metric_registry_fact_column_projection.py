"""Aggregate-query projection column definitions."""

from __future__ import annotations

from mcp_strava.metric_registry_fact_column_model import FactColumnDefinition, _fact_column

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
