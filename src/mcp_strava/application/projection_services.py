"""Projection-focused application services for MCP-facing tool backends."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from typing import Any

from mcp_strava.adapters.duckdb.connection import ReadConn
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.application.freshness import build_freshness_metadata
from mcp_strava.constants import Config
from mcp_strava.refresh.policy import RefreshPolicy
from mcp_strava.settings import get_settings
from mcp_strava.training import forward_simulate
from mcp_strava.types import CompletenessMetadata, ServiceEnvelope, ServiceRationale

PROJECTION_MAX_HORIZON_DAYS = 90
MAINTAIN_LOOKBACK_DAYS = 28
WEEKEND_DAYS = {4, 5, 6}

# Canonical set of projection scenarios. Single source of truth: the MCP tool's
# `scenarios` enum is derived from this, so the schema and the validator cannot drift.
SUPPORTED_PROJECTION_SCENARIOS = ("rest", "easy", "maintain", "custom")


def _connection_context(connection):
    return nullcontext(connection) if connection is not None else ReadConn()


def _policy() -> RefreshPolicy:
    return RefreshPolicy.from_settings(get_settings())


def _freshness_clock(now: datetime | None) -> datetime:
    # Freshness compares `now` against last_success_at, stored UTC-naive (WR-02 basis;
    # see application/freshness.py::_freshness_now). Always hand the freshness layer a
    # UTC-naive instant — an aware datetime here raises "can't subtract offset-naive
    # and offset-aware datetimes" inside _age_seconds.
    if now is None:
        return datetime.now(UTC).replace(tzinfo=None)
    return (now.astimezone(UTC) if now.tzinfo is not None else now).replace(tzinfo=None)


def _read_model_status(repo) -> dict[str, Any]:
    return repo.read_model_status(metric_version=repo.current_metric_version())


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


def _next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


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
) -> tuple[list[float], dict[str, Any]]:
    if scenario == "rest":
        return [0.0 for _ in days], {"template_source": "rest_zero_load"}
    if scenario == "easy":
        easy_value = float(getattr(Config.Plan, "TRIMP_EASY", 80))
        return [easy_value for _ in days], {
            "template_source": "config_plan_constants",
            "activity_template_trimp": easy_value,
        }
    if scenario == "maintain":
        lookback_start = (today_day - timedelta(days=MAINTAIN_LOOKBACK_DAYS - 1)).isoformat()
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


def _daily_trimp_history(repo: DuckDBRepository, start_day: str, end_day: str) -> dict[str, float]:
    rows = repo.fetch_daily_load_facts(
        start_day, _next_day(end_day), scope="all", metric_version=repo.current_metric_version()
    )
    # DailyLoadFactRow fields are ``object``; str() and float() narrow safely at runtime.
    return {str(row["day"]): float(row["effective_trimp"] or 0.0) for row in rows}  # type: ignore[arg-type]


def project_fitness_state_service(
    *,
    target_date: str,
    scenarios: Sequence[str],
    custom_daily_trimp=None,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    allowed = set(SUPPORTED_PROJECTION_SCENARIOS)
    if any(name not in allowed for name in scenarios):
        raise ValueError(f"Supported scenarios are: {', '.join(SUPPORTED_PROJECTION_SCENARIOS)}")

    checked_at = now or datetime.now()  # noqa: DTZ005 — local wall-clock for as_of_day/relative_time display (freshness uses _freshness_clock)
    today_day = checked_at.date()
    target_day = date.fromisoformat(target_date)
    horizon_days = (target_day - today_day).days
    if horizon_days < 0:
        raise ValueError("target_date must be today or later")
    if horizon_days > PROJECTION_MAX_HORIZON_DAYS:
        raise ValueError(f"projection horizon must be <= {PROJECTION_MAX_HORIZON_DAYS} days")

    days = [today_day + timedelta(days=offset) for offset in range(horizon_days + 1)]
    with _connection_context(connection) as conn:
        repo = DuckDBRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, _freshness_clock(now), _policy(), signal_first_use=signal_first_use)
        read_model = _read_model_status(repo)
        version = repo.current_metric_version()
        baseline = repo.fetch_latest_training_model_day(version, as_of_day=today_day.isoformat())
        if baseline is None:
            baseline = repo.fetch_latest_training_model_day(version)
        history_start = (today_day - timedelta(days=MAINTAIN_LOOKBACK_DAYS - 1)).isoformat()
        history_daily_trimp = _daily_trimp_history(repo, history_start, today_day.isoformat())

    # baseline["fitness"]/["fatigue"] are ``object`` (TrainingModelDayRow); float() narrows.
    baseline_fitness = float(baseline["fitness"] or 0.0) if baseline is not None else 0.0  # type: ignore[arg-type]
    baseline_fatigue = float(baseline["fatigue"] or 0.0) if baseline is not None else 0.0  # type: ignore[arg-type]
    missing = [] if baseline is not None else ["read_model_unavailable"]
    scenario_payload: dict[str, dict[str, Any]] = {}
    for scenario in scenarios:
        trimps, assumptions = _scenario_trimps(
            scenario=scenario,
            days=days,
            today_day=today_day,
            history_daily_trimp=history_daily_trimp,
            custom_daily_trimp=custom_daily_trimp,
        )
        # ALPHA constants are computed in a nested class body (pow() expression),
        # which pyright infers as Any. Cast to float once here to keep the call sites typed.
        alpha_fitness: float = float(Config.Model.Banister.ALPHA_FITNESS)  # type: ignore[arg-type]
        alpha_fatigue: float = float(Config.Model.Banister.ALPHA_FATIGUE)  # type: ignore[arg-type]
        sim = forward_simulate(
            baseline_fitness,
            baseline_fatigue,
            trimps,
            today_day,
            alpha_fitness,
            alpha_fatigue,
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
        metadata: dict[str, Any] = {"missing_reasons": []}
        if target_day.weekday() in WEEKEND_DAYS:
            monday = target_day + timedelta(days=(7 - target_day.weekday()))
            monday_sim = forward_simulate(
                baseline_fitness,
                baseline_fatigue,
                trimps + [0.0] * (monday - target_day).days,
                today_day,
                alpha_fitness,
                alpha_fatigue,
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
