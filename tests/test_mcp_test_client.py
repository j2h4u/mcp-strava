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
    _warning_digest,
    default_warm_latency_calls,
    execute_script_steps,
    run_live_smoke,
)

EXPECTED_PRODUCT_BUNDLES = ("daily_brief", "weekly_digest", "historical_facts")


class FakeWarmScriptClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        del arguments
        self.calls.append(name)
        return {"isError": False, "structuredContent": {"data": {"tool": name}, "warnings": []}}


class FakeLiveSmokeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self) -> list[dict]:
        return [{"name": name} for name in sorted(EXPECTED_TOOL_NAMES)]

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        call_arguments = arguments or {}
        self.calls.append((name, call_arguments))
        data: object
        if name == "list_workouts":
            data = [{"activity_id": 701, "kudos_count": 2}]
        elif name == "get_training_aggregates":
            bundle_id = call_arguments.get("metric_bundle")
            data = {
                "rows": [{"metric_id": "trimp", "value": 12.0, "completeness_status": "complete"}],
                "bundle": {
                    "bundle_id": bundle_id,
                    "sections": {
                        "load_context": {
                            "rows": [],
                            "bundle_completeness": {
                                "requested_metrics": ["trimp"],
                                "included_metrics": ["trimp"],
                                "unavailable_metrics": [],
                                "skipped_metrics": [],
                                "scope_incompatible_metrics": [],
                            },
                        }
                    },
                    "bundle_completeness": {
                        "requested_metrics": ["trimp"],
                        "included_metrics": ["trimp"],
                        "unavailable_metrics": [],
                        "skipped_metrics": [],
                        "scope_incompatible_metrics": [],
                    },
                },
            }
        else:
            data = {"tool": name}
        return {"isError": False, "structuredContent": {"data": data, "warnings": []}}


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


def test_default_warm_latency_calls_include_product_fact_bundle_aggregates() -> None:
    calls = default_warm_latency_calls(workout_id=701, today="2026-05-24")

    aggregate_calls = [call for call in calls if call["name"] == "get_training_aggregates"]

    assert {call["name"] for call in calls} == EXPECTED_TOOL_NAMES | {"get_training_aggregates"}
    assert [call["arguments"]["metric_bundle"] for call in aggregate_calls] == list(EXPECTED_PRODUCT_BUNDLES)
    for call in aggregate_calls:
        arguments = call["arguments"]
        assert arguments["start_date"]
        assert arguments["end_date"]
        assert arguments["scope"] == "both"
        assert "as_of_day" not in arguments
        assert "window_days" not in arguments


def test_live_smoke_calls_each_product_bundle_through_training_aggregates() -> None:
    client = FakeLiveSmokeClient()

    result = asyncio.run(run_live_smoke(client, today="2026-05-24"))

    aggregate_bundle_ids = [
        arguments.get("metric_bundle") for name, arguments in client.calls if name == "get_training_aggregates"
    ]
    assert aggregate_bundle_ids == list(EXPECTED_PRODUCT_BUNDLES)
    assert result["aggregate_bundles"] == list(EXPECTED_PRODUCT_BUNDLES)
    # Warnings summary must be a list of digests (code/severity), not an opaque count.
    assert all(isinstance(entries, list) for entries in result["warnings"].values())


def test_warning_digest_surfaces_code_and_severity() -> None:
    payload = {
        "structuredContent": {
            "warnings": [
                {"code": "aggregate_rows_incomplete", "severity": "warning", "message": "ignored"},
                {"code": "read_model_not_current", "severity": "error"},
            ]
        }
    }

    assert _warning_digest(payload) == [
        {"code": "aggregate_rows_incomplete", "severity": "warning"},
        {"code": "read_model_not_current", "severity": "error"},
    ]


def test_warning_digest_empty_when_no_warnings() -> None:
    assert _warning_digest({"structuredContent": {"data": {}}}) == []
    assert _warning_digest({}) == []


def test_mcp_test_client_cli_call_tool(capsys) -> None:
    exit_code = main(["call-tool", "--name", "Echo", "--arguments", '{"value":"cli"}', "--", *_fake_server_command()])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"value": "cli"' in captured.out
