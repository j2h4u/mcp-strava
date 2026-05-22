"""Metric-focused application services for MCP-facing tool backends."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from statistics import median

from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.analytics import weekly_digest
from mcp_strava.application.freshness import build_freshness_metadata
from mcp_strava.application.metric_registry import METRIC_REGISTRY
from mcp_strava.constants import Config, RUNNING_SPORTS
from mcp_strava.db import DbConn
from mcp_strava.metrics import check_hr_anomalies, check_z5_minutes, enrich_activity
from mcp_strava.refresh.policy import RefreshPolicy
from mcp_strava.report import daily_report_from_connection
from mcp_strava.settings import get_settings
from mcp_strava.training import calc_banister, forward_simulate
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

COMPARISON_MISSING_REASONS = {
    "insufficient_history",
    "missing_hr",
    "missing_streams",
    "metric_not_applicable",
    "no_activity_in_period",
}


def _connection_context(connection):
    return nullcontext(connection) if connection is not None else DbConn()


def _policy() -> RefreshPolicy:
    return RefreshPolicy.from_settings(get_settings())


def _metric_if_registered(payload: dict[str, object], metric_id: str, value) -> None:
    if metric_id in METRIC_REGISTRY:
        payload[metric_id] = value


def load_period_activities(repo: SQLiteRepository, start_day: str, end_day: str, sport: str | None = None) -> list:
    rows = repo.activity_rows_between(start_day, end_day)
    if sport is None:
        return rows
    return [row for row in rows if row.sport_type == sport]


def _is_number(value) -> bool:
    return isinstance(value, (int, float))


def aggregate_metric_values(metric_id: str, activities: list, conn) -> tuple[list, list[str]]:
    values: list = []
    missing: list[str] = []
    for row in activities:
        enriched = enrich_activity(conn, row)
        if metric_id == "trimp":
            values.append(enriched.trimp)
        elif metric_id == "distance_km":
            values.append(enriched.distance_km)
        elif metric_id == "moving_time_min":
            values.append(enriched.moving_time_min)
        elif metric_id == "elevation_m":
            values.append(enriched.elevation_m)
        elif metric_id == "cardiac_cost":
            if enriched.cc is None:
                missing.append("missing_streams")
            else:
                values.append(enriched.cc)
        elif metric_id == "cardiac_cost_adjusted":
            cc_adj = enriched.cc
            if cc_adj is None:
                missing.append("missing_streams")
            else:
                values.append(cc_adj)
        elif metric_id == "cardiac_drift_pct":
            if enriched.cardiac_drift is None or enriched.cardiac_drift.drift_pct is None:
                missing.append("missing_streams")
            else:
                values.append(enriched.cardiac_drift.drift_pct)
        elif metric_id == "hr_recovery_median_bpm_per_min":
            if enriched.hr_recovery is None or enriched.hr_recovery.median_rate is None:
                missing.append("missing_hr")
            else:
                values.append(enriched.hr_recovery.median_rate)
        elif metric_id == "hrr_pct":
            if enriched.hrr_pct is None:
                missing.append("missing_hr")
            else:
                values.append(enriched.hrr_pct)
        elif metric_id == "vertical_speed_m_per_h":
            if enriched.vertical_speed is None or enriched.vertical_speed.vmh is None:
                missing.append("missing_streams")
            else:
                values.append(enriched.vertical_speed.vmh)
        elif metric_id == "time_in_hr_zones_min":
            if not enriched.zone_minutes:
                missing.append("missing_hr")
            else:
                values.append(enriched.zone_minutes)
    return values, sorted(set(missing))


def _compare_summary(values: list, comparison_mode: str):
    if not values:
        return None
    if comparison_mode == "sum":
        return round(float(sum(values)), 3)
    if comparison_mode == "avg":
        return round(float(sum(values) / len(values)), 3)
    if comparison_mode == "median":
        return round(float(median(values)), 3)
    if comparison_mode == "last":
        return round(float(values[-1]), 3)
    if comparison_mode == "min":
        return round(float(min(values)), 3)
    if comparison_mode == "max":
        return round(float(max(values)), 3)
    if comparison_mode == "trend":
        if len(values) < 2:
            return None
        return round(float(values[-1] - values[0]), 3)
    return None


def compare_scalar_metric(metric_id: str, comparison_mode: str, values_a: list, values_b: list, missing_a: list[str], missing_b: list[str]) -> dict[str, object]:
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
    }


def compare_distribution_metric(values_a: list, values_b: list, missing_a: list[str], missing_b: list[str]) -> dict[str, object]:
    missing = sorted(set(missing_a + missing_b))
    if not values_a or not values_b:
        missing = sorted(set(missing + ["no_activity_in_period"]))
    zone_count = 5
    buckets_a = {f"z{i + 1}": 0.0 for i in range(zone_count)}
    buckets_b = {f"z{i + 1}": 0.0 for i in range(zone_count)}
    for zones in values_a:
        for idx, value in enumerate(zones[:zone_count]):
            buckets_a[f"z{idx + 1}"] += float(value or 0.0)
    for zones in values_b:
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
        "missing_reasons": missing,
    }


def route_metric_by_sport_scope(metric, *, global_section: dict, per_sport_section: dict, sport_filter: str | None, all_sports: list[str], period_a_rows: list, period_b_rows: list, conn) -> None:
    supported_global = metric.sport_scope in {"global", "both"}
    supported_per_sport = metric.sport_scope in {"per_sport", "both"}

    if supported_global:
        values_a, missing_a = aggregate_metric_values(metric.metric_id, period_a_rows, conn)
        values_b, missing_b = aggregate_metric_values(metric.metric_id, period_b_rows, conn)
        if metric.comparison_mode == "distribution":
            global_section["metrics"][metric.metric_id] = compare_distribution_metric(values_a, values_b, missing_a, missing_b)
        else:
            global_section["metrics"][metric.metric_id] = compare_scalar_metric(
                metric.metric_id, metric.comparison_mode, values_a, values_b, missing_a, missing_b
            )

    if supported_per_sport:
        for sport in all_sports:
            if sport_filter is not None and sport != sport_filter:
                continue
            a_sport = [row for row in period_a_rows if row.sport_type == sport]
            b_sport = [row for row in period_b_rows if row.sport_type == sport]
            if not a_sport and not b_sport:
                continue
            values_a, missing_a = aggregate_metric_values(metric.metric_id, a_sport, conn)
            values_b, missing_b = aggregate_metric_values(metric.metric_id, b_sport, conn)
            per_sport_section.setdefault(sport, {"metrics": {}})
            if metric.comparison_mode == "distribution":
                per_sport_section[sport]["metrics"][metric.metric_id] = compare_distribution_metric(values_a, values_b, missing_a, missing_b)
            else:
                per_sport_section[sport]["metrics"][metric.metric_id] = compare_scalar_metric(
                    metric.metric_id, metric.comparison_mode, values_a, values_b, missing_a, missing_b
                )


COMPARE_PERIODS_HANDLERS = {
    "trimp": "aggregate_metric_values",
    "distance_km": "aggregate_metric_values",
    "moving_time_min": "aggregate_metric_values",
    "elevation_m": "aggregate_metric_values",
    "cardiac_cost": "aggregate_metric_values",
    "cardiac_cost_adjusted": "aggregate_metric_values",
    "cardiac_drift_pct": "aggregate_metric_values",
    "hr_recovery_median_bpm_per_min": "aggregate_metric_values",
    "hrr_pct": "aggregate_metric_values",
    "vertical_speed_m_per_h": "aggregate_metric_values",
    "time_in_hr_zones_min": "aggregate_metric_values",
    "fitness": "model_from_report",
    "fatigue": "model_from_report",
    "form": "model_from_report",
    "acwr": "model_from_report",
}

COMPARE_PERIODS_SKIP_REASONS = {
    metric_id: "metric_not_applicable"
    for metric_id, definition in METRIC_REGISTRY.items()
    if "compare_periods" in definition.exposed_in and definition.comparison_mode != "none" and metric_id not in COMPARE_PERIODS_HANDLERS
}


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
        period_a_rows = load_period_activities(repo, period_a_start, period_a_end, sport=sport)
        period_b_rows = load_period_activities(repo, period_b_start, period_b_end, sport=sport)
        sports = sorted(set([row.sport_type for row in period_a_rows + period_b_rows]))
        global_section = {"scope_filter": "sport" if sport else "all", "metrics": {}}
        per_sport_section: dict[str, dict[str, object]] = {}

        for metric in METRIC_REGISTRY.values():
            if "compare_periods" not in metric.exposed_in or metric.comparison_mode == "none":
                continue
            if metric.metric_id in {"fitness", "fatigue", "form", "acwr"}:
                report_a = daily_report_from_connection(conn, now_local=datetime.fromisoformat(f"{period_a_end}T12:00:00"))
                report_b = daily_report_from_connection(conn, now_local=datetime.fromisoformat(f"{period_b_end}T12:00:00"))
                values_a = []
                values_b = []
                if metric.metric_id == "fitness":
                    values_a = [report_a.banister.fitness] if report_a.banister else []
                    values_b = [report_b.banister.fitness] if report_b.banister else []
                elif metric.metric_id == "fatigue":
                    values_a = [report_a.banister.fatigue] if report_a.banister else []
                    values_b = [report_b.banister.fatigue] if report_b.banister else []
                elif metric.metric_id == "form":
                    values_a = [report_a.banister.form] if report_a.banister else []
                    values_b = [report_b.banister.form] if report_b.banister else []
                elif metric.metric_id == "acwr":
                    values_a = [report_a.acwr] if report_a.acwr is not None else []
                    values_b = [report_b.acwr] if report_b.acwr is not None else []
                global_section["metrics"][metric.metric_id] = compare_scalar_metric(
                    metric.metric_id, metric.comparison_mode, values_a, values_b, ["insufficient_history"] if not values_a else [], ["insufficient_history"] if not values_b else []
                )
                continue
            route_metric_by_sport_scope(
                metric,
                global_section=global_section,
                per_sport_section=per_sport_section,
                sport_filter=sport,
                all_sports=sports,
                period_a_rows=period_a_rows,
                period_b_rows=period_b_rows,
                conn=conn,
            )

        data = {
            "periods": {
                "period_a": {"start": period_a_start, "end": period_a_end},
                "period_b": {"start": period_b_start, "end": period_b_end},
            },
            "global": global_section,
            "per_sport": per_sport_section,
        }

    completeness = CompletenessMetadata(
        status="complete",
        missing=[],
        coverage={
            "global_metrics": sorted(global_section["metrics"].keys()),
            "per_sport": sorted(per_sport_section.keys()),
            "supported_missing_reasons": sorted(COMPARISON_MISSING_REASONS),
        },
    )
    return ServiceEnvelope(
        data=data,
        freshness=freshness,
        completeness=completeness,
        warnings=[],
        rationale=[ServiceRationale(code="metric_bundle_from_local_mirror", message="Period comparison returns factual metric deltas and coverage only.")],
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
        first_training_day = repo.first_activity_day(sport_filter="training")
        history_daily_trimp = repo.effective_trimp_history(first_training_day, today_day.isoformat(), sport_filter="training") if first_training_day else {}
        baseline = calc_banister(history_daily_trimp, today_day.isoformat()) if history_daily_trimp else None
        if baseline is None:
            baseline_fitness = 0.0
            baseline_fatigue = 0.0
        else:
            baseline_fitness = baseline.fitness
            baseline_fatigue = baseline.fatigue

        report = daily_report_from_connection(conn, now_local=checked_at)
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
                "progressive_load_bonus": report.progressive_signal.load_bonus if report.progressive_signal else None,
                "activity_template_trimp": assumptions.get("activity_template_trimp"),
                "post_weekend_monday_form": metadata.get("post_weekend_monday_form"),
                "scenario_metadata": metadata,
            }

    completeness = CompletenessMetadata(
        status="complete",
        missing=[],
        coverage={"scenarios": scenarios, "horizon_days": horizon_days},
    )
    return ServiceEnvelope(
        data={"target_date": target_date, "scenarios": scenario_payload},
        freshness=freshness,
        completeness=completeness,
        warnings=[],
        rationale=[ServiceRationale(code="metric_bundle_from_local_mirror", message="Projection contains model simulation facts only.")],
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
                warnings=[ServiceWarning(code="workout_not_found", severity="warning", message="Requested workout was not found.")],
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
