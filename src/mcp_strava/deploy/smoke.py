"""Compatibility wrapper for the reusable MCP test client."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import cast

from mcp_strava.devtools.mcp_client.client import (
    DEFAULT_LATENCY_P95_MS,
    DEFAULT_LATENCY_SAMPLES,
    DEFAULT_LATENCY_WARMUP,
    HttpMcpClient,
    McpClientError,
    default_warm_latency_calls,
    run_basic_smoke,
    run_warm_latency_gate,
)


async def _run_smoke(
    *,
    url: str,
    expect_tools: list[str],
    call_name: str | None,
    perf: bool,
    samples: int,
    warmup: int,
    p95_ms: float,
    workout_id: int | None,
) -> int:
    del call_name
    try:
        async with HttpMcpClient(url) as client:
            result = await run_basic_smoke(client)
            perf_result = None
            if perf:
                calls = default_warm_latency_calls(workout_id=workout_id) if workout_id is not None else None
                perf_result = await run_warm_latency_gate(
                    client,
                    calls=calls,
                    samples=samples,
                    warmup=warmup,
                    p95_ms=p95_ms,
                    raise_on_failure=False,
                )
    except McpClientError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    tool_names = set(result["tools"])
    missing = [name for name in expect_tools if name not in tool_names]
    if missing:
        print(f"tool surface mismatch: missing={missing}", file=sys.stderr)
        return 1
    if perf and perf_result is not None:
        print(json.dumps(perf_result, ensure_ascii=False, separators=(",", ":")))
        if perf_result["status"] != "ok":
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MCP SDK smoke checker")
    parser.add_argument("--url", required=True)
    parser.add_argument("--expect-tool", action="append", default=[])
    parser.add_argument("--call", choices=["get_fitness_state"], default=None)
    parser.add_argument("--perf", action="store_true", help="Run the warm read-model latency gate after basic smoke.")
    parser.add_argument("--samples", type=int, default=DEFAULT_LATENCY_SAMPLES)
    parser.add_argument("--warmup", type=int, default=DEFAULT_LATENCY_WARMUP)
    parser.add_argument("--p95-ms", type=float, default=DEFAULT_LATENCY_P95_MS)
    parser.add_argument("--workout-id", type=int)
    args = parser.parse_args(argv)
    url = cast(str, args.url)
    expect_tools = cast(list[str], args.expect_tool)
    call_name = cast("str | None", args.call)
    perf = cast(bool, args.perf)
    samples = cast(int, args.samples)
    warmup = cast(int, args.warmup)
    p95_ms = cast(float, args.p95_ms)
    workout_id = cast("int | None", args.workout_id)

    return asyncio.run(
        _run_smoke(
            url=url,
            expect_tools=expect_tools,
            call_name=call_name,
            perf=perf,
            samples=samples,
            warmup=warmup,
            p95_ms=p95_ms,
            workout_id=workout_id,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
