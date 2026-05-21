"""Application services for recent workouts and per-workout analytics."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import datetime

from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.application.freshness import build_freshness_metadata
from mcp_strava.db import DbConn
from mcp_strava.metrics import enrich_activity
from mcp_strava.refresh.policy import RefreshPolicy
from mcp_strava.settings import get_settings
from mcp_strava.types import (
    CompletenessMetadata,
    EnrichedActivity,
    ServiceEnvelope,
    ServiceRationale,
    ServiceWarning,
    parse_strava_activity,
)


def _connection_context(connection):
    return nullcontext(connection) if connection is not None else DbConn()


def _policy() -> RefreshPolicy:
    return RefreshPolicy.from_settings(get_settings())


def _compact_activity(conn, repo: SQLiteRepository, row) -> dict[str, object]:
    raw_summary = json.loads(row.summary_json) if row.summary_json else {}
    summary = parse_strava_activity(raw_summary) if raw_summary else None
    return {
        "id": row.id,
        "date": row.date[:10],
        "name": row.name,
        "sport_type": row.sport_type,
        "distance_km": round(row.distance / 1000, 2),
        "moving_time_min": round(row.moving_time / 60, 1),
        "trimp": repo.activity_trimp(row.id),
        "avg_hr": summary.average_heartrate if summary else None,
        "max_hr": int(round(summary.max_heartrate)) if summary and summary.max_heartrate else None,
    }


def _warnings_from_completeness(completeness: CompletenessMetadata) -> list[ServiceWarning]:
    messages = {
        "missing_hr": "Workout has no heart-rate summary or heart-rate stream data.",
        "missing_streams": "Workout has no stream rows in the local mirror.",
        "metric_unavailable": "One or more stream-derived workout metrics are unavailable.",
        "workout_not_found": "Workout was not found in the local mirror.",
    }
    return [
        ServiceWarning(
            code=code,
            severity="warning",
            message=messages.get(code, "Workout data is incomplete."),
        )
        for code in completeness.missing
    ]


def _workout_completeness(activity: EnrichedActivity) -> CompletenessMetadata:
    missing: list[str] = []
    if activity.avg_hr is None:
        missing.append("missing_hr")
    stream_metrics = (
        activity.hr_recovery,
        activity.vertical_speed,
        activity.cc,
        activity.cardiac_drift,
        activity.hrr_pct,
    )
    if all(value is None for value in stream_metrics):
        missing.append("missing_streams")
    elif any(value is None for value in stream_metrics):
        missing.append("metric_unavailable")

    return CompletenessMetadata(
        status="partial" if missing else "complete",
        missing=missing,
        coverage={
            "has_avg_hr": activity.avg_hr is not None,
            "has_cc": activity.cc is not None,
            "has_cardiac_drift": activity.cardiac_drift is not None,
            "has_hr_recovery": activity.hr_recovery is not None,
            "has_vertical_speed": activity.vertical_speed is not None,
            "has_hrr_pct": activity.hrr_pct is not None,
        },
    )


def get_recent_workouts_service(
    limit: int = 15,
    *,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    """Return compact recent workouts from the local mirror."""
    checked_at = now or datetime.now()
    with _connection_context(connection) as conn:
        repo = SQLiteRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, checked_at, _policy(), signal_first_use=signal_first_use)
        rows = repo.recent_activities(limit)
        data = [_compact_activity(conn, repo, row) for row in rows]

    completeness = CompletenessMetadata(
        status="complete",
        missing=[],
        coverage={"count": len(data), "limit": limit},
    )
    return ServiceEnvelope(
        data=data,
        freshness=freshness,
        completeness=completeness,
        warnings=[],
        rationale=[
            ServiceRationale(
                code="recent_workouts_from_mirror",
                message="Recent workouts are read from local SQLite mirror rows.",
            )
        ],
    )


def get_workout_analytics_service(
    activity_id: int | str,
    *,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    """Return enriched analytics for a single local workout."""
    checked_at = now or datetime.now()
    with _connection_context(connection) as conn:
        repo = SQLiteRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, checked_at, _policy(), signal_first_use=signal_first_use)
        resolved_id = repo.latest_activity_id() if activity_id == "latest" else int(activity_id)
        row = repo.activity_by_id(resolved_id) if resolved_id is not None else None
        if row is None:
            completeness = CompletenessMetadata(
                status="unavailable",
                missing=["workout_not_found"],
                coverage={"activity_id": activity_id},
            )
            return ServiceEnvelope(
                data=None,
                freshness=freshness,
                completeness=completeness,
                warnings=_warnings_from_completeness(completeness),
                rationale=[
                    ServiceRationale(
                        code="workout_not_found",
                        message="Requested workout id was not found in the local mirror.",
                    )
                ],
            )
        data = enrich_activity(conn, row)
        completeness = _workout_completeness(data)

    return ServiceEnvelope(
        data=data,
        freshness=freshness,
        completeness=completeness,
        warnings=_warnings_from_completeness(completeness),
        rationale=[
            ServiceRationale(
                code="workout_analytics_from_mirror",
                message="Workout analytics reuse existing local enrichment calculations.",
            )
        ],
    )
