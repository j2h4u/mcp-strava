"""Whitelisted DuckDB aggregate query builders over prepared metric facts."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import cast

from mcp_strava.adapters.duckdb.aggregate_distribution import _DistributionGroup
from mcp_strava.adapters.duckdb.aggregate_models import AggregateQuery, AggregateRequest, AggregateRow
from mcp_strava.adapters.duckdb.aggregate_query_fetch import _rows, _scalar_cell
from mcp_strava.adapters.duckdb.aggregate_query_sources import SOURCE_DAY_COLUMNS, SOURCE_VIEWS, view_has_sport
from mcp_strava.adapters.duckdb.aggregate_rows import (
    aggregate_row_from_group,
    as_float,
    as_int,
    max_text,
    to_iso,
    with_empty_rows,
)
from mcp_strava.adapters.duckdb.aggregate_sql_expressions import (
    _bucket_expression,
    _denominator_expression,
    _exclusion_expression,
    _sample_expression,
    _sport_output_expression,
    _value_expression,
    _where_clause,
)
from mcp_strava.adapters.duckdb.connection import DuckDBConn
from mcp_strava.adapters.duckdb.schema import create_aggregate_views
from mcp_strava.adapters.duckdb.status_fact_queries import query_status_facts as query_status_facts
from mcp_strava.metric_registry import (
    METRIC_REGISTRY,
    SUPPORTED_AGGREGATE_BUCKETS,
    SUPPORTED_AGGREGATE_SCOPES,
    SUPPORTED_ROLLING_WINDOW_DAYS,
    metrics_for_aggregate_bundle,
)
from mcp_strava.sports import SPORT_ALL as ALL_SPORTS
from mcp_strava.types import MetricDefinition


def validate_aggregate_request(request: AggregateRequest) -> tuple[MetricDefinition, ...]:
    if request.bucket not in SUPPORTED_AGGREGATE_BUCKETS:
        raise ValueError(f"Unsupported aggregate bucket: {request.bucket}")
    if request.scope not in SUPPORTED_AGGREGATE_SCOPES:
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
        _validate_metric_rolling_window(metric, request)
        if request.bucket not in set(metric.supported_buckets):
            raise ValueError(f"Metric {metric.metric_id} does not support bucket {request.bucket}")
        if metric.aggregate_source not in SOURCE_VIEWS:
            raise ValueError(f"Metric {metric.metric_id} has unsupported aggregate source")
        _value_expression(metric)
        _sample_expression(metric)
        _denominator_expression(metric)
    return definitions


def build_aggregate_query(
    metric: MetricDefinition, request: AggregateRequest, metric_version: int = 1
) -> AggregateQuery:
    effective_start, effective_end = _effective_range_for_metric(None, request, metric, metric_version)
    statement, params = _build_numeric_query(metric, request, effective_start, effective_end, metric_version)
    return AggregateQuery(statement=statement, params=tuple(params), metric_id=metric.metric_id, bucket=request.bucket)


def query_training_aggregates(
    conn: DuckDBConn, request: AggregateRequest, *, metric_version: int
) -> list[AggregateRow]:
    """Aggregate read pinned to a single metric_version (R11).

    metric_version is resolved by the CALLER (aggregate_services.py) from
    repo.current_metric_version() so it is consistent with the rest of the
    request. Every fact SELECT below filters `metric_version = ?` — point reads,
    aggregate reads, and the all-time range derivation all see only-current rows,
    so a mixed-version DB never blends old + new into one number.
    """
    create_aggregate_views(conn)
    definitions = validate_aggregate_request(request)
    rows: list[AggregateRow] = []
    for metric in definitions:
        for scoped_request in _scoped_requests_for_metric(request, metric):
            effective_start, effective_end = _effective_range_for_metric(conn, scoped_request, metric, metric_version)
            rows.extend(_query_metric(conn, scoped_request, metric, effective_start, effective_end, metric_version))
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
    if scope == "both":
        if not set(metric.supported_scopes) & set(SUPPORTED_AGGREGATE_SCOPES):
            raise ValueError(f"Metric {metric.metric_id} has no supported aggregate scope")
        return
    scopes = set(metric.supported_scopes)
    if scope == "global" and not ({"global", "both"} & scopes):
        raise ValueError(f"Metric {metric.metric_id} does not support global scope")
    if scope == "per_sport" and not ({"per_sport", "both"} & scopes):
        raise ValueError(f"Metric {metric.metric_id} does not support per_sport scope")


def _validate_metric_rolling_window(metric: MetricDefinition, request: AggregateRequest) -> None:
    if metric.aggregate_source != "rolling_period_fact":
        return
    if (
        request.window_days is not None
        and metric.fixed_rolling_window
        and request.window_days != metric.rolling_window_days
    ):
        raise ValueError(f"Metric {metric.metric_id} requires rolling window {metric.rolling_window_days}")
    if request.window_days is None and metric.rolling_window_days is None:
        raise ValueError(f"Metric {metric.metric_id} requires window_days")


def _effective_rolling_window_days(metric: MetricDefinition, request: AggregateRequest) -> int | None:
    if metric.aggregate_source != "rolling_period_fact":
        return None
    if request.window_days is not None:
        return request.window_days
    return metric.rolling_window_days


def _scoped_requests_for_metric(request: AggregateRequest, metric: MetricDefinition) -> tuple[AggregateRequest, ...]:
    if request.scope != "both":
        return (request,)
    scopes = set(metric.supported_scopes)
    requests: list[AggregateRequest] = []
    if {"global", "both"} & scopes:
        requests.append(replace(request, scope="global"))
    if {"per_sport", "both"} & scopes:
        requests.append(replace(request, scope="per_sport"))
    return tuple(requests)


def _parse_day(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _effective_range_for_metric(
    conn: DuckDBConn | None, request: AggregateRequest, metric: MetricDefinition, metric_version: int
) -> tuple[date, date]:
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
    day_column = SOURCE_DAY_COLUMNS[source]
    view = SOURCE_VIEWS[source]
    # Pin the all-time range derivation to the current version too (R11): an
    # unpinned MIN() would let a stale-version fact widen the range and pull old
    # rows into the bucket. The fact views expose metric_version.
    where = [f"{day_column} < CAST(? AS DATE)", "metric_version = ?"]
    params: list[object] = [end_day.isoformat(), metric_version]
    if request.sport_filter is not None and view_has_sport(source):
        where.append("sport_type = ?")
        params.append(request.sport_filter)
    row = conn.execute(
        f"SELECT MIN({day_column}) AS start_day FROM {view} WHERE {' AND '.join(where)}",
        params,
    ).fetchone()
    start = _scalar_cell(row)
    if start is None:
        activity_row = conn.execute(
            """
            SELECT MIN(activity_day) AS start_day
            FROM activities
            WHERE activity_day < CAST(? AS DATE)
            """,
            [end_day.isoformat()],
        ).fetchone()
        start = _scalar_cell(activity_row)
    if start is None:
        return end_day, end_day
    if isinstance(start, date):
        return start, end_day
    return date.fromisoformat(str(start)), end_day


def _query_metric(
    conn: DuckDBConn,
    request: AggregateRequest,
    metric: MetricDefinition,
    effective_start: date,
    effective_end: date,
    metric_version: int,
) -> list[AggregateRow]:
    if metric.aggregate_mode == "distribution":
        rows = _query_distribution(conn, request, metric, effective_start, effective_end, metric_version)
    else:
        statement, params = _build_numeric_query(metric, request, effective_start, effective_end, metric_version)
        fetched = _rows(conn.execute(statement, params))
        rows = [aggregate_row_from_group(metric, request, effective_start, effective_end, row) for row in fetched]
    return with_empty_rows(rows, metric, request, effective_start, effective_end)


def _build_numeric_query(
    metric: MetricDefinition,
    request: AggregateRequest,
    effective_start: date,
    effective_end: date,
    metric_version: int,
) -> tuple[str, list[object]]:
    source = str(metric.aggregate_source)
    view = SOURCE_VIEWS[source]
    day_column = SOURCE_DAY_COLUMNS[source]
    bucket_expr = _bucket_expression(request, day_column, effective_start)
    sport_expr = _sport_output_expression(request)
    value_expr = _value_expression(metric)
    sample_expr = _sample_expression(metric)
    denominator_expr = _denominator_expression(metric)
    exclusion_expr = _exclusion_expression(metric)
    aggregate_expr = _aggregate_expression(metric, effective_start, effective_end)
    quantile_expr = _quantile_expression(metric)
    where, params = _where_clause(metric, request, effective_start, effective_end, metric_version)
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
    conn: DuckDBConn,
    request: AggregateRequest,
    metric: MetricDefinition,
    effective_start: date,
    effective_end: date,
    metric_version: int,
) -> list[AggregateRow]:
    if metric.metric_id == "time_in_hr_zones_min":
        return _query_hr_zone_distribution(conn, request, metric, effective_start, effective_end, metric_version)
    source = str(metric.aggregate_source)
    view = SOURCE_VIEWS[source]
    day_column = SOURCE_DAY_COLUMNS[source]
    bucket_expr = _bucket_expression(request, day_column, effective_start)
    sport_expr = _sport_output_expression(request)
    value_expr = _value_expression(metric)
    sample_expr = _sample_expression(metric)
    where, params = _where_clause(metric, request, effective_start, effective_end, metric_version)
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
    grouped: dict[tuple[str, str | None], _DistributionGroup] = {}
    for row in _rows(conn.execute(statement, params)):
        bucket_start = to_iso(row["bucket_start"])
        sport_cell = row["output_sport_type"]
        sport_type = sport_cell if isinstance(sport_cell, str) else None
        key = (bucket_start, sport_type)
        current = grouped.get(key)
        if current is None:
            current = _DistributionGroup(bucket_start=row["bucket_start"], output_sport_type=sport_type)
            grouped[key] = current
        category = row["category"]
        if category is not None:
            current.distribution[str(category)] = as_int(row["category_count"])
        current.activity_count += as_int(row["activity_count"])
        current.sample_size += as_int(row["sample_size"])
        current.null_count += as_int(row["null_count"])
        current.metric_version_count = max(current.metric_version_count, as_int(row["metric_version_count"]))
        current.materialized_at = max_text(current.materialized_at, row["materialized_at"])
        statuses = row["completeness_statuses"]
        if isinstance(statuses, list):
            current.completeness_statuses.extend(cast("list[object]", statuses))
        payloads = row["missing_reason_payloads"]
        if isinstance(payloads, list):
            current.missing_reason_payloads.extend(cast("list[object]", payloads))

    return [
        aggregate_row_from_group(metric, request, effective_start, effective_end, group.as_row())
        for group in grouped.values()
    ]


def _query_hr_zone_distribution(
    conn: DuckDBConn,
    request: AggregateRequest,
    metric: MetricDefinition,
    effective_start: date,
    effective_end: date,
    metric_version: int,
) -> list[AggregateRow]:
    source = str(metric.aggregate_source)
    view = SOURCE_VIEWS[source]
    day_column = SOURCE_DAY_COLUMNS[source]
    bucket_expr = _bucket_expression(request, day_column, effective_start)
    sport_expr = _sport_output_expression(request)
    where, params = _where_clause(metric, request, effective_start, effective_end, metric_version)
    statement = f"""
        WITH prepared AS (
            SELECT
                {bucket_expr} AS bucket_start,
                {sport_expr} AS output_sport_type,
                zone1_seconds,
                zone2_seconds,
                zone3_seconds,
                zone4_seconds,
                zone5_seconds,
                heartrate_sample_count,
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
            SUM(COALESCE(zone1_seconds, 0)) / 60.0 AS z1,
            SUM(COALESCE(zone2_seconds, 0)) / 60.0 AS z2,
            SUM(COALESCE(zone3_seconds, 0)) / 60.0 AS z3,
            SUM(COALESCE(zone4_seconds, 0)) / 60.0 AS z4,
            SUM(COALESCE(zone5_seconds, 0)) / 60.0 AS z5,
            COUNT(*) AS row_count,
            SUM(COALESCE(activity_count, 0)) AS activity_count,
            SUM(CASE WHEN heartrate_sample_count IS NULL OR heartrate_sample_count <= 0 THEN 1 ELSE 0 END) AS excluded_count,
            0 AS null_count,
            SUM(COALESCE(heartrate_sample_count, 0)) AS sample_size,
            COUNT(DISTINCT metric_version) AS metric_version_count,
            MAX(computed_at) AS materialized_at,
            list(DISTINCT completeness_status) AS completeness_statuses,
            list(missing_reasons_json) AS missing_reason_payloads
        FROM prepared
        GROUP BY bucket_start, output_sport_type
        ORDER BY bucket_start, output_sport_type
    """
    rows: list[AggregateRow] = []
    for row in _rows(conn.execute(statement, params)):
        row["distribution"] = {f"z{idx}": as_float(row[f"z{idx}"]) for idx in range(1, 6)}
        rows.append(aggregate_row_from_group(metric, request, effective_start, effective_end, row))
    return rows
