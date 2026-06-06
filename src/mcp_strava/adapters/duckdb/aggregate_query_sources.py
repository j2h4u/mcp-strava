"""Prepared aggregate fact source metadata."""

from __future__ import annotations

SOURCE_VIEWS = {
    "activity_summary_fact": "v_activity_aggregate_facts",
    "activity_metric_fact": "v_activity_aggregate_facts",
    "daily_load_fact": "v_daily_aggregate_facts",
    "training_model_fact": "v_training_model_state_facts",
    "rolling_period_fact": "v_rolling_aggregate_facts",
    "social_fact": "v_activity_aggregate_facts",
    "historical_fact": "v_historical_context_facts",
}
SOURCE_DAY_COLUMNS = {
    "activity_summary_fact": "activity_day",
    "activity_metric_fact": "activity_day",
    "daily_load_fact": "day",
    "training_model_fact": "day",
    "rolling_period_fact": "as_of_day",
    "social_fact": "activity_day",
    "historical_fact": "day",
}


def view_has_sport(source: str) -> bool:
    return source in {
        "activity_summary_fact",
        "activity_metric_fact",
        "daily_load_fact",
        "training_model_fact",
        "rolling_period_fact",
        "social_fact",
        "historical_fact",
    }
