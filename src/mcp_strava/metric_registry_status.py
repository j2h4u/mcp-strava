"""Status fact registry and excluded interpretation metadata."""

from __future__ import annotations

from mcp_strava.metric_registry_metrics import METRIC_REGISTRY
from mcp_strava.metric_registry_specs import StatusFactSpec
from mcp_strava.types import ExcludedInterpretation, StatusFactDefinition


def _status_fact(code: str, metric_id: str, spec: StatusFactSpec) -> StatusFactDefinition:
    if metric_id not in METRIC_REGISTRY:
        raise ValueError(f"Unknown status fact metric id: {metric_id}")
    return StatusFactDefinition(
        code=code,
        metric_id=metric_id,
        threshold=dict(spec.threshold),
        window=dict(spec.window),
        evidence_keys=list(spec.evidence_keys),
        completeness_reasons=list(spec.completeness_reasons),
        calculation=spec.calculation,
        materialized_from=spec.materialized_from,
    )


STATUS_FACT_REGISTRY: dict[str, StatusFactDefinition] = {
    "stale_mirror_data": _status_fact(
        "stale_mirror_data",
        "activity_date",
        StatusFactSpec(
            threshold={"max_age_days": 1},
            window={"lookback_days": 1},
            evidence_keys=["last_success_at", "age_days", "threshold_days"],
            completeness_reasons=["refresh_state_missing", "last_success_missing"],
            calculation="Active when the latest mirror refresh success is older than the registered freshness age.",
            materialized_from="refresh_state",
        ),
    ),
    "stale_read_model_facts": _status_fact(
        "stale_read_model_facts",
        "fitness",
        StatusFactSpec(
            threshold={"max_age_days": 1, "dirty_count": 0},
            window={"lookback_days": 1},
            evidence_keys=["last_materialized_at", "age_days", "dirty_count"],
            completeness_reasons=["read_model_run_missing", "read_model_unavailable"],
            calculation="Active when read-model materialization is older than the registered age or dirty rows remain.",
            materialized_from="read_model_refresh_runs,metric_dirty_activities",
        ),
    ),
    "missing_hr": _status_fact(
        "missing_hr",
        "avg_hr",
        StatusFactSpec(
            threshold={"heartrate_sample_count": 1},
            window={"lookback_days": 14},
            evidence_keys=["activity_count", "activity_ids"],
            completeness_reasons=["no_activity_facts"],
            calculation="Active when recent materialized activity facts include activities with zero heart-rate samples.",
            materialized_from="activity_metric_facts",
        ),
    ),
    "missing_streams": _status_fact(
        "missing_streams",
        "time_in_hr_zones_min",
        StatusFactSpec(
            threshold={"stream_sample_count": 1},
            window={"lookback_days": 14},
            evidence_keys=["activity_count", "activity_ids"],
            completeness_reasons=["no_activity_facts"],
            calculation="Active when recent materialized activity facts include activities with zero stream samples.",
            materialized_from="activity_metric_facts",
        ),
    ),
    "excessive_z5_exposure": _status_fact(
        "excessive_z5_exposure",
        "time_in_hr_zones_min",
        StatusFactSpec(
            threshold={"zone5_seconds": 300, "z5_lower_bound_bpm": 177},
            window={"lookback_days": 7},
            evidence_keys=["activity_id", "activity_day", "zone5_seconds", "z5_lower_bound_bpm"],
            completeness_reasons=["no_activity_facts", "missing_hr"],
            calculation="Active when a recent materialized activity has zone5_seconds above the registered Z5 duration threshold.",
            materialized_from="activity_metric_facts",
        ),
    ),
    "hr_anomaly_burst": _status_fact(
        "hr_anomaly_burst",
        "hr_anomaly_count",
        StatusFactSpec(
            threshold={"hr_anomaly_count": 3, "jump_bpm": 30},
            window={"lookback_days": 7},
            evidence_keys=["activity_id", "activity_day", "hr_anomaly_count", "jump_bpm"],
            completeness_reasons=["no_activity_facts", "missing_hr"],
            calculation="Active when a recent materialized activity has at least the registered count of 30 bpm heart-rate jumps.",
            materialized_from="activity_metric_facts",
        ),
    ),
    "cardiac_drift_significant_quality": _status_fact(
        "cardiac_drift_significant_quality",
        "cardiac_drift_significant",
        StatusFactSpec(
            threshold={"cardiac_drift_significant": 1, "quality": ["good", "fair"]},
            window={"lookback_days": 7},
            evidence_keys=["activity_id", "activity_day", "cardiac_drift_significant", "cardiac_drift_quality"],
            completeness_reasons=["no_activity_facts", "missing_streams"],
            calculation="Active when a recent materialized activity is significant for cardiac drift and quality is good or fair.",
            materialized_from="activity_metric_facts",
        ),
    ),
    "consecutive_high_load_hikes": _status_fact(
        "consecutive_high_load_hikes",
        "trimp",
        StatusFactSpec(
            threshold={"combined_trimp": 800, "consecutive_days": 2},
            window={"lookback_days": 7},
            evidence_keys=["hike_days", "combined_trimp"],
            completeness_reasons=["insufficient_hike_history", "no_activity_facts"],
            calculation="Active when two consecutive Hike days in the local read model have combined TRIMP above the registered threshold.",
            materialized_from="activity_metric_facts",
        ),
    ),
    "running_volume_jump": _status_fact(
        "running_volume_jump",
        "distance_km",
        StatusFactSpec(
            threshold={"caution_pct": 10, "high_pct": 15},
            window={"week_start": "monday", "comparison": "previous_week"},
            evidence_keys=["current_week_distance_km", "previous_week_distance_km", "increase_pct"],
            completeness_reasons=["no_previous_running_week", "no_current_running_week"],
            calculation="Active when current Monday-start running distance exceeds previous week distance by a registered percentage threshold.",
            materialized_from="activity_metric_facts",
        ),
    ),
}


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
