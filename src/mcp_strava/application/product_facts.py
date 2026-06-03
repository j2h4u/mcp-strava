"""Shared product factual bundle services.

These services assemble narrative-ready facts from existing application services
and aggregate rows. They intentionally stay factual: no sync controls, raw SQL,
Strava calls, or coaching advice crosses this boundary.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import date, datetime, timedelta
from typing import Any

from mcp_strava.adapters.duckdb.aggregate_queries import query_status_facts
from mcp_strava.adapters.duckdb.connection import ReadConn
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.application.aggregate_services import (
    AggregateServiceRequest,
    get_training_aggregates_service,
)
from mcp_strava.application.metric_services import (
    compare_periods_service,
    get_fitness_state_service,
    get_workout_detail_service,
    list_workouts_service,
)
from mcp_strava.metric_registry import (
    AGGREGATE_METRIC_BUNDLES,
    METRIC_REGISTRY,
    STATUS_FACT_REGISTRY,
    metrics_for_aggregate_bundle,
)
from mcp_strava.types import (
    CompletenessMetadata,
    ServiceEnvelope,
    ServiceRationale,
    ServiceWarning,
    dc_to_dict,
)

PRODUCT_FACT_BUNDLES = frozenset({"daily_brief", "weekly_digest", "historical_facts"})
GEAR_METRIC_IDS = ("gear_id", "gear_name", "gear_distance_km", "gear_primary")


def is_product_fact_bundle(bundle_id: str | None) -> bool:
    return bundle_id in PRODUCT_FACT_BUNDLES


def get_daily_brief_facts_service(
    *,
    as_of_day: str,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    checked_at = now or datetime.now()
    as_of = _parse_day(as_of_day)
    start_14d = as_of - timedelta(days=13)
    end_exclusive = as_of + timedelta(days=1)

    with _connection_context(connection) as conn:
        fitness = get_fitness_state_service(now=checked_at, signal_first_use=signal_first_use, connection=conn)
        recent = list_workouts_service(
            limit=10,
            start_date=start_14d.isoformat(),
            end_date=as_of_day,
            now=checked_at,
            signal_first_use=False,
            connection=conn,
        )
        gear_candidates = list_workouts_service(
            limit=50,
            start_date=(as_of - timedelta(days=27)).isoformat(),
            end_date=as_of_day,
            now=checked_at,
            signal_first_use=False,
            connection=conn,
        )
        bundle_rows = get_training_aggregates_service(
            AggregateServiceRequest(
                metric_ids=(),
                bundle_id="daily_brief",
                bucket="all_time",
                start_day=start_14d.isoformat(),
                end_day_exclusive=end_exclusive.isoformat(),
                scope="both",
            ),
            now=checked_at,
            signal_first_use=False,
            connection=conn,
        )
        daily_load = get_training_aggregates_service(
            AggregateServiceRequest(
                metric_ids=("trimp", "distance_km", "moving_time_min", "elevation_m", "kudos_count"),
                bucket="day",
                start_day=start_14d.isoformat(),
                end_day_exclusive=end_exclusive.isoformat(),
                scope="both",
            ),
            now=checked_at,
            signal_first_use=False,
            connection=conn,
        )
        by_sport = get_training_aggregates_service(
            AggregateServiceRequest(
                metric_ids=("trimp", "distance_km", "moving_time_min", "elevation_m", "kudos_count"),
                bucket="all_time",
                start_day=start_14d.isoformat(),
                end_day_exclusive=end_exclusive.isoformat(),
                scope="both",
            ),
            now=checked_at,
            signal_first_use=False,
            connection=conn,
        )
        status_version = DuckDBRepository.from_connection(conn).current_metric_version()
        status_facts = [
            _normalise_status_fact(item)
            for item in query_status_facts(conn, as_of_day=as_of_day, metric_version=status_version)
        ]
        gear_section = _supported_gear_section(
            _data_list(gear_candidates),
            checked_at=checked_at,
            connection=conn,
        )

    fitness_payload = dc_to_dict(fitness)
    recent_payload = dc_to_dict(recent)
    bundle_payload = dc_to_dict(bundle_rows)
    daily_payload = dc_to_dict(daily_load)
    by_sport_payload = dc_to_dict(by_sport)
    read_model = _read_model_from(fitness_payload, bundle_payload)
    freshness_payload = fitness_payload["freshness"]
    requested = set(metrics_for_aggregate_bundle("daily_brief"))
    bundle_metric_values = _metric_values(_rows(bundle_payload))

    sections = {
        "current_state": _section(
            requested=("fitness", "fatigue", "form", "form_zone", "acwr", "acwr_zone"),
            metrics=_pick_metrics(
                _dict_data(fitness_payload), ("fitness", "fatigue", "form", "form_zone", "acwr", "acwr_zone")
            ),
        ),
        "recent_workouts": _section(
            requested=(
                "activity_id",
                "activity_date",
                "sport_type",
                "distance_km",
                "moving_time_min",
                "elevation_m",
                "trimp",
                "kudos_count",
            ),
            items=_data_list(recent_payload),
        ),
        "daily_load_14d": _section(
            requested=("trimp", "distance_km", "moving_time_min", "elevation_m", "kudos_count"),
            rows=_rows(daily_payload),
        ),
        "by_sport": _section(
            requested=("trimp", "distance_km", "moving_time_min", "elevation_m", "kudos_count"),
            rows=_rows(by_sport_payload),
        ),
        "model_context": _section(
            requested=(
                "fitness",
                "fatigue",
                "form",
                "form_zone",
                "acwr",
                "acwr_zone",
                "weekly_trimp",
                "total_trimp_14d",
                "avg_trimp_per_day",
            ),
            metrics={
                **_pick_metrics(
                    _dict_data(fitness_payload),
                    (
                        "fitness",
                        "fatigue",
                        "form",
                        "form_zone",
                        "acwr",
                        "acwr_zone",
                        "weekly_trimp",
                        "total_trimp_14d",
                        "avg_trimp_per_day",
                    ),
                ),
                **_pick_metrics(bundle_metric_values, ("weekly_trimp", "total_trimp_14d", "avg_trimp_per_day")),
            },
        ),
        "status_facts": _section(
            requested=tuple(sorted({definition.metric_id for definition in STATUS_FACT_REGISTRY.values()})),
            items=status_facts,
        ),
        "supported_gear": gear_section,
        "freshness": _section(
            requested=("activity_date",),
            facts=freshness_payload,
        ),
        "read_model": _section(
            requested=("fitness",),
            facts=read_model,
        ),
    }
    data = _bundle_data(
        bundle_id="daily_brief",
        as_of_day=as_of_day,
        sections=sections,
        requested_metrics=tuple(metrics_for_aggregate_bundle("daily_brief")),
        rows=_rows(bundle_payload),
    )
    return _service_envelope(
        data, fitness, [recent, gear_candidates, bundle_rows, daily_load, by_sport], read_model, requested
    )


def get_weekly_digest_facts_service(
    *,
    as_of_day: str,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    checked_at = now or datetime.now()
    as_of = _parse_day(as_of_day)
    week_start = as_of - timedelta(days=as_of.weekday())
    end_exclusive = as_of + timedelta(days=1)
    previous_start = week_start - timedelta(days=7)
    previous_end = week_start

    with _connection_context(connection) as conn:
        weekly = get_training_aggregates_service(
            AggregateServiceRequest(
                metric_ids=(),
                bundle_id="weekly_digest",
                bucket="all_time",
                start_day=week_start.isoformat(),
                end_day_exclusive=end_exclusive.isoformat(),
                scope="both",
            ),
            now=checked_at,
            signal_first_use=signal_first_use,
            connection=conn,
        )
        current_week = list_workouts_service(
            limit=50,
            start_date=week_start.isoformat(),
            end_date=as_of_day,
            now=checked_at,
            signal_first_use=False,
            connection=conn,
        )
        trends = compare_periods_service(
            period_a_start=week_start.isoformat(),
            period_a_end=end_exclusive.isoformat(),
            period_b_start=previous_start.isoformat(),
            period_b_end=previous_end.isoformat(),
            now=checked_at,
            signal_first_use=False,
            connection=conn,
        )

    weekly_payload = dc_to_dict(weekly)
    current_payload = dc_to_dict(current_week)
    trends_payload = dc_to_dict(trends)
    read_model = _read_model_from(weekly_payload, trends_payload)
    rows = _rows(weekly_payload)
    sections = {
        "load": _section(
            requested=("trimp", "weekly_trimp", "active_days"),
            rows=_filter_rows(rows, {"trimp", "weekly_trimp", "active_days"}),
        ),
        "volume": _section(
            requested=("distance_km", "moving_time_min", "elapsed_time_min", "elevation_m", "volume_7d"),
            rows=_filter_rows(rows, {"distance_km", "moving_time_min", "elapsed_time_min", "elevation_m", "volume_7d"}),
        ),
        "efficiency": _section(
            requested=("avg_hr", "max_hr", "cardiac_cost", "cardiac_cost_adjusted", "cardiac_drift_pct", "hrr_pct"),
            rows=_filter_rows(
                rows, {"avg_hr", "max_hr", "cardiac_cost", "cardiac_cost_adjusted", "cardiac_drift_pct", "hrr_pct"}
            ),
        ),
        "by_sport": _section(
            requested=(
                "distance_km",
                "moving_time_min",
                "elevation_m",
                "avg_hr",
                "max_hr",
                "cardiac_cost",
                "cardiac_drift_pct",
            ),
            rows=[row for row in rows if row.get("scope") == "per_sport"],
        ),
        "current_week_activities": _section(
            requested=(
                "activity_id",
                "activity_date",
                "sport_type",
                "distance_km",
                "moving_time_min",
                "elevation_m",
                "trimp",
                "kudos_count",
            ),
            items=_data_list(current_payload),
        ),
        "period_trends": _section(
            requested=tuple(metrics_for_aggregate_bundle("period_comparison")),
            periods={
                "current": {"start": week_start.isoformat(), "end_exclusive": end_exclusive.isoformat()},
                "previous": {"start": previous_start.isoformat(), "end_exclusive": previous_end.isoformat()},
            },
            comparison=trends_payload["data"],
        ),
        "freshness": _section(requested=("activity_date",), facts=weekly_payload["freshness"]),
        "read_model": _section(requested=("fitness",), facts=read_model),
    }
    data = _bundle_data(
        bundle_id="weekly_digest",
        as_of_day=as_of_day,
        sections=sections,
        requested_metrics=tuple(metrics_for_aggregate_bundle("weekly_digest")),
        rows=rows,
    )
    return _service_envelope(
        data, weekly, [current_week, trends], read_model, set(metrics_for_aggregate_bundle("weekly_digest"))
    )


def get_historical_facts_service(
    *,
    as_of_day: str,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    checked_at = now or datetime.now()
    as_of = _parse_day(as_of_day)
    week_start = as_of - timedelta(days=as_of.weekday())
    end_exclusive = as_of + timedelta(days=1)

    with _connection_context(connection) as conn:
        historical = get_training_aggregates_service(
            AggregateServiceRequest(
                metric_ids=(),
                bundle_id="historical_facts",
                bucket="all_time",
                start_day=None,
                end_day_exclusive=end_exclusive.isoformat(),
                scope="both",
            ),
            now=checked_at,
            signal_first_use=signal_first_use,
            connection=conn,
        )

    historical_payload = dc_to_dict(historical)
    rows = _rows(historical_payload)
    facts = _metric_values(rows)
    read_model = _read_model_from(historical_payload)
    sections = {
        "activity_context": _section(
            requested=("activity_streak_days", "rest_streak_days", "last_hike_days_ago"),
            facts=_pick_metrics(facts, ("activity_streak_days", "rest_streak_days", "last_hike_days_ago")),
        ),
        "calendar_context": _section(
            requested=("activity_date",),
            season=_season(as_of),
            current_week={
                "week_start": week_start.isoformat(),
                "window_start": week_start.isoformat(),
                "window_end_exclusive": end_exclusive.isoformat(),
            },
        ),
        "coverage": _section(
            requested=tuple(metrics_for_aggregate_bundle("historical_facts")),
            read_model=read_model,
            row_count=len(rows),
        ),
        "freshness": _section(requested=("activity_date",), facts=historical_payload["freshness"]),
        "read_model": _section(requested=("fitness",), facts=read_model),
    }
    data = _bundle_data(
        bundle_id="historical_facts",
        as_of_day=as_of_day,
        sections=sections,
        requested_metrics=tuple(metrics_for_aggregate_bundle("historical_facts")),
        rows=rows,
    )
    return _service_envelope(data, historical, [], read_model, set(metrics_for_aggregate_bundle("historical_facts")))


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
        section_id: _section(
            requested=metric_ids,
            rows=_filter_rows(rows, set(metric_ids)),
        )
        for section_id, metric_ids in section_specs[str(bundle_id)].items()
    }
    if read_model is not None:
        sections["read_model"] = _section(requested=("fitness",), facts=read_model)
    return _bundle_data(
        bundle_id=str(bundle_id),
        as_of_day=None,
        sections=sections,
        requested_metrics=requested,
        rows=rows,
    )


def _connection_context(connection):
    return nullcontext(connection) if connection is not None else ReadConn()


def _parse_day(value: str) -> date:
    return date.fromisoformat(value)


def _dict_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _data_list(payload: dict[str, Any] | ServiceEnvelope) -> list[dict[str, Any]]:
    if isinstance(payload, ServiceEnvelope):
        data = payload.data
    else:
        data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    rows = data.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _filter_rows(rows: list[dict[str, Any]], metric_ids: set[str]) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("metric_id")) in metric_ids]


def _metric_values(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for row in rows:
        metric_id = str(row.get("metric_id"))
        value = row.get("value")
        if value is None and isinstance(row.get("distribution"), dict):
            value = row["distribution"]
        if value is None and isinstance(row.get("quantiles"), dict):
            value = row["quantiles"]
        if value is not None:
            values.setdefault(metric_id, value)
    return values


def _pick_metrics(values: dict[str, Any], metric_ids: tuple[str, ...]) -> dict[str, Any]:
    return {
        metric_id: values[metric_id]
        for metric_id in metric_ids
        if metric_id in values and values[metric_id] is not None
    }


def _normalise_status_fact(item) -> dict[str, Any]:
    payload = dc_to_dict(item)
    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    if payload.get("code") == "consecutive_high_load_hikes":
        evidence = dict(evidence)
        if "hike_days" in evidence and "dates" not in evidence:
            evidence["dates"] = evidence["hike_days"]
    if payload.get("code") == "running_volume_jump":
        evidence = dict(evidence)
        aliases = {
            "current_week_distance_km": "current_week_km",
            "previous_week_distance_km": "previous_week_km",
            "increase_pct": "pct_change",
        }
        for source, target in aliases.items():
            if source in evidence and target not in evidence:
                evidence[target] = evidence[source]
    payload["evidence"] = evidence
    return payload


def _supported_gear_section(
    recent_items: list[dict[str, Any]],
    *,
    checked_at: datetime,
    connection,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for workout in recent_items:
        activity_id = workout.get("activity_id")
        if activity_id is None:
            continue
        detail = get_workout_detail_service(
            activity_id,
            now=checked_at,
            signal_first_use=False,
            connection=connection,
        )
        detail_data = dc_to_dict(detail).get("data")
        if not isinstance(detail_data, dict):
            continue
        gear = {metric_id: detail_data.get(metric_id) for metric_id in GEAR_METRIC_IDS}
        if any(value is not None for value in gear.values()):
            items.append({"activity_id": int(activity_id), **gear})

    included = tuple(
        metric_id for metric_id in GEAR_METRIC_IDS if any(item.get(metric_id) is not None for item in items)
    )
    skipped = () if included else tuple(_reason(metric_id, "gear_data_not_mirrored") for metric_id in GEAR_METRIC_IDS)
    return {
        "items": items,
        "bundle_completeness": _bundle_completeness(
            GEAR_METRIC_IDS,
            included_metrics=included,
            skipped_metrics=skipped,
        ),
    }


def _section(
    *,
    requested: tuple[str, ...],
    rows: list[dict[str, Any]] | None = None,
    items: list[dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
    facts: dict[str, Any] | None = None,
    periods: dict[str, Any] | None = None,
    comparison: dict[str, Any] | None = None,
    season: str | None = None,
    current_week: dict[str, Any] | None = None,
    read_model: dict[str, Any] | None = None,
    row_count: int | None = None,
) -> dict[str, Any]:
    section: dict[str, Any] = {}
    if rows is not None:
        section["rows"] = rows
    if items is not None:
        section["items"] = items
    if metrics is not None:
        section["metrics"] = metrics
    if facts is not None:
        section["facts"] = facts
    if periods is not None:
        section["periods"] = periods
    if comparison is not None:
        section["comparison"] = comparison
    if season is not None:
        section["season"] = season
    if current_week is not None:
        section["current_week"] = current_week
    if read_model is not None:
        section["read_model"] = read_model
    if row_count is not None:
        section["row_count"] = row_count

    included = _included_metrics(requested, rows=rows, items=items, metrics=metrics, facts=facts)
    section["bundle_completeness"] = _bundle_completeness(requested, included_metrics=tuple(included))
    return section


def _included_metrics(
    requested: tuple[str, ...],
    *,
    rows: list[dict[str, Any]] | None,
    items: list[dict[str, Any]] | None,
    metrics: dict[str, Any] | None,
    facts: dict[str, Any] | None,
) -> set[str]:
    requested_set = set(requested)
    included: set[str] = set()
    if rows is not None:
        for row in rows:
            metric_id = row.get("metric_id")
            if metric_id in requested_set and row.get("completeness_status") != "unavailable":
                included.add(str(metric_id))
    for payload in (metrics, facts):
        if payload:
            included.update(
                metric_id for metric_id, value in payload.items() if metric_id in requested_set and value is not None
            )
    if items:
        for item in items:
            included.update(metric_id for metric_id in requested_set if item.get(metric_id) is not None)
    return included


def _bundle_data(
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
        "bundle_completeness": _bundle_completeness(requested_metrics, included_metrics=tuple(included)),
    }


def _bundle_completeness(
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
    for metric_id in requested:
        if metric_id not in accounted:
            unavailable.append(_reason(metric_id, "data_absent"))
    return {
        "requested_metrics": list(requested),
        "included_metrics": list(included),
        "unavailable_metrics": unavailable,
        "skipped_metrics": skipped,
        "scope_incompatible_metrics": scope_incompatible,
    }


def _reason(metric_id: str, reason_code: str, *, evidence_count: int = 0) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "reason_code": reason_code,
        "evidence_count": evidence_count,
    }


def _read_model_from(*payloads: dict[str, Any]) -> dict[str, Any]:
    for payload in payloads:
        completeness = payload.get("completeness")
        if not isinstance(completeness, dict):
            continue
        coverage = completeness.get("coverage")
        if not isinstance(coverage, dict):
            continue
        read_model = coverage.get("read_model")
        if isinstance(read_model, dict):
            return read_model
    return {
        "status": "unavailable",
        "last_materialized_at": None,
        "dirty_count": 0,
        "oldest_dirty_day": None,
        "metric_versions_present": [],
        "stale_reason": "read_model_metadata_absent",
    }


def _service_envelope(
    data: dict[str, Any],
    primary: ServiceEnvelope,
    related: list[ServiceEnvelope],
    read_model: dict[str, Any],
    requested_metrics: set[str],
) -> ServiceEnvelope:
    section_statuses = [_section_status(section) for section in data["sections"].values() if isinstance(section, dict)]
    missing = sorted(_missing_reasons(data))
    coverage = {
        "read_model": read_model,
        "bundle_id": data["bundle_id"],
        "requested_metrics": sorted(requested_metrics),
        "section_count": len(data["sections"]),
    }
    warnings = _dedupe_warnings([*primary.warnings, *(warning for env in related for warning in env.warnings)])
    return ServiceEnvelope(
        data=data,
        freshness=primary.freshness,
        completeness=CompletenessMetadata(
            status=_overall_status(section_statuses, read_model),
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


def _section_status(section: dict[str, Any]) -> str:
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


def _overall_status(section_statuses: list[str], read_model: dict[str, Any]) -> str:
    if read_model.get("status") == "stale":
        return "stale"
    if not section_statuses or all(status == "unavailable" for status in section_statuses):
        return "unavailable"
    if any(status != "complete" for status in section_statuses):
        return "partial"
    return "complete"


def _missing_reasons(data: dict[str, Any]) -> set[str]:
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


def _dedupe_warnings(warnings: list[ServiceWarning]) -> list[ServiceWarning]:
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


def _season(day: date) -> str:
    if day.month in {12, 1, 2}:
        return "winter"
    if day.month in {3, 4, 5}:
        return "spring"
    if day.month in {6, 7, 8}:
        return "summer"
    return "autumn"


def registered_product_bundle_ids() -> tuple[str, ...]:
    return tuple(bundle_id for bundle_id in AGGREGATE_METRIC_BUNDLES if bundle_id in PRODUCT_FACT_BUNDLES)
