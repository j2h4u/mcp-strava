"""Offline materialization for DuckDB read-model facts."""

import json
import logging
import time
from datetime import UTC, date, datetime, timedelta
from statistics import median
from typing import Any, cast

from mcp_strava.adapters.duckdb.activity_lookup_queries import activity_by_id, activity_materialization_sources
from mcp_strava.adapters.duckdb.daily_load_queries import daily_load_points_between
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.constants import Config
from mcp_strava.hr_zones import get_zone_model
from mcp_strava.metric_registry import MATERIALIZED_ROLLING_WINDOW_DAYS
from mcp_strava.metrics import (
    calc_cardiac_drift,
    calc_hr_recovery,
    calc_hrr_pct,
    calc_vertical_speed,
    parse_local_hhmm,
)
from mcp_strava.settings import Settings, get_settings
from mcp_strava.training import acwr_zone, calc_banister_series, form_zone

ROLLING_WINDOWS = MATERIALIZED_ROLLING_WINDOW_DAYS

logger = logging.getLogger(__name__)


def _now_parts(now: str | datetime | None) -> tuple[str, str]:
    if now is None:
        # Instant + calendar source: UTC-naive, matching the WR-02 freshness basis.
        dt = datetime.now(UTC).replace(tzinfo=None)
    elif isinstance(now, str):
        dt = datetime.fromisoformat(now)
    else:
        dt = now
    return dt.isoformat(timespec="seconds"), dt.date().isoformat()


def _date_range(start_day: str, end_day: str) -> list[str]:
    current = date.fromisoformat(start_day)
    end = date.fromisoformat(end_day)
    days: list[str] = []
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _json_list(values: list[str]) -> str:
    return json.dumps(sorted(set(values)), ensure_ascii=True)


def _adjusted_cardiac_cost(cc: float | None, distance_m: float | None, elevation_m: float | None) -> float | None:
    if cc is None or not distance_m or distance_m <= 0:
        return None
    elevation_per_km = float(elevation_m or 0.0) / (float(distance_m) / 1000.0)
    return round(float(cc) - Config.Efficiency.CC_ELEV_COEFF * elevation_per_km, 3)


def _median_or_none(values: list[float | None]) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return round(float(median(numeric)), 3) if numeric else None


_HR_REST_MISSING_MSG = (
    "MCP_STRAVA_HR_REST is not set — cannot compute HR zones. "
    "Set MCP_STRAVA_HR_REST to the athlete's resting heart rate."
)


def _detail_calories(detail_json: str | None) -> float | None:
    """Pull Strava's `calories` (kcal) out of a DetailedActivity JSON blob.

    Calories exist only in detail_json (DetailedActivity), never in the summary
    or an activities column, so the materializer extracts them here. Returns None
    when details are absent or the field is missing/non-numeric. Feeds the
    activity_metric_facts.calories_kcal column -> the `calories` aggregate metric.
    """
    if not detail_json:
        return None
    try:
        parsed = cast("object", json.loads(detail_json))
    except ValueError, TypeError:
        return None
    if not isinstance(parsed, dict):
        return None
    value: object = parsed.get("calories")
    if value is None or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError, TypeError:
        return None


