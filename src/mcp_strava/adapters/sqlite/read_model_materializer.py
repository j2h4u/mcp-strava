"""Offline materialization for SQLite read-model facts."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from statistics import median

from mcp_strava.adapters.sqlite.repository import CURRENT_METRIC_VERSION, SQLiteRepository
from mcp_strava.constants import Config
from mcp_strava.metrics import check_hr_anomalies, enrich_activity
from mcp_strava.training import calc_banister_series

ROLLING_WINDOWS = (7, 14, 28, 90)


def _now_parts(now: str | datetime | None) -> tuple[str, str]:
    if now is None:
        dt = datetime.now()
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


def _stream_counts(repo: SQLiteRepository, activity_id: int) -> tuple[int, int]:
    row = repo.conn.execute(
        """
        SELECT COUNT(*) AS stream_count,
               SUM(CASE WHEN heartrate IS NOT NULL THEN 1 ELSE 0 END) AS hr_count
        FROM streams
        WHERE activity_id = ?
        """,
        (activity_id,),
    ).fetchone()
    return int(row["stream_count"] or 0), int(row["hr_count"] or 0)


def _zone_seconds(repo: SQLiteRepository, activity_id: int) -> tuple[int, int, int, int, int]:
    b = Config.Zones.BOUNDS
    row = repo.conn.execute(
        """
        SELECT
          SUM(CASE WHEN heartrate < ? THEN 1 ELSE 0 END) AS z1,
          SUM(CASE WHEN heartrate >= ? AND heartrate < ? THEN 1 ELSE 0 END) AS z2,
          SUM(CASE WHEN heartrate >= ? AND heartrate < ? THEN 1 ELSE 0 END) AS z3,
          SUM(CASE WHEN heartrate >= ? AND heartrate < ? THEN 1 ELSE 0 END) AS z4,
          SUM(CASE WHEN heartrate >= ? THEN 1 ELSE 0 END) AS z5
        FROM streams
        WHERE activity_id = ? AND heartrate IS NOT NULL
        """,
        (b[0], b[0], b[1], b[1], b[2], b[2], b[3], b[-2], activity_id),
    ).fetchone()
    return tuple(int(row[f"z{idx}"] or 0) for idx in range(1, 6))


def _adjusted_cardiac_cost(cc: float | None, distance_m: float | None, elevation_m: float | None) -> float | None:
    if cc is None or not distance_m or distance_m <= 0:
        return None
    elevation_per_km = float(elevation_m or 0.0) / (float(distance_m) / 1000.0)
    return round(float(cc) - Config.Efficiency.CC_ELEV_COEFF * elevation_per_km, 3)


def _form_zone(form: float) -> str:
    if form < -5:
        return "tired"
    if form < 10:
        return "normal"
    return "fresh"


def _acwr_zone(acwr: float | None) -> str:
    if acwr is None:
        return "unknown"
    if 0.8 <= acwr <= 1.3:
        return "sweet_spot"
    if 1.3 < acwr <= Config.Thresholds.ACWR_DANGER:
        return "caution"
    if acwr > Config.Thresholds.ACWR_DANGER:
        return "danger"
    return "undertrained"


def _median_or_none(values: list[object]) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return round(float(median(numeric)), 3) if numeric else None


def _activity_fact(repo: SQLiteRepository, dirty_row, metric_version: int, computed_at: str) -> dict[str, object]:
    activity_id = int(dirty_row["activity_id"])
    activity = repo.activity_by_id(activity_id)
    if activity is None:
        raise RuntimeError(f"Dirty activity missing source row: {activity_id}")
    source = repo.source_state_for_activity(activity_id)
    if source is None:
        raise RuntimeError(f"Dirty activity missing source state: {activity_id}")

    enriched = enrich_activity(repo.conn, activity)
    stream_count, hr_count = _stream_counts(repo, activity_id)
    zone1, zone2, zone3, zone4, zone5 = _zone_seconds(repo, activity_id)
    anomaly_count, _anomaly_warning = check_hr_anomalies(repo.conn, activity_id)

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

    vertical = enriched.vertical_speed
    recovery = enriched.hr_recovery
    drift = enriched.cardiac_drift
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
        "trimp": enriched.trimp,
        "zone1_seconds": zone1,
        "zone2_seconds": zone2,
        "zone3_seconds": zone3,
        "zone4_seconds": zone4,
        "zone5_seconds": zone5,
        "hr_recovery_pause_count": recovery.pauses_found if recovery else 0,
        "hr_recovery_total_rest_sec": recovery.total_rest_sec if recovery else 0,
        "hr_recovery_median_rate": recovery.median_rate if recovery else None,
        "hr_recovery_best_rate": recovery.best_rate if recovery else None,
        "hr_recovery_worst_rate": recovery.worst_rate if recovery else None,
        "hr_recovery_avg_rate": recovery.avg_rate if recovery else None,
        "vertical_speed_vmh": vertical.vmh if vertical else None,
        "vertical_speed_total_ascent_m": vertical.total_ascent_m if vertical else None,
        "vertical_speed_duration_hours": vertical.duration_hours if vertical else None,
        "cardiac_cost": enriched.cc,
        "adjusted_cardiac_cost": _adjusted_cardiac_cost(enriched.cc, activity.distance, activity.total_elevation_gain),
        "cardiac_drift_pct": drift.drift_pct if drift else None,
        "cardiac_drift_severity": drift.severity if drift else None,
        "cardiac_drift_significant": 1 if drift and drift.is_significant else 0,
        "cardiac_drift_quality": drift.quality if drift else None,
        "hrr_pct": enriched.hrr_pct,
        "anomaly_count": anomaly_count,
        "distance_m": activity.distance,
        "moving_time_s": activity.moving_time,
        "elapsed_time_s": activity.elapsed_time,
        "elevation_gain_m": activity.total_elevation_gain,
        "heartrate_sample_count": hr_count,
        "stream_sample_count": stream_count,
    }


def _daily_missing_reasons(status: str) -> list[str]:
    if status == "UNKNOWN":
        return ["missing_streams"]
    if status == "PARTIAL":
        return ["missing_hr"]
    return []


def _materialize_daily_facts(
    repo: SQLiteRepository,
    *,
    start_day: str,
    end_day: str,
    metric_version: int,
    computed_at: str,
) -> dict[str, float]:
    points = repo.daily_load_points_between(start_day, end_day)
    daily_trimp: dict[str, float] = {}
    for point in points:
        sums = repo.conn.execute(
            """
            SELECT
              SUM(distance_m) AS distance_m,
              SUM(moving_time_s) AS moving_time_s,
              SUM(elevation_gain_m) AS elevation_gain_m,
              SUM(zone4_seconds) AS zone4_seconds,
              SUM(zone5_seconds) AS zone5_seconds,
              SUM(anomaly_count) AS anomaly_count
            FROM activity_metric_facts
            WHERE activity_day = ? AND metric_version = ?
            """,
            (point.date, metric_version),
        ).fetchone()
        missing = _daily_missing_reasons(point.status)
        repo.upsert_daily_load_fact(
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
    return daily_trimp


def _materialize_model_facts(
    repo: SQLiteRepository,
    *,
    start_day: str,
    end_day: str,
    metric_version: int,
    computed_at: str,
    daily_trimp: dict[str, float],
) -> None:
    series = calc_banister_series(daily_trimp, end_date=end_day)
    wanted = set(_date_range(start_day, end_day))
    for point in series:
        if point["date"] not in wanted:
            continue
        trimp = float(point["trimp"])
        fitness = float(point["fitness"])
        fatigue = float(point["fatigue"])
        form = float(point["form"])
        acwr = round(fatigue / fitness, 3) if fitness > 0 else None
        repo.upsert_training_model_daily_fact(
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
                "form_zone": _form_zone(form),
                "acwr_zone": _acwr_zone(acwr),
                "acwr": acwr,
                "load_7d": fatigue,
                "load_28d": None,
                "load_42d": fitness,
                "input_days": len(daily_trimp),
                "missing_days": 0,
            }
        )


def _materialize_rolling_facts(
    repo: SQLiteRepository,
    *,
    as_of_day: str,
    metric_version: int,
    computed_at: str,
) -> None:
    as_of = date.fromisoformat(as_of_day)
    for window in ROLLING_WINDOWS:
        start = (as_of - timedelta(days=window - 1)).isoformat()
        row = repo.conn.execute(
            """
            SELECT
              COUNT(*) AS days,
              SUM(activity_count) AS activity_count,
              SUM(CASE WHEN activity_count > 0 THEN 1 ELSE 0 END) AS active_days,
              SUM(CASE WHEN activity_count = 0 THEN 1 ELSE 0 END) AS rest_days,
              SUM(observed_trimp) AS observed_trimp,
              SUM(effective_trimp) AS effective_trimp,
              SUM(distance_m) AS distance_m,
              SUM(moving_time_s) AS moving_time_s,
              SUM(elevation_gain_m) AS elevation_gain_m,
              SUM(high_zone_seconds) AS high_zone_seconds,
              SUM(anomaly_count) AS anomaly_count
            FROM daily_load_facts
            WHERE day BETWEEN ? AND ?
              AND scope = 'all'
              AND sport_type = 'all'
              AND metric_version = ?
            """,
            (start, as_of_day, metric_version),
        ).fetchone()
        model = repo.conn.execute(
            """
            SELECT fitness, fatigue, form, form_zone, acwr_zone, acwr
            FROM training_model_daily
            WHERE day = ? AND scope = 'all' AND sport_type = 'all' AND metric_version = ?
            """,
            (as_of_day, metric_version),
        ).fetchone()
        metric_rows = repo.conn.execute(
            """
            SELECT cardiac_cost, adjusted_cardiac_cost, hr_recovery_median_rate, cardiac_drift_pct
            FROM activity_metric_facts
            WHERE activity_day BETWEEN ? AND ?
              AND metric_version = ?
            """,
            (start, as_of_day, metric_version),
        ).fetchall()
        repo.upsert_rolling_period_fact(
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
                "median_cardiac_cost": _median_or_none([row["cardiac_cost"] for row in metric_rows]),
                "median_adjusted_cardiac_cost": _median_or_none([row["adjusted_cardiac_cost"] for row in metric_rows]),
                "median_hr_recovery": _median_or_none([row["hr_recovery_median_rate"] for row in metric_rows]),
                "median_cardiac_drift_pct": _median_or_none([row["cardiac_drift_pct"] for row in metric_rows]),
            }
        )


def _record_failed_run(repo: SQLiteRepository, started_at: str, metric_version: int, error: Exception) -> None:
    try:
        repo.record_read_model_refresh_run(
            {
                "started_at": started_at,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
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
        repo.conn.commit()
    except Exception:
        repo.conn.rollback()


def materialize_read_model(
    repo: SQLiteRepository,
    metric_version: int = CURRENT_METRIC_VERSION,
    now: str | datetime | None = None,
    limit: int | None = None,
    run_id: int | None = None,
    renew_lease=None,
) -> dict[str, object]:
    del run_id
    computed_at, today = _now_parts(now)
    dirty_rows = repo.dirty_activity_rows_for_materialization(metric_version, limit=limit)
    if not dirty_rows:
        return {"status": "noop", "activities_materialized": 0, "dirty_rows_cleared": 0}

    start_day = min(str(row["activity_day"]) for row in dirty_rows)
    end_day = max(today, max(str(row["activity_day"]) for row in dirty_rows))

    repo.conn.execute("BEGIN")
    try:
        activity_count = 0
        for dirty in dirty_rows:
            fact = _activity_fact(repo, dirty, metric_version, computed_at)
            repo.upsert_activity_metric_fact(fact)
            activity_count += 1
            if renew_lease is not None:
                renew_lease()

        daily_trimp = _materialize_daily_facts(
            repo,
            start_day=start_day,
            end_day=end_day,
            metric_version=metric_version,
            computed_at=computed_at,
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
                "trigger_reason": "materialize_read_model",
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
        repo.conn.rollback()
        _record_failed_run(repo, computed_at, metric_version, exc)
        raise

    repo.conn.commit()
    return {
        "status": "ok",
        "activities_materialized": activity_count,
        "dirty_rows_cleared": cleared,
        "daily_facts_materialized": len(daily_trimp),
        "rolling_facts_materialized": len(ROLLING_WINDOWS),
    }
