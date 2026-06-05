"""Period-comparison application services for MCP-facing tool backends."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import datetime
from typing import Any, cast

from mcp_strava.adapters.duckdb.connection import ReadConn
from mcp_strava.application.aggregate_services import (
    AggregateServiceRequest,
    get_training_aggregates_service,
)
from mcp_strava.types import CompletenessMetadata, ServiceEnvelope, ServiceRationale, ServiceWarning

COMPARISON_MISSING_REASONS = {
    "insufficient_history",
    "missing_denominator",
    "missing_hr",
    "missing_streams",
    "metric_not_applicable",
    "no_activity_in_period",
    "read_model_unavailable",
}


def _connection_context(connection):
    return nullcontext(connection) if connection is not None else ReadConn()


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _rationale(message: str) -> list[ServiceRationale]:
    return [ServiceRationale(code="metric_bundle_from_read_model", message=message)]


def _aggregate_rows(envelope: ServiceEnvelope) -> list[dict[str, Any]]:
    # ServiceEnvelope.data is typed Any; route through object to erase Any at assignment.
    _env_data: object = cast("object", envelope.data)
    data: dict[str, object] = _env_data if isinstance(_env_data, dict) else {}
    rows_raw: object = data.get("rows", [])
    rows: list[object] = rows_raw if isinstance(rows_raw, list) else []
    return [row for row in rows if isinstance(row, dict)]  # type: ignore[return-value]


def _compare_row_key(row: dict[str, Any]) -> tuple[str, str | None, str]:
    scope_raw: object = cast("object", row.get("scope")) or "global"
    scope = str(scope_raw)
    mid_raw: object = cast("object", row.get("metric_id")) or ""
    metric_id = str(mid_raw)
    if scope == "per_sport":
        return scope, str(row.get("sport_type") or "unknown"), metric_id
    return "global", None, metric_id


def _compare_rows_by_key(rows: list[dict[str, Any]]) -> dict[tuple[str, str | None, str], dict[str, Any]]:
    return {_compare_row_key(row): row for row in rows}


def _row_missing_reasons(row: dict[str, Any] | None) -> list[str]:
    if row is None:
        return ["no_activity_in_period"]
    reasons = row.get("missing_reasons") or []
    return [str(reason) for reason in reasons if reason]


def _row_sample_size(row: dict[str, Any] | None) -> int:
    if row is None:
        return 0
    return int(row.get("sample_size") or 0)


def _row_activity_count(row: dict[str, Any] | None) -> int:
    if row is None:
        return 0
    return int(row.get("activity_count") or 0)


def _coverage_value(row: dict[str, Any] | None) -> float:
    if row is None or str(row.get("completeness_status")) == "unavailable":
        return 0.0
    if str(row.get("completeness_status")) == "partial":
        return 0.5
    return 1.0


def _period_record(row: dict[str, Any] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sample_size": _row_sample_size(row),
        "activity_count": _row_activity_count(row),
        "completeness_status": str(row.get("completeness_status")) if row is not None else "unavailable",
        "missing_reasons": _row_missing_reasons(row),
        "metric_version_status": str(row.get("metric_version_status")) if row is not None else "unavailable",
        "bucket_start": row.get("bucket_start") if row is not None else None,
        "bucket_end": row.get("bucket_end") if row is not None else None,
    }
    distribution = row.get("distribution") if row is not None else None
    if isinstance(distribution, dict):
        payload["buckets"] = distribution
    else:
        payload["value"] = row.get("value") if row is not None else None
    return payload


def _metric_version_status(row_a: dict[str, Any] | None, row_b: dict[str, Any] | None) -> str:
    statuses = {
        str(row.get("metric_version_status"))
        for row in (row_a, row_b)
        if row is not None and row.get("metric_version_status") is not None
    }
    if not statuses:
        return "unavailable"
    if "mixed_degraded" in statuses:
        return "mixed_degraded"
    if "mixed_allowed" in statuses:
        return "mixed_allowed"
    if len(statuses) == 1:
        return next(iter(statuses))
    return "mixed_degraded"


def _distribution_delta(
    row_a: dict[str, Any] | None,
    row_b: dict[str, Any] | None,
) -> tuple[dict[str, float], dict[str, float | None], float | None]:
    _dist_a = row_a.get("distribution") if row_a is not None else None
    _dist_b = row_b.get("distribution") if row_b is not None else None
    buckets_a: dict[str, object] = _dist_a if isinstance(_dist_a, dict) else {}
    buckets_b: dict[str, object] = _dist_b if isinstance(_dist_b, dict) else {}
    keys = sorted(set(buckets_a) | set(buckets_b))
    deltas: dict[str, float] = {}
    delta_pct: dict[str, float | None] = {}

    def _fval(v: object) -> float:
        # Narrow object | None from dict[str, object].get() to float; None -> 0.0.
        return float(v) if v is not None else 0.0  # type: ignore[arg-type]

    for key in keys:
        a_value = _fval(buckets_a.get(key))
        b_value = _fval(buckets_b.get(key))
        delta = round(a_value - b_value, 3)
        deltas[key] = delta
        delta_pct[key] = round((delta / b_value) * 100, 2) if b_value else None
    total_a = sum(_fval(value) for value in buckets_a.values())
    total_b = sum(_fval(value) for value in buckets_b.values())
    overlap = None
    if total_a > 0 and total_b > 0:
        overlap = round(
            (sum(min(_fval(buckets_a.get(key)), _fval(buckets_b.get(key))) for key in keys) / max(total_a, total_b))
            * 100,
            2,
        )
    return deltas, delta_pct, overlap


def _compare_aggregate_pair(row_a: dict[str, Any] | None, row_b: dict[str, Any] | None) -> dict[str, Any]:
    period_a = _period_record(row_a)
    period_b = _period_record(row_b)
    missing = sorted(set(_row_missing_reasons(row_a) + _row_missing_reasons(row_b)))
    distribution_a = row_a is not None and isinstance(row_a.get("distribution"), dict)
    distribution_b = row_b is not None and isinstance(row_b.get("distribution"), dict)
    if distribution_a or distribution_b:
        bucket_deltas, bucket_delta_pct, overlap = _distribution_delta(row_a, row_b)
        return {
            "period_a": period_a,
            "period_b": period_b,
            "bucket_deltas": bucket_deltas,
            "bucket_delta_pct": bucket_delta_pct,
            "distribution_overlap_pct": overlap,
            "delta": None,
            "delta_pct": None,
            "trend_direction": "unavailable",
            "sample_size": {"period_a": _row_sample_size(row_a), "period_b": _row_sample_size(row_b)},
            "coverage": {"period_a": _coverage_value(row_a), "period_b": _coverage_value(row_b)},
            "missing_reasons": missing,
            "metric_version_status": _metric_version_status(row_a, row_b),
        }

    value_a = period_a.get("value")
    value_b = period_b.get("value")
    delta: float | None = (
        round(float(value_a) - float(value_b), 3)  # type: ignore[arg-type]
        if _is_number(value_a) and _is_number(value_b)
        else None
    )
    delta_pct: float | None = (
        round((delta / float(value_b)) * 100, 2)  # type: ignore[arg-type]
        if _is_number(delta) and _is_number(value_b) and float(value_b) != 0  # type: ignore[arg-type]
        else None
    )
    trend = "unavailable"
    if delta is not None:
        trend = "flat" if abs(delta) < 1e-9 else ("up" if delta > 0 else "down")
    return {
        "period_a": period_a,
        "period_b": period_b,
        "delta": delta,
        "delta_pct": delta_pct,
        "trend_direction": trend,
        "sample_size": {"period_a": _row_sample_size(row_a), "period_b": _row_sample_size(row_b)},
        "coverage": {"period_a": _coverage_value(row_a), "period_b": _coverage_value(row_b)},
        "missing_reasons": missing,
        "metric_version_status": _metric_version_status(row_a, row_b),
    }


def _compare_request(
    *,
    start_day: str,
    end_day_exclusive: str,
    sport: str | None,
) -> AggregateServiceRequest:
    return AggregateServiceRequest(
        metric_ids=(),
        bundle_id="period_comparison",
        bucket="all_time",
        start_day=start_day,
        end_day_exclusive=end_day_exclusive,
        scope="both",
        sport_filter=sport,
    )


def compare_periods_service(
    *,
    period_a_start: str,
    period_a_end: str,
    period_b_start: str,
    period_b_end: str,
    sport: str | None = None,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    checked_at = now or datetime.now()  # noqa: DTZ005 — local wall-clock for as_of_day/relative_time display (freshness uses _freshness_clock)
    with _connection_context(connection) as conn:
        period_a_envelope = get_training_aggregates_service(
            _compare_request(
                start_day=period_a_start,
                end_day_exclusive=period_a_end,
                sport=sport,
            ),
            now=checked_at,
            signal_first_use=signal_first_use,
            connection=conn,
        )
        period_b_envelope = get_training_aggregates_service(
            _compare_request(
                start_day=period_b_start,
                end_day_exclusive=period_b_end,
                sport=sport,
            ),
            now=checked_at,
            signal_first_use=False,
            connection=conn,
        )

    period_a_by_key = _compare_rows_by_key(_aggregate_rows(period_a_envelope))
    period_b_by_key = _compare_rows_by_key(_aggregate_rows(period_b_envelope))
    keys = sorted(set(period_a_by_key) | set(period_b_by_key))
    global_section = {"scope_filter": "sport" if sport else "all", "metrics": {}}
    per_sport_section: dict[str, dict[str, Any]] = {}
    for scope, sport_name, metric_id in keys:
        comparison = _compare_aggregate_pair(
            period_a_by_key.get((scope, sport_name, metric_id)), period_b_by_key.get((scope, sport_name, metric_id))
        )
        if scope == "per_sport":
            if sport is not None and sport_name != sport:
                continue
            resolved_sport = sport_name or "unknown"
            per_sport_section.setdefault(resolved_sport, {"metrics": {}})
            per_sport_section[resolved_sport]["metrics"][metric_id] = comparison
        else:
            global_section["metrics"][metric_id] = comparison

    data = {
        "periods": {
            "period_a": {"start": period_a_start, "end": period_a_end},
            "period_b": {"start": period_b_start, "end": period_b_end},
        },
        "global": global_section,
        "per_sport": per_sport_section,
    }
    # coverage is dict[str, Any]; route through cast to erase the Any at assignment.
    _rm_a: object = cast("object", period_a_envelope.completeness.coverage.get("read_model", {}))
    read_model: dict[str, object] = _rm_a if isinstance(_rm_a, dict) else {}
    _rm_b: object = cast("object", period_b_envelope.completeness.coverage.get("read_model", {}))
    period_b_read_model: dict[str, object] = _rm_b if isinstance(_rm_b, dict) else {}
    comparison_missing = sorted(
        set(period_a_envelope.completeness.missing) | set(period_b_envelope.completeness.missing)
    )
    comparison_status = _comparison_completeness_status(
        period_a_envelope.completeness.status,
        period_b_envelope.completeness.status,
        period_a_read_model=read_model,
        period_b_read_model=period_b_read_model,
        has_data=bool(global_section["metrics"] or per_sport_section),
    )
    completeness = CompletenessMetadata(
        status=comparison_status,
        missing=comparison_missing,
        coverage={
            "global_metrics": sorted(global_section["metrics"].keys()),
            "per_sport": sorted(per_sport_section.keys()),
            "supported_missing_reasons": sorted(COMPARISON_MISSING_REASONS),
            "read_model": read_model,
            "period_b_read_model": period_b_read_model,
        },
    )
    return ServiceEnvelope(
        data=data,
        freshness=period_a_envelope.freshness,
        completeness=completeness,
        warnings=_dedupe_warnings([*period_a_envelope.warnings, *period_b_envelope.warnings]),
        rationale=_rationale(
            "Period comparison formats two bounded all-time aggregate requests over prepared local metric facts."
        ),
    )


def _dedupe_warnings(warnings: list[ServiceWarning]) -> list[ServiceWarning]:
    deduped: list[ServiceWarning] = []
    seen: set[tuple[str, str, str, str | None, str | None]] = set()
    for warning in warnings:
        evidence_key = (
            json.dumps(warning.evidence, sort_keys=True, default=str) if warning.evidence is not None else None
        )
        key = (warning.code, warning.severity, warning.message, warning.field, evidence_key)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(warning)
    return deduped


def _comparison_completeness_status(
    period_a_status: str,
    period_b_status: str,
    *,
    period_a_read_model: dict[str, object],
    period_b_read_model: dict[str, object],
    has_data: bool,
) -> str:
    if not has_data:
        return "unavailable"
    if period_a_read_model.get("status") == "stale" or period_b_read_model.get("status") == "stale":
        return "stale"
    if period_a_status != "complete" or period_b_status != "complete":
        return "partial"
    return "complete"
