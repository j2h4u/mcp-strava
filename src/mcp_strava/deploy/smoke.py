"""Compatibility wrapper for the reusable MCP test client."""

from __future__ import annotations

import argparse
import asyncio
import sys

from mcp_strava.devtools.mcp_client.client import HttpMcpClient, McpClientError, run_basic_smoke


async def _run_smoke(
    *,
    url: str,
    expect_tools: list[str],
    forbid_tools: list[str],
    call_name: str | None,
) -> int:
    del call_name
    try:
        async with HttpMcpClient(url) as client:
            result = await run_basic_smoke(client)
    except McpClientError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    tool_names = set(result["tools"])
    missing = [name for name in expect_tools if name not in tool_names]
    unexpected = [name for name in forbid_tools if name in tool_names]
    if missing or unexpected:
        print(f"tool surface mismatch: missing={missing}, forbidden={unexpected}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MCP SDK smoke checker")
    parser.add_argument("--url", required=True)
    parser.add_argument("--expect-tool", action="append", default=[])
    parser.add_argument("--forbid-tool", action="append", default=[])
    parser.add_argument("--call", choices=["get_fitness_state"], default=None)
    args = parser.parse_args(argv)

    return asyncio.run(
        _run_smoke(
            url=args.url,
            expect_tools=args.expect_tool,
            forbid_tools=args.forbid_tool,
            call_name=args.call,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
