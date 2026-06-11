"""Status-fact queries over DuckDB read-model facts."""

import itertools
from datetime import date, timedelta
from typing import Any, cast

from mcp_strava.adapters.duckdb.connection import DuckDBConn
from mcp_strava.adapters.duckdb.schema import create_aggregate_views
from mcp_strava.adapters.duckdb.stream_metric_queries import max_heartrate
from mcp_strava.hr_zones import get_zone_model
from mcp_strava.metric_registry import STATUS_FACT_REGISTRY
from mcp_strava.settings import get_settings
from mcp_strava.sports import SPORT_RUNNING as RUNNING_SPORTS
from mcp_strava.types import StatusFact, StatusFactDefinition

_HR_REST_MISSING_MSG = (
    "MCP_STRAVA_HR_REST is not set — cannot compute HR zones. "
    "Set MCP_STRAVA_HR_REST to the athlete's resting heart rate."
)


def query_status_facts(conn: DuckDBConn, *, as_of_day: str, metric_version: int) -> list[StatusFact]:
    """Status-fact read pinned to a single metric_version (R11): every status
    query that touches activity_metric_facts filters `metric_version = ?` so
    status facts are current-only, never a blend across versions."""
    create_aggregate_views(conn)
    as_of = _parse_day(as_of_day, "as_of_day")
    return [_query_status_fact(conn, definition, as_of, metric_version) for definition in STATUS_FACT_REGISTRY.values()]


def _query_status_fact(
    conn: DuckDBConn, definition: StatusFactDefinition, as_of: date, metric_version: int
) -> StatusFact:
    code = definition.code
    if code == "stale_mirror_data":
        return _query_stale_mirror_status(conn, definition, as_of)
    if code == "stale_read_model_facts":
        return _query_stale_read_model_status(conn, definition, as_of)
    if code == "missing_hr":
        return _query_missing_sample_status(conn, definition, as_of, "heartrate_sample_count", metric_version)
    if code == "missing_streams":
        return _query_missing_sample_status(conn, definition, as_of, "stream_sample_count", metric_version)
    if code == "excessive_z5_exposure":
        return _query_excessive_z5_status(conn, definition, as_of, metric_version)
    if code == "hr_anomaly_burst":
        return _query_hr_anomaly_status(conn, definition, as_of, metric_version)
    if code == "cardiac_drift_significant_quality":
        return _query_cardiac_drift_status(conn, definition, as_of, metric_version)
    if code == "consecutive_high_load_hikes":
        return _query_high_load_hike_status(conn, definition, as_of, metric_version)
    if code == "running_volume_jump":
        return _query_running_volume_jump_status(conn, definition, as_of, metric_version)
    return _status_fact(definition, "unavailable", {}, ["unsupported_status_fact"])


def _query_stale_mirror_status(conn: DuckDBConn, definition: StatusFactDefinition, as_of: date) -> StatusFact:
    row = cast(
        "tuple[object, ...] | None",
        conn.execute(
            """
        SELECT last_success_at
        FROM refresh_state
        ORDER BY id
        LIMIT 1
        """
        ).fetchone(),
    )
    if row is None or row[0] is None:
        return _status_fact(definition, "unavailable", {}, ["refresh_state_missing"])
    last_success_day = _day_from_timestamp(row[0])
    if last_success_day is None:
        return _status_fact(definition, "unavailable", {"last_success_at": row[0]}, ["last_success_missing"])
    age_days = max(0, (as_of - last_success_day).days)
    threshold_days = _as_int(_obj_dict(definition.threshold)["max_age_days"])
    evidence = {
        "last_success_at": str(row[0]),
        "age_days": age_days,
        "threshold_days": threshold_days,
    }
    return _status_fact(definition, "active" if age_days > threshold_days else "inactive", evidence)


def _query_stale_read_model_status(conn: DuckDBConn, definition: StatusFactDefinition, as_of: date) -> StatusFact:
    row = conn.execute(
        """
        SELECT MAX(finished_at) AS last_materialized_at
        FROM read_model_refresh_runs
        WHERE status = 'ok'
        """
    ).fetchone()
    dirty_row = conn.execute("SELECT COUNT(*) FROM metric_dirty_activities").fetchone()
    dirty_count = _as_int(_scalar_cell(dirty_row))
    last_materialized_at = _scalar_cell(row)
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
    threshold_days = _as_int(_obj_dict(definition.threshold)["max_age_days"])
    evidence = {
        "last_materialized_at": str(last_materialized_at),
        "age_days": age_days,
        "dirty_count": dirty_count,
    }
    return _status_fact(definition, "active" if age_days > threshold_days or dirty_count > 0 else "inactive", evidence)


