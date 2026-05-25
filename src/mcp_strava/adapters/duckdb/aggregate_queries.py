"""Whitelisted DuckDB aggregate query builders over prepared metric facts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import calendar
import json
from typing import Any

from mcp_strava.adapters.duckdb.schema import create_aggregate_views
from mcp_strava.application.metric_registry import (
    METRIC_REGISTRY,
    SUPPORTED_AGGREGATE_BUCKETS,
    SUPPORTED_ROLLING_WINDOW_DAYS,
    metrics_for_aggregate_bundle,
)
from mcp_strava.constants import ALL_SPORTS
from mcp_strava.types import MetricDefinition


@dataclass(frozen=True)
class AggregateRequest:
    metric_ids: tuple[str, ...]
    bucket: str
    start_day: str | None
    end_day_exclusive: str
    bundle_id: str | None = None
    scope: str = "global"
    sport_filter: str | None = None
    include_empty_buckets: bool = False
    as_of_day: str | None = None
    window_days: int | None = None


@dataclass(frozen=True)
class AggregateQuery:
    statement: str
    params: tuple[object, ...]
    metric_id: str
    bucket: str


@dataclass
class AggregateRow:
    bucket_start: str
    bucket_end: str
    bucket_width: str
    metric_id: str
    unit: str
    calculation: str
    aggregation_mode: str
    denominator: str | None
    value: float | int | str | None
    quantiles: dict[str, float] | None
    distribution: dict[str, int] | None
    sample_size: int
    activity_count: int
    null_count: int
    excluded_count: int
    completeness_status: str
    missing_reasons: list[str] = field(default_factory=list)
    metric_version_status: str = "unavailable"
    materialized_at: str | None = None
    mirror_freshness: dict[str, Any] | None = None
    read_model_freshness: dict[str, Any] | None = None
    scope: str = "global"
    sport_type: str | None = None


_VERSION_STATUS_VIEW = "v_metric_version_status"
_SOURCE_VIEWS = {
    "activity_summary_fact": "v_activity_aggregate_facts",
    "activity_metric_fact": "v_activity_aggregate_facts",
    "daily_load_fact": "v_daily_aggregate_facts",
    "training_model_fact": "v_training_model_state_facts",
    "rolling_period_fact": "v_rolling_aggregate_facts",
    "social_fact": "v_activity_aggregate_facts",
    "historical_fact": "v_training_model_state_facts",
}
_SOURCE_DAY_COLUMNS = {
    "activity_summary_fact": "activity_day",
    "activity_metric_fact": "activity_day",
    "daily_load_fact": "day",
    "training_model_fact": "day",
    "rolling_period_fact": "as_of_day",
    "social_fact": "activity_day",
    "historical_fact": "day",
}
_ALLOWED_COLUMNS = {
    "activity_count",
    "activity_sample_count",
    "active_day_count",
    "rest_day_count",
    "calendar_days",
    "calendar_day_count",
    "model_day_count",
    "rolling_sample_count",
    "trimp",
    "distance_m",
    "moving_time_s",
    "elapsed_time_s",
    "elevation_gain_m",
    "avg_hr",
    "max_hr",
    "kudos_count",
    "heartrate_sample_count",
    "stream_sample_count",
    "hr_recovery_median_rate",
    "vertical_speed_vmh",
    "vertical_speed_total_ascent_m",
    "vertical_speed_duration_hours",
    "cardiac_cost",
    "adjusted_cardiac_cost",
    "cardiac_drift_pct",
    "cardiac_drift_significant",
    "cardiac_drift_severity",
    "cardiac_drift_quality",
    "hrr_pct",
    "effective_trimp",
    "fitness",
    "fatigue",
    "form",
    "form_zone",
    "acwr",
    "acwr_zone",
    "daily_avg_trimp_7d",
    "daily_avg_trimp_28d",
    "daily_avg_trimp_90d",
    "median_cardiac_cost",
    "median_adjusted_cardiac_cost",
    "median_hr_recovery",
    "median_cardiac_drift_pct",
}
_METRIC_VALUE_EXPRESSIONS = {
    "distance_km": "distance_m / 1000.0",
    "moving_time_min": "moving_time_s / 60.0",
    "elapsed_time_min": "elapsed_time_s / 60.0",
    "elevation_m": "elevation_gain_m",
}
_QUANTILE_LABELS = ("p25", "median", "p75")


def validate_aggregate_request(request: AggregateRequest) -> tuple[MetricDefinition, ...]:
    if request.bucket not in SUPPORTED_AGGREGATE_BUCKETS:
        raise ValueError(f"Unsupported aggregate bucket: {request.bucket}")
    if request.scope not in {"global", "per_sport"}:
        raise ValueError(f"Unsupported aggregate scope: {request.scope}")
    if request.sport_filter is not None and request.sport_filter not in ALL_SPORTS:
        raise ValueError(f"Unsupported sport filter: {request.sport_filter}")
    if request.window_days is not None:
        if request.window_days not in SUPPORTED_ROLLING_WINDOW_DAYS:
            raise ValueError(f"Unsupported rolling window days: {request.window_days}")
        if request.as_of_day is None:
            raise ValueError("as_of_day is required when window_days is supplied")
        _parse_day(request.as_of_day, "as_of_day")
    elif request.as_of_day is not None:
        raise ValueError("window_days is required when as_of_day is supplied")

    if request.start_day is not None:
        _parse_day(request.start_day, "start_day")
    end_day = _parse_day(request.end_day_exclusive, "end_day_exclusive")
    if request.start_day is not None and _parse_day(request.start_day, "start_day") >= end_day:
        raise ValueError("start_day must be before end_day_exclusive")

    metric_ids = _metric_ids_for_request(request)
    definitions = tuple(_metric_definition(metric_id) for metric_id in metric_ids)
    for metric in definitions:
        _validate_metric_scope(metric, request.scope)
        if request.bucket not in set(metric.supported_buckets):
            raise ValueError(f"Metric {metric.metric_id} does not support bucket {request.bucket}")
        if metric.aggregate_source not in _SOURCE_VIEWS:
            raise ValueError(f"Metric {metric.metric_id} has unsupported aggregate source")
        _value_expression(metric)
        _sample_expression(metric)
        _denominator_expression(metric)
    return definitions


def build_aggregate_query(metric: MetricDefinition, request: AggregateRequest) -> AggregateQuery:
    effective_start, effective_end = _effective_range_for_metric(None, request, metric)
    statement, params = _build_numeric_query(metric, request, effective_start, effective_end)
    return AggregateQuery(statement=statement, params=tuple(params), metric_id=metric.metric_id, bucket=request.bucket)


def query_training_aggregates(conn, request: AggregateRequest) -> list[AggregateRow]:
    create_aggregate_views(conn)
    definitions = validate_aggregate_request(request)
    rows: list[AggregateRow] = []
    for metric in definitions:
        effective_start, effective_end = _effective_range_for_metric(conn, request, metric)
        rows.extend(_query_metric(conn, request, metric, effective_start, effective_end))
    return sorted(rows, key=lambda row: (row.bucket_start, row.metric_id, row.sport_type or ""))


def _metric_ids_for_request(request: AggregateRequest) -> tuple[str, ...]:
    explicit = tuple(request.metric_ids or ())
    if explicit and request.bundle_id is not None:
        raise ValueError("Use metric_ids or bundle_id, not both")
    if request.bundle_id is not None:
        return metrics_for_aggregate_bundle(request.bundle_id)
    if not explicit:
        raise ValueError("At least one metric id or bundle_id is required")
    return explicit


def _metric_definition(metric_id: str) -> MetricDefinition:
    metric = METRIC_REGISTRY.get(metric_id)
    if metric is None or metric.aggregate_mode is None:
        raise ValueError(f"Unknown aggregate metric id: {metric_id}")
    return metric


def _validate_metric_scope(metric: MetricDefinition, scope: str) -> None:
    scopes = set(metric.supported_scopes)
    if scope == "global" and not ({"global", "both"} & scopes):
        raise ValueError(f"Metric {metric.metric_id} does not support global scope")
    if scope == "per_sport" and not ({"per_sport", "both"} & scopes):
        raise ValueError(f"Metric {metric.metric_id} does not support per_sport scope")


def _parse_day(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _to_iso(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _effective_range_for_metric(conn, request: AggregateRequest, metric: MetricDefinition) -> tuple[date, date]:
    if request.window_days is not None and request.as_of_day is not None:
        as_of = _parse_day(request.as_of_day, "as_of_day")
        return as_of - timedelta(days=request.window_days - 1), as_of + timedelta(days=1)
    end_day = _parse_day(request.end_day_exclusive, "end_day_exclusive")
    if request.start_day is not None:
        return _parse_day(request.start_day, "start_day"), end_day
    if request.bucket != "all_time":
        raise ValueError("start_day is required unless bucket is all_time")
    if conn is None:
        return end_day, end_day
    source = str(metric.aggregate_source)
    day_column = _SOURCE_DAY_COLUMNS[source]
    view = _SOURCE_VIEWS[source]
    where = [f"{day_column} < CAST(? AS DATE)"]
    params: list[object] = [end_day.isoformat()]
    if request.sport_filter is not None and _view_has_sport(source):
        where.append("sport_type = ?")
        params.append(request.sport_filter)
    row = conn.execute(
        f"SELECT MIN({day_column}) AS start_day FROM {view} WHERE {' AND '.join(where)}",
        params,
    ).fetchone()
    start = row[0] if row is not None else None
    if start is None:
        activity_row = conn.execute(
            """
            SELECT MIN(activity_day) AS start_day
            FROM activities
            WHERE activity_day < CAST(? AS DATE)
            """,
            [end_day.isoformat()],
        ).fetchone()
        start = activity_row[0] if activity_row is not None else None
    if start is None:
        return end_day, end_day
    if isinstance(start, date):
        return start, end_day
    return date.fromisoformat(str(start)), end_day


def _view_has_sport(source: str) -> bool:
    return source in {
        "activity_summary_fact",
        "activity_metric_fact",
        "daily_load_fact",
        "training_model_fact",
        "rolling_period_fact",
        "social_fact",
        "historical_fact",
    }


def _query_metric(
    conn,
    request: AggregateRequest,
    metric: MetricDefinition,
    effective_start: date,
    effective_end: date,
) -> list[AggregateRow]:
    if metric.aggregate_mode == "distribution":
        rows = _query_distribution(conn, request, metric, effective_start, effective_end)
    else:
        statement, params = _build_numeric_query(metric, request, effective_start, effective_end)
        fetched = _rows(conn.execute(statement, params))
        rows = [_aggregate_row_from_group(metric, request, effective_start, effective_end, row) for row in fetched]
    return _with_empty_rows(rows, metric, request, effective_start, effective_end)


def _build_numeric_query(
    metric: MetricDefinition,
    request: AggregateRequest,
    effective_start: date,
    effective_end: date,
) -> tuple[str, list[object]]:
    source = str(metric.aggregate_source)
    view = _SOURCE_VIEWS[source]
    day_column = _SOURCE_DAY_COLUMNS[source]
    bucket_expr = _bucket_expression(request, day_column, effective_start)
    sport_expr = _sport_output_expression(request)
    value_expr = _value_expression(metric)
    sample_expr = _sample_expression(metric)
    denominator_expr = _denominator_expression(metric)
    exclusion_expr = _exclusion_expression(metric)
    aggregate_expr = _aggregate_expression(metric, effective_start, effective_end)
    quantile_expr = _quantile_expression(metric)
    where, params = _where_clause(source, request, effective_start, effective_end)
    statement = f"""
        WITH prepared AS (
            SELECT
                {bucket_expr} AS bucket_start,
                {sport_expr} AS output_sport_type,
                CAST({value_expr} AS DOUBLE) AS value_raw,
                CAST({sample_expr} AS DOUBLE) AS sample_raw,
                CAST({denominator_expr} AS DOUBLE) AS denominator_raw,
                {exclusion_expr} AS excluded_raw,
                activity_count,
                metric_version,
                computed_at,
                completeness_status,
                missing_reasons_json,
                {day_column} AS source_day
            FROM {view}
            WHERE {where}
        )
        SELECT
            bucket_start,
            output_sport_type,
            {aggregate_expr} AS value,
            COUNT(*) AS row_count,
            SUM(COALESCE(activity_count, 0)) AS activity_count,
            SUM(CASE WHEN value_raw IS NULL THEN 1 ELSE 0 END) AS null_count,
            SUM(CASE WHEN excluded_raw THEN 1 ELSE 0 END) AS excluded_count,
            SUM(COALESCE(sample_raw, 0)) AS sample_size,
            SUM(COALESCE(denominator_raw, 0)) AS denominator_sum,
            {quantile_expr} AS quantile_values,
            COUNT(DISTINCT metric_version) AS metric_version_count,
            MAX(computed_at) AS materialized_at,
            list(DISTINCT completeness_status) AS completeness_statuses,
            list(missing_reasons_json) AS missing_reason_payloads
        FROM prepared
        GROUP BY bucket_start, output_sport_type
        ORDER BY bucket_start, output_sport_type
    """
    return statement, params


def _aggregate_expression(metric: MetricDefinition, effective_start: date, effective_end: date) -> str:
    mode = metric.aggregate_mode
    if mode in {"sum", "kudos_count"}:
        return "SUM(value_raw)"
    if mode == "calendar_average":
        return (
            "SUM(value_raw) / "
            f"NULLIF(date_diff('day', DATE '{effective_start.isoformat()}', DATE '{effective_end.isoformat()}'), 0)"
        )
    if mode == "weighted_average":
        return (
            "weighted_avg("
            "CASE WHEN denominator_raw > 0 THEN value_raw ELSE NULL END, "
            "CASE WHEN denominator_raw > 0 THEN denominator_raw ELSE NULL END"
            ")"
        )
    if mode == "ratio_of_sums":
        return "SUM(value_raw) / NULLIF(SUM(denominator_raw), 0)"
    if mode == "quantile":
        return "quantile_cont(value_raw, 0.5) FILTER (WHERE value_raw IS NOT NULL)"
    if mode == "last_state":
        return "arg_max(value_raw, source_day) FILTER (WHERE value_raw IS NOT NULL)"
    raise ValueError(f"Unsupported numeric aggregate mode: {mode}")


def _quantile_expression(metric: MetricDefinition) -> str:
    if metric.aggregate_mode != "quantile":
        return "NULL"
    return "quantile_cont(value_raw, [0.25, 0.5, 0.75]) FILTER (WHERE value_raw IS NOT NULL)"


def _query_distribution(
    conn,
    request: AggregateRequest,
    metric: MetricDefinition,
    effective_start: date,
    effective_end: date,
) -> list[AggregateRow]:
    source = str(metric.aggregate_source)
    view = _SOURCE_VIEWS[source]
    day_column = _SOURCE_DAY_COLUMNS[source]
    bucket_expr = _bucket_expression(request, day_column, effective_start)
    sport_expr = _sport_output_expression(request)
    value_expr = _value_expression(metric)
    sample_expr = _sample_expression(metric)
    where, params = _where_clause(source, request, effective_start, effective_end)
    statement = f"""
        WITH prepared AS (
            SELECT
                {bucket_expr} AS bucket_start,
                {sport_expr} AS output_sport_type,
                CAST({value_expr} AS VARCHAR) AS category,
                CAST({sample_expr} AS DOUBLE) AS sample_raw,
                activity_count,
                metric_version,
                computed_at,
                completeness_status,
                missing_reasons_json
            FROM {view}
            WHERE {where}
        )
        SELECT
            bucket_start,
            output_sport_type,
            category,
            COUNT(*) AS category_count,
            SUM(COALESCE(activity_count, 0)) AS activity_count,
            SUM(COALESCE(sample_raw, 0)) AS sample_size,
            SUM(CASE WHEN category IS NULL THEN 1 ELSE 0 END) AS null_count,
            COUNT(DISTINCT metric_version) AS metric_version_count,
            MAX(computed_at) AS materialized_at,
            list(DISTINCT completeness_status) AS completeness_statuses,
            list(missing_reasons_json) AS missing_reason_payloads
        FROM prepared
        GROUP BY bucket_start, output_sport_type, category
        ORDER BY bucket_start, output_sport_type, category
    """
    grouped: dict[tuple[str, str | None], dict[str, Any]] = {}
    for row in _rows(conn.execute(statement, params)):
        bucket_start = _to_iso(row["bucket_start"])
        sport_type = row["output_sport_type"]
        key = (bucket_start, sport_type)
        current = grouped.setdefault(
            key,
            {
                "bucket_start": row["bucket_start"],
                "output_sport_type": sport_type,
                "distribution": {},
                "activity_count": 0,
                "sample_size": 0,
                "null_count": 0,
                "excluded_count": 0,
                "metric_version_count": 0,
                "materialized_at": None,
                "completeness_statuses": [],
                "missing_reason_payloads": [],
            },
        )
        category = row["category"]
        if category is not None:
            current["distribution"][str(category)] = int(row["category_count"] or 0)
        current["activity_count"] += int(row["activity_count"] or 0)
        current["sample_size"] += int(row["sample_size"] or 0)
        current["null_count"] += int(row["null_count"] or 0)
        current["metric_version_count"] = max(current["metric_version_count"], int(row["metric_version_count"] or 0))
        current["materialized_at"] = _max_text(current["materialized_at"], row["materialized_at"])
        current["completeness_statuses"].extend(row["completeness_statuses"] or [])
        current["missing_reason_payloads"].extend(row["missing_reason_payloads"] or [])

    return [_aggregate_row_from_group(metric, request, effective_start, effective_end, row) for row in grouped.values()]


def _rows(result) -> list[dict[str, object]]:
    columns = [item[0] for item in result.description]
    return [dict(zip(columns, row, strict=False)) for row in result.fetchall()]


def _bucket_expression(request: AggregateRequest, day_column: str, effective_start: date) -> str:
    if request.window_days is not None:
        return f"DATE '{effective_start.isoformat()}'"
    if request.bucket == "all_time":
        return f"DATE '{effective_start.isoformat()}'"
    widths = {
        "day": "1 day",
        "week": "1 week",
        "month": "1 month",
        "year": "1 year",
    }
    return f"time_bucket(INTERVAL '{widths[request.bucket]}', CAST({day_column} AS DATE))"


def _sport_output_expression(request: AggregateRequest) -> str:
    if request.scope == "per_sport":
        if request.sport_filter is not None:
            return f"'{request.sport_filter}'"
        return "sport_type"
    return "NULL"


def _where_clause(
    source: str,
    request: AggregateRequest,
    effective_start: date,
    effective_end: date,
) -> tuple[str, list[object]]:
    day_column = _SOURCE_DAY_COLUMNS[source]
    where: list[str] = []
    params: list[object] = []
    if request.window_days is not None and request.as_of_day is not None:
        where.extend([f"{day_column} = CAST(? AS DATE)", "window_days = ?"])
        params.extend([request.as_of_day, request.window_days])
    else:
        where.extend([f"{day_column} >= CAST(? AS DATE)", f"{day_column} < CAST(? AS DATE)"])
        params.extend([effective_start.isoformat(), effective_end.isoformat()])
    if source in {"daily_load_fact", "training_model_fact", "rolling_period_fact", "historical_fact"}:
        where.append("scope = 'all'")
        if request.scope == "global":
            where.append("sport_type = 'all'")
    if request.sport_filter is not None and source in {"activity_summary_fact", "activity_metric_fact", "social_fact"}:
        where.append("sport_type = ?")
        params.append(request.sport_filter)
    return " AND ".join(where), params


def _value_expression(metric: MetricDefinition) -> str:
    if metric.aggregate_mode == "ratio_of_sums" and metric.numerator_column is not None:
        return _column_expression(metric.numerator_column, metric.metric_id)
    if metric.metric_id in _METRIC_VALUE_EXPRESSIONS:
        return _METRIC_VALUE_EXPRESSIONS[metric.metric_id]
    column = metric.value_column
    if column is None:
        raise ValueError(f"Metric {metric.metric_id} has no aggregate value column")
    return _column_expression(column, metric.metric_id)


def _sample_expression(metric: MetricDefinition) -> str:
    column = metric.sample_size_column or "activity_count"
    return _column_expression(column, metric.metric_id)


def _denominator_expression(metric: MetricDefinition) -> str:
    if metric.aggregate_mode == "ratio_of_sums":
        column = metric.denominator_column
    elif metric.aggregate_mode == "weighted_average":
        column = metric.weight_column or metric.denominator_column
    else:
        column = metric.denominator_column or metric.weight_column or metric.sample_size_column or "activity_count"
    if column is None:
        return "activity_count"
    if column == "calendar_days":
        return "calendar_days"
    return _column_expression(column, metric.metric_id)


def _exclusion_expression(metric: MetricDefinition) -> str:
    if metric.aggregate_mode in {"weighted_average", "ratio_of_sums"}:
        denominator = _denominator_expression(metric)
        return f"({denominator} IS NULL OR {denominator} <= 0)"
    return "FALSE"


def _column_expression(column: str, metric_id: str) -> str:
    if column not in _ALLOWED_COLUMNS:
        raise ValueError(f"Metric {metric_id} references unsupported aggregate column")
    return column


def _aggregate_row_from_group(
    metric: MetricDefinition,
    request: AggregateRequest,
    effective_start: date,
    effective_end: date,
    row: dict[str, object],
) -> AggregateRow:
    bucket_start = _to_iso(row["bucket_start"])
    bucket_end = _bucket_end(bucket_start, request, effective_end)
    value = _aggregate_value(metric, row)
    distribution = row.get("distribution") if metric.aggregate_mode == "distribution" else None
    quantiles = _quantiles(metric, row)
    missing_reasons = _missing_reasons(row)
    excluded_count = int(row.get("excluded_count") or 0)
    null_count = int(row.get("null_count") or 0)
    if excluded_count:
        missing_reasons.append("missing_denominator")
    row_count = int(row.get("row_count") or 0)
    if isinstance(distribution, dict) and row_count == 0:
        row_count = sum(distribution.values())
    completeness = _completeness_status(
        value=value,
        distribution=distribution,
        row_count=row_count,
        null_count=null_count,
        excluded_count=excluded_count,
        statuses=row.get("completeness_statuses") or [],
    )
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
        sample_size=int(row.get("sample_size") or 0),
        activity_count=int(row.get("activity_count") or 0),
        null_count=null_count,
        excluded_count=excluded_count,
        completeness_status=completeness,
        missing_reasons=sorted(set(missing_reasons)),
        metric_version_status=_metric_version_status(metric, int(row.get("metric_version_count") or 0)),
        materialized_at=str(row["materialized_at"]) if row.get("materialized_at") else None,
        mirror_freshness=None,
        read_model_freshness=None,
        scope=request.scope,
        sport_type=row.get("output_sport_type"),
    )


def _aggregate_value(metric: MetricDefinition, row: dict[str, object]) -> float | int | str | None:
    if metric.aggregate_mode == "distribution":
        return None
    value = row.get("value")
    if value is None:
        return None
    if metric.metric_id in {"moving_time_min", "elapsed_time_min"}:
        return float(value)
    return float(value)


def _quantiles(metric: MetricDefinition, row: dict[str, object]) -> dict[str, float] | None:
    if metric.aggregate_mode != "quantile":
        return None
    value = row.get("value")
    if value is None:
        return None
    source = str(metric.aggregate_source)
    day_column = _SOURCE_DAY_COLUMNS[source]
    del day_column
    return _quantiles_from_group(row)


def _quantiles_from_group(row: dict[str, object]) -> dict[str, float] | None:
    # The quantile list is fetched by a focused follow-up query to keep the row contract stable.
    values = row.get("quantile_values")
    if not values:
        median = row.get("value")
        if median is None:
            return None
        return {"p25": float(median), "median": float(median), "p75": float(median)}
    return {label: float(value) for label, value in zip(_QUANTILE_LABELS, values, strict=False)}


def _missing_reasons(row: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    for payload in row.get("missing_reason_payloads") or []:
        if payload is None:
            continue
        try:
            parsed = json.loads(str(payload))
        except json.JSONDecodeError:
            parsed = [str(payload)]
        if isinstance(parsed, list):
            reasons.extend(str(item) for item in parsed if item)
    return reasons


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
    if excluded_count > 0 or null_count > 0 or any(str(status) != "complete" for status in statuses if status is not None):
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
        year = start.year + (1 if start.month == 12 else 0)
        month = 1 if start.month == 12 else start.month + 1
        return date(year, month, 1).isoformat()
    if request.bucket == "year":
        return date(start.year + 1, 1, 1).isoformat()
    return effective_end.isoformat()


def _with_empty_rows(
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
            additions.append(_empty_row(metric, request, current, _date_from_iso(_bucket_end(current.isoformat(), request, effective_end)), sport_type))
        current = _next_bucket(current, request.bucket)
    return sorted([*rows, *additions], key=lambda row: (row.bucket_start, row.metric_id, row.sport_type or ""))


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
        year = start.year + (1 if start.month == 12 else 0)
        month = 1 if start.month == 12 else start.month + 1
        return date(year, month, 1)
    if bucket == "year":
        return date(start.year + 1, 1, 1)
    return start


def _date_from_iso(value: str) -> date:
    return date.fromisoformat(value)


def _max_text(left: object | None, right: object | None) -> str | None:
    if left is None:
        return str(right) if right is not None else None
    if right is None:
        return str(left)
    return max(str(left), str(right))
