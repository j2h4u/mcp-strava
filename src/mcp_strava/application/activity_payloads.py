"""Activity payload assembly for workout-facing application services."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from mcp_strava.adapters.duckdb.repository_models import ActivityMetricFactRow

_HOURS_PER_DAY = 24

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


def parse_json_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    parsed: object = None
    try:
        parsed = cast("object", json.loads(str(value)))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def row_get(row: object, key: str, default: object = None) -> object:
    if row is None:
        return default
    # SIM118 suppressed: row is a polymorphic DuckDB Row | dict; explicit .keys()-membership
    # is the safe contract — `key in row` is not guaranteed key-membership on Row objects.
    if hasattr(row, "keys") and key in row.keys():  # type: ignore[union-attr]  # noqa: SIM118
        return row[key]  # type: ignore[index]
    if isinstance(row, dict):
        return row.get(key, default)
    return default


def json_object_from_row(row: object, key: str) -> dict[str, Any]:
    raw = row_get(row, key)
    if not raw:
        return {}
    result: object = None
    try:
        result = cast("object", json.loads(str(raw)))
    except json.JSONDecodeError:
        return {}
    return result if isinstance(result, dict) else {}  # type: ignore[return-value]


def summary_json(row: object) -> dict[str, Any]:
    return json_object_from_row(row, "summary_json")


def detail_json(row: object) -> dict[str, Any]:
    return json_object_from_row(row, "detail_json")


def kudos_count(summary: dict[str, Any]) -> int:
    raw: object = summary.get("kudos_count")
    try:
        return int(raw) if raw is not None else 0  # type: ignore[arg-type]
    except TypeError, ValueError:
        return 0


def kudos_names(rows: list[dict[str, object]]) -> list[str]:
    names: list[str] = []
    for row in rows:
        firstname = str(row_get(row, "firstname", "") or "").strip()
        lastname = str(row_get(row, "lastname", "") or "").strip()
        name = " ".join(part for part in (firstname, lastname) if part)
        if name:
            names.append(name)
    return names


def zone_minutes(row: ActivityMetricFactRow) -> list[float]:
    # zone*_seconds fields are ``object`` (nullable BIGINT); ``or 0`` collapses NULL.
    row_dict = cast("dict[str, object]", row)
    return [round(float(row_dict[f"zone{idx}_seconds"] or 0) / 60, 3) for idx in range(1, 6)]  # type: ignore[arg-type]


def activity_value(row: ActivityMetricFactRow, metric_id: str) -> object:
    if metric_id in {"avg_hr", "max_hr"}:
        summary = summary_json(row)
        summary_key = "average_heartrate" if metric_id == "avg_hr" else "max_heartrate"
        value = summary.get(summary_key)
        return round(float(value), 3) if value is not None else None  # type: ignore[arg-type]
    if metric_id == "time_in_hr_zones_min":
        return zone_minutes(row)
    if metric_id == "cardiac_drift_severity":
        return row["cardiac_drift_severity"]
    column, scale = ACTIVITY_SCALAR_FACTS.get(metric_id, (None, 1.0))
    if column is None:
        return None
    row_dict = cast("dict[str, object]", row)
    value: object = row_dict.get(column)
    if value is None:
        return None
    return round(float(value) * float(scale), 3)  # type: ignore[arg-type]


def gear_payload(row: ActivityMetricFactRow, summary: dict[str, Any]) -> dict[str, Any]:
    detail = detail_json(row)
    _gear_raw = detail.get("gear")
    gear: dict[str, Any] = _gear_raw if isinstance(_gear_raw, dict) else {}
    gear_id = summary.get("gear_id") or detail.get("gear_id") or gear.get("id")
    distance_m = gear.get("distance") or gear.get("converted_distance")
    try:
        gear_distance_km = round(float(distance_m) / 1000.0, 3) if distance_m is not None else None  # type: ignore[arg-type]
    except TypeError, ValueError:
        gear_distance_km = None
    primary = gear.get("primary")
    return {
        "gear_id": str(gear_id) if gear_id is not None else None,  # type: ignore[arg-type]
        "gear_name": gear.get("name") or gear.get("nickname"),
        "gear_distance_km": gear_distance_km,
        "gear_primary": bool(primary) if primary is not None else None,  # type: ignore[arg-type]
    }


def parse_start_dt(value: str | None) -> datetime | None:
    """Parse a Strava ISO datetime string to a datetime, or None."""
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError, TypeError:
        return None


def relative_time(start_date: str | None, now: datetime) -> str | None:
    """Human recency of an activity relative to `now`, computed at read time."""
    activity_dt = parse_start_dt(start_date)
    if activity_dt is None:
        return None
    if activity_dt.tzinfo is not None:
        activity_dt = activity_dt.astimezone(UTC).replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.astimezone(UTC).replace(tzinfo=None)
    total_minutes = int((now - activity_dt).total_seconds() // 60)
    if total_minutes < 0:
        total_minutes = 0
    hours, minutes = divmod(total_minutes, 60)
    if hours < _HOURS_PER_DAY:
        return f"{hours}h {minutes}m"
    days, rem_hours = divmod(hours, _HOURS_PER_DAY)
    return f"{days}d {rem_hours}h"


def fact_status(row: ActivityMetricFactRow) -> dict[str, Any]:
    missing = parse_json_list(row["missing_reasons_json"])
    return {
        "status": str(row["completeness_status"]),
        "missing": missing,
        "source_revision": int(row["source_revision"]),  # type: ignore[arg-type]
        "metric_version": int(row["metric_version"]),  # type: ignore[arg-type]
        "materialized_at": row["computed_at"],
    }


def activity_payload(
    row: ActivityMetricFactRow,
    *,
    now: datetime,
    kudos_names: list[str] | None = None,
    include_detail_context: bool = False,
) -> dict[str, Any]:
    summary = summary_json(row)
    # start_time_local is a materialized fact column (HH:MM), parsed once at
    # materialization from summary.start_date_local via metrics.parse_local_hhmm.
    # A NULL here means the source had no parseable local start — surfaced as-is,
    # never re-derived at read time (the fingerprint recompute keeps it current).
    start_time_local = row_get(row, "start_time_local")
    payload = {
        "activity_id": int(row["activity_id"]),  # type: ignore[arg-type]
        "activity_date": row["activity_day"],
        "sport_type": row["sport_type"],
        "activity_name": row["activity_name"],
        "distance_km": activity_value(row, "distance_km"),
        "moving_time_min": activity_value(row, "moving_time_min"),
        "elapsed_time_min": activity_value(row, "elapsed_time_min"),
        "elevation_m": activity_value(row, "elevation_m"),
        "trimp": activity_value(row, "trimp"),
        "avg_hr": summary.get("average_heartrate"),
        "max_hr": round(summary["max_heartrate"]) if summary.get("max_heartrate") else None,  # type: ignore[arg-type]
        "time_in_hr_zones_min": zone_minutes(row),
        "hr_recovery_pauses": int(row["hr_recovery_pause_count"] or 0),  # type: ignore[arg-type]
        "hr_recovery_total_rest_sec": int(row["hr_recovery_total_rest_sec"] or 0),  # type: ignore[arg-type]
        "hr_recovery_median_bpm_per_min": activity_value(row, "hr_recovery_median_bpm_per_min"),
        "hr_recovery_best_bpm_per_min": activity_value(row, "hr_recovery_best_bpm_per_min"),
        "hr_recovery_worst_bpm_per_min": activity_value(row, "hr_recovery_worst_bpm_per_min"),
        "hr_recovery_avg_bpm_per_min": activity_value(row, "hr_recovery_avg_bpm_per_min"),
        "vertical_speed_m_per_h": activity_value(row, "vertical_speed_m_per_h"),
        "vertical_ascent_m": activity_value(row, "vertical_ascent_m"),
        "vertical_duration_h": activity_value(row, "vertical_duration_h"),
        "cardiac_cost": activity_value(row, "cardiac_cost"),
        "cardiac_cost_adjusted": activity_value(row, "cardiac_cost_adjusted"),
        "cardiac_drift_pct": activity_value(row, "cardiac_drift_pct"),
        "cardiac_drift_severity": row["cardiac_drift_severity"],
        "cardiac_drift_significant": int(row["cardiac_drift_significant"] or 0),  # type: ignore[arg-type]
        "cardiac_drift_quality": row["cardiac_drift_quality"],
        "hrr_pct": activity_value(row, "hrr_pct"),
        "start_time_local": start_time_local,
        "relative_time": relative_time(summary.get("start_date"), now),
        "hr_anomaly_count": int(row["anomaly_count"] or 0),  # type: ignore[arg-type]
        "kudos_count": kudos_count(summary),
        "completeness": fact_status(row),
    }
    if include_detail_context:
        payload.update(gear_payload(row, summary))
    if kudos_names is not None:
        payload["kudos_names"] = kudos_names
    return payload
