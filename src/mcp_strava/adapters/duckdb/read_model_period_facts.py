"""Daily, model, and rolling fact construction for read-model materialization."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from mcp_strava.adapters.duckdb.daily_load_queries import daily_load_points_between
from mcp_strava.adapters.duckdb.read_model_materializer_utils import _date_range, _json_list, _median_or_none
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.metric_registry import MATERIALIZED_ROLLING_WINDOW_DAYS
from mcp_strava.training import acwr_zone, calc_banister_series, form_zone

ROLLING_WINDOWS = MATERIALIZED_ROLLING_WINDOW_DAYS


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
