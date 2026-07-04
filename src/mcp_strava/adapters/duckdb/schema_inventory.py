"""DuckDB schema inventory constants."""

from __future__ import annotations

DUCKDB_TABLES: tuple[str, ...] = (
    "activities",
    "streams",
    "stream_channels",
    "sync_log",
    "kudos",
    "refresh_state",
    "refresh_requests",
    "activity_source_state",
    "metric_dirty_activities",
    "activity_metric_facts",
    "daily_load_facts",
    "training_model_daily",
    "rolling_period_facts",
    "read_model_refresh_runs",
    "read_model_logic_version",
)

DATE_COLUMNS: dict[str, tuple[str, ...]] = {
    "activities": ("activity_day",),
    "activity_source_state": ("activity_day",),
    "metric_dirty_activities": ("activity_day",),
    "activity_metric_facts": ("activity_day",),
    "daily_load_facts": ("day",),
    "training_model_daily": ("day",),
    "rolling_period_facts": ("as_of_day",),
}

DUCKDB_VIEWS: tuple[str, ...] = (
    "v_activity_aggregate_facts",
    "v_daily_aggregate_facts",
    "v_training_model_state_facts",
    "v_historical_context_facts",
    "v_rolling_aggregate_facts",
    "v_metric_version_status",
)
