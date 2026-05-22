"""Metric-focused application services for MCP-facing tool backends."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import date, datetime, timedelta

from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.analytics import weekly_digest
from mcp_strava.application.freshness import build_freshness_metadata
from mcp_strava.application.metric_registry import METRIC_REGISTRY
from mcp_strava.constants import RUNNING_SPORTS
from mcp_strava.db import DbConn
from mcp_strava.metrics import check_hr_anomalies, check_z5_minutes, enrich_activity
from mcp_strava.refresh.policy import RefreshPolicy
from mcp_strava.report import daily_report_from_connection
from mcp_strava.settings import get_settings
from mcp_strava.types import (
    CompletenessMetadata,
    ServiceEnvelope,
    ServiceRationale,
    ServiceWarning,
    parse_strava_activity,
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


def _connection_context(connection):
    return nullcontext(connection) if connection is not None else DbConn()


def _policy() -> RefreshPolicy:
    return RefreshPolicy.from_settings(get_settings())


def _metric_if_registered(payload: dict[str, object], metric_id: str, value) -> None:
    if metric_id in METRIC_REGISTRY:
        payload[metric_id] = value


def _project_fitness_state_metrics(report, digest) -> dict[str, object]:
    data: dict[str, object] = {}

    if report.banister is not None:
        _metric_if_registered(data, "fitness", report.banister.fitness)
        _metric_if_registered(data, "fatigue", report.banister.fatigue)
        _metric_if_registered(data, "form", report.banister.form)
        _metric_if_registered(data, "form_zone", report.banister.form_zone)
    _metric_if_registered(data, "acwr", report.acwr)
    _metric_if_registered(data, "acwr_zone", report.acwr_zone)
    _metric_if_registered(data, "atl", report.acwr_atl)
    _metric_if_registered(data, "ctl", report.acwr_ctl)
    _metric_if_registered(data, "weekly_trimp", report.weekly_trimp)
    _metric_if_registered(data, "total_trimp_14d", report.total_trimp_14d)
    _metric_if_registered(data, "avg_trimp_per_day", report.avg_trimp_per_day)
    _metric_if_registered(data, "active_days", report.active_days)
    _metric_if_registered(data, "rest_days", report.rest_days)

    if report.progressive_signal is not None:
        _metric_if_registered(data, "progressive_load_bonus", report.progressive_signal.load_bonus)
        _metric_if_registered(data, "progressive_cc_trends", report.progressive_signal.cc_trends)
    else:
        _metric_if_registered(data, "progressive_load_bonus", None)
        _metric_if_registered(data, "progressive_cc_trends", None)

    if digest is not None:
        load = digest.current_state.get("load", {})
        context = digest.context
        _metric_if_registered(data, "daily_avg_trimp_7d", load.get("daily_avg_trimp_7d"))
        _metric_if_registered(data, "daily_avg_trimp_28d", load.get("daily_avg_trimp_28d"))
        _metric_if_registered(data, "daily_avg_trimp_90d", load.get("daily_avg_trimp_90d"))
        _metric_if_registered(data, "activity_streak_days", context.get("activity_streak"))
        _metric_if_registered(data, "rest_streak_days", context.get("rest_streak"))
        _metric_if_registered(data, "last_hike_days_ago", context.get("last_hike_days_ago"))

    return data


def _safety_warnings(repo: SQLiteRepository, report, digest) -> list[ServiceWarning]:
    warnings: list[ServiceWarning] = []
    today = date.fromisoformat(report.today)
    yesterday = (today - timedelta(days=1)).isoformat()
    day_before = (today - timedelta(days=2)).isoformat()

    yesterday_activities = [a for a in report.activities_14d if a.date == yesterday]
    z5_total = 0
    hr_anomaly_total = 0
    severe_drift_count = 0

    for activity in yesterday_activities:
        z5_seconds, _ = check_z5_minutes(repo.conn, activity.id)
        if z5_seconds:
            z5_total += z5_seconds
        anomaly_count, _ = check_hr_anomalies(repo.conn, activity.id)
        if anomaly_count:
            hr_anomaly_total += anomaly_count
        if activity.cardiac_drift and activity.cardiac_drift.severity in {"significant", "severe"}:
            severe_drift_count += 1

    _metric_if_registered = METRIC_REGISTRY.__contains__
    if _metric_if_registered("z5_seconds") and z5_total > 0:
        warnings.append(
            ServiceWarning(
                code="z5_excessive",
                severity="warning",
                message="Elevated high-zone heart-rate duration detected.",
                field="z5_seconds",
                evidence={"z5_seconds": z5_total},
            )
        )

    if _metric_if_registered("hr_anomaly_count") and hr_anomaly_total > 0:
        warnings.append(
            ServiceWarning(
                code="hr_anomaly_burst",
                severity="warning",
                message="Multiple heart-rate anomalies detected.",
                field="hr_anomaly_count",
                evidence={"hr_anomaly_count": hr_anomaly_total},
            )
        )

    if severe_drift_count > 0:
        warnings.append(
            ServiceWarning(
                code="cardiac_drift_severe_yesterday",
                severity="warning",
                message="Severe cardiac drift was detected in yesterday activity.",
                field="cardiac_drift_pct",
                evidence={"activities_with_severe_drift": severe_drift_count},
            )
        )

    yesterday_hike = sum(a.trimp for a in report.activities_14d if a.date == yesterday and a.sport_type == "Hike")
    day_before_hike = sum(a.trimp for a in report.activities_14d if a.date == day_before and a.sport_type == "Hike")
    if yesterday_hike > 0 and day_before_hike > 0:
        two_day_hike_trimp = round(yesterday_hike + day_before_hike, 1)
        if two_day_hike_trimp > 800:
            warnings.append(
                ServiceWarning(
                    code="hike_load_consecutive_high",
                    severity="warning",
                    message="Consecutive high hike load detected.",
                    evidence={"two_day_hike_trimp": two_day_hike_trimp, "threshold": 800},
                )
            )

    week_start = today - timedelta(days=today.weekday())
    this_km = repo.total_distance_km_between(week_start.isoformat(), today.isoformat(), RUNNING_SPORTS)
    prev_km = repo.total_distance_km_between(
        (week_start - timedelta(days=7)).isoformat(),
        (week_start - timedelta(days=1)).isoformat(),
        RUNNING_SPORTS,
    )
    if prev_km > 0 and this_km > 0:
        jump_pct = (this_km / prev_km - 1) * 100
        if jump_pct > 10:
            warnings.append(
                ServiceWarning(
                    code="running_volume_jump_high",
                    severity="warning",
                    message="Running weekly volume jump detected.",
                    evidence={"jump_pct": round(jump_pct, 1), "previous_km": round(prev_km, 1), "current_km": round(this_km, 1)},
                )
            )

    if any(activity.avg_hr is None for activity in report.activities_14d):
        warnings.append(
            ServiceWarning(
                code="low_hr_data",
                severity="warning",
                message="Heart-rate coverage is incomplete in local mirror window.",
            )
        )

    if digest is None:
        warnings.append(
            ServiceWarning(
                code="insufficient_history",
                severity="warning",
                message="Not enough local history for weekly context metrics.",
            )
        )

    return [w for w in warnings if w.code in SAFETY_WARNING_CODES]


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
        report = daily_report_from_connection(conn, now_local=checked_at)
        digest = weekly_digest(conn, today=checked_at.date())
        data = _project_fitness_state_metrics(report, digest)
        z5_total = 0
        hr_anomaly_total = 0
        yesterday = (checked_at.date() - timedelta(days=1)).isoformat()
        for activity in report.activities_14d:
            if activity.date != yesterday:
                continue
            z5_seconds, _ = check_z5_minutes(conn, activity.id)
            if z5_seconds:
                z5_total += z5_seconds
            anomalies, _ = check_hr_anomalies(conn, activity.id)
            if anomalies:
                hr_anomaly_total += anomalies
        _metric_if_registered(data, "z5_seconds", z5_total)
        _metric_if_registered(data, "hr_anomaly_count", hr_anomaly_total)
        warnings = _safety_warnings(repo, report, digest)

    completeness = CompletenessMetadata(
        status="complete" if data else "insufficient",
        missing=[] if data else ["insufficient_history"],
        coverage={"metrics": sorted(data.keys())},
    )
    return ServiceEnvelope(
        data=data,
        freshness=freshness,
        completeness=completeness,
        warnings=warnings,
        rationale=[ServiceRationale(code="metric_bundle_from_local_mirror", message="Metric bundle projected from local mirror model and activity facts.")],
    )


def _row_completeness(summary) -> dict[str, object]:
    missing: list[str] = []
    if summary is None or summary.average_heartrate is None:
        missing.append("missing_hr")
    return {
        "status": "partial" if missing else "complete",
        "missing": missing,
    }


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
    checked_at = now or datetime.now()
    with _connection_context(connection) as conn:
        repo = SQLiteRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, checked_at, _policy(), signal_first_use=signal_first_use)
        rows = repo.list_activities(start_date=start_date, end_date=end_date, sport=sport, limit=limit)

        data: list[dict[str, object]] = []
        for row in rows:
            raw_summary = json.loads(row.summary_json) if row.summary_json else {}
            summary = parse_strava_activity(raw_summary) if raw_summary else None
            data.append(
                {
                    "activity_id": row.id,
                    "activity_date": row.date[:10],
                    "sport_type": row.sport_type,
                    "activity_name": row.name,
                    "distance_km": round(row.distance / 1000, 2),
                    "moving_time_min": round(row.moving_time / 60, 1),
                    "elevation_m": row.total_elevation_gain,
                    "trimp": repo.activity_trimp(row.id),
                    "avg_hr": summary.average_heartrate if summary else None,
                    "max_hr": int(round(summary.max_heartrate)) if summary and summary.max_heartrate else None,
                    "completeness": _row_completeness(summary),
                }
            )

    completeness = CompletenessMetadata(
        status="complete",
        missing=[],
        coverage={"count": len(data), "limit": limit, "filters": {"start_date": start_date, "end_date": end_date, "sport": sport}},
    )
    return ServiceEnvelope(
        data=data,
        freshness=freshness,
        completeness=completeness,
        warnings=[],
        rationale=[ServiceRationale(code="metric_bundle_from_local_mirror", message="Workout list projected from local activity rows and summary facts.")],
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
        resolved_id = repo.latest_activity_id() if activity_id == "latest" else int(activity_id)
        row = repo.activity_by_id(resolved_id) if resolved_id is not None else None

        if row is None:
            completeness = CompletenessMetadata(status="unavailable", missing=["workout_not_found"], coverage={"activity_id": activity_id})
            return ServiceEnvelope(
                data=None,
                freshness=freshness,
                completeness=completeness,
                warnings=[ServiceWarning(code="metric_unavailable", severity="warning", message="Requested workout was not found.")],
                rationale=[ServiceRationale(code="metric_bundle_from_local_mirror", message="Workout detail requested from local mirror id.")],
            )

        enriched = enrich_activity(conn, row)
        zone_minutes = enriched.zone_minutes if enriched.zone_minutes else [0.0] * 5
        data = {
            "activity_id": enriched.id,
            "activity_date": enriched.date,
            "sport_type": enriched.sport_type,
            "activity_name": enriched.name,
            "distance_km": enriched.distance_km,
            "moving_time_min": enriched.moving_time_min,
            "elapsed_time_min": enriched.elapsed_time_min,
            "elevation_m": enriched.elevation_m,
            "trimp": enriched.trimp,
            "avg_hr": enriched.avg_hr,
            "max_hr": enriched.max_hr,
            "time_in_hr_zones_min": zone_minutes,
            "hr_recovery_pauses": enriched.hr_recovery.pauses_found if enriched.hr_recovery else None,
            "hr_recovery_total_rest_sec": enriched.hr_recovery.total_rest_sec if enriched.hr_recovery else None,
            "hr_recovery_median_bpm_per_min": enriched.hr_recovery.median_rate if enriched.hr_recovery else None,
            "hr_recovery_best_bpm_per_min": enriched.hr_recovery.best_rate if enriched.hr_recovery else None,
            "hr_recovery_worst_bpm_per_min": enriched.hr_recovery.worst_rate if enriched.hr_recovery else None,
            "hr_recovery_avg_bpm_per_min": enriched.hr_recovery.avg_rate if enriched.hr_recovery else None,
            "vertical_speed_m_per_h": enriched.vertical_speed.vmh if enriched.vertical_speed else None,
            "vertical_ascent_m": enriched.vertical_speed.total_ascent_m if enriched.vertical_speed else None,
            "vertical_duration_h": enriched.vertical_speed.duration_hours if enriched.vertical_speed else None,
            "cardiac_cost": enriched.cc,
            "cardiac_drift_pct": enriched.cardiac_drift.drift_pct if enriched.cardiac_drift else None,
            "cardiac_drift_severity": enriched.cardiac_drift.severity if enriched.cardiac_drift else None,
            "cardiac_drift_quality": enriched.cardiac_drift.quality if enriched.cardiac_drift else None,
            "cardiac_drift_significant": enriched.cardiac_drift.is_significant if enriched.cardiac_drift else None,
            "hrr_pct": enriched.hrr_pct,
            "start_time": enriched.start_time,
            "z5_seconds": check_z5_minutes(conn, enriched.id)[0] or 0,
            "hr_anomaly_count": check_hr_anomalies(conn, enriched.id)[0],
        }

        missing: list[str] = []
        if enriched.avg_hr is None:
            missing.append("missing_hr")
        stream_derived = [
            data["hr_recovery_median_bpm_per_min"],
            data["vertical_speed_m_per_h"],
            data["cardiac_cost"],
            data["cardiac_drift_pct"],
            data["hrr_pct"],
        ]
        if all(value is None for value in stream_derived):
            missing.append("missing_streams")
        elif any(value is None for value in stream_derived):
            missing.append("metric_unavailable")

        completeness = CompletenessMetadata(
            status="partial" if missing else "complete",
            missing=missing,
            coverage={"metric_count": len(data)},
        )
        warnings = [
            ServiceWarning(code=code, severity="warning", message="Workout metric coverage is partial.")
            for code in missing
            if code in {"missing_hr", "missing_streams", "metric_unavailable"}
        ]

    return ServiceEnvelope(
        data=data,
        freshness=freshness,
        completeness=completeness,
        warnings=warnings,
        rationale=[ServiceRationale(code="metric_bundle_from_local_mirror", message="Workout detail projected from local enriched workout facts.")],
    )
