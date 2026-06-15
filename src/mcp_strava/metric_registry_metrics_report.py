"""Report metric definitions."""

from __future__ import annotations

from mcp_strava.metric_registry_metric_factory import _metric
from mcp_strava.metric_registry_specs import MetricSpec
from mcp_strava.types import MetricDefinition

REPORT_METRICS: dict[str, MetricDefinition] = {
    "daily_trimp": _metric(
        "daily_trimp",
        MetricSpec(
            label="Daily TRIMP",
            unit="trimp",
            source="report",
            scope="period",
            sport_scope="global",
            comparison_mode="sum",
            directionality="higher_is_more",
        ),
        [],
    ),
    "total_trimp_14d": _metric(
        "total_trimp_14d",
        MetricSpec(
            label="Total TRIMP 14d",
            unit="trimp",
            source="report",
            scope="period",
            sport_scope="global",
            comparison_mode="sum",
            directionality="higher_is_more",
        ),
        ["get_fitness_state", "compare_periods"],
    ),
    "avg_trimp_per_day": _metric(
        "avg_trimp_per_day",
        MetricSpec(
            label="Average TRIMP Per Day",
            unit="trimp",
            source="report",
            scope="period",
            sport_scope="global",
            comparison_mode="avg",
            directionality="higher_is_more",
        ),
        ["get_fitness_state", "compare_periods"],
    ),
    "active_days": _metric(
        "active_days",
        MetricSpec(
            label="Active Days",
            unit="count",
            source="report",
            scope="period",
            sport_scope="global",
            comparison_mode="sum",
            directionality="higher_is_more",
        ),
        ["get_fitness_state", "compare_periods"],
    ),
    "rest_days": _metric(
        "rest_days",
        MetricSpec(
            label="Rest Days",
            unit="count",
            source="report",
            scope="period",
            sport_scope="global",
            comparison_mode="sum",
            directionality="higher_is_more",
        ),
        ["get_fitness_state", "compare_periods"],
    ),
    "weekly_trimp": _metric(
        "weekly_trimp",
        MetricSpec(
            label="Weekly TRIMP",
            unit="trimp",
            source="report",
            scope="period",
            sport_scope="global",
            comparison_mode="sum",
            directionality="higher_is_more",
        ),
        ["get_fitness_state", "compare_periods"],
    ),
    "by_sport_trimp": _metric(
        "by_sport_trimp",
        MetricSpec(
            label="TRIMP By Sport",
            unit="trimp",
            source="report",
            scope="period",
            sport_scope="both",
            comparison_mode="distribution",
            directionality="context",
        ),
        [],
    ),
    "by_sport_distance_km": _metric(
        "by_sport_distance_km",
        MetricSpec(
            label="Distance By Sport",
            unit="km",
            source="report",
            scope="period",
            sport_scope="both",
            comparison_mode="distribution",
            directionality="higher_is_more",
        ),
        [],
    ),
    "by_sport_time_min": _metric(
        "by_sport_time_min",
        MetricSpec(
            label="Time By Sport",
            unit="minutes",
            source="report",
            scope="period",
            sport_scope="both",
            comparison_mode="distribution",
            directionality="higher_is_more",
        ),
        [],
    ),
    "by_sport_elevation_m": _metric(
        "by_sport_elevation_m",
        MetricSpec(
            label="Elevation By Sport",
            unit="m",
            source="report",
            scope="period",
            sport_scope="both",
            comparison_mode="distribution",
            directionality="higher_is_more",
        ),
        [],
    ),
    "acwr": _metric(
        "acwr",
        MetricSpec(
            label="ACWR",
            unit="ratio",
            source="report",
            scope="model",
            sport_scope="global",
            comparison_mode="last",
            directionality="context",
        ),
        ["get_fitness_state", "compare_periods"],
    ),
    "acwr_zone": _metric(
        "acwr_zone",
        MetricSpec(
            label="ACWR Zone",
            unit="category",
            source="report",
            scope="model",
            sport_scope="global",
            comparison_mode="none",
            directionality="context",
        ),
        ["get_fitness_state"],
    ),
    "acwr_history": _metric(
        "acwr_history",
        MetricSpec(
            label="ACWR History",
            unit="ratio",
            source="report",
            scope="period",
            sport_scope="global",
            comparison_mode="trend",
            directionality="context",
        ),
        [],
    ),
}
