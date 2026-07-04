"""Product bundle formatting and completeness helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, cast

from mcp_strava.metric_registry import METRIC_REGISTRY, metrics_for_aggregate_bundle
from mcp_strava.types import CompletenessMetadata, ServiceEnvelope, ServiceRationale, ServiceWarning


@dataclass(frozen=True, slots=True, kw_only=True)
class BundleSectionContent:
    """Cohesive optional payload fields for a single bundle section."""

    rows: list[dict[str, Any]] | None = field(default=None)
    items: list[dict[str, Any]] | None = field(default=None)
    metrics: dict[str, Any] | None = field(default=None)
    facts: dict[str, object] | None = field(default=None)
    periods: dict[str, Any] | None = field(default=None)
    comparison: dict[str, object] | None = field(default=None)
    season: str | None = field(default=None)
    current_week: dict[str, Any] | None = field(default=None)
    read_model: dict[str, Any] | None = field(default=None)
    row_count: int | None = field(default=None)


PRODUCT_FACT_BUNDLES = frozenset({"daily_brief", "weekly_digest", "historical_facts"})


def is_product_fact_bundle(bundle_id: str | None) -> bool:
    return bundle_id in PRODUCT_FACT_BUNDLES


def format_aggregate_product_bundle(
    bundle_id: str | None,
    rows: list[dict[str, Any]],
    *,
    read_model: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not is_product_fact_bundle(bundle_id):
        return None
    requested = tuple(metrics_for_aggregate_bundle(str(bundle_id)))
    section_specs = {
        "daily_brief": {
            "current_state": ("fitness", "fatigue", "form", "form_zone", "acwr", "acwr_zone"),
            "load_context": (
                "weekly_trimp",
                "total_trimp_14d",
                "avg_trimp_per_day",
                "active_days",
                "rest_days",
                "daily_avg_trimp_7d",
            ),
            "efficiency_context": ("rolling_median_cc", "rolling_median_hr_recovery"),
            "social_context": ("kudos_count",),
        },
        "weekly_digest": {
            "load": ("trimp", "weekly_trimp", "active_days"),
            "volume": ("distance_km", "moving_time_min", "elapsed_time_min", "elevation_m", "volume_7d"),
            "efficiency": ("avg_hr", "max_hr", "cardiac_cost", "cardiac_cost_adjusted", "cardiac_drift_pct", "hrr_pct"),
            "by_sport": ("avg_hr", "max_hr", "cardiac_cost", "cardiac_cost_adjusted", "cardiac_drift_pct", "hrr_pct"),
        },
        "historical_facts": {
            "activity_context": ("activity_streak_days", "rest_streak_days", "last_hike_days_ago"),
            "status_context": ("form_zone", "acwr_zone", "cardiac_drift_severity", "cardiac_drift_quality"),
            "social_context": ("kudos_count",),
        },
    }
    sections = {
        section_id: bundle_section(
            requested=metric_ids,
            content=BundleSectionContent(rows=filter_rows(rows, set(metric_ids))),
        )
        for section_id, metric_ids in section_specs[str(bundle_id)].items()
    }
    if read_model is not None:
        sections["read_model"] = bundle_section(
            requested=("fitness",),
            content=BundleSectionContent(facts=read_model),
        )
    return bundle_data(
        bundle_id=str(bundle_id),
        as_of_day=None,
        sections=sections,
        requested_metrics=requested,
        rows=rows,
    )


def dict_data(payload: dict[str, object]) -> dict[str, Any]:
    data: object = payload.get("data")
    return data if isinstance(data, dict) else {}  # type: ignore[return-value]


def data_list(payload: dict[str, object] | ServiceEnvelope) -> list[dict[str, Any]]:
    if isinstance(payload, ServiceEnvelope):
        raw_data: object = cast("object", payload.data)
    else:
        raw_data = payload.get("data")
    if not isinstance(raw_data, list):
        return []
    return [item for item in raw_data if isinstance(item, dict)]  # type: ignore[return-value]


def rows_from_payload(payload: dict[str, object]) -> list[dict[str, Any]]:
    data: object = payload.get("data")
    if not isinstance(data, dict):
        return []
    rows: object = data.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]  # type: ignore[return-value]


def filter_rows(rows: list[dict[str, Any]], metric_ids: set[str]) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("metric_id")) in metric_ids]


def metric_values(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for row in rows:
        metric_id = str(row.get("metric_id"))
        raw_value: object = cast("object", row.get("value"))
        if raw_value is None and isinstance(cast("object", row.get("distribution")), dict):
            raw_value = cast("object", row["distribution"])
        if raw_value is None and isinstance(cast("object", row.get("quantiles")), dict):
            raw_value = cast("object", row["quantiles"])
        if raw_value is not None:
            values.setdefault(metric_id, raw_value)
    return values


def pick_metrics(values: dict[str, Any], metric_ids: tuple[str, ...]) -> dict[str, Any]:
    return {
        metric_id: values[metric_id]
        for metric_id in metric_ids
        if metric_id in values and values[metric_id] is not None
    }


def _collect_section_fields(content: BundleSectionContent) -> dict[str, Any]:
    """Collect all optional section fields into a dict, omitting None values."""
    return {
        key: value
        for key, value in (
            ("rows", content.rows),
            ("items", content.items),
            ("metrics", content.metrics),
            ("facts", content.facts),
            ("periods", content.periods),
            ("comparison", content.comparison),
            ("season", content.season),
            ("current_week", content.current_week),
            ("read_model", content.read_model),
            ("row_count", content.row_count),
        )
        if value is not None
    }


def bundle_section(
    *,
    requested: tuple[str, ...],
    content: BundleSectionContent,
) -> dict[str, Any]:
    section = _collect_section_fields(content)
    included = included_metrics(
        requested,
        rows=content.rows,
        items=content.items,
        metrics=content.metrics,
        facts=content.facts,
    )
    section["bundle_completeness"] = bundle_completeness(requested, included_metrics=tuple(included))
    return section


def _included_from_rows(rows: list[dict[str, Any]], requested_set: set[str]) -> set[str]:
    included: set[str] = set()
    for row in rows:
        metric_id: object = cast("object", row.get("metric_id"))
        if metric_id in requested_set and cast("object", row.get("completeness_status")) != "unavailable":
            included.add(str(metric_id))
    return included


def _included_from_metrics(metrics: dict[str, Any], requested_set: set[str]) -> set[str]:
    metrics_typed: dict[str, object] = cast("dict[str, object]", metrics)
    return {mid for mid, val in metrics_typed.items() if mid in requested_set and val is not None}


def _included_from_facts(facts: dict[str, object], requested_set: set[str]) -> set[str]:
    return {mid for mid, val in facts.items() if mid in requested_set and val is not None}


def _included_from_items(items: list[dict[str, Any]], requested_set: set[str]) -> set[str]:
    included: set[str] = set()
    for item in items:
        included.update(mid for mid in requested_set if cast("object", item.get(mid)) is not None)
    return included


def included_metrics(
    requested: tuple[str, ...],
    *,
    rows: list[dict[str, Any]] | None,
    items: list[dict[str, Any]] | None,
    metrics: dict[str, Any] | None,
    facts: dict[str, object] | None,
) -> set[str]:
    requested_set = set(requested)
    included: set[str] = set()
    if rows is not None:
        included |= _included_from_rows(rows, requested_set)
    if metrics is not None:
        included |= _included_from_metrics(metrics, requested_set)
    if facts is not None:
        included |= _included_from_facts(facts, requested_set)
    if items:
        included |= _included_from_items(items, requested_set)
    return included


def bundle_data(
    *,
    bundle_id: str,
    as_of_day: str | None,
    sections: dict[str, dict[str, Any]],
    requested_metrics: tuple[str, ...],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    included: set[str] = set()
    for section in sections.values():
        completeness = section.get("bundle_completeness")
        if isinstance(completeness, dict):
            included.update(str(metric_id) for metric_id in completeness.get("included_metrics", []))
    included.update(str(row.get("metric_id")) for row in rows if row.get("completeness_status") != "unavailable")
    return {
        "bundle_id": bundle_id,
        "as_of_day": as_of_day,
        "sections": sections,
        "bundle_completeness": bundle_completeness(requested_metrics, included_metrics=tuple(included)),
    }


def bundle_completeness(
    requested_metrics: tuple[str, ...],
    *,
    included_metrics: tuple[str, ...] = (),
    unavailable_metrics: tuple[dict[str, Any], ...] = (),
    skipped_metrics: tuple[dict[str, Any], ...] = (),
    scope_incompatible_metrics: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    requested = tuple(metric_id for metric_id in requested_metrics if metric_id in METRIC_REGISTRY)
    included = tuple(dict.fromkeys(metric_id for metric_id in included_metrics if metric_id in requested))
    unavailable = list(unavailable_metrics)
    skipped = list(skipped_metrics)
    scope_incompatible = list(scope_incompatible_metrics)
    accounted = set(included)
    accounted.update(str(item.get("metric_id")) for item in unavailable if isinstance(item, dict))
    accounted.update(str(item.get("metric_id")) for item in skipped if isinstance(item, dict))
    accounted.update(str(item.get("metric_id")) for item in scope_incompatible if isinstance(item, dict))
    unavailable.extend(reason(metric_id, "data_absent") for metric_id in requested if metric_id not in accounted)
    return {
        "requested_metrics": list(requested),
        "included_metrics": list(included),
        "unavailable_metrics": unavailable,
        "skipped_metrics": skipped,
        "scope_incompatible_metrics": scope_incompatible,
    }


def reason(metric_id: str, reason_code: str, *, evidence_count: int = 0) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "reason_code": reason_code,
        "evidence_count": evidence_count,
    }


def read_model_from(*payloads: dict[str, object]) -> dict[str, Any]:
    for payload in payloads:
        completeness: object = payload.get("completeness")
        if not isinstance(completeness, dict):
            continue
        coverage: object = completeness.get("coverage")
        if not isinstance(coverage, dict):
            continue
        read_model: object = coverage.get("read_model")
        if isinstance(read_model, dict):
            return read_model  # type: ignore[return-value]
    return {
        "status": "unavailable",
        "last_materialized_at": None,
        "dirty_count": 0,
        "oldest_dirty_day": None,
        "stale_reason": "read_model_metadata_absent",
    }


def service_envelope(
    data: dict[str, Any],
    primary: ServiceEnvelope,
    related: list[ServiceEnvelope],
    read_model: dict[str, Any],
    requested_metrics: set[str],
) -> ServiceEnvelope:
    sections_raw: object = cast("object", data["sections"])
    sections_dict: dict[str, object] = sections_raw if isinstance(sections_raw, dict) else {}
    section_statuses = [
        section_status(section)
        for section in sections_dict.values()
        if isinstance(section, dict)  # type: ignore[arg-type]
    ]
    missing = sorted(missing_reasons(data))
    coverage = {
        "read_model": read_model,
        "bundle_id": cast("object", data["bundle_id"]),
        "requested_metrics": sorted(requested_metrics),
        "section_count": len(sections_dict),
    }
    warnings = dedupe_warnings([*primary.warnings, *(warning for env in related for warning in env.warnings)])
    return ServiceEnvelope(
        data=data,
        freshness=primary.freshness,
        completeness=CompletenessMetadata(
            status=overall_status(section_statuses, read_model),
            missing=missing,
            coverage=coverage,
        ),
        warnings=warnings,
        rationale=[
            ServiceRationale(
                code="product_fact_bundle",
                message="Factual bundle assembled from prepared local metric facts and application services.",
            )
        ],
    )


def section_status(section: dict[str, Any]) -> str:
    completeness = section.get("bundle_completeness")
    if not isinstance(completeness, dict):
        return "unavailable"
    requested = set(completeness.get("requested_metrics", []))
    included = set(completeness.get("included_metrics", []))
    if not requested:
        return "unavailable"
    if requested <= included:
        return "complete"
    if included:
        return "partial"
    return "unavailable"


def overall_status(section_statuses: list[str], read_model: dict[str, Any]) -> str:
    if read_model.get("status") == "stale":
        return "stale"
    if not section_statuses or all(status == "unavailable" for status in section_statuses):
        return "unavailable"
    if any(status != "complete" for status in section_statuses):
        return "partial"
    return "complete"


def missing_reasons(data: dict[str, Any]) -> set[str]:
    missing: set[str] = set()
    sections = data.get("sections")
    if not isinstance(sections, dict):
        return missing
    for section in sections.values():
        if not isinstance(section, dict):
            continue
        completeness = section.get("bundle_completeness")
        if not isinstance(completeness, dict):
            continue
        for bucket_name in ("unavailable_metrics", "skipped_metrics", "scope_incompatible_metrics"):
            bucket = completeness.get(bucket_name)
            if not isinstance(bucket, list):
                continue
            for item in bucket:
                if isinstance(item, dict) and item.get("reason_code"):
                    missing.add(str(item["reason_code"]))
    return missing


def dedupe_warnings(warnings: list[ServiceWarning]) -> list[ServiceWarning]:
    deduped: list[ServiceWarning] = []
    seen: set[tuple[str, str, str, str | None, str | None]] = set()
    for warning in warnings:
        evidence = warning.evidence
        evidence_key = str(sorted(evidence.items())) if isinstance(evidence, dict) else None
        key = (warning.code, warning.severity, warning.message, warning.field, evidence_key)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(warning)
    return deduped


def season(day: date) -> str:
    if day.month in {12, 1, 2}:
        return "winter"
    if day.month in {3, 4, 5}:
        return "spring"
    if day.month in {6, 7, 8}:
        return "summer"
    return "autumn"
