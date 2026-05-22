"""Product application services for local mirror analytics."""

from mcp_strava.application.freshness import build_freshness_metadata, get_freshness_service
from mcp_strava.application.metric_registry import (
    EXCLUDED_INTERPRETATIONS,
    MCP_TOOL_IDS,
    METRIC_REGISTRY,
    comparable_metrics,
    metric_catalog_payload,
    metric_definition,
    metrics_for_tool,
)
from mcp_strava.application.reports import get_daily_report_service, get_weekly_summary_service
from mcp_strava.application.registry import PRODUCT_SERVICE_NAMES, PRODUCT_SERVICES
from mcp_strava.application.workouts import get_recent_workouts_service, get_workout_analytics_service

__all__ = [
    "EXCLUDED_INTERPRETATIONS",
    "MCP_TOOL_IDS",
    "METRIC_REGISTRY",
    "PRODUCT_SERVICE_NAMES",
    "PRODUCT_SERVICES",
    "build_freshness_metadata",
    "comparable_metrics",
    "get_daily_report_service",
    "get_freshness_service",
    "get_recent_workouts_service",
    "get_weekly_summary_service",
    "get_workout_analytics_service",
    "metric_catalog_payload",
    "metric_definition",
    "metrics_for_tool",
]
