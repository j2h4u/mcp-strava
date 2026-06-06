from __future__ import annotations

from typing import TypedDict

DEFAULT_TIMEOUT_SECONDS = 5.0

DEFAULT_LATENCY_WARMUP = 2

DEFAULT_LATENCY_SAMPLES = 20

DEFAULT_LATENCY_P95_MS = 100.0

EXPECTED_TOOL_NAMES = {
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
    "get_training_aggregates",
}

LATENCY_TOOL_ORDER = [
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
    "get_training_aggregates",
]

PRODUCT_BUNDLE_SMOKE_IDS = ("daily_brief", "weekly_digest", "historical_facts")


class SmokeResult(TypedDict):
    """Return shape of :func:`run_basic_smoke`."""

    status: str
    mode: str
    tools: list[str]
    called: list[str]
    data_shapes: dict[str, object]
    warnings: dict[str, object]


class LiveSmokeResult(TypedDict):
    """Return shape of :func:`run_live_smoke` (superset of :class:`SmokeResult`)."""

    status: str
    mode: str
    tools: list[str]
    called: list[str]
    aggregate_bundles: list[str]
    workout_id: int
    data_shapes: dict[str, object]
    warnings: dict[str, object]


class LatencyToolResult(TypedDict):
    """Per-tool metrics within :class:`LatencyGateResult`."""

    status: str
    tool_name: str
    arguments: dict[str, object]
    samples: int
    warmup: int
    p50_ms: float
    p95_ms: float
    max_ms: float
    threshold_ms: float


class LatencyGateResult(TypedDict):
    """Return shape of :func:`run_warm_latency_gate` / :func:`measure_warm_tool_latency`."""

    status: str
    mode: str
    startup_ms: float
    tools: dict[str, LatencyToolResult]


class McpClientError(RuntimeError):
    """Raised when the MCP endpoint or protocol response is invalid."""
