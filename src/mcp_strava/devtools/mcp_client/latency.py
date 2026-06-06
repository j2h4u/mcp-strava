from __future__ import annotations

import math
import time
from datetime import date, timedelta

from mcp_strava.devtools.mcp_client.contracts import (
    DEFAULT_LATENCY_P95_MS,
    DEFAULT_LATENCY_SAMPLES,
    DEFAULT_LATENCY_WARMUP,
    LatencyGateResult,
    LatencyToolResult,
    McpClientError,
)
from mcp_strava.devtools.mcp_client.transport import HttpMcpClient, StdioMcpClient
from mcp_strava.devtools.mcp_client.utils import (
    _coerce_day,
    _extract_first_workout_id,
    _product_bundle_aggregate_calls,
    _require_success,
)


def default_warm_latency_calls(*, workout_id: int, today: str | date | None = None) -> list[dict[str, object]]:
    if workout_id < 0:
        raise ValueError("workout_id must be zero or positive")
    today_date = _coerce_day(today)

    return [
        {"name": "get_fitness_state", "arguments": {}},
        {"name": "list_workouts", "arguments": {"limit": 10}},
        {"name": "get_workout_detail", "arguments": {"workout_id": workout_id}},
        {
            "name": "compare_periods",
            "arguments": {
                "period_a_start": (today_date - timedelta(days=13)).isoformat(),
                "period_a_end": (today_date - timedelta(days=7)).isoformat(),
                "period_b_start": (today_date - timedelta(days=6)).isoformat(),
                "period_b_end": today_date.isoformat(),
            },
        },
        {
            "name": "project_fitness_state",
            "arguments": {
                "target_date": (today_date + timedelta(days=7)).isoformat(),
                "scenarios": ["rest", "maintain"],
            },
        },
        *_product_bundle_aggregate_calls(today_date),
    ]


async def resolve_default_warm_latency_calls(
    client: StdioMcpClient | HttpMcpClient,
    *,
    today: str | date | None = None,
) -> list[dict[str, object]]:
    workouts = _require_success("list_workouts", await client.call_tool("list_workouts", {"limit": 1}))
    try:
        workout_id = _extract_first_workout_id(workouts)
    except McpClientError:
        workout_id = 0
    return default_warm_latency_calls(workout_id=workout_id, today=today)


async def run_warm_latency_gate(
    client: StdioMcpClient | HttpMcpClient,
    *,
    calls: list[dict[str, object]] | None = None,
    warmup: int = DEFAULT_LATENCY_WARMUP,
    samples: int = DEFAULT_LATENCY_SAMPLES,
    p95_ms: float = DEFAULT_LATENCY_P95_MS,
    startup_ms: float = 0.0,
    raise_on_failure: bool = True,
) -> LatencyGateResult:
    selected_calls = calls if calls is not None else await resolve_default_warm_latency_calls(client)
    return await measure_warm_tool_latency(
        client,
        calls=selected_calls,
        warmup=warmup,
        samples=samples,
        p95_ms=p95_ms,
        startup_ms=startup_ms,
        raise_on_failure=raise_on_failure,
    )


async def measure_warm_tool_latency(
    client: StdioMcpClient | HttpMcpClient,
    *,
    calls: list[dict[str, object]],
    warmup: int = DEFAULT_LATENCY_WARMUP,
    samples: int = DEFAULT_LATENCY_SAMPLES,
    p95_ms: float = DEFAULT_LATENCY_P95_MS,
    startup_ms: float = 0.0,
    raise_on_failure: bool = True,
) -> LatencyGateResult:
    normalized_calls = _normalize_latency_calls(calls)
    if warmup < 0:
        raise ValueError("warmup must be zero or positive")
    if samples <= 0:
        raise ValueError("samples must be positive")
    if p95_ms <= 0:
        raise ValueError("p95_ms must be positive")
    if startup_ms < 0:
        raise ValueError("startup_ms must be zero or positive")

    tool_results: dict[str, LatencyToolResult] = {}
    exceeded: list[str] = []
    result_key_counts: dict[str, int] = {}
    for call in normalized_calls:
        name = str(call["name"])  # _normalize_latency_calls guarantees "name" is a non-empty str
        raw_args = call["arguments"]
        arguments: dict[str, object] = dict(raw_args) if isinstance(raw_args, dict) else {}
        result_key = _latency_result_key(name, arguments, result_key_counts)
        for _ in range(warmup):
            _require_success(name, await client.call_tool(name, arguments))

        timings: list[float] = []
        for _ in range(samples):
            started_at = time.perf_counter()
            _require_success(name, await client.call_tool(name, arguments))
            timings.append((time.perf_counter() - started_at) * 1000)

        p50_value = _percentile(timings, 50)
        p95_value = _percentile(timings, 95)
        max_value = max(timings)
        status = "ok" if p95_value <= p95_ms else "exceeded"
        if status != "ok":
            exceeded.append(result_key)
        tool_results[result_key] = LatencyToolResult(
            status=status,
            tool_name=name,
            arguments=arguments,
            samples=samples,
            warmup=warmup,
            p50_ms=round(p50_value, 3),
            p95_ms=round(p95_value, 3),
            max_ms=round(max_value, 3),
            threshold_ms=p95_ms,
        )

    result = LatencyGateResult(
        status="ok" if not exceeded else "failed",
        mode="warm_latency",
        startup_ms=round(startup_ms, 3),
        tools=tool_results,
    )
    if exceeded and raise_on_failure:
        details = ", ".join(
            f"{key} (p95={tool_results[key]['p95_ms']}ms > {tool_results[key]['threshold_ms']}ms)" for key in exceeded
        )
        raise McpClientError(f"p95 threshold exceeded for tools: {details}")
    return result


def _normalize_latency_calls(raw_calls: object) -> list[dict[str, object]]:
    if not isinstance(raw_calls, list) or not raw_calls:
        raise ValueError("latency calls must be a non-empty list")
    normalized: list[dict[str, object]] = []
    for index, call in enumerate(raw_calls, start=1):
        if not isinstance(call, dict):
            raise ValueError(f"latency call {index} must be an object")
        name = call.get("name")
        arguments = call.get("arguments", {})
        if not isinstance(name, str) or not name:
            raise ValueError(f"latency call {index} is missing string field 'name'")
        if not isinstance(arguments, dict):
            raise ValueError(f"latency call {index} field 'arguments' must be an object")
        normalized.append({"name": name, "arguments": arguments})
    return normalized


def _latency_result_key(name: str, arguments: dict[str, object], counts: dict[str, int]) -> str:
    metric_bundle = arguments.get("metric_bundle") if name == "get_training_aggregates" else None
    base = f"{name}:{metric_bundle}" if isinstance(metric_bundle, str) and metric_bundle else name
    count = counts.get(base, 0) + 1
    counts[base] = count
    return base if count == 1 else f"{base}#{count}"


def _optional_int(value: object, *, default: int, field: str) -> int:
    if value is None:
        return default
    if not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _optional_float(value: object, *, default: float, field: str) -> float:
    if value is None:
        return default
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    return float(value)


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        raise ValueError("values must not be empty")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((percentile / 100) * len(ordered)) - 1))
    return ordered[index]
