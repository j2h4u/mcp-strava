"""Whitelisted DuckDB aggregate query builders over prepared metric facts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any

from mcp_strava.adapters.duckdb.schema import create_aggregate_views
from mcp_strava.hr_zones import get_zone_model
from mcp_strava.metric_registry import (
    METRIC_REGISTRY,
    STATUS_FACT_REGISTRY,
    SUPPORTED_AGGREGATE_BUCKETS,
    SUPPORTED_ROLLING_WINDOW_DAYS,
    aggregate_query_allowed_columns,
    metrics_for_aggregate_bundle,
)
from mcp_strava.settings import get_settings
from mcp_strava.sports import SPORT_ALL as ALL_SPORTS
from mcp_strava.sports import SPORT_RUNNING as RUNNING_SPORTS
from mcp_strava.types import MetricDefinition, StatusFact, StatusFactDefinition

_HR_REST_MISSING_MSG = (
    "MCP_STRAVA_HR_REST is not set — cannot compute HR zones. "
    "Set MCP_STRAVA_HR_REST to the athlete's resting heart rate."
)


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
    distribution: dict[str, float | int] | None
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
    "historical_fact": "v_historical_context_facts",
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
_ALLOWED_COLUMNS = aggregate_query_allowed_columns()
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
    if request.scope not in {"global", "per_sport", "both"}:
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
        for scoped_request in _scoped_requests_for_metric(request, metric):
            effective_start, effective_end = _effective_range_for_metric(conn, scoped_request, metric)
            rows.extend(_query_metric(conn, scoped_request, metric, effective_start, effective_end))
    return sorted(rows, key=lambda row: (row.bucket_start, row.metric_id, row.sport_type or ""))


def query_status_facts(conn, *, as_of_day: str) -> list[StatusFact]:
    create_aggregate_views(conn)
    as_of = _parse_day(as_of_day, "as_of_day")
    return [_query_status_fact(conn, definition, as_of) for definition in STATUS_FACT_REGISTRY.values()]


def _query_status_fact(conn, definition: StatusFactDefinition, as_of: date) -> StatusFact:
    code = definition.code
    if code == "stale_mirror_data":
        return _query_stale_mirror_status(conn, definition, as_of)
    if code == "stale_read_model_facts":
        return _query_stale_read_model_status(conn, definition, as_of)
    if code == "missing_hr":
        return _query_missing_sample_status(conn, definition, as_of, "heartrate_sample_count")
    if code == "missing_streams":
        return _query_missing_sample_status(conn, definition, as_of, "stream_sample_count")
    if code == "excessive_z5_exposure":
        return _query_excessive_z5_status(conn, definition, as_of)
    if code == "hr_anomaly_burst":
        return _query_hr_anomaly_status(conn, definition, as_of)
    if code == "cardiac_drift_significant_quality":
        return _query_cardiac_drift_status(conn, definition, as_of)
    if code == "consecutive_high_load_hikes":
        return _query_high_load_hike_status(conn, definition, as_of)
    if code == "running_volume_jump":
        return _query_running_volume_jump_status(conn, definition, as_of)
    return _status_fact(definition, "unavailable", {}, ["unsupported_status_fact"])


def _query_stale_mirror_status(conn, definition: StatusFactDefinition, as_of: date) -> StatusFact:
    row = conn.execute(
        """
        SELECT last_success_at
        FROM refresh_state
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()
    if row is None or row[0] is None:
        return _status_fact(definition, "unavailable", {}, ["refresh_state_missing"])
    last_success_day = _day_from_timestamp(row[0])
    if last_success_day is None:
        return _status_fact(definition, "unavailable", {"last_success_at": row[0]}, ["last_success_missing"])
    age_days = max(0, (as_of - last_success_day).days)
    threshold_days = int(definition.threshold["max_age_days"])
    evidence = {
        "last_success_at": str(row[0]),
        "age_days": age_days,
        "threshold_days": threshold_days,
    }
    return _status_fact(definition, "active" if age_days > threshold_days else "inactive", evidence)


def _query_stale_read_model_status(conn, definition: StatusFactDefinition, as_of: date) -> StatusFact:
    row = conn.execute(
        """
        SELECT MAX(finished_at) AS last_materialized_at
        FROM read_model_refresh_runs
        WHERE status = 'ok'
        """
    ).fetchone()
    dirty_row = conn.execute("SELECT COUNT(*) FROM metric_dirty_activities").fetchone()
    dirty_count = int(dirty_row[0] or 0) if dirty_row is not None else 0
    last_materialized_at = row[0] if row is not None else None
    if last_materialized_at is None:
        return _status_fact(
            definition,
            "unavailable",
            {"dirty_count": dirty_count},
            ["read_model_run_missing"],
        )
    last_materialized_day = _day_from_timestamp(last_materialized_at)
    if last_materialized_day is None:
        return _status_fact(
            definition,
            "unavailable",
            {"last_materialized_at": str(last_materialized_at), "dirty_count": dirty_count},
            ["read_model_unavailable"],
        )
    age_days = max(0, (as_of - last_materialized_day).days)
    threshold_days = int(definition.threshold["max_age_days"])
    evidence = {
        "last_materialized_at": str(last_materialized_at),
        "age_days": age_days,
        "dirty_count": dirty_count,
    }
    return _status_fact(definition, "active" if age_days > threshold_days or dirty_count > 0 else "inactive", evidence)


