"""Shared constants for the metric registry surface."""

from __future__ import annotations

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
AGGREGATE_BUCKET_INTERVALS = {
    "day": "1 day",
    "week": "1 week",
    "month": "1 month",
    "year": "1 year",
}
SUPPORTED_AGGREGATE_BUCKETS = (*AGGREGATE_BUCKET_INTERVALS, "all_time")
SUPPORTED_AGGREGATE_SCOPES = ("global", "per_sport", "both")
SUPPORTED_ROLLING_WINDOW_DAYS = (7, 14, 28, 42, 90)
MATERIALIZED_ROLLING_WINDOW_DAYS = SUPPORTED_ROLLING_WINDOW_DAYS
DEFAULT_AGGREGATE_QUANTILES = ("p25", "median", "p75")
