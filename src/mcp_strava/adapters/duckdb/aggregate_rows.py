"""Aggregate row projection helpers for DuckDB aggregate queries."""

from __future__ import annotations

from datetime import date, timedelta

from mcp_strava.adapters.duckdb.aggregate_models import AggregateRequest, AggregateRow
from mcp_strava.metric_registry import DEFAULT_AGGREGATE_QUANTILES
from mcp_strava.types import MetricDefinition


def to_iso(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def as_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError(f"expected an int-like cell, got {type(value).__name__}")


def as_float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"expected a float-like cell, got {type(value).__name__}")


def aggregate_row_from_group(
    metric: MetricDefinition,
    request: AggregateRequest,
    effective_start: date,
    effective_end: date,
    row: dict[str, object],
) -> AggregateRow:
    bucket_start = to_iso(row["bucket_start"])
    bucket_end = _bucket_end(bucket_start, request, effective_end)
    value = _aggregate_value(metric, row)
    raw_distribution = row.get("distribution") if metric.aggregate_mode == "distribution" else None
    distribution = raw_distribution if isinstance(raw_distribution, dict) else None
    quantiles = _quantiles(metric, row)
    missing_reasons = _missing_reasons(row)
    excluded_count = as_int(row.get("excluded_count"))
    null_count = as_int(row.get("null_count"))
    if excluded_count:
        missing_reasons.append("missing_denominator")
    row_count = as_int(row.get("row_count"))
    if distribution is not None and row_count == 0:
        row_count = sum(as_int(count) for count in distribution.values())
    statuses = row.get("completeness_statuses")
    completeness = _completeness_status(
        value=value,
        distribution=distribution,
        row_count=row_count,
        null_count=null_count,
        excluded_count=excluded_count,
        statuses=statuses if isinstance(statuses, list) else [],
    )
    sport_type = row.get("output_sport_type")
    return AggregateRow(
        bucket_start=bucket_start,
        bucket_end=bucket_end,
        bucket_width=_bucket_width(request),
        metric_id=metric.metric_id,
        unit=metric.unit,
        calculation=metric.calculation,
        aggregation_mode=str(metric.aggregate_mode),
        denominator=metric.denominator,
        value=value,
        quantiles=quantiles,
        distribution=distribution,
        sample_size=as_int(row.get("sample_size")),
        activity_count=as_int(row.get("activity_count")),
        null_count=null_count,
        excluded_count=excluded_count,
        completeness_status=completeness,
        missing_reasons=sorted(set(missing_reasons)),
        metric_version_status=_metric_version_status(metric, as_int(row.get("metric_version_count"))),
        materialized_at=str(row["materialized_at"]) if row.get("materialized_at") else None,
        mirror_freshness=None,
        read_model_freshness=None,
        scope=request.scope,
        sport_type=sport_type if isinstance(sport_type, str) else None,
    )


def with_empty_rows(
    rows: list[AggregateRow],
    metric: MetricDefinition,
    request: AggregateRequest,
    effective_start: date,
    effective_end: date,
) -> list[AggregateRow]:
    if request.window_days is not None:
        return rows or [_empty_row(metric, request, effective_start, effective_end, request.sport_filter)]
    if request.bucket == "all_time":
        return rows or [_empty_row(metric, request, effective_start, effective_end, request.sport_filter)]
    if not request.include_empty_buckets:
        return rows

    existing = {(row.bucket_start, row.sport_type) for row in rows}
    sport_type = request.sport_filter if request.scope == "per_sport" else None
    current = _bucket_start_for_day(effective_start, request.bucket)
    additions: list[AggregateRow] = []
    while current < effective_end:
        key = (current.isoformat(), sport_type)
        if key not in existing:
            additions.append(
                _empty_row(
                    metric,
                    request,
                    current,
                    date.fromisoformat(_bucket_end(current.isoformat(), request, effective_end)),
                    sport_type,
                )
            )
        current = _next_bucket(current, request.bucket)
    return sorted([*rows, *additions], key=lambda row: (row.bucket_start, row.metric_id, row.sport_type or ""))


def max_text(left: object | None, right: object | None) -> str | None:
    if left is None:
        return str(right) if right is not None else None
    if right is None:
        return str(left)
    return max(str(left), str(right))


def _aggregate_value(metric: MetricDefinition, row: dict[str, object]) -> float | int | str | None:
    if metric.aggregate_mode == "distribution":
        return None
    value = row.get("value")
    if value is None:
        return None
    return as_float(value)