def _query_missing_sample_status(
    conn,
    definition: StatusFactDefinition,
    as_of: date,
    sample_column: str,
) -> StatusFact:
    start = _lookback_start(definition, as_of)
    total = _activity_fact_count(conn, start, as_of)
    if total == 0:
        return _status_fact(definition, "unavailable", {}, ["no_activity_facts"])
    rows = conn.execute(
        f"""
        SELECT activity_id
        FROM activity_metric_facts
        WHERE activity_day >= CAST(? AS DATE)
          AND activity_day <= CAST(? AS DATE)
          AND {sample_column} <= 0
        ORDER BY activity_day, activity_id
        """,
        [start.isoformat(), as_of.isoformat()],
    ).fetchall()
    activity_ids = [int(row[0]) for row in rows]
    evidence = {
        "activity_count": len(activity_ids),
        "activity_ids": activity_ids,
        "sample_column": sample_column,
    }
    return _status_fact(definition, "active" if activity_ids else "inactive", evidence)


def _query_excessive_z5_status(conn, definition: StatusFactDefinition, as_of: date) -> StatusFact:
    start = _lookback_start(definition, as_of)
    total = _activity_fact_count(conn, start, as_of)
    if total == 0:
        return _status_fact(definition, "unavailable", {}, ["no_activity_facts"])
    threshold = int(definition.threshold["zone5_seconds"])
    if "z5_lower_bound_bpm" in definition.threshold:
        z5_lower_bound = int(definition.threshold["z5_lower_bound_bpm"])
    else:
        from mcp_strava.adapters.duckdb.repository import DuckDBRepository

        _athlete = get_settings().athlete
        if _athlete.hr_rest is None:
            raise RuntimeError(_HR_REST_MISSING_MSG)
        _repo = DuckDBRepository.from_connection(conn)
        _hr_max = _repo.max_heartrate()
        if _hr_max is None:
            # No HR data in DB — no Z5 events are possible; use max int as unreachable threshold.
            z5_lower_bound = 300
        else:
            _bounds = get_zone_model(_athlete.hr_zone_model).zone_bounds(hr_max=int(_hr_max), hr_rest=_athlete.hr_rest)
            z5_lower_bound = _bounds[-2]
    row = conn.execute(
        """
        SELECT activity_id, activity_day, zone5_seconds
        FROM activity_metric_facts
        WHERE activity_day >= CAST(? AS DATE)
          AND activity_day <= CAST(? AS DATE)
          AND zone5_seconds > ?
        ORDER BY zone5_seconds DESC, activity_day DESC
        LIMIT 1
        """,
        [start.isoformat(), as_of.isoformat(), threshold],
    ).fetchone()
    if row is None:
        return _status_fact(definition, "inactive", {"threshold_seconds": threshold})
    evidence = {
        "activity_id": int(row[0]),
        "activity_day": _to_iso(row[1]),
        "zone5_seconds": int(row[2] or 0),
        "z5_lower_bound_bpm": z5_lower_bound,
    }
    return _status_fact(definition, "active", evidence)


def _query_hr_anomaly_status(conn, definition: StatusFactDefinition, as_of: date) -> StatusFact:
    start = _lookback_start(definition, as_of)
    total = _activity_fact_count(conn, start, as_of)
    if total == 0:
        return _status_fact(definition, "unavailable", {}, ["no_activity_facts"])
    threshold = int(definition.threshold["hr_anomaly_count"])
    row = conn.execute(
        """
        SELECT activity_id, activity_day, anomaly_count
        FROM activity_metric_facts
        WHERE activity_day >= CAST(? AS DATE)
          AND activity_day <= CAST(? AS DATE)
          AND anomaly_count >= ?
        ORDER BY anomaly_count DESC, activity_day DESC
        LIMIT 1
        """,
        [start.isoformat(), as_of.isoformat(), threshold],
    ).fetchone()
    if row is None:
        return _status_fact(definition, "inactive", {"threshold_count": threshold})
    evidence = {
        "activity_id": int(row[0]),
        "activity_day": _to_iso(row[1]),
        "hr_anomaly_count": int(row[2] or 0),
        "jump_bpm": int(definition.threshold["jump_bpm"]),
    }
    return _status_fact(definition, "active", evidence)


