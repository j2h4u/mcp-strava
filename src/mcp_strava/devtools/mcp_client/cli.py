from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import cast

from mcp_strava.devtools.mcp_client.client import (
    DEFAULT_LATENCY_P95_MS,
    DEFAULT_LATENCY_SAMPLES,
    DEFAULT_LATENCY_WARMUP,
    DEFAULT_TIMEOUT_SECONDS,
    HttpMcpClient,
    McpClientError,
    StdioMcpClient,
    default_warm_latency_calls,
    execute_script_steps,
    load_script_steps,
    run_basic_smoke,
    run_live_smoke,
    run_warm_latency_gate,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reusable MCP client for mcp-strava testing.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_tools = subparsers.add_parser("list-tools", help="Initialize MCP and print tools/list.")
    _add_common_arguments(list_tools)
    _add_http_arguments(list_tools)

    call_tool = subparsers.add_parser("call-tool", help="Initialize MCP and call one tool.")
    call_tool.add_argument("--name", required=True)
    call_tool.add_argument("--arguments", default="{}", help="JSON object with tool arguments.")
    _add_common_arguments(call_tool)
    _add_http_arguments(call_tool)

    script = subparsers.add_parser("script", help="Run MCP actions from a JSON file.")
    script.add_argument("--file", required=True)
    _add_common_arguments(script)
    _add_http_arguments(script)

    smoke = subparsers.add_parser("smoke-live", help="Run the canonical live MCP E2E smoke.")
    _add_common_arguments(smoke)
    _add_http_arguments(smoke)

    smoke_basic = subparsers.add_parser("smoke-basic", help="Run a fast MCP transport and tool-surface smoke.")
    _add_common_arguments(smoke_basic)
    _add_http_arguments(smoke_basic)

    perf = subparsers.add_parser("perf-read-model", help="Measure repeated warm MCP tool-call latency.")
    perf.add_argument("--samples", type=int, default=DEFAULT_LATENCY_SAMPLES)
    perf.add_argument("--warmup", type=int, default=DEFAULT_LATENCY_WARMUP)
    perf.add_argument("--p95-ms", type=float, default=DEFAULT_LATENCY_P95_MS)
    perf.add_argument(
        "--workout-id", type=int, help="Use a known workout id instead of resolving one via list_workouts."
    )
    _add_common_arguments(perf)
    _add_http_arguments(perf)

    return parser


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-request timeout in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}",
    )
    parser.add_argument("--compact", action="store_true", help="Print one-line JSON.")
    parser.add_argument(
        "server_command",
        nargs=argparse.REMAINDER,
        help="Command used to launch a stdio MCP server. Prefix with '--'.",
    )


def _add_http_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", help="Streamable HTTP MCP endpoint. When set, server_command is ignored.")


def parse_tool_arguments(raw_arguments: str) -> dict[str, object]:
    try:
        payload = cast(object, json.loads(raw_arguments))
    except json.JSONDecodeError as exc:
        raise ValueError(f"--arguments must be valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("--arguments JSON must be an object")
    return payload


def normalize_server_command(server_command: list[str]) -> list[str]:
    command = list(server_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("server command is required; pass it after '--'")
    return command


def print_json(payload: object, *, compact: bool) -> None:
    if compact:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def _run_command(args: argparse.Namespace) -> object:
    started_at = time.perf_counter()
    url: str | None = cast(str | None, args.url)
    timeout: float = cast(float, args.timeout)
    if url:
        async with HttpMcpClient(url, timeout_seconds=timeout) as client:
            startup_ms = (time.perf_counter() - started_at) * 1000
            return await _dispatch(args, client, startup_ms=startup_ms)

    server_command: list[str] = cast(list[str], args.server_command)
    command = normalize_server_command(server_command)
    async with StdioMcpClient(command, timeout_seconds=timeout) as client:
        startup_ms = (time.perf_counter() - started_at) * 1000
        return await _dispatch(args, client, startup_ms=startup_ms)


async def _dispatch(args: argparse.Namespace, client: StdioMcpClient | HttpMcpClient, *, startup_ms: float) -> object:
    cmd: str = cast(str, args.command)
    if cmd == "list-tools":
        return await client.list_tools()
    if cmd == "call-tool":
        name: str = cast(str, args.name)
        arguments: str = cast(str, args.arguments)
        return await client.call_tool(name, parse_tool_arguments(arguments))
    if cmd == "script":
        file_path: str = cast(str, args.file)
        return await execute_script_steps(client, load_script_steps(Path(file_path)))
    if cmd == "smoke-basic":
        return await run_basic_smoke(client)
    if cmd == "smoke-live":
        return await run_live_smoke(client)
    if cmd == "perf-read-model":
        workout_id: int | None = cast(int | None, args.workout_id)
        warmup: int = cast(int, args.warmup)
        samples: int = cast(int, args.samples)
        p95_ms: float = cast(float, args.p95_ms)
        calls = default_warm_latency_calls(workout_id=workout_id) if workout_id is not None else None
        return await run_warm_latency_gate(
            client,
            calls=calls,
            warmup=warmup,
            samples=samples,
            p95_ms=p95_ms,
            startup_ms=startup_ms,
            raise_on_failure=False,
        )
    raise ValueError(f"unsupported command: {cmd}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    compact: bool = cast(bool, args.compact)
    try:
        payload = asyncio.run(_run_command(args))
    except (ValueError, McpClientError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print_json(payload, compact=compact)
    if isinstance(payload, dict) and payload.get("mode") == "warm_latency" and payload.get("status") != "ok":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
