"""SQL expression helpers for prepared aggregate fact queries."""

from __future__ import annotations

from datetime import date

from mcp_strava.adapters.duckdb.aggregate_models import AggregateRequest
from mcp_strava.adapters.duckdb.aggregate_query_sources import SOURCE_DAY_COLUMNS
from mcp_strava.metric_registry import AGGREGATE_BUCKET_INTERVALS, aggregate_query_allowed_columns
from mcp_strava.types import MetricDefinition

_ALLOWED_COLUMNS = aggregate_query_allowed_columns()
_METRIC_VALUE_EXPRESSIONS = {
    "distance_km": "distance_m / 1000.0",
    "moving_time_min": "moving_time_s / 60.0",
    "elapsed_time_min": "elapsed_time_s / 60.0",
    "elevation_m": "elevation_gain_m",
}


def _bucket_expression(request: AggregateRequest, day_column: str, effective_start: date) -> str:
    if request.window_days is not None:
        return f"DATE '{effective_start.isoformat()}'"
    if request.bucket == "all_time":
        return f"DATE '{effective_start.isoformat()}'"
    return f"time_bucket(INTERVAL '{AGGREGATE_BUCKET_INTERVALS[request.bucket]}', CAST({day_column} AS DATE))"


def _sport_output_expression(request: AggregateRequest) -> str:
    if request.scope == "per_sport":
        return "sport_type"
    return "NULL"


def _where_clause(
    metric: MetricDefinition,
    request: AggregateRequest,
    effective_start: date,
    effective_end: date,
    metric_version: int,
) -> tuple[str, list[object]]:
    source = str(metric.aggregate_source)
    day_column = SOURCE_DAY_COLUMNS[source]
    # R11 version pin: every aggregate fact view exposes metric_version, so this
    # parameterized predicate keeps a mixed-version DB from blending old + new
    # rows into one aggregate. Bound as `?`, never string-formatted (T-15-05).
    where: list[str] = ["metric_version = ?"]
    params: list[object] = [metric_version]
    if request.window_days is not None and request.as_of_day is not None:
        where.extend([f"{day_column} = CAST(? AS DATE)", "window_days = ?"])
        params.extend([request.as_of_day, request.window_days])
    else:
        where.extend([f"{day_column} >= CAST(? AS DATE)", f"{day_column} < CAST(? AS DATE)"])
        params.extend([effective_start.isoformat(), effective_end.isoformat()])
        rolling_window_days = _effective_rolling_window_days(metric, request)
        if rolling_window_days is not None:
            where.append("window_days = ?")
            params.append(rolling_window_days)
    if source == "rolling_period_fact" and request.scope == "per_sport":
        where.append("scope = 'sport'")
        if request.sport_filter is not None:
            where.append("sport_type = ?")
            params.append(request.sport_filter)
    elif source in {"daily_load_fact", "training_model_fact", "rolling_period_fact", "historical_fact"}:
        where.append("scope = 'all'")
        if request.scope == "global":
            where.append("sport_type = 'all'")
    if request.sport_filter is not None and source in {"activity_summary_fact", "activity_metric_fact", "social_fact"}:
        where.append("sport_type = ?")
        params.append(request.sport_filter)
    return " AND ".join(where), params


def _effective_rolling_window_days(metric: MetricDefinition, request: AggregateRequest) -> int | None:
    if metric.aggregate_source != "rolling_period_fact":
        return None
    if request.window_days is not None:
        return request.window_days
    return metric.rolling_window_days


def _value_expression(metric: MetricDefinition) -> str:
    if metric.metric_id == "time_in_hr_zones_min":
        return "zone1_seconds"
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