def _query_cardiac_drift_status(conn, definition: StatusFactDefinition, as_of: date) -> StatusFact:
    start = _lookback_start(definition, as_of)
    total = _activity_fact_count(conn, start, as_of)
    if total == 0:
        return _status_fact(definition, "unavailable", {}, ["no_activity_facts"])
    qualities = tuple(str(value) for value in definition.threshold["quality"])
    placeholders = ",".join("?" for _ in qualities)
    row = conn.execute(
        f"""
        SELECT activity_id, activity_day, cardiac_drift_significant, cardiac_drift_quality
        FROM activity_metric_facts
        WHERE activity_day >= CAST(? AS DATE)
          AND activity_day <= CAST(? AS DATE)
          AND cardiac_drift_significant >= ?
          AND cardiac_drift_quality IN ({placeholders})
        ORDER BY activity_day DESC, activity_id DESC
        LIMIT 1
        """,
        [start.isoformat(), as_of.isoformat(), int(definition.threshold["cardiac_drift_significant"]), *qualities],
    ).fetchone()
    if row is None:
        return _status_fact(definition, "inactive", {"quality": list(qualities)})
    evidence = {
        "activity_id": int(row[0]),
        "activity_day": _to_iso(row[1]),
        "cardiac_drift_significant": int(row[2] or 0),
        "cardiac_drift_quality": str(row[3]),
    }
    return _status_fact(definition, "active", evidence)


def _query_high_load_hike_status(conn, definition: StatusFactDefinition, as_of: date) -> StatusFact:
    start = _lookback_start(definition, as_of)
    rows = conn.execute(
        """
        SELECT activity_day, SUM(COALESCE(trimp, 0.0)) AS daily_trimp
        FROM activity_metric_facts
        WHERE activity_day >= CAST(? AS DATE)
          AND activity_day <= CAST(? AS DATE)
          AND sport_type = 'Hike'
        GROUP BY activity_day
        ORDER BY activity_day
        """,
        [start.isoformat(), as_of.isoformat()],
    ).fetchall()
    if len(rows) < 2:
        return _status_fact(definition, "unavailable", {"hike_day_count": len(rows)}, ["insufficient_hike_history"])
    threshold = float(definition.threshold["combined_trimp"])
    best_pair: tuple[object, object, float] | None = None
    for previous, current in zip(rows, rows[1:], strict=False):
        previous_day = _coerce_day(previous[0])
        current_day = _coerce_day(current[0])
        if previous_day is None or current_day is None or (current_day - previous_day).days != 1:
            continue
        combined = float(previous[1] or 0.0) + float(current[1] or 0.0)
        if best_pair is None or combined > best_pair[2]:
            best_pair = (previous[0], current[0], combined)
    if best_pair is None:
        return _status_fact(definition, "inactive", {"hike_day_count": len(rows)})
    evidence = {
        "hike_days": [_to_iso(best_pair[0]), _to_iso(best_pair[1])],
        "combined_trimp": best_pair[2],
    }
    return _status_fact(definition, "active" if best_pair[2] > threshold else "inactive", evidence)


def _query_running_volume_jump_status(conn, definition: StatusFactDefinition, as_of: date) -> StatusFact:
    week_start = as_of - timedelta(days=as_of.weekday())
    current_start = week_start
    current_end = as_of + timedelta(days=1)
    previous_start = week_start - timedelta(days=7)
    previous_end = week_start
    running_sports = tuple(sorted(RUNNING_SPORTS))
    placeholders = ",".join("?" for _ in running_sports)
    query = f"""
        SELECT COALESCE(SUM(distance_m), 0.0) / 1000.0 AS distance_km
        FROM activity_metric_facts
        WHERE sport_type IN ({placeholders})
          AND activity_day >= CAST(? AS DATE)
          AND activity_day < CAST(? AS DATE)
    """
    previous = float(
        conn.execute(query, [*running_sports, previous_start.isoformat(), previous_end.isoformat()]).fetchone()[0]
        or 0.0
    )
    current = float(
        conn.execute(query, [*running_sports, current_start.isoformat(), current_end.isoformat()]).fetchone()[0] or 0.0
    )
    if previous <= 0:
        return _status_fact(
            definition,
            "unavailable",
            {"current_week_distance_km": current, "previous_week_distance_km": previous},
            ["no_previous_running_week"],
        )
    if current <= 0:
        return _status_fact(
            definition,
            "unavailable",
            {"current_week_distance_km": current, "previous_week_distance_km": previous},
            ["no_current_running_week"],
        )
    increase_pct = round((current / previous - 1.0) * 100.0, 2)
    evidence = {
        "current_week_distance_km": current,
        "previous_week_distance_km": previous,
        "increase_pct": increase_pct,
        "current_week_start": current_start.isoformat(),
        "previous_week_start": previous_start.isoformat(),
    }
    return _status_fact(
        definition, "active" if increase_pct >= float(definition.threshold["caution_pct"]) else "inactive", evidence
    )


