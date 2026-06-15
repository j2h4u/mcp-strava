"""Training metric definitions."""

from __future__ import annotations

from mcp_strava.metric_registry_metric_factory import _metric
from mcp_strava.metric_registry_specs import MetricSpec
from mcp_strava.types import MetricDefinition

TRAINING_METRICS: dict[str, MetricDefinition] = {
    "fitness": _metric(
        "fitness",
        MetricSpec(
            label="Fitness",
            unit="model_units",
            source="training",
            scope="model",
            sport_scope="global",
            comparison_mode="last",
            directionality="higher_is_more",
        ),
        ["get_fitness_state", "compare_periods"],
    ),
    "fatigue": _metric(
        "fatigue",
        MetricSpec(
            label="Fatigue",
            unit="model_units",
            source="training",
            scope="model",
            sport_scope="global",
            comparison_mode="last",
            directionality="higher_is_more",
        ),
        ["get_fitness_state", "compare_periods"],
    ),
    "form": _metric(
        "form",
        MetricSpec(
            label="Form",
            unit="model_units",
            source="training",
            scope="model",
            sport_scope="global",
            comparison_mode="last",
            directionality="higher_is_more",
        ),
        ["get_fitness_state", "compare_periods"],
    ),
    "form_zone": _metric(
        "form_zone",
        MetricSpec(
            label="Form Zone",
            unit="category",
            source="training",
            scope="model",
            sport_scope="global",
            comparison_mode="none",
            directionality="context",
        ),
        ["get_fitness_state"],
    ),
    "banister_history": _metric(
        "banister_history",
        MetricSpec(
            label="Banister History",
            unit="model_units",
            source="training",
            scope="period",
            sport_scope="global",
            comparison_mode="trend",
            directionality="context",
        ),
        [],
    ),
    "progressive_load_bonus": _metric(
        "progressive_load_bonus",
        MetricSpec(
            label="Progressive Load Bonus",
            unit="ratio",
            source="training",
            scope="model",
            sport_scope="global",
            comparison_mode="last",
            directionality="higher_is_more",
        ),
        [],
    ),
    "progressive_cc_trends": _metric(
        "progressive_cc_trends",
        MetricSpec(
            label="Progressive CC Trends",
            unit="percent",
            source="training",
            scope="model",
            sport_scope="per_sport",
            comparison_mode="trend",
            directionality="lower_is_better",
        ),
        [],
    ),
    "projected_daily_trimp": _metric(
        "projected_daily_trimp",
        MetricSpec(
            label="Projected Daily TRIMP",
            unit="trimp",
            source="training",
            scope="projection",
            sport_scope="global",
            comparison_mode="distribution",
            directionality="context",
        ),
        ["project_fitness_state"],
    ),
    "projected_fitness": _metric(
        "projected_fitness",
        MetricSpec(
            label="Projected Fitness",
            unit="model_units",
            source="training",
            scope="projection",
            sport_scope="global",
            comparison_mode="last",
            directionality="higher_is_more",
        ),
        ["project_fitness_state"],
    ),
    "projected_fatigue": _metric(
        "projected_fatigue",
        MetricSpec(
            label="Projected Fatigue",
            unit="model_units",
            source="training",
            scope="projection",
            sport_scope="global",
            comparison_mode="last",
            directionality="higher_is_more",
        ),
        ["project_fitness_state"],
    ),
    "projected_form": _metric(
        "projected_form",
        MetricSpec(
            label="Projected Form",
            unit="model_units",
            source="training",
            scope="projection",
            sport_scope="global",
            comparison_mode="last",
            directionality="higher_is_more",
        ),
        ["project_fitness_state"],
    ),
    "target_date_form": _metric(
        "target_date_form",
        MetricSpec(
            label="Target Date Form",
            unit="model_units",
            source="training",
            scope="projection",
            sport_scope="global",
            comparison_mode="last",
            directionality="higher_is_more",
        ),
        ["project_fitness_state"],
    ),
    "post_weekend_monday_form": _metric(
        "post_weekend_monday_form",
        MetricSpec(
            label="Post Weekend Monday Form",
            unit="model_units",
            source="training",
            scope="projection",
            sport_scope="global",
            comparison_mode="distribution",
            directionality="higher_is_more",
        ),
        ["project_fitness_state"],
    ),
    "activity_template_trimp": _metric(
        "activity_template_trimp",
        MetricSpec(
            label="Activity Template TRIMP",
            unit="trimp",
            source="training",
            scope="projection",
            sport_scope="global",
            comparison_mode="distribution",
            directionality="context",
        ),
        ["project_fitness_state"],
    ),
}
