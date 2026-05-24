from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from mcp_strava.devtools.mcp_client.client import (
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_LATENCY_P95_MS,
    DEFAULT_LATENCY_SAMPLES,
    DEFAULT_LATENCY_WARMUP,
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
    perf.add_argument("--workout-id", type=int, help="Use a known workout id instead of resolving one via list_workouts.")
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


def parse_tool_arguments(raw_arguments: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_arguments)
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


def print_json(payload: Any, *, compact: bool) -> None:
    if compact:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def _run_command(args: argparse.Namespace) -> Any:
    started_at = time.perf_counter()
    if args.url:
        async with HttpMcpClient(args.url, timeout_seconds=args.timeout) as client:
            startup_ms = (time.perf_counter() - started_at) * 1000
            return await _dispatch(args, client, startup_ms=startup_ms)

    command = normalize_server_command(args.server_command)
    async with StdioMcpClient(command, timeout_seconds=args.timeout) as client:
        startup_ms = (time.perf_counter() - started_at) * 1000
        return await _dispatch(args, client, startup_ms=startup_ms)


async def _dispatch(args: argparse.Namespace, client: StdioMcpClient | HttpMcpClient, *, startup_ms: float) -> Any:
    if args.command == "list-tools":
        return await client.list_tools()
    if args.command == "call-tool":
        return await client.call_tool(args.name, parse_tool_arguments(args.arguments))
    if args.command == "script":
        return await execute_script_steps(client, load_script_steps(Path(args.file)))
    if args.command == "smoke-basic":
        return await run_basic_smoke(client)
    if args.command == "smoke-live":
        return await run_live_smoke(client)
    if args.command == "perf-read-model":
        calls = default_warm_latency_calls(workout_id=args.workout_id) if args.workout_id is not None else None
        return await run_warm_latency_gate(
            client,
            calls=calls,
            warmup=args.warmup,
            samples=args.samples,
            p95_ms=args.p95_ms,
            startup_ms=startup_ms,
            raise_on_failure=False,
        )
    raise ValueError(f"unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = asyncio.run(_run_command(args))
    except (ValueError, McpClientError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print_json(payload, compact=args.compact)
    if isinstance(payload, dict) and payload.get("mode") == "warm_latency" and payload.get("status") != "ok":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
