"""Activity fact construction for read-model materialization."""

from __future__ import annotations

import json
from typing import Any, cast

from mcp_strava.adapters.duckdb.activity_lookup_queries import activity_by_id, activity_materialization_sources
from mcp_strava.adapters.duckdb.read_model_materializer_utils import _HR_REST_MISSING_MSG, _json_list
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.duckdb.stream_metric_queries import (
    activity_cc,
    activity_hr_range,
    activity_median_heartrate,
    activity_stream_scalars_for_materialization,
    activity_trimp,
    activity_zone_trimp_for_bounds,
    max_heartrate_to_date,
    max_heartrate_to_dates,
    stream_altitude_rows,
    stream_altitude_rows_for_activities,
    stream_counts_for_activity,
    stream_hr_velocity_simple_rows,
    stream_hr_velocity_simple_rows_for_activities,
    stream_hr_velocity_time_rows,
    stream_hr_velocity_time_rows_for_activities,
    zone_seconds_for_activity,
)
from mcp_strava.constants import Config
from mcp_strava.hr_zones import get_zone_model
from mcp_strava.metrics import (
    calc_cardiac_drift,
    calc_hr_recovery,
    calc_hrr_pct,
    calc_vertical_speed,
    parse_local_hhmm,
)
from mcp_strava.settings import Settings


def _adjusted_cardiac_cost(cc: float | None, distance_m: float | None, elevation_m: float | None) -> float | None:
    if cc is None or not distance_m or distance_m <= 0:
        return None
    elevation_per_km = float(elevation_m or 0.0) / (float(distance_m) / 1000.0)
    return round(float(cc) - Config.Efficiency.CC_ELEV_COEFF * elevation_per_km, 3)


def _detail_calories(detail_json: str | None) -> float | None:
    """Pull Strava's `calories` (kcal) out of a DetailedActivity JSON blob."""
    if not detail_json:
        return None
    try:
        parsed = cast("object", json.loads(detail_json))
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    value: object = parsed.get("calories")
    if value is None or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _start_time_local(summary_json: str | None) -> str | None:
    """Materialize the local time-of-day (HH:MM) the activity started."""
    if not summary_json:
        return None
    try:
        parsed = cast("object", json.loads(summary_json))
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    start_date_local: object = parsed.get("start_date_local")
    if start_date_local is not None and not isinstance(start_date_local, str):
        return None
    return parse_local_hhmm(start_date_local)


