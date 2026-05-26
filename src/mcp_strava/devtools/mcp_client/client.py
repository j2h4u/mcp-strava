from __future__ import annotations

import json
import math
import time
from contextlib import AsyncExitStack
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_LATENCY_WARMUP = 2
DEFAULT_LATENCY_SAMPLES = 20
DEFAULT_LATENCY_P95_MS = 100.0

EXPECTED_TOOL_NAMES = {
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
    "get_training_aggregates",
}

LATENCY_TOOL_ORDER = [
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
    "get_training_aggregates",
]

PRODUCT_BUNDLE_SMOKE_IDS = ("daily_brief", "weekly_digest", "historical_facts")


class McpClientError(RuntimeError):
    """Raised when the MCP endpoint or protocol response is invalid."""


class StdioMcpClient:
    """Small async wrapper around the official MCP stdio client transport."""

    def __init__(
        self,
        command: list[str],
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        if not command:
            raise ValueError("command must contain at least one program name")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._server = StdioServerParameters(command=command[0], args=command[1:], cwd=cwd, env=env)
        self._timeout_seconds = timeout_seconds
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> StdioMcpClient:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.stop()

    async def start(self) -> None:
        if self._session is not None:
            return
        exit_stack = AsyncExitStack()
        try:
            read_stream, write_stream = await exit_stack.enter_async_context(stdio_client(self._server))
            session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
        except Exception as exc:
            await exit_stack.aclose()
            raise McpClientError(str(exc)) from exc
        self._exit_stack = exit_stack
        self._session = session

    async def stop(self) -> None:
        exit_stack = self._exit_stack
        self._exit_stack = None
        self._session = None
        if exit_stack is not None:
            await exit_stack.aclose()

    async def list_tools(self) -> list[dict[str, Any]]:
        session = self._require_session()
        try:
            result = await session.list_tools()
        except Exception as exc:
            raise McpClientError(str(exc)) from exc
        return [tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self._require_session()
        try:
            result = await session.call_tool(
                name,
                arguments or {},
                read_timeout_seconds=timedelta(seconds=self._timeout_seconds),
            )
        except Exception as exc:
            raise McpClientError(str(exc)) from exc
        return result.model_dump(mode="json", by_alias=True, exclude_none=True)

    def _require_session(self) -> ClientSession:
        session = self._session
        if session is None:
            raise McpClientError("client session is not initialized")
        return session


class HttpMcpClient:
    """Small async wrapper around the official MCP Streamable HTTP client transport."""

    def __init__(self, url: str, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        if not url:
            raise ValueError("url must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._url = url
        self._timeout_seconds = timeout_seconds
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> HttpMcpClient:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.stop()

    async def start(self) -> None:
        if self._session is not None:
            return
        exit_stack = AsyncExitStack()
        try:
            read_stream, write_stream, _get_session_id = await exit_stack.enter_async_context(
                streamable_http_client(self._url)
            )
            session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
        except Exception as exc:
            await exit_stack.aclose()
            raise McpClientError(str(exc)) from exc
        self._exit_stack = exit_stack
        self._session = session

    async def stop(self) -> None:
        exit_stack = self._exit_stack
        self._exit_stack = None
        self._session = None
        if exit_stack is not None:
            await exit_stack.aclose()

    async def list_tools(self) -> list[dict[str, Any]]:
        session = self._require_session()
        try:
            result = await session.list_tools()
        except Exception as exc:
            raise McpClientError(str(exc)) from exc
        return [tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self._require_session()
        try:
            result = await session.call_tool(
                name,
                arguments or {},
                read_timeout_seconds=timedelta(seconds=self._timeout_seconds),
            )
        except Exception as exc:
            raise McpClientError(str(exc)) from exc
        return result.model_dump(mode="json", by_alias=True, exclude_none=True)

    def _require_session(self) -> ClientSession:
        session = self._session
        if session is None:
            raise McpClientError("client session is not initialized")
        return session


def load_script_steps(script_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(script_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        steps = payload
    elif isinstance(payload, dict):
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError("script JSON object must contain a list field named 'steps'")
        steps = raw_steps
    else:
        raise ValueError("script JSON must be a list or an object with a 'steps' field")

    normalized_steps: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"script step {index} must be an object")
        normalized_steps.append(step)
    return normalized_steps


async def execute_script_steps(client: StdioMcpClient | HttpMcpClient, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        action = step.get("action")
        if action == "list_tools":
            result = await client.list_tools()
            _assert_step_expectations(index=index, action=action, result=result, expect=step.get("expect"))
            results.append({"step": index, "action": action, "result": result})
            continue

        if action == "call_tool":
            name = step.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError(f"script step {index} is missing string field 'name'")
            arguments = step.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError(f"script step {index} field 'arguments' must be an object")
            result = await client.call_tool(name, arguments)
            _assert_step_expectations(index=index, action=action, result=result, expect=step.get("expect"))
            results.append({"step": index, "action": action, "name": name, "result": result})
            continue

        if action == "measure_warm_tool_latency":
            result = await measure_warm_tool_latency(
                client,
                calls=_normalize_latency_calls(step.get("calls")),
                warmup=_optional_int(step.get("warmup"), default=DEFAULT_LATENCY_WARMUP, field="warmup"),
                samples=_optional_int(step.get("samples"), default=DEFAULT_LATENCY_SAMPLES, field="samples"),
                p95_ms=_optional_float(step.get("p95_ms"), default=DEFAULT_LATENCY_P95_MS, field="p95_ms"),
                startup_ms=_optional_float(step.get("startup_ms"), default=0.0, field="startup_ms"),
            )
            _assert_step_expectations(index=index, action=action, result=result, expect=step.get("expect"))
            results.append({"step": index, "action": action, "result": result})
            continue

        raise ValueError(f"unsupported script action at step {index}: {action!r}")
    return results


async def verify_tool_surface(client: StdioMcpClient | HttpMcpClient) -> list[str]:
    tools = await client.list_tools()
    tool_names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
    missing = sorted(EXPECTED_TOOL_NAMES - tool_names)
    unexpected = sorted(tool_names - EXPECTED_TOOL_NAMES)
    if missing or unexpected:
        raise McpClientError(f"unexpected MCP tool surface: missing={missing}, unexpected={unexpected}")
    return sorted(tool_names)


async def run_basic_smoke(client: StdioMcpClient | HttpMcpClient) -> dict[str, Any]:
    tool_names = await verify_tool_surface(client)
    workouts = _require_success("list_workouts", await client.call_tool("list_workouts", {"limit": 1}))
    return {
        "status": "ok",
        "mode": "basic",
        "tools": tool_names,
        "called": ["list_workouts"],
        "data_shapes": {
            "list_workouts": _data_shape(workouts.get("structuredContent", {}).get("data")),
        },
        "warnings": {
            "list_workouts": len(workouts.get("structuredContent", {}).get("warnings") or []),
        },
    }


def default_warm_latency_calls(*, workout_id: int, today: str | date | None = None) -> list[dict[str, Any]]:
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


def _coerce_day(value: str | date | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _product_bundle_aggregate_calls(today_date: date) -> list[dict[str, Any]]:
    end_exclusive = (today_date + timedelta(days=1)).isoformat()
    return [
        {
            "name": "get_training_aggregates",
            "arguments": {
                "start_date": (today_date - timedelta(days=13)).isoformat(),
                "end_date": end_exclusive,
                "bucket": "all_time",
                "metric_bundle": "daily_brief",
                "scope": "both",
            },
        },
        {
            "name": "get_training_aggregates",
            "arguments": {
                "start_date": (today_date - timedelta(days=27)).isoformat(),
                "end_date": end_exclusive,
                "bucket": "week",
                "metric_bundle": "weekly_digest",
                "scope": "both",
            },
        },
        {
            "name": "get_training_aggregates",
            "arguments": {
                "start_date": (today_date - timedelta(days=365)).isoformat(),
                "end_date": end_exclusive,
                "bucket": "all_time",
                "metric_bundle": "historical_facts",
                "scope": "both",
            },
        },
    ]


async def resolve_default_warm_latency_calls(
    client: StdioMcpClient | HttpMcpClient,
    *,
    today: str | date | None = None,
) -> list[dict[str, Any]]:
    workouts = _require_success("list_workouts", await client.call_tool("list_workouts", {"limit": 1}))
    try:
        workout_id = _extract_first_workout_id(workouts)
    except McpClientError:
        workout_id = 0
    return default_warm_latency_calls(workout_id=workout_id, today=today)


async def run_warm_latency_gate(
    client: StdioMcpClient | HttpMcpClient,
    *,
    calls: list[dict[str, Any]] | None = None,
    warmup: int = DEFAULT_LATENCY_WARMUP,
    samples: int = DEFAULT_LATENCY_SAMPLES,
    p95_ms: float = DEFAULT_LATENCY_P95_MS,
    startup_ms: float = 0.0,
    raise_on_failure: bool = True,
) -> dict[str, Any]:
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
    calls: list[dict[str, Any]],
    warmup: int = DEFAULT_LATENCY_WARMUP,
    samples: int = DEFAULT_LATENCY_SAMPLES,
    p95_ms: float = DEFAULT_LATENCY_P95_MS,
    startup_ms: float = 0.0,
    raise_on_failure: bool = True,
) -> dict[str, Any]:
    normalized_calls = _normalize_latency_calls(calls)
    if warmup < 0:
        raise ValueError("warmup must be zero or positive")
    if samples <= 0:
        raise ValueError("samples must be positive")
    if p95_ms <= 0:
        raise ValueError("p95_ms must be positive")
    if startup_ms < 0:
        raise ValueError("startup_ms must be zero or positive")

    tool_results: dict[str, dict[str, Any]] = {}
    exceeded: list[str] = []
    for call in normalized_calls:
        name = str(call["name"])
        arguments = dict(call["arguments"])
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
            exceeded.append(name)
        tool_results[name] = {
            "status": status,
            "samples": samples,
            "warmup": warmup,
            "p50_ms": round(p50_value, 3),
            "p95_ms": round(p95_value, 3),
            "max_ms": round(max_value, 3),
            "threshold_ms": p95_ms,
        }

    result = {
        "status": "ok" if not exceeded else "failed",
        "mode": "warm_latency",
        "startup_ms": round(startup_ms, 3),
        "tools": tool_results,
    }
    if exceeded and raise_on_failure:
        raise McpClientError(f"p95 threshold exceeded for tools: {', '.join(exceeded)}")
    return result


async def run_live_smoke(
    client: StdioMcpClient | HttpMcpClient,
    *,
    today: str | date | None = None,
) -> dict[str, Any]:
    tool_names = await verify_tool_surface(client)
    fitness = _require_success("get_fitness_state", await client.call_tool("get_fitness_state", {}))
    workouts = _require_success("list_workouts", await client.call_tool("list_workouts", {"limit": 3}))
    workout_id = _extract_first_workout_id(workouts)
    detail = _require_success("get_workout_detail", await client.call_tool("get_workout_detail", {"workout_id": workout_id}))

    today_date = _coerce_day(today)
    comparison = _require_success(
        "compare_periods",
        await client.call_tool(
            "compare_periods",
            {
                "period_a_start": (today_date - timedelta(days=13)).isoformat(),
                "period_a_end": (today_date - timedelta(days=7)).isoformat(),
                "period_b_start": (today_date - timedelta(days=6)).isoformat(),
                "period_b_end": today_date.isoformat(),
            },
        ),
    )
    projection = _require_success(
        "project_fitness_state",
        await client.call_tool(
            "project_fitness_state",
            {"target_date": (today_date + timedelta(days=7)).isoformat(), "scenarios": ["rest", "maintain"]},
        ),
    )
    aggregate_payloads: dict[str, dict[str, Any]] = {}
    for call in _product_bundle_aggregate_calls(today_date):
        arguments = dict(call["arguments"])
        bundle_id = str(arguments["metric_bundle"])
        aggregate_payloads[bundle_id] = _require_success(
            "get_training_aggregates",
            await client.call_tool("get_training_aggregates", arguments),
        )

    payloads = {
        "get_fitness_state": fitness,
        "list_workouts": workouts,
        "get_workout_detail": detail,
        "compare_periods": comparison,
        "project_fitness_state": projection,
        **{
            f"get_training_aggregates:{bundle_id}": payload
            for bundle_id, payload in aggregate_payloads.items()
        },
    }
    return {
        "status": "ok",
        "mode": "full",
        "tools": sorted(tool_names),
        "called": sorted(payloads.keys()),
        "aggregate_bundles": list(aggregate_payloads),
        "workout_id": workout_id,
        "data_shapes": {name: _data_shape(payload.get("structuredContent", {}).get("data")) for name, payload in payloads.items()},
        "warnings": {
            name: len(payload.get("structuredContent", {}).get("warnings") or [])
            for name, payload in payloads.items()
        },
    }


def _require_success(name: str, result: dict[str, Any]) -> dict[str, Any]:
    if result.get("isError") is True:
        raise McpClientError(f"{name} returned isError=true")
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raise McpClientError(f"{name} returned no structuredContent object")
    return result


def _extract_first_workout_id(result: dict[str, Any]) -> int:
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raise McpClientError("list_workouts returned no structuredContent")
    data = structured.get("data")
    candidates = data if isinstance(data, list) else []
    if isinstance(data, dict):
        for key in ("workouts", "items", "activities"):
            value = data.get(key)
            if isinstance(value, list):
                candidates = value
                break
    for item in candidates:
        if not isinstance(item, dict):
            continue
        for key in ("activity_id", "workout_id", "id"):
            if key in item:
                return int(item[key])
    raise McpClientError("list_workouts returned no extractable workout id")


def _assert_step_expectations(*, index: int, action: str, result: Any, expect: Any) -> None:
    if expect is None:
        return
    if not isinstance(expect, dict):
        raise ValueError(f"script step {index} field 'expect' must be an object")

    path_equals = expect.get("path_equals")
    if path_equals is not None:
        if not isinstance(path_equals, dict):
            raise ValueError(f"script step {index} field 'expect.path_equals' must be an object")
        for path, expected_value in path_equals.items():
            actual_value = _lookup_path(result, path)
            if actual_value != expected_value:
                raise McpClientError(
                    f"script step {index} expected path {path!r} to equal {expected_value!r}, got {actual_value!r}"
                )

    if action == "list_tools":
        _assert_list_tools_expectations(index=index, result=result, expect=expect)
    elif action == "call_tool":
        _assert_call_tool_expectations(index=index, result=result, expect=expect)
    elif action == "measure_warm_tool_latency":
        _assert_latency_expectations(index=index, result=result, expect=expect)


def _assert_list_tools_expectations(*, index: int, result: Any, expect: dict[str, Any]) -> None:
    if not isinstance(result, list):
        raise McpClientError(f"script step {index} list_tools result is not a list")
    include = expect.get("tool_names_include")
    if include is not None:
        if not isinstance(include, list) or not all(isinstance(item, str) for item in include):
            raise ValueError(f"script step {index} field 'expect.tool_names_include' must be a list of strings")
        tool_names = {tool.get("name") for tool in result if isinstance(tool, dict)}
        missing = [name for name in include if name not in tool_names]
        if missing:
            raise McpClientError(f"script step {index} is missing tools: {missing}")

    exclude = expect.get("tool_names_exclude")
    if exclude is not None:
        if not isinstance(exclude, list) or not all(isinstance(item, str) for item in exclude):
            raise ValueError(f"script step {index} field 'expect.tool_names_exclude' must be a list of strings")
        tool_names = {tool.get("name") for tool in result if isinstance(tool, dict)}
        present = [name for name in exclude if name in tool_names]
        if present:
            raise McpClientError(f"script step {index} has forbidden tools: {present}")


def _assert_call_tool_expectations(*, index: int, result: Any, expect: dict[str, Any]) -> None:
    if not isinstance(result, dict):
        raise McpClientError(f"script step {index} call_tool result is not an object")
    expected_is_error = expect.get("is_error")
    if expected_is_error is not None:
        if not isinstance(expected_is_error, bool):
            raise ValueError(f"script step {index} field 'expect.is_error' must be a boolean")
        actual_is_error = result.get("isError")
        if actual_is_error != expected_is_error:
            raise McpClientError(
                f"script step {index} expected isError={expected_is_error!r}, got {actual_is_error!r}"
            )


def _assert_latency_expectations(*, index: int, result: Any, expect: dict[str, Any]) -> None:
    if not isinstance(result, dict):
        raise McpClientError(f"script step {index} latency result is not an object")
    expected_status = expect.get("latency_status")
    if expected_status is not None and result.get("status") != expected_status:
        raise McpClientError(
            f"script step {index} expected latency_status={expected_status!r}, got {result.get('status')!r}"
        )
    include = expect.get("tool_names_include")
    if include is not None:
        if not isinstance(include, list) or not all(isinstance(item, str) for item in include):
            raise ValueError(f"script step {index} field 'expect.tool_names_include' must be a list of strings")
        tools = result.get("tools")
        if not isinstance(tools, dict):
            raise McpClientError(f"script step {index} latency result has no tools object")
        missing = [name for name in include if name not in tools]
        if missing:
            raise McpClientError(f"script step {index} is missing latency tools: {missing}")


def _normalize_latency_calls(raw_calls: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_calls, list) or not raw_calls:
        raise ValueError("latency calls must be a non-empty list")
    normalized: list[dict[str, Any]] = []
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


def _optional_int(value: Any, *, default: int, field: str) -> int:
    if value is None:
        return default
    if not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _optional_float(value: Any, *, default: float, field: str) -> float:
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


def _lookup_path(payload: Any, path: str) -> Any:
    current = payload
    for segment in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError) as exc:
                raise McpClientError(f"cannot resolve list segment {segment!r} in path {path!r}") from exc
            continue
        if isinstance(current, dict):
            if segment not in current:
                raise McpClientError(f"missing path segment {segment!r} in path {path!r}")
            current = current[segment]
            continue
        raise McpClientError(f"cannot descend into non-container value at segment {segment!r} for path {path!r}")
    return current


def _data_shape(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {"type": "dict", "keys": sorted(value.keys())[:30]}
    if isinstance(value, list):
        first = value[0] if value else None
        first_keys = sorted(first.keys())[:30] if isinstance(first, dict) else None
        return {"type": "list", "count": len(value), "first_keys": first_keys}
    return {"type": type(value).__name__}