def _start_time_local(summary_json: str | None) -> str | None:
    """Materialize the local time-of-day (HH:MM) the activity started.

    Pulls start_date_local out of the activity summary_json and delegates the
    parse/format to the pure-domain metrics.parse_local_hhmm (fromisoformat +
    strftime, Z/offset-normalizing, None-safe) — the SAME helper the read-time
    payload uses, so the materialized column and any read-time fallback never
    diverge. Returns None when summary_json is absent/garbage or has no
    start_date_local. Feeds activity_metric_facts.start_time_local -> the
    `start_time_local` metric on the workout payload.
    """
    if not summary_json:
        return None
    try:
        parsed = cast("object", json.loads(summary_json))
    except ValueError, TypeError:
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

    stream_count, hr_count = repo.stream_counts_for_activity(activity_id)

    # Validate hr_rest before any zone computation.
    athlete = settings.athlete
    if athlete.hr_rest is None:
        raise RuntimeError(_HR_REST_MISSING_MSG)

    # Running max-HR-to-date for this activity's day.
    activity_day = str(dirty_row["activity_day"])
    hr_max_observed = repo.max_heartrate_to_date(activity_day)

    # When no HR samples exist at all (for any activity up to this date),
    # zones are all zero and TRIMP is 0. No fallback max is fabricated.
    if hr_max_observed is None or hr_count == 0:
        zone1 = zone2 = zone3 = zone4 = zone5 = 0
        trimp_val = 0.0
        hr_max_used = None
        bounds = None
    else:
        bounds = get_zone_model(athlete.hr_zone_model).zone_bounds(hr_max=int(hr_max_observed), hr_rest=athlete.hr_rest)
        zone1, zone2, zone3, zone4, zone5 = repo.zone_seconds_for_activity(activity_id, bounds)
        trimp_val = repo.activity_trimp(activity_id, bounds=bounds)
        hr_max_used = int(hr_max_observed)

    min_hr, max_hr = repo.activity_hr_range(activity_id)
    cc = repo.activity_cc(activity_id, Config.Thresholds.VEL_MOVING)

    # ── Pure metric computation (wires the 14 previously-default columns) ──
    hr_rows = repo.stream_hr_velocity_time_rows(activity_id)
    alt_rows = repo.stream_altitude_rows(activity_id)
    drift_rows = repo.stream_hr_velocity_simple_rows(activity_id, Config.Thresholds.VEL_MOVING)
    median_hr = repo.activity_median_heartrate(activity_id)

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
        "cardiac_drift_significant": 1 if (drift and drift.is_significant) else 0,
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
    scalars = repo.activity_stream_scalars_for_materialization(activity_ids, Config.Thresholds.VEL_MOVING)
    hr_max_by_day = repo.max_heartrate_to_dates(str(row["activity_day"]) for row in dirty_rows)

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

    zone_trimp_by_activity_id = repo.activity_zone_trimp_for_bounds(bounds_by_activity_id)
    hr_rows_by_activity_id = repo.stream_hr_velocity_time_rows_for_activities(activity_ids)
    alt_rows_by_activity_id = repo.stream_altitude_rows_for_activities(activity_ids)
    drift_rows_by_activity_id = repo.stream_hr_velocity_simple_rows_for_activities(
        activity_ids, Config.Thresholds.VEL_MOVING
    )

    fact_rows: list[dict[str, Any]] = []
    for dirty_row in dirty_rows:
        activity_id = int(dirty_row["activity_id"])
        source = sources.get(activity_id)
        if source is None:
            raise RuntimeError(f"Dirty activity missing source row: {activity_id}")

        activity = source.activity
        scalar = scalars[activity_id]
        zones = zone_trimp_by_activity_id.get(activity_id)
        if zones is None:
            zone1 = zone2 = zone3 = zone4 = zone5 = 0
            trimp_val = 0.0
        else:
            zone1 = zones.zone1_seconds
            zone2 = zones.zone2_seconds
            zone3 = zones.zone3_seconds
            zone4 = zones.zone4_seconds
            zone5 = zones.zone5_seconds
            trimp_val = zones.trimp

        hr_rows = hr_rows_by_activity_id.get(activity_id, [])
        alt_rows = alt_rows_by_activity_id.get(activity_id, [])
        drift_rows = drift_rows_by_activity_id.get(activity_id, [])
        hr_rec = calc_hr_recovery(hr_rows)
        vspeed = calc_vertical_speed(alt_rows)
        drift = calc_cardiac_drift(drift_rows, activity.sport_type)
        hr_max_observed = hr_max_by_day.get(str(dirty_row["activity_day"]))
        hr_max_for_hrr = scalar.max_hr if scalar.max_hr is not None else hr_max_observed
        hrr = calc_hrr_pct(scalar.median_hr, athlete.hr_rest, hr_max_for_hrr)

        missing: list[str] = []
        if activity.detail_json is None:
            missing.append("missing_details")
        if scalar.stream_count == 0:
            missing.append("missing_streams")
        if scalar.hr_count == 0:
            missing.append("missing_hr")
        completeness = "complete"
        if "missing_streams" in missing:
            completeness = "unknown"
        elif missing:
            completeness = "partial"

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
                "cardiac_drift_significant": 1 if (drift and drift.is_significant) else 0,
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


