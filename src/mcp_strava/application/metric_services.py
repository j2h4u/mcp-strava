"""Metric-focused application services for MCP-facing tool backends."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from statistics import median

from mcp_strava.adapters.sqlite.repository import CURRENT_METRIC_VERSION, SQLiteRepository
from mcp_strava.application.freshness import build_freshness_metadata
from mcp_strava.application.metric_registry import METRIC_REGISTRY
from mcp_strava.constants import Config
from mcp_strava.db import DbConn
from mcp_strava.refresh.policy import RefreshPolicy
from mcp_strava.settings import get_settings
from mcp_strava.training import forward_simulate
from mcp_strava.types import (
    CompletenessMetadata,
    ServiceEnvelope,
    ServiceRationale,
    ServiceWarning,
)

SAFETY_WARNING_CODES = {
    "z5_excessive",
    "hike_load_consecutive_high",
    "running_volume_jump_high",
    "cardiac_drift_severe_yesterday",
    "hr_anomaly_burst",
    "low_hr_data",
    "insufficient_history",
}

COMPARISON_MISSING_REASONS = {
    "insufficient_history",
    "missing_hr",
    "missing_streams",
    "metric_not_applicable",
    "no_activity_in_period",
    "read_model_unavailable",
}

ACTIVITY_SCALAR_FACTS = {
    "trimp": ("trimp", 1.0),
    "distance_km": ("distance_m", 1 / 1000),
    "moving_time_min": ("moving_time_s", 1 / 60),
    "elapsed_time_min": ("elapsed_time_s", 1 / 60),
    "elevation_m": ("elevation_gain_m", 1.0),
    "avg_hr": (None, 1.0),
    "max_hr": (None, 1.0),
    "hr_recovery_pauses": ("hr_recovery_pause_count", 1.0),
    "hr_recovery_total_rest_sec": ("hr_recovery_total_rest_sec", 1.0),
    "hr_recovery_median_bpm_per_min": ("hr_recovery_median_rate", 1.0),
    "hr_recovery_best_bpm_per_min": ("hr_recovery_best_rate", 1.0),
    "hr_recovery_worst_bpm_per_min": ("hr_recovery_worst_rate", 1.0),
    "hr_recovery_avg_bpm_per_min": ("hr_recovery_avg_rate", 1.0),
    "vertical_speed_m_per_h": ("vertical_speed_vmh", 1.0),
    "vertical_ascent_m": ("vertical_speed_total_ascent_m", 1.0),
    "vertical_duration_h": ("vertical_speed_duration_hours", 1.0),
    "cardiac_cost": ("cardiac_cost", 1.0),
    "cardiac_cost_adjusted": ("adjusted_cardiac_cost", 1.0),
    "cardiac_drift_pct": ("cardiac_drift_pct", 1.0),
    "cardiac_drift_significant": ("cardiac_drift_significant", 1.0),
    "hrr_pct": ("hrr_pct", 1.0),
    "hr_anomaly_count": ("anomaly_count", 1.0),
}

MODEL_FACTS = {
    "fitness": "fitness",
    "fatigue": "fatigue",
    "form": "form",
    "form_zone": "form_zone",
    "acwr_zone": "acwr_zone",
    "acwr": "acwr",
}

ROLLING_FACTS = {
    "weekly_trimp": (7, "effective_trimp", 1.0),
    "total_trimp_14d": (14, "effective_trimp", 1.0),
    "avg_trimp_per_day": (14, "effective_trimp", 1 / 14),
    "active_days": (14, "active_days", 1.0),
    "rest_days": (14, "rest_days", 1.0),
    "daily_avg_trimp_7d": (7, "effective_trimp", 1 / 7),
    "daily_avg_trimp_28d": (28, "effective_trimp", 1 / 28),
    "daily_avg_trimp_90d": (90, "effective_trimp", 1 / 90),
    "rolling_median_cc": (90, "median_cardiac_cost", 1.0),
    "rolling_median_cc_adj": (90, "median_adjusted_cardiac_cost", 1.0),
    "rolling_median_hr_recovery": (90, "median_hr_recovery", 1.0),
    "rolling_median_cardiac_drift_pct": (90, "median_cardiac_drift_pct", 1.0),
    "volume_7d": (7, "activity_count", 1.0),
    "volume_28d": (28, "activity_count", 1.0),
}

COMPARE_PERIODS_HANDLERS = {
    **{metric_id: "activity_metric_facts" for metric_id in ACTIVITY_SCALAR_FACTS},
    "time_in_hr_zones_min": "activity_metric_facts",
    **{metric_id: "training_model_daily" for metric_id in MODEL_FACTS},
    **{metric_id: "rolling_period_facts" for metric_id in ROLLING_FACTS},
}

COMPARE_PERIODS_SKIP_REASONS: dict[str, str] = {}


def _project_fitness_state_metrics(model, rolling: dict[int, object]) -> dict[str, object]:
    data: dict[str, object] = {}
    if model is not None:
        for metric_id, column in MODEL_FACTS.items():
            _metric_if_registered(data, metric_id, model[column])
    for metric_id, (window, column, scale) in ROLLING_FACTS.items():
        row = rolling.get(window)
        value = row[column] if row is not None else None
        _metric_if_registered(data, metric_id, round(float(value) * scale, 3) if value is not None else None)
    return data


def _connection_context(connection):
    return nullcontext(connection) if connection is not None else DbConn()


def _policy() -> RefreshPolicy:
    return RefreshPolicy.from_settings(get_settings())


def _metric_if_registered(payload: dict[str, object], metric_id: str, value) -> None:
    if metric_id in METRIC_REGISTRY:
        payload[metric_id] = value


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_json_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _summary_json(row) -> dict[str, object]:
    raw = row["summary_json"] if "summary_json" in row.keys() else None
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def _read_model_status(repo: SQLiteRepository) -> dict[str, object]:
    return repo.read_model_status(metric_version=CURRENT_METRIC_VERSION)


def _coverage_with_read_model(read_model: dict[str, object], extra: dict[str, object] | None = None) -> dict[str, object]:
    coverage = dict(extra or {})
    coverage["read_model"] = read_model
    return coverage


def _status_from_read_model(read_model: dict[str, object], *, has_data: bool, missing: list[str]) -> str:
    if not has_data:
        return "unavailable"
    if read_model.get("status") == "stale":
        return "stale"
    if missing:
        return "partial"
    return "complete"


def _rationale(message: str) -> list[ServiceRationale]:
    return [ServiceRationale(code="metric_bundle_from_read_model", message=message)]


def _fact_status(row) -> dict[str, object]:
    missing = _parse_json_list(row["missing_reasons_json"])
    return {
        "status": row["completeness_status"],
        "missing": missing,
        "source_revision": int(row["source_revision"]),
        "metric_version": int(row["metric_version"]),
        "materialized_at": row["computed_at"],
    }


def _row_get(row, key: str, default=None):
    if row is None:
        return default
    if hasattr(row, "keys") and key in row.keys():
        return row[key]
    if isinstance(row, dict):
        return row.get(key, default)
    return default


def _zone_minutes(row) -> list[float]:
    return [
        round(float(row[f"zone{idx}_seconds"] or 0) / 60, 3)
        for idx in range(1, 6)
    ]


def _activity_value(row, metric_id: str):
    if metric_id in {"avg_hr", "max_hr"}:
        summary = _summary_json(row)
        summary_key = "average_heartrate" if metric_id == "avg_hr" else "max_heartrate"
        value = summary.get(summary_key)
        return round(float(value), 3) if value is not None else None
    if metric_id == "time_in_hr_zones_min":
        return _zone_minutes(row)
    if metric_id == "cardiac_drift_severity":
        return row["cardiac_drift_severity"]
    column, scale = ACTIVITY_SCALAR_FACTS.get(metric_id, (None, 1.0))
    if column is None:
        return None
    value = row[column]
    if value is None:
        return None
    return round(float(value) * float(scale), 3)


def _activity_payload(row) -> dict[str, object]:
    summary = _summary_json(row)
    return {
        "activity_id": int(row["activity_id"]),
        "activity_date": row["activity_day"],
        "sport_type": row["sport_type"],
        "activity_name": row["activity_name"],
        "distance_km": _activity_value(row, "distance_km"),
        "moving_time_min": _activity_value(row, "moving_time_min"),
        "elapsed_time_min": _activity_value(row, "elapsed_time_min"),
        "elevation_m": _activity_value(row, "elevation_m"),
        "trimp": _activity_value(row, "trimp"),
        "avg_hr": summary.get("average_heartrate"),
        "max_hr": int(round(summary["max_heartrate"])) if summary.get("max_heartrate") else None,
        "time_in_hr_zones_min": _zone_minutes(row),
        "hr_recovery_pauses": int(row["hr_recovery_pause_count"] or 0),
        "hr_recovery_total_rest_sec": int(row["hr_recovery_total_rest_sec"] or 0),
        "hr_recovery_median_bpm_per_min": _activity_value(row, "hr_recovery_median_bpm_per_min"),
        "hr_recovery_best_bpm_per_min": _activity_value(row, "hr_recovery_best_bpm_per_min"),
        "hr_recovery_worst_bpm_per_min": _activity_value(row, "hr_recovery_worst_bpm_per_min"),
        "hr_recovery_avg_bpm_per_min": _activity_value(row, "hr_recovery_avg_bpm_per_min"),
        "vertical_speed_m_per_h": _activity_value(row, "vertical_speed_m_per_h"),
        "vertical_ascent_m": _activity_value(row, "vertical_ascent_m"),
        "vertical_duration_h": _activity_value(row, "vertical_duration_h"),
        "cardiac_cost": _activity_value(row, "cardiac_cost"),
        "cardiac_cost_adjusted": _activity_value(row, "cardiac_cost_adjusted"),
        "cardiac_drift_pct": _activity_value(row, "cardiac_drift_pct"),
        "cardiac_drift_severity": row["cardiac_drift_severity"],
        "cardiac_drift_significant": int(row["cardiac_drift_significant"] or 0),
        "cardiac_drift_quality": row["cardiac_drift_quality"],
        "hrr_pct": _activity_value(row, "hrr_pct"),
        "start_time": str(summary.get("start_date_local", ""))[11:16] or None,
        "hr_anomaly_count": int(row["anomaly_count"] or 0),
        "completeness": _fact_status(row),
    }


def _latest_as_of_day(checked_at: datetime) -> str:
    return checked_at.date().isoformat()


def _rolling_by_window(repo: SQLiteRepository, as_of_day: str) -> dict[int, object]:
    return {
        window: repo.fetch_rolling_period_facts(
            as_of_day,
            window,
            scope="all",
            metric_version=CURRENT_METRIC_VERSION,
        )
        for window in (7, 14, 28, 90)
    }


def get_fitness_state_service(
    *,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    checked_at = now or datetime.now()
    with _connection_context(connection) as conn:
        repo = SQLiteRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, checked_at, _policy(), signal_first_use=signal_first_use)
        read_model = _read_model_status(repo)
        as_of_day = _latest_as_of_day(checked_at)
        model = repo.fetch_latest_training_model_day(CURRENT_METRIC_VERSION, as_of_day=as_of_day)
        if model is None:
            model = repo.fetch_latest_training_model_day(CURRENT_METRIC_VERSION)
        rolling = _rolling_by_window(repo, model["day"] if model is not None else as_of_day)

    missing: list[str] = []
    if model is None:
        missing.append("read_model_unavailable")
    data = _project_fitness_state_metrics(model, rolling)

    completeness = CompletenessMetadata(
        status=_status_from_read_model(read_model, has_data=bool(data), missing=missing),
        missing=missing,
        coverage=_coverage_with_read_model(read_model, {"metrics": sorted(data.keys())}),
    )
    return ServiceEnvelope(
        data=data,
        freshness=freshness,
        completeness=completeness,
        warnings=[],
        rationale=_rationale("Metric bundle projected from materialized read-model facts."),
    )


def list_workouts_service(
    limit: int = 20,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    sport: str | None = None,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    if not isinstance(limit, int):
        raise ValueError("limit must be an integer")
    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200")
    checked_at = now or datetime.now()
    start_day = start_date or "0001-01-01"
    end_day = _next_day(end_date) if end_date else "9999-12-31"
    with _connection_context(connection) as conn:
        repo = SQLiteRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, checked_at, _policy(), signal_first_use=signal_first_use)
        rows = repo.fetch_activity_metric_facts(
            start_day,
            end_day,
            sport=sport,
            metric_version=CURRENT_METRIC_VERSION,
            limit=limit,
        )
        read_model = _read_model_status(repo)
        data = [_activity_payload(row) for row in rows]

        completeness = CompletenessMetadata(
            status=_status_from_read_model(read_model, has_data=True, missing=[]),
            missing=[],
            coverage=_coverage_with_read_model(
                read_model,
                {"count": len(data), "limit": limit, "filters": {"start_date": start_date, "end_date": end_date, "sport": sport}},
            ),
        )

    compact_rows = [
        {
            key: row[key]
            for key in (
                "activity_id",
                "activity_date",
                "sport_type",
                "activity_name",
                "distance_km",
                "moving_time_min",
                "elevation_m",
                "trimp",
                "avg_hr",
                "max_hr",
                "completeness",
            )
        }
        for row in data
    ]
    return ServiceEnvelope(
        data=compact_rows,
        freshness=freshness,
        completeness=completeness,
        warnings=[],
        rationale=_rationale("Workout list projected from materialized activity facts."),
    )


def get_workout_detail_service(
    activity_id: int | str,
    *,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    checked_at = now or datetime.now()
    with _connection_context(connection) as conn:
        repo = SQLiteRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, checked_at, _policy(), signal_first_use=signal_first_use)
        read_model = _read_model_status(repo)
        resolved_id = repo.latest_activity_id() if activity_id == "latest" else int(activity_id)
        row = repo.fetch_activity_metric_fact(resolved_id, metric_version=CURRENT_METRIC_VERSION) if resolved_id is not None else None

        if row is None:
            completeness = CompletenessMetadata(
                status="unavailable",
                missing=["workout_not_found"],
                coverage=_coverage_with_read_model(read_model, {"activity_id": activity_id}),
            )
            return ServiceEnvelope(
                data=None,
                freshness=freshness,
                completeness=completeness,
                warnings=[ServiceWarning(code="workout_not_found", severity="warning", message="Requested workout was not found.")],
                rationale=_rationale("Workout detail requested from materialized activity facts."),
            )

        data = _activity_payload(row)
        missing = _parse_json_list(row["missing_reasons_json"])
        stream_derived = [
            data["hr_recovery_median_bpm_per_min"],
            data["vertical_speed_m_per_h"],
            data["cardiac_cost"],
            data["cardiac_drift_pct"],
            data["hrr_pct"],
        ]
        if all(value is None for value in stream_derived) and "missing_streams" not in missing:
            missing.append("missing_streams")
        elif any(value is None for value in stream_derived) and "metric_unavailable" not in missing:
            missing.append("metric_unavailable")

        completeness = CompletenessMetadata(
            status=_status_from_read_model(read_model, has_data=True, missing=missing),
            missing=sorted(set(missing)),
            coverage=_coverage_with_read_model(read_model, {"metric_count": len(data), "activity_id": resolved_id}),
        )
        warnings = [
            ServiceWarning(code=code, severity="warning", message="Workout metric coverage is partial.")
            for code in completeness.missing
            if code in {"missing_hr", "missing_streams", "metric_unavailable"}
        ]

    return ServiceEnvelope(
        data=data,
        freshness=freshness,
        completeness=completeness,
        warnings=warnings,
        rationale=_rationale("Workout detail projected from materialized activity facts."),
    )


def _compare_summary(values: list, comparison_mode: str):
    scalar_values = [value for value in values if _is_number(value)]
    if not scalar_values:
        return None
    if comparison_mode == "sum":
        return round(float(sum(scalar_values)), 3)
    if comparison_mode == "avg":
        return round(float(sum(scalar_values) / len(scalar_values)), 3)
    if comparison_mode == "median":
        return round(float(median(scalar_values)), 3)
    if comparison_mode == "last":
        return round(float(scalar_values[-1]), 3)
    if comparison_mode == "min":
        return round(float(min(scalar_values)), 3)
    if comparison_mode == "max":
        return round(float(max(scalar_values)), 3)
    if comparison_mode == "trend":
        if len(scalar_values) < 2:
            return None
        return round(float(scalar_values[-1] - scalar_values[0]), 3)
    return None


def _version_status(rows_a: list, rows_b: list) -> str:
    versions = {int(row["metric_version"]) for row in rows_a + rows_b if row["metric_version"] is not None}
    if not versions:
        return "missing"
    if len(versions) > 1:
        return "mixed"
    return "consistent"


def compare_scalar_metric(
    metric_id: str,
    comparison_mode: str,
    values_a: list,
    values_b: list,
    missing_a: list[str],
    missing_b: list[str],
    rows_a: list | None = None,
    rows_b: list | None = None,
) -> dict[str, object]:
    a_value = _compare_summary(values_a, comparison_mode)
    b_value = _compare_summary(values_b, comparison_mode)
    missing = sorted(set(missing_a + missing_b))
    if not values_a:
        missing.append("no_activity_in_period")
    if not values_b:
        missing.append("no_activity_in_period")
    missing = sorted(set(missing))
    delta = round(a_value - b_value, 3) if _is_number(a_value) and _is_number(b_value) else None
    delta_pct = round((delta / b_value) * 100, 2) if _is_number(delta) and _is_number(b_value) and b_value != 0 else None
    trend = "unavailable"
    if _is_number(delta):
        trend = "flat" if abs(delta) < 1e-9 else ("up" if delta > 0 else "down")
    return {
        "period_a": {"value": a_value, "sample_size": len(values_a)},
        "period_b": {"value": b_value, "sample_size": len(values_b)},
        "delta": delta,
        "delta_pct": delta_pct,
        "trend_direction": trend,
        "sample_size": {"period_a": len(values_a), "period_b": len(values_b)},
        "coverage": {"period_a": 1.0 if values_a else 0.0, "period_b": 1.0 if values_b else 0.0},
        "missing_reasons": missing,
        "metric_version_status": _version_status(rows_a or [], rows_b or []),
    }


def compare_distribution_metric(values_a: list, values_b: list, missing_a: list[str], missing_b: list[str], rows_a: list | None = None, rows_b: list | None = None) -> dict[str, object]:
    missing = sorted(set(missing_a + missing_b))
    if not values_a or not values_b:
        missing = sorted(set(missing + ["no_activity_in_period"]))
    zone_count = 5
    buckets_a = {f"z{i + 1}": 0.0 for i in range(zone_count)}
    buckets_b = {f"z{i + 1}": 0.0 for i in range(zone_count)}
    for zones in values_a:
        if not isinstance(zones, list):
            continue
        for idx, value in enumerate(zones[:zone_count]):
            buckets_a[f"z{idx + 1}"] += float(value or 0.0)
    for zones in values_b:
        if not isinstance(zones, list):
            continue
        for idx, value in enumerate(zones[:zone_count]):
            buckets_b[f"z{idx + 1}"] += float(value or 0.0)
    for key in buckets_a:
        buckets_a[key] = round(buckets_a[key], 2)
        buckets_b[key] = round(buckets_b[key], 2)
    bucket_deltas = {key: round(buckets_a[key] - buckets_b[key], 2) for key in buckets_a}
    bucket_delta_pct = {
        key: (round((bucket_deltas[key] / buckets_b[key]) * 100, 2) if buckets_b[key] else None) for key in buckets_a
    }
    total_a = sum(buckets_a.values())
    total_b = sum(buckets_b.values())
    overlap = None
    if total_a > 0 and total_b > 0:
        overlap = round((sum(min(buckets_a[k], buckets_b[k]) for k in buckets_a) / max(total_a, total_b)) * 100, 2)
    elif "insufficient_history" not in missing:
        missing.append("insufficient_history")
    return {
        "period_a": {"buckets": buckets_a, "sample_size": len(values_a)},
        "period_b": {"buckets": buckets_b, "sample_size": len(values_b)},
        "bucket_deltas": bucket_deltas,
        "bucket_delta_pct": bucket_delta_pct,
        "distribution_overlap_pct": overlap,
        "delta": None,
        "delta_pct": None,
        "trend_direction": "unavailable",
        "sample_size": {"period_a": len(values_a), "period_b": len(values_b)},
        "coverage": {"period_a": 1.0 if values_a else 0.0, "period_b": 1.0 if values_b else 0.0},
        "missing_reasons": sorted(set(missing)),
        "metric_version_status": _version_status(rows_a or [], rows_b or []),
    }


def _values_for_metric(metric_id: str, rows: list) -> tuple[list, list[str]]:
    values: list = []
    missing: list[str] = []
    for row in rows:
        value = _activity_value(row, metric_id)
        if value is None:
            missing.extend(_parse_json_list(row["missing_reasons_json"]) or ["metric_not_applicable"])
        else:
            values.append(value)
    return values, sorted(set(missing))


def _compare_metric_from_rows(metric, rows_a: list, rows_b: list) -> dict[str, object]:
    values_a, missing_a = _values_for_metric(metric.metric_id, rows_a)
    values_b, missing_b = _values_for_metric(metric.metric_id, rows_b)
    if metric.comparison_mode == "distribution":
        return compare_distribution_metric(values_a, values_b, missing_a, missing_b, rows_a, rows_b)
    return compare_scalar_metric(
        metric.metric_id,
        metric.comparison_mode,
        values_a,
        values_b,
        missing_a,
        missing_b,
        rows_a,
        rows_b,
    )


def _compare_model_metric(metric, model_a, model_b) -> dict[str, object]:
    column = MODEL_FACTS[metric.metric_id]
    value_a = model_a[column] if model_a is not None else None
    value_b = model_b[column] if model_b is not None else None
    rows_a = [model_a] if model_a is not None else []
    rows_b = [model_b] if model_b is not None else []
    return compare_scalar_metric(
        metric.metric_id,
        metric.comparison_mode,
        [value_a] if value_a is not None else [],
        [value_b] if value_b is not None else [],
        [] if value_a is not None else ["insufficient_history"],
        [] if value_b is not None else ["insufficient_history"],
        rows_a,
        rows_b,
    )


def _compare_rolling_metric(metric, rolling_a: dict[int, object], rolling_b: dict[int, object]) -> dict[str, object]:
    window, column, scale = ROLLING_FACTS[metric.metric_id]
    row_a = rolling_a.get(window)
    row_b = rolling_b.get(window)
    value_a = row_a[column] if row_a is not None else None
    value_b = row_b[column] if row_b is not None else None
    scaled_a = round(float(value_a) * scale, 3) if value_a is not None else None
    scaled_b = round(float(value_b) * scale, 3) if value_b is not None else None
    rows_a = [row_a] if row_a is not None else []
    rows_b = [row_b] if row_b is not None else []
    return compare_scalar_metric(
        metric.metric_id,
        metric.comparison_mode,
        [scaled_a] if scaled_a is not None else [],
        [scaled_b] if scaled_b is not None else [],
        [] if scaled_a is not None else ["insufficient_history"],
        [] if scaled_b is not None else ["insufficient_history"],
        rows_a,
        rows_b,
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
    checked_at = now or datetime.now()
    with _connection_context(connection) as conn:
        repo = SQLiteRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, checked_at, _policy(), signal_first_use=signal_first_use)
        read_model = _read_model_status(repo)
        period_a_rows = repo.fetch_activity_metric_facts(
            period_a_start,
            _next_day(period_a_end),
            sport=sport,
            metric_version=CURRENT_METRIC_VERSION,
        )
        period_b_rows = repo.fetch_activity_metric_facts(
            period_b_start,
            _next_day(period_b_end),
            sport=sport,
            metric_version=CURRENT_METRIC_VERSION,
        )
        model_a = repo.fetch_latest_training_model_day(
            CURRENT_METRIC_VERSION,
            as_of_day=period_a_end,
        )
        model_b = repo.fetch_latest_training_model_day(
            CURRENT_METRIC_VERSION,
            as_of_day=period_b_end,
        )
        rolling_windows = sorted({spec[0] for spec in ROLLING_FACTS.values()})
        rolling_a = {
            window: repo.fetch_rolling_period_facts(
                period_a_end,
                window,
                scope="all",
                metric_version=CURRENT_METRIC_VERSION,
            )
            for window in rolling_windows
        }
        rolling_b = {
            window: repo.fetch_rolling_period_facts(
                period_b_end,
                window,
                scope="all",
                metric_version=CURRENT_METRIC_VERSION,
            )
            for window in rolling_windows
        }
        sports = sorted(set([row["sport_type"] for row in period_a_rows + period_b_rows]))

    global_section = {"scope_filter": "sport" if sport else "all", "metrics": {}}
    per_sport_section: dict[str, dict[str, object]] = {}
    for metric in METRIC_REGISTRY.values():
        if "compare_periods" not in metric.exposed_in or metric.comparison_mode == "none":
            continue
        if metric.metric_id in MODEL_FACTS:
            global_section["metrics"][metric.metric_id] = _compare_model_metric(metric, model_a, model_b)
            continue
        if metric.metric_id in ROLLING_FACTS:
            global_section["metrics"][metric.metric_id] = _compare_rolling_metric(metric, rolling_a, rolling_b)
            continue
        if metric.metric_id not in ACTIVITY_SCALAR_FACTS and metric.metric_id != "time_in_hr_zones_min":
            continue
        if metric.sport_scope in {"global", "both"}:
            global_section["metrics"][metric.metric_id] = _compare_metric_from_rows(metric, period_a_rows, period_b_rows)
        if metric.sport_scope in {"per_sport", "both"}:
            for sport_name in sports:
                if sport is not None and sport_name != sport:
                    continue
                a_rows = [row for row in period_a_rows if row["sport_type"] == sport_name]
                b_rows = [row for row in period_b_rows if row["sport_type"] == sport_name]
                if not a_rows and not b_rows:
                    continue
                per_sport_section.setdefault(sport_name, {"metrics": {}})
                per_sport_section[sport_name]["metrics"][metric.metric_id] = _compare_metric_from_rows(metric, a_rows, b_rows)

    data = {
        "periods": {
            "period_a": {"start": period_a_start, "end": period_a_end},
            "period_b": {"start": period_b_start, "end": period_b_end},
        },
        "global": global_section,
        "per_sport": per_sport_section,
    }
    completeness = CompletenessMetadata(
        status=_status_from_read_model(read_model, has_data=True, missing=[]),
        missing=[],
        coverage={
            "global_metrics": sorted(global_section["metrics"].keys()),
            "per_sport": sorted(per_sport_section.keys()),
            "supported_missing_reasons": sorted(COMPARISON_MISSING_REASONS),
            "read_model": read_model,
        },
    )
    return ServiceEnvelope(
        data=data,
        freshness=freshness,
        completeness=completeness,
        warnings=[],
        rationale=_rationale("Period comparison returns factual read-model metric deltas and coverage only."),
    )


def _validate_iso_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("custom_daily_trimp.date must be ISO YYYY-MM-DD") from exc


def _validated_custom_series(custom_daily_trimp, today_day: date, target_day: date) -> dict[str, float]:
    if not isinstance(custom_daily_trimp, list):
        raise ValueError("custom_daily_trimp must be a list")
    by_day: dict[str, float] = {}
    prev = None
    for row in custom_daily_trimp:
        if not isinstance(row, dict):
            raise ValueError("custom_daily_trimp rows must include date and trimp")
        if "date" not in row or "trimp" not in row:
            raise ValueError("custom_daily_trimp rows must include date and trimp")
    for row in sorted(custom_daily_trimp, key=lambda item: item["date"]):
        day = _validate_iso_day(row["date"])
        if day < today_day or day > target_day:
            raise ValueError("custom_daily_trimp rows must be within today..target_date")
        trimp = row.get("trimp")
        if not isinstance(trimp, (int, float)):
            raise ValueError("custom_daily_trimp.trimp must be numeric")
        if trimp < 0:
            raise ValueError("custom_daily_trimp.trimp must be non-negative")
        day_key = day.isoformat()
        if day_key in by_day:
            raise ValueError("custom_daily_trimp dates must be unique")
        if prev is not None and day < prev:
            raise ValueError("custom_daily_trimp dates must be monotonic")
        by_day[day_key] = float(trimp)
        prev = day
    return by_day


def _scenario_trimps(
    *,
    scenario: str,
    days: list[date],
    today_day: date,
    history_daily_trimp: dict[str, float],
    custom_daily_trimp,
) -> tuple[list[float], dict[str, object]]:
    if scenario == "rest":
        return [0.0 for _ in days], {"template_source": "rest_zero_load"}
    if scenario == "easy":
        easy_value = float(getattr(Config.Plan, "TRIMP_EASY", 80))
        return [easy_value for _ in days], {"template_source": "config_plan_constants", "activity_template_trimp": easy_value}
    if scenario == "maintain":
        lookback_start = (today_day - timedelta(days=27)).isoformat()
        lookback = {k: v for k, v in history_daily_trimp.items() if lookback_start <= k <= today_day.isoformat()}
        nonzero = [v for v in lookback.values() if v > 0]
        avg_nonzero = float(round(sum(nonzero) / len(nonzero), 2)) if nonzero else 0.0
        weekday_has_training = {date.fromisoformat(k).weekday() for k, v in lookback.items() if v > 0}
        trimps = [avg_nonzero if d.weekday() in weekday_has_training else 0.0 for d in days]
        return trimps, {"template_source": "maintain_weekday_pattern", "mean_nonzero_trimp_28d": avg_nonzero}
    if scenario == "custom":
        custom_by_day = _validated_custom_series(custom_daily_trimp, today_day, days[-1])
        return [float(custom_by_day.get(d.isoformat(), 0.0)) for d in days], {"template_source": "custom_input"}
    raise ValueError(f"Unsupported scenario: {scenario}")


def _daily_trimp_history(repo: SQLiteRepository, start_day: str, end_day: str) -> dict[str, float]:
    rows = repo.fetch_daily_load_facts(start_day, _next_day(end_day), scope="all", metric_version=CURRENT_METRIC_VERSION)
    return {row["day"]: float(row["effective_trimp"] or 0.0) for row in rows}


def project_fitness_state_service(
    *,
    target_date: str,
    scenarios: list[str],
    custom_daily_trimp=None,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    allowed = {"rest", "easy", "maintain", "custom"}
    if any(name not in allowed for name in scenarios):
        raise ValueError("Supported scenarios are: rest, easy, maintain, custom")

    checked_at = now or datetime.now()
    today_day = checked_at.date()
    target_day = date.fromisoformat(target_date)
    horizon_days = (target_day - today_day).days
    if horizon_days < 0:
        raise ValueError("target_date must be today or later")
    if horizon_days > 90:
        raise ValueError("projection horizon must be <= 90 days")

    days = [today_day + timedelta(days=offset) for offset in range(horizon_days + 1)]
    with _connection_context(connection) as conn:
        repo = SQLiteRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, checked_at, _policy(), signal_first_use=signal_first_use)
        read_model = _read_model_status(repo)
        baseline = repo.fetch_latest_training_model_day(CURRENT_METRIC_VERSION, as_of_day=today_day.isoformat())
        if baseline is None:
            baseline = repo.fetch_latest_training_model_day(CURRENT_METRIC_VERSION)
        history_start = (today_day - timedelta(days=27)).isoformat()
        history_daily_trimp = _daily_trimp_history(repo, history_start, today_day.isoformat())

    baseline_fitness = float(baseline["fitness"] or 0.0) if baseline is not None else 0.0
    baseline_fatigue = float(baseline["fatigue"] or 0.0) if baseline is not None else 0.0
    missing = [] if baseline is not None else ["read_model_unavailable"]
    scenario_payload: dict[str, dict[str, object]] = {}
    for scenario in scenarios:
        trimps, assumptions = _scenario_trimps(
            scenario=scenario,
            days=days,
            today_day=today_day,
            history_daily_trimp=history_daily_trimp,
            custom_daily_trimp=custom_daily_trimp,
        )
        sim = forward_simulate(
            baseline_fitness,
            baseline_fatigue,
            trimps,
            today_day,
            Config.Model.Banister.ALPHA_FITNESS,
            Config.Model.Banister.ALPHA_FATIGUE,
        )
        daily_rows = [
            {
                "date": row.date,
                "projected_daily_trimp": float(trimps[index]),
                "projected_fitness": row.fitness,
                "projected_fatigue": row.fatigue,
                "projected_form": row.form,
            }
            for index, row in enumerate(sim)
        ]
        metadata: dict[str, object] = {"missing_reasons": []}
        if target_day.weekday() in {4, 5, 6}:
            monday = target_day + timedelta(days=(7 - target_day.weekday()))
            monday_sim = forward_simulate(
                baseline_fitness,
                baseline_fatigue,
                trimps + [0.0] * (monday - target_day).days,
                today_day,
                Config.Model.Banister.ALPHA_FITNESS,
                Config.Model.Banister.ALPHA_FATIGUE,
            )
            metadata["post_weekend_monday_form"] = monday_sim[-1].form if monday_sim else None
        else:
            metadata["missing_reasons"] = ["target_not_weekend_context"]
        scenario_payload[scenario] = {
            "daily_rows": daily_rows,
            "target_date_form": daily_rows[-1]["projected_form"] if daily_rows else None,
            "model_assumptions": assumptions,
            "activity_template_trimp": assumptions.get("activity_template_trimp"),
            "post_weekend_monday_form": metadata.get("post_weekend_monday_form"),
            "scenario_metadata": metadata,
        }

    completeness = CompletenessMetadata(
        status=_status_from_read_model(read_model, has_data=bool(scenario_payload), missing=missing),
        missing=missing,
        coverage={"scenarios": scenarios, "horizon_days": horizon_days, "read_model": read_model},
    )
    return ServiceEnvelope(
        data={"target_date": target_date, "scenarios": scenario_payload},
        freshness=freshness,
        completeness=completeness,
        warnings=[],
        rationale=_rationale("Projection contains bounded model simulation from materialized baseline facts."),
    )
