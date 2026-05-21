"""Application services for daily and weekly training reports."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime

from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.analytics import weekly_digest
from mcp_strava.application.freshness import build_freshness_metadata
from mcp_strava.db import DbConn
from mcp_strava.refresh.policy import RefreshPolicy
from mcp_strava.report import daily_report_from_connection
from mcp_strava.settings import get_settings
from mcp_strava.types import (
    CompletenessMetadata,
    DailyReport,
    ServiceEnvelope,
    ServiceRationale,
    ServiceWarning,
    WeeklyDigest,
)


def _connection_context(connection):
    return nullcontext(connection) if connection is not None else DbConn()


def _policy() -> RefreshPolicy:
    return RefreshPolicy.from_settings(get_settings())


def _load_completeness(repo: SQLiteRepository, start_day: str, end_day: str) -> tuple[str, list[str], dict[str, object]]:
    points = repo.daily_load_points_between(start_day, end_day, sport_filter="training")
    partial_days = [point.date for point in points if point.status == "PARTIAL"]
    unknown_days = [point.date for point in points if point.status == "UNKNOWN"]
    missing: list[str] = []
    if partial_days:
        missing.append("missing_hr")
    if unknown_days:
        missing.append("missing_streams")
    status = "partial" if missing else "complete"
    return (
        status,
        missing,
        {
            "days": len(points),
            "partial_days": partial_days,
            "unknown_days": unknown_days,
        },
    )


def _daily_completeness(repo: SQLiteRepository, report: DailyReport) -> CompletenessMetadata:
    status, missing, coverage = _load_completeness(repo, report.window_start, report.today)
    missing_details = repo.activities_missing_details(report.window_start)
    if missing_details:
        missing.append("missing_details")
        status = "partial"
        coverage["missing_details_count"] = len(missing_details)
    if any(activity.avg_hr is None for activity in report.activities_14d):
        if "missing_hr" not in missing:
            missing.append("missing_hr")
        status = "partial"
    return CompletenessMetadata(status=status, missing=missing, coverage=coverage)


def _weekly_completeness(repo: SQLiteRepository, digest: WeeklyDigest, today: str) -> CompletenessMetadata:
    first_day = digest.period.get("first_activity") or today
    status, missing, coverage = _load_completeness(repo, first_day, today)
    this_week = digest.this_week or []
    if not this_week:
        missing.append("empty_weekly_history")
        status = "insufficient" if status == "complete" else status
    return CompletenessMetadata(status=status, missing=missing, coverage=coverage)


def _warnings_from_completeness(completeness: CompletenessMetadata) -> list[ServiceWarning]:
    messages = {
        "missing_hr": "Some mirrored activities do not have heart-rate data.",
        "missing_streams": "Some mirrored activities do not have stream data.",
        "missing_details": "Some mirrored activities do not have detailed payloads.",
        "empty_weekly_history": "No activity rows are available for this weekly summary.",
        "insufficient_history": "Not enough local mirror history is available.",
    }
    return [
        ServiceWarning(
            code=code,
            severity="warning",
            message=messages.get(code, "Local mirror data is incomplete."),
        )
        for code in completeness.missing
    ]


def _warnings_from_freshness(freshness) -> list[ServiceWarning]:
    if freshness.freshness_state not in {"aging", "stale"}:
        return []
    return [
        ServiceWarning(
            code="mirror_stale",
            severity="warning",
            message="Local mirror refresh is not recent.",
            field="last_successful_refresh_at",
        )
    ]


def get_daily_report_service(
    *,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    """Return the daily report through the shared product-service envelope."""
    checked_at = now or datetime.now()
    with _connection_context(connection) as conn:
        repo = SQLiteRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, checked_at, _policy(), signal_first_use=signal_first_use)
        report = daily_report_from_connection(conn, now_local=checked_at)
        completeness = _daily_completeness(repo, report)

    return ServiceEnvelope(
        data=report,
        freshness=freshness,
        completeness=completeness,
        warnings=_warnings_from_freshness(freshness) + _warnings_from_completeness(completeness),
        rationale=[
            ServiceRationale(
                code="daily_report_from_mirror",
                message="Daily report uses existing local mirror analytics calculations.",
            )
        ],
    )


def get_weekly_summary_service(
    *,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    """Return the weekly digest through the shared product-service envelope."""
    checked_at = now or datetime.now()
    with _connection_context(connection) as conn:
        repo = SQLiteRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, checked_at, _policy(), signal_first_use=signal_first_use)
        digest = weekly_digest(conn, today=checked_at.date())
        if digest is None:
            completeness = CompletenessMetadata(
                status="insufficient",
                missing=["insufficient_history"],
                coverage={"activities": 0},
            )
        else:
            completeness = _weekly_completeness(repo, digest, checked_at.date().isoformat())

    return ServiceEnvelope(
        data=digest,
        freshness=freshness,
        completeness=completeness,
        warnings=_warnings_from_freshness(freshness) + _warnings_from_completeness(completeness),
        rationale=[
            ServiceRationale(
                code="weekly_summary_from_mirror",
                message="Weekly summary uses existing local mirror analytics calculations.",
            )
        ],
    )
