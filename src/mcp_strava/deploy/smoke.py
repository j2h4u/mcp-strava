"""MCP SDK-backed smoke checks for backend and gateway URLs."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def _run_smoke(
    *,
    url: str,
    expect_tools: list[str],
    forbid_tools: list[str],
    call_name: str | None,
) -> int:
    async with streamable_http_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            tool_names = {tool.name for tool in tools_result.tools}

            missing = [name for name in expect_tools if name not in tool_names]
            if missing:
                print(f"missing tools: {', '.join(missing)}", file=sys.stderr)
                return 1

            unexpected = [name for name in forbid_tools if name in tool_names]
            if unexpected:
                print(f"forbidden tools present: {', '.join(unexpected)}", file=sys.stderr)
                return 1

            if call_name == "get_fitness_state":
                result = await session.call_tool("get_fitness_state", {})
                if result.isError:
                    print("get_fitness_state returned error", file=sys.stderr)
                    return 1
                payload_found = False
                for item in result.content:
                    data = getattr(item, "data", None)
                    if isinstance(data, dict):
                        payload_found = True
                        break
                if not payload_found:
                    print("get_fitness_state returned no structured payload", file=sys.stderr)
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
