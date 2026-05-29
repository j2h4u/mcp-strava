"""Metric-focused application services for MCP-facing tool backends."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import date, datetime, timedelta

from mcp_strava.adapters.duckdb.repository import CURRENT_METRIC_VERSION
from mcp_strava.application.aggregate_services import (
    AggregateServiceRequest,
    get_training_aggregates_service,
)
from mcp_strava.application.freshness import build_freshness_metadata
from mcp_strava.application.metric_registry import METRIC_REGISTRY
from mcp_strava.constants import Config
from mcp_strava.db import ReadConn, repository_from_connection
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
    "missing_denominator",
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
    return nullcontext(connection) if connection is not None else ReadConn()


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


def _json_object_from_row(row, key: str) -> dict[str, object]:
    raw = _row_get(row, key)
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _summary_json(row) -> dict[str, object]:
    return _json_object_from_row(row, "summary_json")


def _detail_json(row) -> dict[str, object]:
    return _json_object_from_row(row, "detail_json")


def _kudos_count(summary: dict[str, object]) -> int:
    value = summary.get("kudos_count")
    try:
        return int(value) if value is not None else 0
    except TypeError, ValueError:
        return 0


def _kudos_names(rows) -> list[str]:
    names: list[str] = []
    for row in rows:
        firstname = str(_row_get(row, "firstname", "") or "").strip()
        lastname = str(_row_get(row, "lastname", "") or "").strip()
        name = " ".join(part for part in (firstname, lastname) if part)
        if name:
            names.append(name)
    return names


def _next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def _read_model_status(repo) -> dict[str, object]:
    return repo.read_model_status(metric_version=CURRENT_METRIC_VERSION)


def _coverage_with_read_model(
    read_model: dict[str, object], extra: dict[str, object] | None = None
) -> dict[str, object]:
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
    return [round(float(row[f"zone{idx}_seconds"] or 0) / 60, 3) for idx in range(1, 6)]


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


def _gear_payload(row, summary: dict[str, object]) -> dict[str, object]:
    detail = _detail_json(row)
    gear = detail.get("gear") if isinstance(detail.get("gear"), dict) else {}
    gear_id = summary.get("gear_id") or detail.get("gear_id") or gear.get("id")
    distance_m = gear.get("distance") or gear.get("converted_distance")
    try:
        gear_distance_km = round(float(distance_m) / 1000.0, 3) if distance_m is not None else None
    except TypeError, ValueError:
        gear_distance_km = None
    primary = gear.get("primary")
    return {
        "gear_id": str(gear_id) if gear_id is not None else None,
        "gear_name": gear.get("name") or gear.get("nickname"),
        "gear_distance_km": gear_distance_km,
        "gear_primary": bool(primary) if primary is not None else None,
    }


def _activity_payload(
    row,
    *,
    kudos_names: list[str] | None = None,
    include_detail_context: bool = False,
) -> dict[str, object]:
    summary = _summary_json(row)
    payload = {
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
        "kudos_count": _kudos_count(summary),
        "completeness": _fact_status(row),
    }
    if include_detail_context:
        payload.update(_gear_payload(row, summary))
    if kudos_names is not None:
        payload["kudos_names"] = kudos_names
    return payload


def _latest_as_of_day(checked_at: datetime) -> str:
    return checked_at.date().isoformat()


def _rolling_by_window(repo, as_of_day: str) -> dict[int, object]:
    windows = (7, 14, 28, 90)
    batch_fetch = getattr(repo, "fetch_rolling_period_facts_by_windows", None)
    if batch_fetch is not None:
        return batch_fetch(
            as_of_day,
            windows,
            scope="all",
            metric_version=CURRENT_METRIC_VERSION,
        )
    return {
        window: repo.fetch_rolling_period_facts(
            as_of_day,
            window,
            scope="all",
            metric_version=CURRENT_METRIC_VERSION,
        )
        for window in windows
    }


def get_fitness_state_service(
    *,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    checked_at = now or datetime.now()
    with _connection_context(connection) as conn:
        repo = repository_from_connection(conn)
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
        repo = repository_from_connection(conn)
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
                {
                    "count": len(data),
                    "limit": limit,
                    "filters": {"start_date": start_date, "end_date": end_date, "sport": sport},
                },
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
                "kudos_count",
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
        repo = repository_from_connection(conn)
        freshness = build_freshness_metadata(repo, checked_at, _policy(), signal_first_use=signal_first_use)
        read_model = _read_model_status(repo)
        resolved_id = repo.latest_activity_id() if activity_id == "latest" else int(activity_id)
        row = (
            repo.fetch_activity_metric_fact(resolved_id, metric_version=CURRENT_METRIC_VERSION)
            if resolved_id is not None
            else None
        )

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
                warnings=[
                    ServiceWarning(
                        code="workout_not_found", severity="warning", message="Requested workout was not found."
                    )
                ],
                rationale=_rationale("Workout detail requested from materialized activity facts."),
            )

        data = _activity_payload(
            row,
            kudos_names=_kudos_names(repo.kudos_for_activity(resolved_id)),
            include_detail_context=True,
        )
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


def _aggregate_rows(envelope: ServiceEnvelope) -> list[dict[str, object]]:
    data = envelope.data if isinstance(envelope.data, dict) else {}
    rows = data.get("rows", [])
    return [row for row in rows if isinstance(row, dict)]


def _compare_row_key(row: dict[str, object]) -> tuple[str, str | None, str]:
    scope = str(row.get("scope") or "global")
    metric_id = str(row["metric_id"])
    if scope == "per_sport":
        return scope, str(row.get("sport_type") or "unknown"), metric_id
    return "global", None, metric_id


def _compare_rows_by_key(rows: list[dict[str, object]]) -> dict[tuple[str, str | None, str], dict[str, object]]:
    return {_compare_row_key(row): row for row in rows}


def _row_missing_reasons(row: dict[str, object] | None) -> list[str]:
    if row is None:
        return ["no_activity_in_period"]
    reasons = row.get("missing_reasons") or []
    return [str(reason) for reason in reasons if reason]


def _row_sample_size(row: dict[str, object] | None) -> int:
    if row is None:
        return 0
    return int(row.get("sample_size") or 0)


def _row_activity_count(row: dict[str, object] | None) -> int:
    if row is None:
        return 0
    return int(row.get("activity_count") or 0)


def _coverage_value(row: dict[str, object] | None) -> float:
    if row is None or str(row.get("completeness_status")) == "unavailable":
        return 0.0
    if str(row.get("completeness_status")) == "partial":
        return 0.5
    return 1.0


def _period_record(row: dict[str, object] | None) -> dict[str, object]:
    payload: dict[str, object] = {
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


def _metric_version_status(row_a: dict[str, object] | None, row_b: dict[str, object] | None) -> str:
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
    row_a: dict[str, object] | None,
    row_b: dict[str, object] | None,
) -> tuple[dict[str, float], dict[str, float | None], float | None]:
    buckets_a = row_a.get("distribution") if row_a is not None and isinstance(row_a.get("distribution"), dict) else {}
    buckets_b = row_b.get("distribution") if row_b is not None and isinstance(row_b.get("distribution"), dict) else {}
    keys = sorted(set(buckets_a) | set(buckets_b))
    deltas: dict[str, float] = {}
    delta_pct: dict[str, float | None] = {}
    for key in keys:
        a_value = float(buckets_a.get(key) or 0.0)
        b_value = float(buckets_b.get(key) or 0.0)
        delta = round(a_value - b_value, 3)
        deltas[key] = delta
        delta_pct[key] = round((delta / b_value) * 100, 2) if b_value else None
    total_a = sum(float(value or 0.0) for value in buckets_a.values())
    total_b = sum(float(value or 0.0) for value in buckets_b.values())
    overlap = None
    if total_a > 0 and total_b > 0:
        overlap = round(
            (
                sum(min(float(buckets_a.get(key) or 0.0), float(buckets_b.get(key) or 0.0)) for key in keys)
                / max(total_a, total_b)
            )
            * 100,
            2,
        )
    return deltas, delta_pct, overlap


def _compare_aggregate_pair(row_a: dict[str, object] | None, row_b: dict[str, object] | None) -> dict[str, object]:
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
    delta = round(float(value_a) - float(value_b), 3) if _is_number(value_a) and _is_number(value_b) else None
    delta_pct = (
        round((delta / float(value_b)) * 100, 2)
        if _is_number(delta) and _is_number(value_b) and float(value_b) != 0
        else None
    )
    trend = "unavailable"
    if _is_number(delta):
        trend = "flat" if abs(float(delta)) < 1e-9 else ("up" if float(delta) > 0 else "down")
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
    checked_at = now or datetime.now()
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
    per_sport_section: dict[str, dict[str, object]] = {}
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
    read_model = period_a_envelope.completeness.coverage.get("read_model", {})
    period_b_read_model = period_b_envelope.completeness.coverage.get("read_model", {})
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
        return [easy_value for _ in days], {
            "template_source": "config_plan_constants",
            "activity_template_trimp": easy_value,
        }
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


def _daily_trimp_history(repo, start_day: str, end_day: str) -> dict[str, float]:
    rows = repo.fetch_daily_load_facts(
        start_day, _next_day(end_day), scope="all", metric_version=CURRENT_METRIC_VERSION
    )
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
        repo = repository_from_connection(conn)
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