def _quantiles(metric: MetricDefinition, row: dict[str, object]) -> dict[str, float] | None:
    if metric.aggregate_mode != "quantile":
        return None
    value = row.get("value")
    if value is None:
        return None
    return _quantiles_from_group(row)


def _quantiles_from_group(row: dict[str, object]) -> dict[str, float] | None:
    values = row.get("quantile_values")
    if not values:
        median = row.get("value")
        if median is None:
            return None
        median_value = as_float(median)
        return dict.fromkeys(DEFAULT_AGGREGATE_QUANTILES, median_value)
    if not isinstance(values, list):
        return None
    return {label: as_float(value) for label, value in zip(DEFAULT_AGGREGATE_QUANTILES, values, strict=False)}


def _missing_reasons(row: dict[str, object]) -> list[str]:
    payloads = row.get("missing_reason_payloads")
    if not isinstance(payloads, list):
        return []
    return [str(item) for item in payloads if item is not None]


def _completeness_status(
    *,
    value: object,
    distribution: dict[str, int] | None,
    row_count: int,
    null_count: int,
    excluded_count: int,
    statuses: list[object],
) -> str:
    if row_count <= 0:
        return "unavailable"
    if distribution is not None and not distribution:
        return "unavailable"
    if distribution is None and value is None:
        return "unavailable"
    if (
        excluded_count > 0
        or null_count > 0
        or any(str(status) != "complete" for status in statuses if status is not None)
    ):
        return "partial"
    return "complete"


def _metric_version_status(metric: MetricDefinition, version_count: int) -> str:
    if version_count <= 0:
        return "unavailable"
    if version_count == 1:
        return "single"
    if metric.metric_version_policy == "mixed_allowed":
        return "mixed_allowed"
    return "mixed_degraded"


def _bucket_width(request: AggregateRequest) -> str:
    if request.window_days is not None:
        return f"rolling_{request.window_days}d"
    return request.bucket


def _bucket_end(bucket_start: str, request: AggregateRequest, effective_end: date) -> str:
    if request.window_days is not None or request.bucket == "all_time":
        return effective_end.isoformat()
    start = date.fromisoformat(bucket_start)
    if request.bucket == "day":
        return (start + timedelta(days=1)).isoformat()
    if request.bucket == "week":
        return (start + timedelta(days=7)).isoformat()
    if request.bucket == "month":
        year = start.year + (1 if start.month == 12 else 0)  # noqa: PLR2004
        month = 1 if start.month == 12 else start.month + 1  # noqa: PLR2004
        return date(year, month, 1).isoformat()
    if request.bucket == "year":
        return date(start.year + 1, 1, 1).isoformat()
    return effective_end.isoformat()


def _empty_row(
    metric: MetricDefinition,
    request: AggregateRequest,
    bucket_start: date,
    bucket_end: date,
    sport_type: str | None,
) -> AggregateRow:
    return AggregateRow(
        bucket_start=bucket_start.isoformat(),
        bucket_end=bucket_end.isoformat(),
        bucket_width=_bucket_width(request),
        metric_id=metric.metric_id,
        unit=metric.unit,
        calculation=metric.calculation,
        aggregation_mode=str(metric.aggregate_mode),
        denominator=metric.denominator,
        value=None,
        quantiles=None,
        distribution={} if metric.aggregate_mode == "distribution" else None,
        sample_size=0,
        activity_count=0,
        null_count=0,
        excluded_count=0,
        completeness_status="unavailable",
        missing_reasons=["no_facts"],
        metric_version_status="unavailable",
        materialized_at=None,
        mirror_freshness=None,
        read_model_freshness=None,
        scope=request.scope,
        sport_type=sport_type,
    )


def _bucket_start_for_day(day: date, bucket: str) -> date:
    if bucket == "day":
        return day
    if bucket == "week":
        return day - timedelta(days=day.weekday())
    if bucket == "month":
        return date(day.year, day.month, 1)
    if bucket == "year":
        return date(day.year, 1, 1)
    return day


def _next_bucket(start: date, bucket: str) -> date:
    if bucket == "day":
        return start + timedelta(days=1)
    if bucket == "week":
        return start + timedelta(days=7)
    if bucket == "month":
        year = start.year + (1 if start.month == 12 else 0)  # noqa: PLR2004
        month = 1 if start.month == 12 else start.month + 1  # noqa: PLR2004
        return date(year, month, 1)
    if bucket == "year":
        return date(start.year + 1, 1, 1)
    return start