def _activity_fact(
    repo: DuckDBRepository,
    dirty_row,
    metric_version: int,
    computed_at: str,
    settings: Settings,
) -> dict[str, Any]:
    activity_id = int(dirty_row["activity_id"])
    activity = activity_by_id(repo, activity_id)
    if activity is None:
        raise RuntimeError(f"Dirty activity missing source row: {activity_id}")
    source = repo.source_state_for_activity(activity_id)
    if source is None:
        raise RuntimeError(f"Dirty activity missing source state: {activity_id}")

    stream_count, hr_count = stream_counts_for_activity(repo, activity_id)

    # Validate hr_rest before any zone computation.
    athlete = settings.athlete
    if athlete.hr_rest is None:
        raise RuntimeError(_HR_REST_MISSING_MSG)

    # Running max-HR-to-date for this activity's day.
    activity_day = str(dirty_row["activity_day"])
    hr_max_observed = max_heartrate_to_date(repo, activity_day)

    # When no HR samples exist at all (for any activity up to this date),
    # zones are all zero and TRIMP is 0. No fallback max is fabricated.
    if hr_max_observed is None or hr_count == 0:
        zone1 = zone2 = zone3 = zone4 = zone5 = 0
        trimp_val = 0.0
        hr_max_used = None
        bounds = None
    else:
        bounds = get_zone_model(athlete.hr_zone_model).zone_bounds(hr_max=int(hr_max_observed), hr_rest=athlete.hr_rest)
        zone1, zone2, zone3, zone4, zone5 = zone_seconds_for_activity(repo, activity_id, bounds)
        trimp_val = activity_trimp(repo, activity_id, bounds=bounds)
        hr_max_used = int(hr_max_observed)

    min_hr, max_hr = activity_hr_range(repo, activity_id)
    cc = activity_cc(repo, activity_id, Config.Thresholds.VEL_MOVING)

    # ── Pure metric computation (wires the 14 previously-default columns) ──
    hr_rows = stream_hr_velocity_time_rows(repo, activity_id)
    alt_rows = stream_altitude_rows(repo, activity_id)
    drift_rows = stream_hr_velocity_simple_rows(repo, activity_id, Config.Thresholds.VEL_MOVING)
    median_hr = activity_median_heartrate(repo, activity_id)

    hr_rec = calc_hr_recovery(hr_rows)
    vspeed = calc_vertical_speed(alt_rows)
    drift = calc_cardiac_drift(drift_rows, activity.sport_type)
    # %HRR uses this activity's own observed max so the numerator (per-activity
    # median) and denominator share the same activity scope. Using the running
    # cross-activity max (hr_max_observed) against a single-activity median would
    # understate %HRR for an easy effort that follows a hard peak day. Fall back
    # to the running max only when this activity has no HR samples (WR-03).
    hr_max_for_hrr = max_hr if max_hr is not None else hr_max_observed
    hrr = calc_hrr_pct(median_hr, athlete.hr_rest, hr_max_for_hrr)

    missing: list[str] = []
    if activity.detail_json is None:
        missing.append("missing_details")
    if stream_count == 0:
        missing.append("missing_streams")
    if hr_count == 0:
        missing.append("missing_hr")
    completeness = "complete"
    if "missing_streams" in missing:
        completeness = "unknown"
    elif missing:
        completeness = "partial"

    return {
        "activity_id": activity_id,
        "activity_day": dirty_row["activity_day"],
        "sport_type": activity.sport_type,
        "source_hash": source["source_hash"],
        "source_revision": int(source["source_revision"]),
        "metric_version": metric_version,
        "computed_at": computed_at,
        "completeness_status": completeness,
        "missing_reasons_json": _json_list(missing),
        "trimp": trimp_val,
        "zone1_seconds": zone1,
        "zone2_seconds": zone2,
        "zone3_seconds": zone3,
        "zone4_seconds": zone4,
        "zone5_seconds": zone5,
        "hr_recovery_pause_count": hr_rec.pauses_found if hr_rec else 0,
        "hr_recovery_total_rest_sec": hr_rec.total_rest_sec if hr_rec else 0,
        "hr_recovery_median_rate": hr_rec.median_rate if hr_rec else None,
        "hr_recovery_best_rate": hr_rec.best_rate if hr_rec else None,
        "hr_recovery_worst_rate": hr_rec.worst_rate if hr_rec else None,
        "hr_recovery_avg_rate": hr_rec.avg_rate if hr_rec else None,
        "vertical_speed_vmh": vspeed.vmh if vspeed else None,
        "vertical_speed_total_ascent_m": vspeed.total_ascent_m if vspeed else None,
        "vertical_speed_duration_hours": vspeed.duration_hours if vspeed else None,
        "cardiac_cost": cc,
        "adjusted_cardiac_cost": _adjusted_cardiac_cost(cc, activity.distance, activity.total_elevation_gain),
        "cardiac_drift_pct": drift.drift_pct if drift else None,
        "cardiac_drift_severity": drift.severity if drift else None,
        "cardiac_drift_significant": bool(drift and drift.is_significant),
        "cardiac_drift_quality": drift.quality if drift else None,
        "hrr_pct": hrr,
        "anomaly_count": 0,
        "distance_m": activity.distance,
        "calories_kcal": _detail_calories(activity.detail_json),
        "moving_time_s": activity.moving_time,
        "elapsed_time_s": activity.elapsed_time,
        "elevation_gain_m": activity.total_elevation_gain,
        "heartrate_sample_count": hr_count,
        "stream_sample_count": stream_count,
        "observed_min_hr": min_hr,
        "observed_max_hr": max_hr,
        "hr_zone_model": athlete.hr_zone_model,
        "hr_max_used": hr_max_used,
        "hr_rest_used": athlete.hr_rest,
        # Local time-of-day (HH:MM) parsed from summary_json.start_date_local via
        # the shared pure helper. NULL until the row is (re)materialised.
        "start_time_local": _start_time_local(activity.summary_json),
    }