def _query_missing_sample_status(
    conn: DuckDBConn,
    definition: StatusFactDefinition,
    as_of: date,
    sample_column: str,
    metric_version: int,
) -> StatusFact:
    start = _lookback_start(definition, as_of)
    total = _activity_fact_count(conn, start, as_of, metric_version)
    if total == 0:
        return _status_fact(definition, "unavailable", {}, ["no_activity_facts"])
    rows = conn.execute(
        f"""
        SELECT activity_id
        FROM activity_metric_facts
        WHERE activity_day >= CAST(? AS DATE)
          AND activity_day <= CAST(? AS DATE)
          AND metric_version = ?
          AND {sample_column} <= 0
        ORDER BY activity_day, activity_id
        """,
        [start.isoformat(), as_of.isoformat(), metric_version],
    ).fetchall()
    activity_ids = [_as_int(_scalar_cell(row)) for row in rows]
    evidence = {
        "activity_count": len(activity_ids),
        "activity_ids": activity_ids,
        "sample_column": sample_column,
    }
    return _status_fact(definition, "active" if activity_ids else "inactive", evidence)


def _query_excessive_z5_status(
    conn: DuckDBConn, definition: StatusFactDefinition, as_of: date, metric_version: int
) -> StatusFact:
    start = _lookback_start(definition, as_of)
    total = _activity_fact_count(conn, start, as_of, metric_version)
    if total == 0:
        return _status_fact(definition, "unavailable", {}, ["no_activity_facts"])
    threshold = _as_int(_obj_dict(definition.threshold)["zone5_seconds"])
    if "z5_lower_bound_bpm" in definition.threshold:
        z5_lower_bound = _as_int(_obj_dict(definition.threshold)["z5_lower_bound_bpm"])
    else:
        from mcp_strava.adapters.duckdb.repository import DuckDBRepository

        athlete = get_settings().athlete
        if athlete.hr_rest is None:
            raise RuntimeError(_HR_REST_MISSING_MSG)
        repo = DuckDBRepository.from_connection(conn)
        hr_max = max_heartrate(repo)
        if hr_max is None:
            # No HR data in DB: no Z5 events are possible; use max int as unreachable threshold.
            z5_lower_bound = 300
        else:
            bounds = get_zone_model(athlete.hr_zone_model).zone_bounds(hr_max=int(hr_max), hr_rest=athlete.hr_rest)
            z5_lower_bound = bounds[-2]
    row = conn.execute(
        """
        SELECT activity_id, activity_day, zone5_seconds
        FROM activity_metric_facts
        WHERE activity_day >= CAST(? AS DATE)
          AND activity_day <= CAST(? AS DATE)
          AND metric_version = ?
          AND zone5_seconds > ?
        ORDER BY zone5_seconds DESC, activity_day DESC
        LIMIT 1
        """,
        [start.isoformat(), as_of.isoformat(), metric_version, threshold],
    ).fetchone()
    if row is None:
        return _status_fact(definition, "inactive", {"threshold_seconds": threshold})
    evidence = {
        "activity_id": _as_int(_scalar_cell(row, 0)),
        "activity_day": _to_iso(_scalar_cell(row, 1)),
        "zone5_seconds": _as_int(_scalar_cell(row, 2)),
        "z5_lower_bound_bpm": z5_lower_bound,
    }
    return _status_fact(definition, "active", evidence)


def _query_hr_anomaly_status(
    conn: DuckDBConn, definition: StatusFactDefinition, as_of: date, metric_version: int
) -> StatusFact:
    start = _lookback_start(definition, as_of)
    total = _activity_fact_count(conn, start, as_of, metric_version)
    if total == 0:
        return _status_fact(definition, "unavailable", {}, ["no_activity_facts"])
    threshold = _as_int(_obj_dict(definition.threshold)["hr_anomaly_count"])
    row = conn.execute(
        """
        SELECT activity_id, activity_day, anomaly_count
        FROM activity_metric_facts
        WHERE activity_day >= CAST(? AS DATE)
          AND activity_day <= CAST(? AS DATE)
          AND metric_version = ?
          AND anomaly_count >= ?
        ORDER BY anomaly_count DESC, activity_day DESC
        LIMIT 1
        """,
        [start.isoformat(), as_of.isoformat(), metric_version, threshold],
    ).fetchone()
    if row is None:
        return _status_fact(definition, "inactive", {"threshold_count": threshold})
    evidence = {
        "activity_id": _as_int(_scalar_cell(row, 0)),
        "activity_day": _to_iso(_scalar_cell(row, 1)),
        "hr_anomaly_count": _as_int(_scalar_cell(row, 2)),
        "jump_bpm": _as_int(_obj_dict(definition.threshold)["jump_bpm"]),
    }
    return _status_fact(definition, "active", evidence)