# Per-day SUM shape for a day with no activity_metric_facts rows (REST/UNKNOWN/
# PARTIAL). Mirrors the all-NULL row the old no-GROUP-BY per-day query returned, so
# days absent from the batched GROUP BY read still produce a zeroed daily fact via the
# `sums[...] or 0` accessors below — byte-identical to the per-day-read behaviour.
_EMPTY_DAILY_SUMS: dict[str, Any] = {
    "distance_m": None,
    "moving_time_s": None,
    "elevation_gain_m": None,
    "zone4_seconds": None,
    "zone5_seconds": None,
    "anomaly_count": None,
}


def _daily_missing_reasons(status: str) -> list[str]:
    if status == "UNKNOWN":
        return ["missing_streams"]
    if status == "PARTIAL":
        return ["missing_hr"]
    return []


def _materialize_daily_facts(
    repo: DuckDBRepository,
    *,
    start_day: str,
    end_day: str,
    metric_version: int,
    computed_at: str,
    bounds: list[int],
) -> dict[str, float]:
    points = daily_load_points_between(repo, start_day, end_day, bounds=bounds)
    # One GROUP BY range read for the whole window, replacing the former per-day
    # daily_fact_sums() call inside this loop (the ~2000-read full-recompute lever).
    sums_by_day = repo.daily_fact_sums_between(start_day, end_day, metric_version)
    daily_trimp: dict[str, float] = {}
    fact_rows: list[dict[str, object]] = []
    for point in points:
        sums = sums_by_day.get(point.date, _EMPTY_DAILY_SUMS)
        missing = _daily_missing_reasons(point.status)
        fact_rows.append(
            {
                "day": point.date,
                "scope": "all",
                "sport_type": "all",
                "metric_version": metric_version,
                "computed_at": computed_at,
                "completeness_status": point.status.lower(),
                "missing_reasons_json": _json_list(missing),
                "activity_count": point.activity_count,
                "stream_point_count": point.stream_points,
                "heartrate_point_count": point.heartrate_points,
                "observed_trimp": point.observed_trimp,
                "effective_trimp": point.effective_trimp,
                "distance_m": float(sums["distance_m"] or 0.0),
                "moving_time_s": int(sums["moving_time_s"] or 0),
                "elevation_gain_m": float(sums["elevation_gain_m"] or 0.0),
                "zone4_seconds": int(sums["zone4_seconds"] or 0),
                "zone5_seconds": int(sums["zone5_seconds"] or 0),
                "high_zone_seconds": int((sums["zone4_seconds"] or 0) + (sums["zone5_seconds"] or 0)),
                "anomaly_count": int(sums["anomaly_count"] or 0),
            }
        )
        daily_trimp[point.date] = float(point.effective_trimp or 0.0)
    repo.upsert_daily_load_facts(fact_rows)
    return daily_trimp


def _materialize_model_facts(
    repo: DuckDBRepository,
    *,
    start_day: str,
    end_day: str,
    metric_version: int,
    computed_at: str,
    daily_trimp: dict[str, float],
) -> None:
    series = calc_banister_series(daily_trimp, end_date=end_day)
    wanted = set(_date_range(start_day, end_day))
    fact_rows: list[dict[str, object]] = []
    for point in series:
        if point["date"] not in wanted:
            continue
        trimp = float(point["trimp"])
        fitness = float(point["fitness"])
        fatigue = float(point["fatigue"])
        form = float(point["form"])
        acwr = round(fatigue / fitness, 3) if fitness > 0 else None
        fact_rows.append(
            {
                "day": point["date"],
                "scope": "all",
                "sport_type": "all",
                "metric_version": metric_version,
                "computed_at": computed_at,
                "completeness_status": "complete",
                "missing_reasons_json": "[]",
                "effective_trimp": trimp,
                "observed_trimp": trimp,
                "fitness": fitness,
                "fatigue": fatigue,
                "form": form,
                "form_zone": form_zone(form),
                "acwr_zone": acwr_zone(acwr),
                "acwr": acwr,
                "load_7d": fatigue,
                "load_28d": None,
                "load_42d": fitness,
                "input_days": len(daily_trimp),
                "missing_days": 0,
            }
        )
    repo.upsert_training_model_daily_facts(fact_rows)


