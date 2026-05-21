"""Product service allowlist for future MCP dispatch."""

from __future__ import annotations

from collections.abc import Callable

from mcp_strava.application.freshness import get_freshness_service
from mcp_strava.types import ServiceEnvelope

PRODUCT_SERVICE_NAMES = (
    "daily_report",
    "weekly_summary",
    "recent_workouts",
    "workout_analytics",
    "freshness",
)

PRODUCT_SERVICES: dict[str, Callable[..., ServiceEnvelope]] = {
    "freshness": get_freshness_service,
}
