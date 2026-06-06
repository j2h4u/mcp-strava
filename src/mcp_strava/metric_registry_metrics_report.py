"""Report metric definitions."""

from __future__ import annotations

from mcp_strava.metric_registry_metric_factory import _metric
from mcp_strava.types import MetricDefinition

REPORT_METRICS: dict[str, MetricDefinition] = {
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
}