def _materialize_rolling_facts(
    repo: DuckDBRepository,
    *,
    as_of_day: str,
    metric_version: int,
    computed_at: str,
) -> None:
    as_of = date.fromisoformat(as_of_day)
    fact_rows: list[dict[str, object]] = []
    model = repo.training_model_row(as_of_day, metric_version)
    for window in ROLLING_WINDOWS:
        start = (as_of - timedelta(days=window - 1)).isoformat()
        row = repo.rolling_load_aggregate(start, as_of_day, metric_version)
        metric_rows = repo.rolling_cardiac_metric_rows(start, as_of_day, metric_version)
        fact_rows.append(
            {
                "as_of_day": as_of_day,
                "window_days": window,
                "scope": "all",
                "sport_type": "all",
                "metric_version": metric_version,
                "computed_at": computed_at,
                "completeness_status": "complete",
                "missing_reasons_json": "[]",
                "activity_count": int(row["activity_count"] or 0),
                "active_days": int(row["active_days"] or 0),
                "rest_days": int(row["rest_days"] or 0),
                "observed_trimp": float(row["observed_trimp"] or 0.0),
                "effective_trimp": float(row["effective_trimp"] or 0.0),
                "distance_m": float(row["distance_m"] or 0.0),
                "moving_time_s": int(row["moving_time_s"] or 0),
                "elevation_gain_m": float(row["elevation_gain_m"] or 0.0),
                "high_zone_seconds": int(row["high_zone_seconds"] or 0),
                "anomaly_count": int(row["anomaly_count"] or 0),
                "fitness": model["fitness"] if model else None,
                "fatigue": model["fatigue"] if model else None,
                "form": model["form"] if model else None,
                "form_zone": model["form_zone"] if model else None,
                "acwr_zone": model["acwr_zone"] if model else None,
                "acwr": model["acwr"] if model else None,
                "median_cardiac_cost": _median_or_none([item["cardiac_cost"] for item in metric_rows]),
                "median_adjusted_cardiac_cost": _median_or_none(
                    [item["adjusted_cardiac_cost"] for item in metric_rows]
                ),
                "median_hr_recovery": _median_or_none([item["hr_recovery_median_rate"] for item in metric_rows]),
                "median_cardiac_drift_pct": _median_or_none([item["cardiac_drift_pct"] for item in metric_rows]),
            }
        )
    repo.upsert_rolling_period_facts(fact_rows)


def _record_failed_run(repo: DuckDBRepository, started_at: str, metric_version: int, error: Exception) -> None:
    try:
        repo.record_read_model_refresh_run(
            {
                "started_at": started_at,
                "finished_at": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
                "status": "failed",
                "metric_version": metric_version,
                "trigger_reason": "materialize_read_model",
                "activities_considered": 0,
                "activities_materialized": 0,
                "dirty_rows_claimed": 0,
                "dirty_rows_cleared": 0,
                "attempt_count": 1,
                "last_error": str(error),
            }
        )
        # WR-03: commit through the lock-aware repository helper, not a raw
        # repo.conn.commit(). record_read_model_refresh_run already writes via
        # _execute (which takes duckdb_process_lock()); _commit_if_standalone
        # finalizes that write under the same single-writer lock the rest of the
        # repository honors, so the failed-run bookkeeping cannot interleave with
        # another writer's transaction.
        repo._commit_if_standalone()
    except Exception as exc:
        logger.warning("read-model failed-run recording failed: %s", exc)
        repo.rollback()