def _build_zone_bounds_maps(
    dirty_rows,
    scalars,
    hr_max_by_day,
    athlete,
) -> tuple[dict[int, list[int]], dict[int, int | None]]:
    """Pre-compute HR zone bounds and hr_max_used for each activity in the batch."""
    bounds_by_activity_id: dict[int, list[int]] = {}
    hr_max_used_by_activity_id: dict[int, int | None] = {}
    for dirty_row in dirty_rows:
        activity_id = int(dirty_row["activity_id"])
        activity_day = str(dirty_row["activity_day"])
        scalar = scalars[activity_id]
        hr_max_observed = hr_max_by_day.get(activity_day)
        if hr_max_observed is None or scalar.hr_count == 0:
            hr_max_used_by_activity_id[activity_id] = None
            continue
        bounds = get_zone_model(athlete.hr_zone_model).zone_bounds(hr_max=int(hr_max_observed), hr_rest=athlete.hr_rest)
        bounds_by_activity_id[activity_id] = bounds
        hr_max_used_by_activity_id[activity_id] = int(hr_max_observed)
    return bounds_by_activity_id, hr_max_used_by_activity_id


def _unpack_zone_trimp(zones) -> tuple[int, int, int, int, int, float]:
    """Return (zone1..5 seconds, trimp) — zeros when no zone data available."""
    if zones is None:
        return 0, 0, 0, 0, 0, 0.0
    return (
        zones.zone1_seconds,
        zones.zone2_seconds,
        zones.zone3_seconds,
        zones.zone4_seconds,
        zones.zone5_seconds,
        zones.trimp,
    )


def _completeness_status(activity, scalar) -> tuple[str, list[str]]:
    """Derive completeness label and missing-reason list from activity + scalar."""
    missing: list[str] = []
    if activity.detail_json is None:
        missing.append("missing_details")
    if scalar.stream_count == 0:
        missing.append("missing_streams")
    if scalar.hr_count == 0:
        missing.append("missing_hr")
    if "missing_streams" in missing:
        return "unknown", missing
    if missing:
        return "partial", missing
    return "complete", missing


