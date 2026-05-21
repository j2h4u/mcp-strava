"""Product service allowlist for future MCP dispatch."""

from __future__ import annotations

from collections.abc import Callable

from mcp_strava.application.freshness import get_freshness_service
from mcp_strava.application.reports import get_daily_report_service, get_weekly_summary_service
from mcp_strava.application.workouts import get_recent_workouts_service, get_workout_analytics_service
from mcp_strava.types import ServiceEnvelope

PRODUCT_SERVICE_NAMES = (
    "daily_report",
    "weekly_summary",
    "recent_workouts",
    "workout_analytics",
    "freshness",
)

PRODUCT_SERVICES: dict[str, Callable[..., ServiceEnvelope]] = {
    "daily_report": get_daily_report_service,
    "weekly_summary": get_weekly_summary_service,
    "recent_workouts": get_recent_workouts_service,
    "workout_analytics": get_workout_analytics_service,
    "freshness": get_freshness_service,
}
