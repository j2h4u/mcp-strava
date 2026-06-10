"""Strava adapter package."""

from mcp_strava.adapters.strava.client import StravaClient, _build_strava_transport
from mcp_strava.adapters.strava.clock import SystemClock, SystemSleeper
from mcp_strava.adapters.strava.rate_limit import RateLimitDecision, RateLimitPolicy
from mcp_strava.adapters.strava.token_provider import FileTokenProvider
from mcp_strava.adapters.strava.token_refresh import TokenRefreshTransport
from mcp_strava.adapters.strava.transport import StravaTransport
from mcp_strava.adapters.strava.types import (
    Clock,
    RefreshedTokens,
    RefreshReason,
    Sleeper,
    StravaRateInfo,
    StravaResponse,
    StravaUnavailableError,
)

__all__ = [
    "Clock",
    "FileTokenProvider",
    "RateLimitDecision",
    "RateLimitPolicy",
    "RefreshReason",
    "RefreshedTokens",
    "Sleeper",
    "StravaClient",
    "StravaRateInfo",
    "StravaResponse",
    "StravaTransport",
    "StravaUnavailableError",
    "SystemClock",
    "SystemSleeper",
    "TokenRefreshTransport",
    "_build_strava_transport",
]
