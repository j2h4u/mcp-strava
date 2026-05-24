from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from mcp_strava.devtools.mcp_client.cli import main
from mcp_strava.devtools.mcp_client.client import McpClientError, StdioMcpClient, execute_script_steps


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


def test_mcp_test_client_cli_call_tool(capsys) -> None:
    exit_code = main(["call-tool", "--name", "Echo", "--arguments", '{"value":"cli"}', "--", *_fake_server_command()])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"value": "cli"' in captured.out
