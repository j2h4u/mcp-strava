"""Product service allowlist for future MCP dispatch."""

from __future__ import annotations

from collections.abc import Callable

from mcp_strava.application.freshness import get_freshness_service
from mcp_strava.application.metric_services import (
    get_fitness_state_service,
    get_workout_detail_service,
    list_workouts_service,
)
from mcp_strava.application.product_facts import (
    get_daily_brief_facts_service,
    get_historical_facts_service,
    get_weekly_digest_facts_service,
)
from mcp_strava.types import ServiceEnvelope

PRODUCT_SERVICE_NAMES = (
    "daily_brief_facts",
    "weekly_digest_facts",
    "historical_facts",
    "recent_workouts",
    "workout_detail",
    "fitness_state",
    "freshness",
)

PRODUCT_SERVICES: dict[str, Callable[..., ServiceEnvelope]] = {
    "daily_brief_facts": get_daily_brief_facts_service,
    "weekly_digest_facts": get_weekly_digest_facts_service,
    "historical_facts": get_historical_facts_service,
    "recent_workouts": list_workouts_service,
    "workout_detail": get_workout_detail_service,
    "fitness_state": get_fitness_state_service,
    "freshness": get_freshness_service,
}