def _query_cardiac_drift_status(
    conn: DuckDBConn, definition: StatusFactDefinition, as_of: date, metric_version: int
) -> StatusFact:
    start = _lookback_start(definition, as_of)
    total = _activity_fact_count(conn, start, as_of, metric_version)
    if total == 0:
        return _status_fact(definition, "unavailable", {}, ["no_activity_facts"])
    qualities = tuple(str(value) for value in cast("list[object]", _obj_dict(definition.threshold)["quality"]))
    placeholders = ",".join("?" for _ in qualities)
    row = conn.execute(
        f"""
        SELECT activity_id, activity_day, cardiac_drift_significant, cardiac_drift_quality
        FROM activity_metric_facts
        WHERE activity_day >= CAST(? AS DATE)
          AND activity_day <= CAST(? AS DATE)
          AND metric_version = ?
          AND cardiac_drift_significant = TRUE
          AND cardiac_drift_quality IN ({placeholders})
        ORDER BY activity_day DESC, activity_id DESC
        LIMIT 1
        """,
        [
            start.isoformat(),
            as_of.isoformat(),
            metric_version,
            *qualities,
        ],
    ).fetchone()
    if row is None:
        return _status_fact(definition, "inactive", {"quality": list(qualities)})
    evidence = {
        "activity_id": _as_int(_scalar_cell(row, 0)),
        "activity_day": _to_iso(_scalar_cell(row, 1)),
        "cardiac_drift_significant": _as_int(_scalar_cell(row, 2)),
        "cardiac_drift_quality": str(_scalar_cell(row, 3)),
    }
    return _status_fact(definition, "active", evidence)


def _query_high_load_hike_status(
    conn: DuckDBConn, definition: StatusFactDefinition, as_of: date, metric_version: int
) -> StatusFact:
    start = _lookback_start(definition, as_of)
    rows = conn.execute(
        """
        SELECT activity_day, SUM(COALESCE(trimp, 0.0)) AS daily_trimp
        FROM activity_metric_facts
        WHERE activity_day >= CAST(? AS DATE)
          AND activity_day <= CAST(? AS DATE)
          AND metric_version = ?
          AND sport_type = 'Hike'
        GROUP BY activity_day
        ORDER BY activity_day
        """,
        [start.isoformat(), as_of.isoformat(), metric_version],
    ).fetchall()
    if len(rows) < 2:
        return _status_fact(definition, "unavailable", {"hike_day_count": len(rows)}, ["insufficient_hike_history"])
    threshold = _as_float(_obj_dict(definition.threshold)["combined_trimp"])
    best_pair: tuple[object, object, float] | None = None
    for previous, current in itertools.pairwise(rows):
        prev_day_cell = _scalar_cell(previous, 0)
        curr_day_cell = _scalar_cell(current, 0)
        previous_day = _coerce_day(prev_day_cell)
        current_day = _coerce_day(curr_day_cell)
        if previous_day is None or current_day is None or (current_day - previous_day).days != 1:
            continue
        combined = _as_float(_scalar_cell(previous, 1)) + _as_float(_scalar_cell(current, 1))
        if best_pair is None or combined > best_pair[2]:
            best_pair = (prev_day_cell, curr_day_cell, combined)
    if best_pair is None:
        return _status_fact(definition, "inactive", {"hike_day_count": len(rows)})
    evidence = {
        "hike_days": [_to_iso(best_pair[0]), _to_iso(best_pair[1])],
        "combined_trimp": best_pair[2],
    }
    return _status_fact(definition, "active" if best_pair[2] > threshold else "inactive", evidence)


def _query_running_volume_jump_status(
    conn: DuckDBConn, definition: StatusFactDefinition, as_of: date, metric_version: int
) -> StatusFact:
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
          AND metric_version = ?
          AND activity_day >= CAST(? AS DATE)
          AND activity_day < CAST(? AS DATE)
    """
    previous = _as_float(
        _scalar_cell(
            conn.execute(
                query, [*running_sports, metric_version, previous_start.isoformat(), previous_end.isoformat()]
            ).fetchone()
        )
    )
    current = _as_float(
        _scalar_cell(
            conn.execute(
                query, [*running_sports, metric_version, current_start.isoformat(), current_end.isoformat()]
            ).fetchone()
        )
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
        definition,
        "active" if increase_pct >= _as_float(_obj_dict(definition.threshold)["caution_pct"]) else "inactive",
        evidence,
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
    lookback_days = _as_int(_obj_dict(definition.window).get("lookback_days"), default=1)
    return as_of - timedelta(days=max(lookback_days - 1, 0))


def _activity_fact_count(conn: DuckDBConn, start: date, as_of: date, metric_version: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM activity_metric_facts
        WHERE activity_day >= CAST(? AS DATE)
          AND activity_day <= CAST(? AS DATE)
          AND metric_version = ?
        """,
        [start.isoformat(), as_of.isoformat(), metric_version],
    ).fetchone()
    return _as_int(_scalar_cell(row))


def _parse_day(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


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
    # activity_day/day cells come from native DATE columns → already date | None.
    return value if isinstance(value, date) else None


def _to_iso(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _scalar_cell(row: tuple[Any, ...] | None, index: int = 0) -> object:
    if row is None:
        return None
    return cast("tuple[object, ...]", row)[index]


def _as_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError(f"expected an int-like cell, got {type(value).__name__}")


def _as_float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"expected a float-like cell, got {type(value).__name__}")


def _obj_dict(value: dict[str, Any]) -> dict[str, object]:
    return cast("dict[str, object]", value)