def _status_fact(
    definition: StatusFactDefinition,
    status: str,
    evidence: dict[str, Any],
    missing_reasons: list[str] | None = None,
) -> StatusFact:
    missing = list(missing_reasons or [])
    completeness_status = "unavailable" if status == "unavailable" else "complete"
    return StatusFact(
        code=definition.code,
        metric_id=definition.metric_id,
        status=status,
        threshold=definition.threshold,
        window=definition.window,
        evidence=evidence,
        completeness={"status": completeness_status, "missing_reasons": missing},
        calculation=definition.calculation,
        materialized_from=definition.materialized_from,
    )


def _lookback_start(definition: StatusFactDefinition, as_of: date) -> date:
    lookback_days = int(definition.window.get("lookback_days", 1))
    return as_of - timedelta(days=max(lookback_days - 1, 0))


def _activity_fact_count(conn, start: date, as_of: date) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM activity_metric_facts
        WHERE activity_day >= CAST(? AS DATE)
          AND activity_day <= CAST(? AS DATE)
        """,
        [start.isoformat(), as_of.isoformat()],
    ).fetchone()
    return int(row[0] or 0) if row is not None else 0


def _day_from_timestamp(value: object) -> date | None:
    if value is None:
        return None
    text = str(value)
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _coerce_day(value: object) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


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
        if not set(metric.supported_scopes) & {"global", "per_sport", "both"}:
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
    where, params = _where_clause(metric, request, effective_start, effective_end)
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
    if metric.metric_id == "time_in_hr_zones_min":
        return _query_hr_zone_distribution(conn, request, metric, effective_start, effective_end)
    source = str(metric.aggregate_source)
    view = _SOURCE_VIEWS[source]
    day_column = _SOURCE_DAY_COLUMNS[source]
    bucket_expr = _bucket_expression(request, day_column, effective_start)
    sport_expr = _sport_output_expression(request)
    value_expr = _value_expression(metric)
    sample_expr = _sample_expression(metric)
    where, params = _where_clause(metric, request, effective_start, effective_end)
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


def _query_hr_zone_distribution(
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
    where, params = _where_clause(metric, request, effective_start, effective_end)
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
    rows = []
    for row in _rows(conn.execute(statement, params)):
        row["distribution"] = {f"z{idx}": float(row[f"z{idx}"] or 0.0) for idx in range(1, 6)}
        rows.append(_aggregate_row_from_group(metric, request, effective_start, effective_end, row))
    return rows


def _rows(result) -> list[dict[str, Any]]:
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
        return "sport_type"
    return "NULL"


def _where_clause(
    metric: MetricDefinition,
    request: AggregateRequest,
    effective_start: date,
    effective_end: date,
) -> tuple[str, list[object]]:
    source = str(metric.aggregate_source)
    day_column = _SOURCE_DAY_COLUMNS[source]
    where: list[str] = []
    params: list[object] = []
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


def _aggregate_row_from_group(
    metric: MetricDefinition,
    request: AggregateRequest,
    effective_start: date,
    effective_end: date,
    row: dict[str, Any],
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


def _aggregate_value(metric: MetricDefinition, row: dict[str, Any]) -> float | int | str | None:
    if metric.aggregate_mode == "distribution":
        return None
    value = row.get("value")
    if value is None:
        return None
    if metric.metric_id in {"moving_time_min", "elapsed_time_min"}:
        return float(value)
    return float(value)


def _quantiles(metric: MetricDefinition, row: dict[str, Any]) -> dict[str, float] | None:
    if metric.aggregate_mode != "quantile":
        return None
    value = row.get("value")
    if value is None:
        return None
    return _quantiles_from_group(row)


def _quantiles_from_group(row: dict[str, Any]) -> dict[str, float] | None:
    # The quantile list is fetched by a focused follow-up query to keep the row contract stable.
    values = row.get("quantile_values")
    if not values:
        median = row.get("value")
        if median is None:
            return None
        return {"p25": float(median), "median": float(median), "p75": float(median)}
    return {label: float(value) for label, value in zip(_QUANTILE_LABELS, values, strict=False)}


def _missing_reasons(row: dict[str, Any]) -> list[str]:
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
            additions.append(
                _empty_row(
                    metric,
                    request,
                    current,
                    _date_from_iso(_bucket_end(current.isoformat(), request, effective_end)),
                    sport_type,
                )
            )
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
