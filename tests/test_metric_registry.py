"""Metric registry contract tests for Phase 05 plan 05-01."""

from pathlib import Path

from mcp_strava.application.metric_registry import (
    AGGREGATE_METRIC_BUNDLES,
    AGGREGATE_MODES,
    EXCLUDED_INTERPRETATIONS,
    MCP_TOOL_IDS,
    METRIC_REGISTRY,
    SUPPORTED_AGGREGATE_BUCKETS,
    SUPPORTED_AGGREGATE_SCOPES,
    SUPPORTED_ROLLING_WINDOW_DAYS,
    metric_catalog_payload,
    metrics_for_aggregate_bundle,
    metrics_for_tool,
)
from mcp_strava.application import metric_services
import pytest


REQUIRED_METRIC_IDS = {
    "activity_id",
    "activity_date",
    "sport_type",
    "activity_name",
    "kudos_count",
    "kudos_names",
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
    "cardiac_drift_significant",
    "cardiac_drift_quality",
    "hrr_pct",
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
    "acwr_history",
    "daily_avg_trimp_7d",
    "daily_avg_trimp_28d",
    "daily_avg_trimp_90d",
    "rolling_median_cc",
    "rolling_median_cc_adj",
    "rolling_median_epkm",
    "rolling_median_hr_recovery",
    "rolling_median_cardiac_drift_pct",
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

FORBIDDEN_METRIC_IDS = {
    "z5_seconds",
    "atl",
    "ctl",
}

ALLOWED_SPORT_SCOPE = {"global", "per_sport", "both"}
ALLOWED_COMPARISON_MODE = {"sum", "avg", "median", "last", "min", "max", "trend", "distribution", "none"}
EXPECTED_AGGREGATE_MODES = {
    "sum",
    "calendar_average",
    "weighted_average",
    "ratio_of_sums",
    "quantile",
    "last_state",
    "distribution",
    "kudos_count",
}
EXPECTED_AGGREGATE_BUCKETS = {"day", "week", "month", "year", "all_time"}
EXPECTED_AGGREGATE_SCOPES = {"global", "per_sport", "both"}
EXPECTED_ROLLING_WINDOWS = {7, 14, 28, 42, 90}
EXPECTED_AGGREGATE_BUNDLES = {
    "daily_brief",
    "weekly_digest",
    "monthly_digest",
    "period_comparison",
    "sport_efficiency",
    "historical_facts",
}
EXPECTED_QUANTILES = ("p25", "median", "p75")
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


def test_registry_rejects_duplicate_or_placeholder_metric_ids():
    assert METRIC_REGISTRY.keys().isdisjoint(FORBIDDEN_METRIC_IDS)


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
        assert metric.calculation


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


def test_registry_entries_describe_calculation_contract():
    banned_placeholders = {"todo", "tbd", "n/a", "unknown"}
    banned_phrases = {
        "reserved",
        "currently returns null",
        "currently not materialized",
        "currently skipped",
        "currently materialized as the same value",
        "not materialized for",
    }
    for metric in METRIC_REGISTRY.values():
        calculation = metric.calculation.strip()
        assert len(calculation) >= 24, f"{metric.metric_id} calculation is too terse"
        assert calculation.lower() not in banned_placeholders
        assert metric.metric_id != calculation, f"{metric.metric_id} repeats its id instead of explaining calculation"
        lowered = calculation.lower()
        assert not any(phrase in lowered for phrase in banned_phrases), metric.metric_id


def test_metric_catalog_payload_exposes_calculation_contracts():
    payload = metric_catalog_payload()
    catalog_metrics = {metric["metric_id"]: metric for metric in payload["metrics"]}
    for metric_id, definition in METRIC_REGISTRY.items():
        assert catalog_metrics[metric_id]["calculation"] == definition.calculation


def test_docs_metrics_md_stays_in_sync_with_registry():
    docs_text = Path("docs/metrics.md").read_text(encoding="utf-8")
    for metric_id in METRIC_REGISTRY:
        assert metric_id in docs_text, f"docs/metrics.md missing metric id: {metric_id}"
        assert METRIC_REGISTRY[metric_id].calculation in docs_text, (
            f"docs/metrics.md missing calculation for metric id: {metric_id}"
        )
    for key in EXCLUDED_INTERPRETATIONS:
        assert key in docs_text, f"docs/metrics.md missing exclusion key: {key}"
    for metric_id in FORBIDDEN_METRIC_IDS:
        assert metric_id not in docs_text, f"docs/metrics.md still documents removed metric id: {metric_id}"


def test_docs_metrics_md_includes_aggregate_registry_contract():
    docs_text = Path("docs/metrics.md").read_text(encoding="utf-8")
    assert "## Aggregate Registry Contract" in docs_text
    aggregate_section = docs_text.split("## Aggregate Registry Contract", 1)[1].split("## Metric Inventory", 1)[0]

    for mode in AGGREGATE_MODES:
        assert f"`{mode}`" in aggregate_section
    for bucket in SUPPORTED_AGGREGATE_BUCKETS:
        assert f"`{bucket}`" in aggregate_section
    for scope in SUPPORTED_AGGREGATE_SCOPES:
        assert f"`{scope}`" in aggregate_section
    for window_days in SUPPORTED_ROLLING_WINDOW_DAYS:
        assert f"`{window_days}`" in aggregate_section
    for bundle_id, metric_ids in AGGREGATE_METRIC_BUNDLES.items():
        assert f"`{bundle_id}`" in aggregate_section
        for metric_id in metric_ids:
            assert f"`{metric_id}`" in aggregate_section

    for metric in METRIC_REGISTRY.values():
        if metric.aggregate_mode is None:
            continue
        for value in (
            metric.denominator,
            metric.weight_column,
            metric.numerator_column,
            metric.denominator_column,
            metric.sample_size_column,
        ):
            if value is not None:
                assert f"`{value}`" in aggregate_section, metric.metric_id
        for quantile in metric.quantiles:
            assert f"`{quantile}`" in aggregate_section, metric.metric_id

    assert "Week buckets use Monday start" in aggregate_section
    assert "`[start_day, end_day_exclusive)`" in aggregate_section

    added_coaching_terms = ("should", "ready", "advice", "recommend", "coach")
    lowered = aggregate_section.lower()
    assert not any(term in lowered for term in added_coaching_terms)


def test_compare_periods_registry_metrics_are_mapped_without_skip_bucket():
    mapped = set(metric_services.COMPARE_PERIODS_HANDLERS.keys())
    assert metric_services.COMPARE_PERIODS_SKIP_REASONS == {}
    for metric_id, definition in METRIC_REGISTRY.items():
        if definition.comparison_mode == "none" or "compare_periods" not in definition.exposed_in:
            continue
        assert metric_id in mapped, f"{metric_id} must be mapped"


def test_aggregate_registry_contract_enumerates_supported_modes_and_filters():
    assert set(AGGREGATE_MODES) == EXPECTED_AGGREGATE_MODES
    assert set(SUPPORTED_AGGREGATE_BUCKETS) == EXPECTED_AGGREGATE_BUCKETS
    assert set(SUPPORTED_AGGREGATE_SCOPES) == EXPECTED_AGGREGATE_SCOPES
    assert set(SUPPORTED_ROLLING_WINDOW_DAYS) == EXPECTED_ROLLING_WINDOWS


def test_aggregate_exposed_metrics_have_complete_query_metadata():
    aggregate_metrics = [metric for metric in METRIC_REGISTRY.values() if metric.aggregate_mode is not None]
    assert aggregate_metrics, "get_training_aggregates must have registry-owned metrics"

    for metric in aggregate_metrics:
        assert metric.unit
        assert metric.calculation
        assert metric.aggregate_mode in EXPECTED_AGGREGATE_MODES
        assert metric.aggregate_source
        assert metric.metric_version_policy in {"single", "mixed_allowed", "mixed_degraded"}
        assert set(metric.supported_buckets).issubset(EXPECTED_AGGREGATE_BUCKETS)
        assert metric.supported_buckets, f"{metric.metric_id} must declare aggregate buckets"
        assert set(metric.supported_scopes).issubset(EXPECTED_AGGREGATE_SCOPES)
        assert metric.supported_scopes, f"{metric.metric_id} must declare aggregate scopes"
        assert not set(metric.supported_scopes) & {"gear", "equipment"}
        assert metric.sample_size_column, f"{metric.metric_id} must expose sample-size provenance"


def test_aggregate_modes_map_locked_semantic_decisions():
    expected_modes = {
        "distance_km": ("sum", "distance_m"),
        "moving_time_min": ("sum", "moving_time_s"),
        "elevation_m": ("sum", "elevation_gain_m"),
        "trimp": ("sum", "trimp"),
        "avg_trimp_per_day": ("calendar_average", "calendar_days"),
        "avg_hr": ("weighted_average", "heartrate_sample_count"),
        "vertical_speed_m_per_h": ("ratio_of_sums", "vertical_speed_duration_hours"),
        "cardiac_cost": ("quantile", None),
        "fitness": ("last_state", None),
        "form_zone": ("distribution", None),
        "kudos_count": ("kudos_count", "activity_count"),
    }
    for metric_id, (mode, denominator) in expected_modes.items():
        metric = METRIC_REGISTRY[metric_id]
        assert metric.aggregate_mode == mode, metric_id
        if denominator is not None:
            assert metric.denominator == denominator or metric.denominator_column == denominator, metric_id


def test_weighted_hr_and_power_metrics_require_explicit_denominators():
    weighted_metrics = [
        metric
        for metric in METRIC_REGISTRY.values()
        if metric.aggregate_mode == "weighted_average" or metric.unit in {"bpm", "watts"}
    ]
    assert weighted_metrics
    for metric in weighted_metrics:
        assert metric.weight_column, metric.metric_id
        assert metric.denominator_column, metric.metric_id
        assert metric.denominator != "naive_activity_average", metric.metric_id


def test_quantile_metrics_require_distribution_context_and_sample_size():
    quantile_metrics = [metric for metric in METRIC_REGISTRY.values() if metric.aggregate_mode == "quantile"]
    assert quantile_metrics
    for metric in quantile_metrics:
        assert tuple(metric.quantiles) == EXPECTED_QUANTILES, metric.metric_id
        assert metric.sample_size_column, metric.metric_id
        assert "sample" in metric.sample_size_column, metric.metric_id


def test_aggregate_bundles_resolve_only_known_metric_ids():
    assert set(AGGREGATE_METRIC_BUNDLES) == EXPECTED_AGGREGATE_BUNDLES
    for bundle_id, metric_ids in AGGREGATE_METRIC_BUNDLES.items():
        assert metric_ids, f"{bundle_id} bundle must not be empty"
        assert set(metrics_for_aggregate_bundle(bundle_id)) == set(metric_ids)
        unknown = set(metric_ids) - set(METRIC_REGISTRY)
        assert not unknown, f"{bundle_id} has unknown metric ids: {sorted(unknown)}"
        for metric_id in metric_ids:
            metric = METRIC_REGISTRY[metric_id]
            assert metric.aggregate_mode is not None, metric_id
            assert bundle_id in metric.bundle_ids, metric_id

    with pytest.raises(ValueError):
        metrics_for_aggregate_bundle("gear_efficiency")


def test_aggregate_registry_does_not_create_pseudo_metric_ids_for_math_variants():
    forbidden_suffixes = (
        "_sum",
        "_weighted_avg",
        "_weighted_average",
        "_ratio_sum",
        "_ratio_of_sums",
        "_quantile",
        "_p25",
        "_p75",
        "_last_state",
    )
    offenders = [
        metric_id
        for metric_id in METRIC_REGISTRY
        if metric_id.endswith(forbidden_suffixes)
    ]
    assert not offenders


def test_kudos_aggregate_excludes_kudos_names():
    assert METRIC_REGISTRY["kudos_count"].aggregate_mode == "kudos_count"
    assert METRIC_REGISTRY["kudos_names"].aggregate_mode is None
    for metric_ids in AGGREGATE_METRIC_BUNDLES.values():
        assert "kudos_names" not in metric_ids
