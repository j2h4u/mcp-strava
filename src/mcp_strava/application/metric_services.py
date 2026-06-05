"""Metric-focused application services for MCP-facing tool backends."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import date, datetime, timedelta
from typing import Any, cast

from mcp_strava.adapters.duckdb.connection import ReadConn
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.duckdb.repository_models import (
    RollingPeriodFactRow,
    TrainingModelDayRow,
)
from mcp_strava.application.activity_payloads import activity_payload, kudos_names, parse_json_list
from mcp_strava.application.freshness import _freshness_now, build_freshness_metadata
from mcp_strava.metric_registry import METRIC_REGISTRY
from mcp_strava.refresh.policy import RefreshPolicy
from mcp_strava.settings import get_settings
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


def _project_fitness_state_metrics(
    model: TrainingModelDayRow | None,
    rolling: dict[int, RollingPeriodFactRow],
) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if model is not None:
        # TypedDict fields are all ``object``; treat as a plain dict for dynamic key
        # access (MODEL_FACTS maps metric_id → column name, both str, all defined fields).
        model_dict = cast("dict[str, object]", model)
        for metric_id, column in MODEL_FACTS.items():
            _metric_if_registered(data, metric_id, model_dict.get(column))
    for metric_id, (window, column, scale) in ROLLING_FACTS.items():
        row = rolling.get(window)
        # RollingPeriodFactRow fields are all ``object``; dynamic column access via cast.
        raw_value: object = cast("dict[str, object]", row).get(column) if row is not None else None
        _metric_if_registered(
            data,
            metric_id,
            round(float(raw_value) * scale, 3) if raw_value is not None else None,  # type: ignore[arg-type]
        )
    return data


def _connection_context(connection):
    return nullcontext(connection) if connection is not None else ReadConn()


def _policy() -> RefreshPolicy:
    return RefreshPolicy.from_settings(get_settings())


def _metric_if_registered(payload: dict[str, Any], metric_id: str, value) -> None:
    if metric_id in METRIC_REGISTRY:
        payload[metric_id] = value


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def _read_model_status(repo) -> dict[str, Any]:
    return repo.read_model_status(metric_version=repo.current_metric_version())


def _coverage_with_read_model(read_model: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    coverage = dict(extra or {})
    coverage["read_model"] = read_model
    return coverage


def _status_from_read_model(read_model: dict[str, Any], *, has_data: bool, missing: list[str]) -> str:
    if not has_data:
        return "unavailable"
    if read_model.get("status") == "stale":
        return "stale"
    if missing:
        return "partial"
    return "complete"


def _rationale(message: str) -> list[ServiceRationale]:
    return [ServiceRationale(code="metric_bundle_from_read_model", message=message)]


def _latest_as_of_day(checked_at: datetime) -> str:
    return checked_at.date().isoformat()


def _freshness_clock(now: datetime | None) -> datetime:
    """The shared UTC-naive instant for time-difference computations: freshness
    staleness (vs UTC-stored last_success_at) and activity recency (vs UTC
    start_date).

    When the caller supplies an explicit `now`, honor it (tests/callers control
    the clock). Otherwise default to a UTC-naive instant so those diffs are
    offset-correct. The local `checked_at` is kept separately for the as_of_day
    calendar derivation — that stays local; only this instant clock is UTC.
    """
    return now if now is not None else _freshness_now()


def _rolling_by_window(repo: DuckDBRepository, as_of_day: str) -> dict[int, RollingPeriodFactRow]:
    windows = tuple(sorted({window for window, _column, _scale in ROLLING_FACTS.values()}))
    version = repo.current_metric_version()
    return repo.fetch_rolling_period_facts_by_windows(
        as_of_day,
        windows,
        scope="all",
        metric_version=version,
    )


def get_fitness_state_service(
    *,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    checked_at = now or datetime.now()  # noqa: DTZ005 — local wall-clock for as_of_day/relative_time display (freshness uses _freshness_clock)
    with _connection_context(connection) as conn:
        repo = DuckDBRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, _freshness_clock(now), _policy(), signal_first_use=signal_first_use)
        read_model = _read_model_status(repo)
        as_of_day = _latest_as_of_day(checked_at)
        version = repo.current_metric_version()
        model = repo.fetch_latest_training_model_day(version, as_of_day=as_of_day)
        if model is None:
            model = repo.fetch_latest_training_model_day(version)
        rolling = _rolling_by_window(repo, str(model["day"]) if model is not None else as_of_day)

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
    instant = _freshness_clock(now)  # UTC instant for freshness + recency diffs
    start_day = start_date or "0001-01-01"
    end_day = _next_day(end_date) if end_date else "9999-12-31"
    with _connection_context(connection) as conn:
        repo = DuckDBRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, instant, _policy(), signal_first_use=signal_first_use)
        rows = repo.fetch_activity_metric_facts(
            start_day,
            end_day,
            sport=sport,
            metric_version=repo.current_metric_version(),
            limit=limit,
        )
        read_model = _read_model_status(repo)
        data = [activity_payload(row, now=instant) for row in rows]

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
                "start_time_local",
                "relative_time",
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
    instant = _freshness_clock(now)  # UTC instant for freshness + recency diffs
    with _connection_context(connection) as conn:
        repo = DuckDBRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, instant, _policy(), signal_first_use=signal_first_use)
        read_model = _read_model_status(repo)
        resolved_id = repo.latest_activity_id() if activity_id == "latest" else int(activity_id)
        row = (
            repo.fetch_activity_metric_fact(resolved_id, metric_version=repo.current_metric_version())
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

        assert resolved_id is not None, "row is non-None only when resolved_id is non-None"
        data = activity_payload(
            row,
            now=instant,
            kudos_names=kudos_names(repo.kudos_for_activity(resolved_id)),
            include_detail_context=True,
        )
        missing = parse_json_list(row["missing_reasons_json"])
        stream_derived: list[object] = [
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
