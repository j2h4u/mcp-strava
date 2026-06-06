from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from mcp_strava.devtools.mcp_client.contracts import (
    DEFAULT_LATENCY_P95_MS,
    DEFAULT_LATENCY_SAMPLES,
    DEFAULT_LATENCY_WARMUP,
    McpClientError,
)
from mcp_strava.devtools.mcp_client.latency import (
    _normalize_latency_calls,
    _optional_float,
    _optional_int,
    measure_warm_tool_latency,
)
from mcp_strava.devtools.mcp_client.transport import HttpMcpClient, StdioMcpClient
from mcp_strava.devtools.mcp_client.utils import _lookup_path


def load_script_steps(script_path: Path) -> list[dict[str, object]]:
    raw = cast(object, json.loads(script_path.read_text(encoding="utf-8")))
    if isinstance(raw, list):
        steps = raw
    elif isinstance(raw, dict):
        raw_steps = raw.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError("script JSON object must contain a list field named 'steps'")
        steps = raw_steps
    else:
        raise ValueError("script JSON must be a list or an object with a 'steps' field")

    normalized_steps: list[dict[str, object]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"script step {index} must be an object")
        normalized_steps.append(step)
    return normalized_steps


async def execute_script_steps(
    client: StdioMcpClient | HttpMcpClient, steps: list[dict[str, object]]
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for index, step in enumerate(steps, start=1):
        action = step.get("action")
        if action == "list_tools":
            result = await client.list_tools()
            _assert_step_expectations(index=index, action=str(action), result=result, expect=step.get("expect"))
            results.append({"step": index, "action": action, "result": result})
            continue

        if action == "call_tool":
            name = step.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError(f"script step {index} is missing string field 'name'")
            raw_arguments = step.get("arguments", {})
            if not isinstance(raw_arguments, dict):
                raise ValueError(f"script step {index} field 'arguments' must be an object")
            arguments: dict[str, object] = raw_arguments
            result = await client.call_tool(name, arguments)
            _assert_step_expectations(index=index, action=str(action), result=result, expect=step.get("expect"))
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
            _assert_step_expectations(index=index, action=str(action), result=result, expect=step.get("expect"))
            results.append({"step": index, "action": action, "result": result})
            continue

        raise ValueError(f"unsupported script action at step {index}: {action!r}")
    return results


def _assert_step_expectations(*, index: int, action: str, result: object, expect: object) -> None:
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


def _assert_list_tools_expectations(*, index: int, result: object, expect: dict[str, object]) -> None:
    if not isinstance(result, list):
        raise McpClientError(f"script step {index} list_tools result is not a list")
    include = expect.get("tool_names_include")
    if include is not None:
        if not isinstance(include, list) or not all(isinstance(item, str) for item in include):
            raise ValueError(f"script step {index} field 'expect.tool_names_include' must be a list of strings")
        tool_names: set[object] = {tool.get("name") for tool in result if isinstance(tool, dict)}
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


def _assert_call_tool_expectations(*, index: int, result: object, expect: dict[str, object]) -> None:
    if not isinstance(result, dict):
        raise McpClientError(f"script step {index} call_tool result is not an object")
    expected_is_error = expect.get("is_error")
    if expected_is_error is not None:
        if not isinstance(expected_is_error, bool):
            raise ValueError(f"script step {index} field 'expect.is_error' must be a boolean")
        actual_is_error = result.get("isError")
        if actual_is_error != expected_is_error:
            raise McpClientError(f"script step {index} expected isError={expected_is_error!r}, got {actual_is_error!r}")


def _assert_latency_expectations(*, index: int, result: object, expect: dict[str, object]) -> None:
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
