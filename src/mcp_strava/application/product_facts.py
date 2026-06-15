"""Shared product factual bundle services.

These services assemble narrative-ready facts from existing application services
and aggregate rows. They intentionally stay factual: no sync controls, raw SQL,
Strava calls, or coaching advice crosses this boundary.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import date, datetime, timedelta
from typing import Any, cast

from mcp_strava.adapters.duckdb.aggregate_queries import query_status_facts
from mcp_strava.adapters.duckdb.connection import ReadConn
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.application.aggregate_services import (
    AggregateServiceRequest,
    get_training_aggregates_service,
)
from mcp_strava.application.comparison_services import PeriodComparisonRequest, compare_periods_service
from mcp_strava.application.freshness import _freshness_now
from mcp_strava.application.metric_services import (
    get_fitness_state_service,
    get_workout_detail_service,
    list_workouts_service,
)
from mcp_strava.application.product_bundle_format import (
    BundleSectionContent,
    bundle_completeness,
    bundle_data,
    bundle_section,
    data_list,
    dict_data,
    filter_rows,
    metric_values,
    pick_metrics,
    read_model_from,
    reason,
    rows_from_payload,
    season,
    service_envelope,
)
from mcp_strava.metric_registry import STATUS_FACT_REGISTRY, metrics_for_aggregate_bundle
from mcp_strava.types import (
    ServiceEnvelope,
    dc_to_dict,
)

GEAR_METRIC_IDS = ("gear_id", "gear_name", "gear_distance_km", "gear_primary")


def get_daily_brief_facts_service(
    *,
    as_of_day: str,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    # WR-02: default to a UTC-naive instant. checked_at flows down only as the
    # `now` for freshness (instant vs UTC last_success_at) and relative_time (an
    # instant duration); the wall-clock calendar comes from the explicit as_of_day.
    checked_at = now if now is not None else _freshness_now()
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
            data_list(gear_candidates),
            checked_at=checked_at,
            connection=conn,
        )

    # dc_to_dict returns Any; annotate as dict[str, object] to erase the Any cascade.
    fitness_payload: dict[str, object] = cast("dict[str, object]", dc_to_dict(fitness))
    recent_payload: dict[str, object] = cast("dict[str, object]", dc_to_dict(recent))
    bundle_payload: dict[str, object] = cast("dict[str, object]", dc_to_dict(bundle_rows))
    daily_payload: dict[str, object] = cast("dict[str, object]", dc_to_dict(daily_load))
    by_sport_payload: dict[str, object] = cast("dict[str, object]", dc_to_dict(by_sport))
    read_model = read_model_from(fitness_payload, bundle_payload)
    # fitness_payload["freshness"] is object (dict[str,object].__getitem__); cast for _section.
    freshness_payload: dict[str, object] = cast("dict[str, object]", fitness_payload["freshness"])
    requested = set(metrics_for_aggregate_bundle("daily_brief"))
    bundle_metric_values = metric_values(rows_from_payload(bundle_payload))

    sections = {
        "current_state": bundle_section(
            requested=("fitness", "fatigue", "form", "form_zone", "acwr", "acwr_zone"),
            content=BundleSectionContent(
                metrics=pick_metrics(
                    dict_data(fitness_payload), ("fitness", "fatigue", "form", "form_zone", "acwr", "acwr_zone")
                ),
            ),
        ),
        "recent_workouts": bundle_section(
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
            content=BundleSectionContent(items=data_list(recent_payload)),
        ),
        "daily_load_14d": bundle_section(
            requested=("trimp", "distance_km", "moving_time_min", "elevation_m", "kudos_count"),
            content=BundleSectionContent(rows=rows_from_payload(daily_payload)),
        ),
        "by_sport": bundle_section(
            requested=("trimp", "distance_km", "moving_time_min", "elevation_m", "kudos_count"),
            content=BundleSectionContent(rows=rows_from_payload(by_sport_payload)),
        ),
        "model_context": bundle_section(
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
            content=BundleSectionContent(
                metrics={
                    **pick_metrics(
                        dict_data(fitness_payload),
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
                    **pick_metrics(bundle_metric_values, ("weekly_trimp", "total_trimp_14d", "avg_trimp_per_day")),
                },
            ),
        ),
        "status_facts": bundle_section(
            requested=tuple(sorted({definition.metric_id for definition in STATUS_FACT_REGISTRY.values()})),
            content=BundleSectionContent(items=status_facts),
        ),
        "supported_gear": gear_section,
        "freshness": bundle_section(
            requested=("activity_date",),
            content=BundleSectionContent(facts=freshness_payload),
        ),
        "read_model": bundle_section(
            requested=("fitness",),
            content=BundleSectionContent(facts=read_model),
        ),
    }
    data = bundle_data(
        bundle_id="daily_brief",
        as_of_day=as_of_day,
        sections=sections,
        requested_metrics=tuple(metrics_for_aggregate_bundle("daily_brief")),
        rows=rows_from_payload(bundle_payload),
    )
    return service_envelope(
        data, fitness, [recent, gear_candidates, bundle_rows, daily_load, by_sport], read_model, requested
    )


def get_weekly_digest_facts_service(
    *,
    as_of_day: str,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    # WR-02: default to a UTC-naive instant. checked_at flows down only as the
    # `now` for freshness (instant vs UTC last_success_at) and relative_time (an
    # instant duration); the wall-clock calendar comes from the explicit as_of_day.
    checked_at = now if now is not None else _freshness_now()
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
            PeriodComparisonRequest(
                period_a_start=week_start.isoformat(),
                period_a_end=end_exclusive.isoformat(),
                period_b_start=previous_start.isoformat(),
                period_b_end=previous_end.isoformat(),
            ),
            now=checked_at,
            signal_first_use=False,
            connection=conn,
        )

    weekly_payload: dict[str, object] = cast("dict[str, object]", dc_to_dict(weekly))
    current_payload: dict[str, object] = cast("dict[str, object]", dc_to_dict(current_week))
    trends_payload: dict[str, object] = cast("dict[str, object]", dc_to_dict(trends))
    read_model = read_model_from(weekly_payload, trends_payload)
    rows = rows_from_payload(weekly_payload)
    sections = {
        "load": bundle_section(
            requested=("trimp", "weekly_trimp", "active_days"),
            content=BundleSectionContent(rows=filter_rows(rows, {"trimp", "weekly_trimp", "active_days"})),
        ),
        "volume": bundle_section(
            requested=("distance_km", "moving_time_min", "elapsed_time_min", "elevation_m", "volume_7d"),
            content=BundleSectionContent(
                rows=filter_rows(
                    rows, {"distance_km", "moving_time_min", "elapsed_time_min", "elevation_m", "volume_7d"}
                ),
            ),
        ),
        "efficiency": bundle_section(
            requested=("avg_hr", "max_hr", "cardiac_cost", "cardiac_cost_adjusted", "cardiac_drift_pct", "hrr_pct"),
            content=BundleSectionContent(
                rows=filter_rows(
                    rows,
                    {"avg_hr", "max_hr", "cardiac_cost", "cardiac_cost_adjusted", "cardiac_drift_pct", "hrr_pct"},
                ),
            ),
        ),
        "by_sport": bundle_section(
            requested=(
                "distance_km",
                "moving_time_min",
                "elevation_m",
                "avg_hr",
                "max_hr",
                "cardiac_cost",
                "cardiac_drift_pct",
            ),
            content=BundleSectionContent(rows=[row for row in rows if row.get("scope") == "per_sport"]),
        ),
        "current_week_activities": bundle_section(
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
            content=BundleSectionContent(items=data_list(current_payload)),
        ),
        "period_trends": bundle_section(
            requested=tuple(metrics_for_aggregate_bundle("period_comparison")),
            content=BundleSectionContent(
                periods={
                    "current": {"start": week_start.isoformat(), "end_exclusive": end_exclusive.isoformat()},
                    "previous": {"start": previous_start.isoformat(), "end_exclusive": previous_end.isoformat()},
                },
                comparison=cast("dict[str, object]", trends_payload["data"]),
            ),
        ),
        "freshness": bundle_section(
            requested=("activity_date",),
            content=BundleSectionContent(facts=cast("dict[str, object]", weekly_payload["freshness"])),
        ),
        "read_model": bundle_section(
            requested=("fitness",),
            content=BundleSectionContent(facts=read_model),
        ),
    }
    data = bundle_data(
        bundle_id="weekly_digest",
        as_of_day=as_of_day,
        sections=sections,
        requested_metrics=tuple(metrics_for_aggregate_bundle("weekly_digest")),
        rows=rows,
    )
    return service_envelope(
        data, weekly, [current_week, trends], read_model, set(metrics_for_aggregate_bundle("weekly_digest"))
    )


def get_historical_facts_service(
    *,
    as_of_day: str,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    # WR-02: default to a UTC-naive instant. checked_at flows down only as the
    # `now` for freshness (instant vs UTC last_success_at) and relative_time (an
    # instant duration); the wall-clock calendar comes from the explicit as_of_day.
    checked_at = now if now is not None else _freshness_now()
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

    historical_payload: dict[str, object] = cast("dict[str, object]", dc_to_dict(historical))
    rows = rows_from_payload(historical_payload)
    facts = metric_values(rows)
    read_model = read_model_from(historical_payload)
    sections = {
        "activity_context": bundle_section(
            requested=("activity_streak_days", "rest_streak_days", "last_hike_days_ago"),
            content=BundleSectionContent(
                facts=pick_metrics(facts, ("activity_streak_days", "rest_streak_days", "last_hike_days_ago")),
            ),
        ),
        "calendar_context": bundle_section(
            requested=("activity_date",),
            content=BundleSectionContent(
                season=season(as_of),
                current_week={
                    "week_start": week_start.isoformat(),
                    "window_start": week_start.isoformat(),
                    "window_end_exclusive": end_exclusive.isoformat(),
                },
            ),
        ),
        "coverage": bundle_section(
            requested=tuple(metrics_for_aggregate_bundle("historical_facts")),
            content=BundleSectionContent(read_model=read_model, row_count=len(rows)),
        ),
        "freshness": bundle_section(
            requested=("activity_date",),
            content=BundleSectionContent(facts=cast("dict[str, object]", historical_payload["freshness"])),
        ),
        "read_model": bundle_section(
            requested=("fitness",),
            content=BundleSectionContent(facts=read_model),
        ),
    }
    data = bundle_data(
        bundle_id="historical_facts",
        as_of_day=as_of_day,
        sections=sections,
        requested_metrics=tuple(metrics_for_aggregate_bundle("historical_facts")),
        rows=rows,
    )
    return service_envelope(data, historical, [], read_model, set(metrics_for_aggregate_bundle("historical_facts")))


def _connection_context(connection):
    return nullcontext(connection) if connection is not None else ReadConn()


def _parse_day(value: str) -> date:
    return date.fromisoformat(value)


def _normalise_status_fact(item: object) -> dict[str, Any]:
    payload: dict[str, object] = cast("dict[str, object]", dc_to_dict(item))
    evidence_raw: object = payload.get("evidence")
    evidence: dict[str, object] = evidence_raw if isinstance(evidence_raw, dict) else {}
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
    return cast("dict[str, Any]", payload)


def _supported_gear_section(
    recent_items: list[dict[str, Any]],
    *,
    checked_at: datetime,
    connection,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for workout in recent_items:
        activity_id_raw: object = cast("object", workout.get("activity_id"))
        if activity_id_raw is None:
            continue
        detail = get_workout_detail_service(
            activity_id_raw,  # type: ignore[arg-type]
            now=checked_at,
            signal_first_use=False,
            connection=connection,
        )
        detail_dict: dict[str, object] = cast("dict[str, object]", dc_to_dict(detail))
        detail_data_raw: object = detail_dict.get("data")
        if not isinstance(detail_data_raw, dict):
            continue
        detail_data: dict[str, object] = detail_data_raw
        gear = {metric_id: detail_data.get(metric_id) for metric_id in GEAR_METRIC_IDS}
        if any(value is not None for value in gear.values()):
            items.append({"activity_id": int(activity_id_raw), **gear})  # type: ignore[arg-type]

    included = tuple(
        metric_id for metric_id in GEAR_METRIC_IDS if any(item.get(metric_id) is not None for item in items)
    )
    skipped = () if included else tuple(reason(metric_id, "gear_data_not_mirrored") for metric_id in GEAR_METRIC_IDS)
    return {
        "items": items,
        "bundle_completeness": bundle_completeness(
            GEAR_METRIC_IDS,
            included_metrics=included,
            skipped_metrics=skipped,
        ),
    }
