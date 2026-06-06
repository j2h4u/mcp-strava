from __future__ import annotations

from datetime import date, timedelta

from mcp_strava.devtools.mcp_client.contracts import EXPECTED_TOOL_NAMES, LiveSmokeResult, McpClientError, SmokeResult
from mcp_strava.devtools.mcp_client.transport import HttpMcpClient, StdioMcpClient
from mcp_strava.devtools.mcp_client.utils import (
    _coerce_day,
    _data_shape,
    _extract_first_workout_id,
    _get_structured_data,
    _product_bundle_aggregate_calls,
    _require_success,
    _warning_digest,
)


async def verify_tool_surface(client: StdioMcpClient | HttpMcpClient) -> list[str]:
    tools = await client.list_tools()
    tool_names: set[str] = set()
    for tool in tools:
        if isinstance(tool, dict):
            name_val = tool.get("name")
            if isinstance(name_val, str):
                tool_names.add(name_val)
    missing = sorted(EXPECTED_TOOL_NAMES - tool_names)
    unexpected = sorted(tool_names - EXPECTED_TOOL_NAMES)
    if missing or unexpected:
        raise McpClientError(f"unexpected MCP tool surface: missing={missing}, unexpected={unexpected}")
    return sorted(tool_names)


async def run_basic_smoke(client: StdioMcpClient | HttpMcpClient) -> SmokeResult:
    tool_names = await verify_tool_surface(client)
    workouts = _require_success("list_workouts", await client.call_tool("list_workouts", {"limit": 1}))
    sc = workouts.get("structuredContent")
    workouts_data = sc.get("data") if isinstance(sc, dict) else None
    return {
        "status": "ok",
        "mode": "basic",
        "tools": tool_names,
        "called": ["list_workouts"],
        "data_shapes": {
            "list_workouts": _data_shape(workouts_data),
        },
        "warnings": {
            "list_workouts": _warning_digest(workouts),
        },
    }


async def run_live_smoke(
    client: StdioMcpClient | HttpMcpClient,
    *,
    today: str | date | None = None,
) -> LiveSmokeResult:
    tool_names = await verify_tool_surface(client)
    fitness = _require_success("get_fitness_state", await client.call_tool("get_fitness_state", {}))
    workouts = _require_success("list_workouts", await client.call_tool("list_workouts", {"limit": 3}))
    workout_id = _extract_first_workout_id(workouts)
    detail = _require_success(
        "get_workout_detail", await client.call_tool("get_workout_detail", {"workout_id": workout_id})
    )

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
    aggregate_payloads: dict[str, dict[str, object]] = {}
    for call in _product_bundle_aggregate_calls(today_date):
        raw_args = call["arguments"]
        arguments_obj: dict[str, object] = dict(raw_args) if isinstance(raw_args, dict) else {}
        bundle_id = str(arguments_obj["metric_bundle"])
        aggregate_payloads[bundle_id] = _require_success(
            "get_training_aggregates",
            await client.call_tool("get_training_aggregates", arguments_obj),
        )

    payloads = {
        "get_fitness_state": fitness,
        "list_workouts": workouts,
        "get_workout_detail": detail,
        "compare_periods": comparison,
        "project_fitness_state": projection,
        **{f"get_training_aggregates:{bundle_id}": payload for bundle_id, payload in aggregate_payloads.items()},
    }
    return {
        "status": "ok",
        "mode": "full",
        "tools": sorted(tool_names),
        "called": sorted(payloads.keys()),
        "aggregate_bundles": list(aggregate_payloads),
        "workout_id": workout_id,
        "data_shapes": {name: _data_shape(_get_structured_data(payload)) for name, payload in payloads.items()},
        "warnings": {name: _warning_digest(payload) for name, payload in payloads.items()},
    }