def _activity_facts_batched(
    repo: DuckDBRepository,
    dirty_rows,
    metric_version: int,
    computed_at: str,
    settings: Settings,
    renew_lease=None,
) -> list[dict[str, Any]]:
    if not dirty_rows:
        return []

    athlete = settings.athlete
    if athlete.hr_rest is None:
        raise RuntimeError(_HR_REST_MISSING_MSG)

    activity_ids = [int(row["activity_id"]) for row in dirty_rows]
    sources = activity_materialization_sources(repo, activity_ids)
    scalars = activity_stream_scalars_for_materialization(repo, activity_ids, Config.Thresholds.VEL_MOVING)
    hr_max_by_day = max_heartrate_to_dates(repo, (str(row["activity_day"]) for row in dirty_rows))

    bounds_by_activity_id, hr_max_used_by_activity_id = _build_zone_bounds_maps(
        dirty_rows, scalars, hr_max_by_day, athlete
    )
    zone_trimp_by_activity_id = activity_zone_trimp_for_bounds(repo, bounds_by_activity_id)
    hr_rows_by_activity_id = stream_hr_velocity_time_rows_for_activities(repo, activity_ids)
    alt_rows_by_activity_id = stream_altitude_rows_for_activities(repo, activity_ids)
    drift_rows_by_activity_id = stream_hr_velocity_simple_rows_for_activities(
        repo, activity_ids, Config.Thresholds.VEL_MOVING
    )

    fact_rows: list[dict[str, Any]] = []
    for dirty_row in dirty_rows:
        activity_id = int(dirty_row["activity_id"])
        source = sources.get(activity_id)
        if source is None:
            raise RuntimeError(f"Dirty activity missing source row: {activity_id}")

        activity = source.activity
        scalar = scalars[activity_id]
        zone1, zone2, zone3, zone4, zone5, trimp_val = _unpack_zone_trimp(zone_trimp_by_activity_id.get(activity_id))

        hr_rec = calc_hr_recovery(hr_rows_by_activity_id.get(activity_id, []))
        vspeed = calc_vertical_speed(alt_rows_by_activity_id.get(activity_id, []))
        drift = calc_cardiac_drift(drift_rows_by_activity_id.get(activity_id, []), activity.sport_type)
        hr_max_observed = hr_max_by_day.get(str(dirty_row["activity_day"]))
        hr_max_for_hrr = scalar.max_hr if scalar.max_hr is not None else hr_max_observed
        hrr = calc_hrr_pct(scalar.median_hr, athlete.hr_rest, hr_max_for_hrr)
        completeness, missing = _completeness_status(activity, scalar)

        fact_rows.append(
            {
                "activity_id": activity_id,
                "activity_day": dirty_row["activity_day"],
                "sport_type": activity.sport_type,
                "source_hash": source.source_hash,
                "source_revision": source.source_revision,
                "metric_version": metric_version,
                "computed_at": computed_at,
                "completeness_status": completeness,
                "missing_reasons_json": _json_list(missing),
                "trimp": trimp_val,
                "zone1_seconds": zone1,
                "zone2_seconds": zone2,
                "zone3_seconds": zone3,
                "zone4_seconds": zone4,
                "zone5_seconds": zone5,
                "hr_recovery_pause_count": hr_rec.pauses_found if hr_rec else 0,
                "hr_recovery_total_rest_sec": hr_rec.total_rest_sec if hr_rec else 0,
                "hr_recovery_median_rate": hr_rec.median_rate if hr_rec else None,
                "hr_recovery_best_rate": hr_rec.best_rate if hr_rec else None,
                "hr_recovery_worst_rate": hr_rec.worst_rate if hr_rec else None,
                "hr_recovery_avg_rate": hr_rec.avg_rate if hr_rec else None,
                "vertical_speed_vmh": vspeed.vmh if vspeed else None,
                "vertical_speed_total_ascent_m": vspeed.total_ascent_m if vspeed else None,
                "vertical_speed_duration_hours": vspeed.duration_hours if vspeed else None,
                "cardiac_cost": scalar.cardiac_cost,
                "adjusted_cardiac_cost": _adjusted_cardiac_cost(
                    scalar.cardiac_cost, activity.distance, activity.total_elevation_gain
                ),
                "cardiac_drift_pct": drift.drift_pct if drift else None,
                "cardiac_drift_severity": drift.severity if drift else None,
                "cardiac_drift_significant": bool(drift and drift.is_significant),
                "cardiac_drift_quality": drift.quality if drift else None,
                "hrr_pct": hrr,
                "anomaly_count": 0,
                "distance_m": activity.distance,
                "calories_kcal": _detail_calories(activity.detail_json),
                "moving_time_s": activity.moving_time,
                "elapsed_time_s": activity.elapsed_time,
                "elevation_gain_m": activity.total_elevation_gain,
                "heartrate_sample_count": scalar.hr_count,
                "stream_sample_count": scalar.stream_count,
                "observed_min_hr": scalar.min_hr,
                "observed_max_hr": scalar.max_hr,
                "hr_zone_model": athlete.hr_zone_model,
                "hr_max_used": hr_max_used_by_activity_id.get(activity_id),
                "hr_rest_used": athlete.hr_rest,
                "start_time_local": _start_time_local(activity.summary_json),
            }
        )
        if renew_lease is not None:
            renew_lease()
    return fact_rows
