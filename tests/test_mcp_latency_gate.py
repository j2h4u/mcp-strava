from __future__ import annotations

import asyncio
from typing import Any

import pytest

from mcp_strava.devtools.mcp_client.client import (
    DEFAULT_LATENCY_P95_MS,
    EXPECTED_TOOL_NAMES,
    McpClientError,
    measure_warm_tool_latency,
    run_warm_latency_gate,
)


class FakeLatencyClient:
    def __init__(self, *, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((name, arguments or {}))
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return {
            "isError": False,
            "structuredContent": {
                "data": {"tool": name},
                "warnings": [],
            },
        }


def test_default_latency_gate_threshold_is_100_ms() -> None:
    assert DEFAULT_LATENCY_P95_MS == 100.0


def test_measure_warm_tool_latency_records_startup_separately() -> None:
    calls = [
        {"name": "get_fitness_state", "arguments": {}},
        {"name": "list_workouts", "arguments": {"limit": 1}},
    ]

    async def run() -> dict[str, Any]:
        client = FakeLatencyClient()
        result = await measure_warm_tool_latency(
            client,
            calls=calls,
            warmup=2,
            samples=3,
            p95_ms=500,
            startup_ms=123.4,
        )
        assert [name for name, _args in client.calls] == [
            "get_fitness_state",
            "get_fitness_state",
            "get_fitness_state",
            "get_fitness_state",
            "get_fitness_state",
            "list_workouts",
            "list_workouts",
            "list_workouts",
            "list_workouts",
            "list_workouts",
        ]
        return result

    result = asyncio.run(run())

    assert result["status"] == "ok"
    assert result["startup_ms"] == pytest.approx(123.4)
    assert set(result["tools"]) == {"get_fitness_state", "list_workouts"}
    for tool_result in result["tools"].values():
        assert tool_result["status"] == "ok"
        assert tool_result["samples"] == 3
        assert {"p50_ms", "p95_ms", "max_ms", "threshold_ms"} <= set(tool_result)


def test_measure_warm_tool_latency_fails_when_any_tool_exceeds_p95() -> None:
    async def run() -> None:
        client = FakeLatencyClient(delay_seconds=0.005)
        await measure_warm_tool_latency(
            client,
            calls=[{"name": "get_fitness_state", "arguments": {}}],
            warmup=0,
            samples=3,
            p95_ms=1,
        )

    with pytest.raises(McpClientError, match="p95"):
        asyncio.run(run())


def test_default_latency_gate_call_set_covers_all_product_tools() -> None:
    from mcp_strava.devtools.mcp_client.client import default_warm_latency_calls

    calls = default_warm_latency_calls(workout_id=701, today="2026-05-24")

    assert {call["name"] for call in calls} == EXPECTED_TOOL_NAMES
    assert all(isinstance(call.get("arguments"), dict) for call in calls)
    assert next(call for call in calls if call["name"] == "get_workout_detail")["arguments"] == {"workout_id": 701}


def test_warm_latency_gate_uses_missing_workout_fallback_when_list_is_empty() -> None:
    class EmptyWorkoutClient(FakeLatencyClient):
        async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
            self.calls.append((name, arguments or {}))
            data: object = [] if name == "list_workouts" else {"tool": name}
            return {"isError": False, "structuredContent": {"data": data, "warnings": []}}

    async def run() -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
        client = EmptyWorkoutClient()
        result = await run_warm_latency_gate(client, warmup=0, samples=1, p95_ms=500)
        return result, client.calls

    result, calls = asyncio.run(run())

    assert result["status"] == "ok"
    assert ("get_workout_detail", {"workout_id": 0}) in calls