def materialize_read_model(
    repo: DuckDBRepository,
    metric_version: int,
    now: str | datetime | None = None,
    limit: int | None = None,
    run_id: int | None = None,
    renew_lease=None,
    settings: Settings | None = None,
    trigger_reason: str = "materialize_read_model",
) -> dict[str, Any]:
    del run_id
    _settings = settings or get_settings()
    athlete = _settings.athlete
    if athlete.hr_rest is None:
        raise RuntimeError(_HR_REST_MISSING_MSG)
    computed_at, today = _now_parts(now)
    dirty_rows = repo.dirty_activity_rows_for_materialization(metric_version, limit=limit)
    if not dirty_rows:
        return {"status": "noop", "activities_materialized": 0, "dirty_rows_cleared": 0}

    started = time.perf_counter()
    start_day = min(str(row["activity_day"]) for row in dirty_rows)
    end_day = max(today, max(str(row["activity_day"]) for row in dirty_rows))

    # Compute a session-level bounds for daily-fact aggregation (global max at end_day).
    # Per-activity facts use per-activity running max; this bounds is only used to
    # aggregate already-computed TRIMP via observed_trimp_history (cross-activity daily sum).
    global_hr_max = repo.max_heartrate_to_date(end_day)
    if global_hr_max is None:
        # No HR data at all — use a sentinel bounds that returns 0 TRIMP for all rows.
        session_bounds = get_zone_model(athlete.hr_zone_model).zone_bounds(
            hr_max=athlete.hr_rest + 1, hr_rest=athlete.hr_rest
        )
    else:
        session_bounds = get_zone_model(athlete.hr_zone_model).zone_bounds(
            hr_max=int(global_hr_max), hr_rest=athlete.hr_rest
        )

    try:
        activity_facts: list[dict[str, object]] = _activity_facts_batched(
            repo, dirty_rows, metric_version, computed_at, _settings, renew_lease=renew_lease
        )
    except Exception as exc:
        _record_failed_run(repo, computed_at, metric_version, exc)
        raise

    repo.begin()
    try:
        activity_count = len(activity_facts)
        repo.upsert_activity_metric_facts(activity_facts)

        daily_trimp = _materialize_daily_facts(
            repo,
            start_day=start_day,
            end_day=end_day,
            metric_version=metric_version,
            computed_at=computed_at,
            bounds=session_bounds,
        )
        _materialize_model_facts(
            repo,
            start_day=start_day,
            end_day=end_day,
            metric_version=metric_version,
            computed_at=computed_at,
            daily_trimp=daily_trimp,
        )
        _materialize_rolling_facts(
            repo,
            as_of_day=end_day,
            metric_version=metric_version,
            computed_at=computed_at,
        )
        repo.record_read_model_refresh_run(
            {
                "started_at": computed_at,
                "finished_at": computed_at,
                "status": "ok",
                "metric_version": metric_version,
                "trigger_reason": trigger_reason,
                "activities_considered": len(dirty_rows),
                "activities_materialized": activity_count,
                "daily_facts_materialized": len(daily_trimp),
                "model_facts_materialized": len(daily_trimp),
                "rolling_facts_materialized": len(ROLLING_WINDOWS),
                "dirty_rows_claimed": len(dirty_rows),
                "dirty_rows_cleared": len(dirty_rows),
                "attempt_count": 1,
                "last_error": None,
            }
        )
        cleared = repo.clear_dirty_activity_rows(dirty_rows)
    except Exception as exc:
        repo.rollback()
        _record_failed_run(repo, computed_at, metric_version, exc)
        raise

    repo.commit()
    # Operational counter for a domain that has regressed before: surfaces materialize
    # cost so the next slowdown is visible without a profiler.
    logger.info(
        "read-model materialize: activities=%d daily=%d rolling=%d cleared=%d elapsed_ms=%d",
        activity_count,
        len(daily_trimp),
        len(ROLLING_WINDOWS),
        cleared,
        int((time.perf_counter() - started) * 1000),
    )
    return {
        "status": "ok",
        "activities_materialized": activity_count,
        "dirty_rows_cleared": cleared,
        "daily_facts_materialized": len(daily_trimp),
        "rolling_facts_materialized": len(ROLLING_WINDOWS),
    }
