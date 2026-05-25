from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from mcp_strava.devtools.mcp_client.cli import main
from mcp_strava.devtools.mcp_client.client import (
    EXPECTED_TOOL_NAMES,
    McpClientError,
    StdioMcpClient,
    default_warm_latency_calls,
    execute_script_steps,
)


class FakeWarmScriptClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        del arguments
        self.calls.append(name)
        return {"isError": False, "structuredContent": {"data": {"tool": name}, "warnings": []}}


def _fake_server_command() -> list[str]:
    return [sys.executable, str(Path(__file__).parent / "fixtures" / "fake_mcp_server.py")]


def test_mcp_test_client_lists_tools() -> None:
    async def run() -> list[dict]:
        async with StdioMcpClient(_fake_server_command()) as client:
            return await client.list_tools()

    tools = asyncio.run(run())
    assert [tool["name"] for tool in tools] == ["Echo", "Fail"]


def test_mcp_test_client_calls_tool() -> None:
    async def run() -> dict:
        async with StdioMcpClient(_fake_server_command()) as client:
            return await client.call_tool("Echo", {"value": "hello"})

    result = asyncio.run(run())
    assert result["isError"] is False
    assert result["structuredContent"] == {"value": "hello"}


def test_mcp_test_client_script_assertions() -> None:
    steps = [
        {
            "action": "list_tools",
            "expect": {
                "tool_names_include": ["Echo"],
                "tool_names_exclude": ["sync", "backfill", "sql"],
            },
        },
        {
            "action": "call_tool",
            "name": "Echo",
            "arguments": {"value": "script"},
            "expect": {
                "is_error": False,
                "path_equals": {"structuredContent.value": "script"},
            },
        },
    ]

    async def run() -> list[dict]:
        async with StdioMcpClient(_fake_server_command()) as client:
            return await execute_script_steps(client, steps)

    results = asyncio.run(run())
    assert results[0]["action"] == "list_tools"
    assert results[1]["name"] == "Echo"


def test_mcp_test_client_script_assertion_failure() -> None:
    steps = [{"action": "list_tools", "expect": {"tool_names_exclude": ["Echo"]}}]

    async def run() -> None:
        async with StdioMcpClient(_fake_server_command()) as client:
            await execute_script_steps(client, steps)

    with pytest.raises(McpClientError, match="forbidden tools"):
        asyncio.run(run())


def test_mcp_test_client_script_can_measure_repeated_warm_samples_for_all_product_tools() -> None:
    calls = [{"name": name, "arguments": {}} for name in sorted(EXPECTED_TOOL_NAMES)]
    steps = [
        {
            "action": "measure_warm_tool_latency",
            "calls": calls,
            "warmup": 1,
            "samples": 2,
            "p95_ms": 500,
            "expect": {
                "latency_status": "ok",
                "tool_names_include": sorted(EXPECTED_TOOL_NAMES),
            },
        }
    ]

    async def run() -> tuple[list[dict], list[str]]:
        client = FakeWarmScriptClient()
        results = await execute_script_steps(client, steps)
        return results, client.calls

    results, tool_calls = asyncio.run(run())

    assert results[0]["action"] == "measure_warm_tool_latency"
    assert set(results[0]["result"]["tools"]) == EXPECTED_TOOL_NAMES
    for name in sorted(EXPECTED_TOOL_NAMES):
        assert tool_calls.count(name) == 3


def test_default_warm_latency_calls_include_training_aggregates() -> None:
    calls = default_warm_latency_calls(workout_id=701, today="2026-05-24")

    aggregate_call = next(call for call in calls if call["name"] == "get_training_aggregates")

    assert {call["name"] for call in calls} == EXPECTED_TOOL_NAMES | {"get_training_aggregates"}
    assert aggregate_call["arguments"] == {
        "start_date": "2026-04-26",
        "end_date": "2026-05-24",
        "bucket": "week",
        "metric_bundle": "weekly_digest",
        "scope": "global",
    }


def test_mcp_test_client_cli_call_tool(capsys) -> None:
    exit_code = main(["call-tool", "--name", "Echo", "--arguments", '{"value":"cli"}', "--", *_fake_server_command()])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"value": "cli"' in captured.out
