from __future__ import annotations

import json
from contextlib import AsyncExitStack
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

DEFAULT_TIMEOUT_SECONDS = 5.0

EXPECTED_TOOL_NAMES = {
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
}


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


async def run_live_smoke(client: StdioMcpClient | HttpMcpClient) -> dict[str, Any]:
    tool_names = await verify_tool_surface(client)
    fitness = _require_success("get_fitness_state", await client.call_tool("get_fitness_state", {}))
    workouts = _require_success("list_workouts", await client.call_tool("list_workouts", {"limit": 3}))
    workout_id = _extract_first_workout_id(workouts)
    detail = _require_success("get_workout_detail", await client.call_tool("get_workout_detail", {"workout_id": workout_id}))

    today = date.today()
    comparison = _require_success(
        "compare_periods",
        await client.call_tool(
            "compare_periods",
            {
                "period_a_start": (today - timedelta(days=13)).isoformat(),
                "period_a_end": (today - timedelta(days=7)).isoformat(),
                "period_b_start": (today - timedelta(days=6)).isoformat(),
                "period_b_end": today.isoformat(),
            },
        ),
    )
    projection = _require_success(
        "project_fitness_state",
        await client.call_tool(
            "project_fitness_state",
            {"target_date": (today + timedelta(days=7)).isoformat(), "scenarios": ["rest", "maintain"]},
        ),
    )

    payloads = {
        "get_fitness_state": fitness,
        "list_workouts": workouts,
        "get_workout_detail": detail,
        "compare_periods": comparison,
        "project_fitness_state": projection,
    }
    return {
        "status": "ok",
        "mode": "full",
        "tools": sorted(tool_names),
        "called": sorted(payloads.keys()),
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
