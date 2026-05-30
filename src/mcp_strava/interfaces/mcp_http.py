"""Read-only HTTP MCP surface for metric services."""

from __future__ import annotations

import json
import sys
import time
from copy import deepcopy
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from mcp_strava.application.aggregate_services import (
    AggregateServiceRequest,
    get_training_aggregates_service,
)
from mcp_strava.application.metric_services import (
    compare_periods_service,
    get_fitness_state_service,
    get_workout_detail_service,
    list_workouts_service,
    project_fitness_state_service,
)
from mcp_strava.mcp_content import MCP_PROMPT_NAMES, load_prompt  # noqa: F401
from mcp_strava.settings import Settings, get_settings, load_settings
from mcp_strava.types import ServiceEnvelope, dc_to_dict

MCP_TOOL_NAMES = (
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
    "get_training_aggregates",
)

MCP_INSTRUCTIONS = """Read-only factual training metrics from the local Strava mirror.
Do not invent or request sync, admin, debug, raw SQL, token, or raw Strava capabilities.
For user-facing narrative, expand abbreviations on first use, avoid raw floating-point dumps,
and explain what each important number means in context. Do not make medical diagnoses or
pretend this MCP server interprets training; interpretation belongs to the calling agent."""

_SAFE_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_WILDCARD_HOSTS = {"0.0.0.0", "::"}
_UNSAFE_TRANSPORT_VALUES = {"*", "0.0.0.0", "::"}
_CACHEABLE_TOOL_NAMES = {"compare_periods", "get_training_aggregates"}
_TOOL_CACHE_TTL_SECONDS = 30.0
_TOOL_CACHE_MAX_ENTRIES = 32
_TOOL_RESPONSE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _tool_annotations() -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


def _envelope_payload(envelope: ServiceEnvelope) -> dict[str, Any]:
    return {
        "data": dc_to_dict(envelope.data, round_floats=True),
        "freshness": dc_to_dict(envelope.freshness, round_floats=True),
        "completeness": dc_to_dict(envelope.completeness, round_floats=True),
        "warnings": [dc_to_dict(item, round_floats=True) for item in envelope.warnings],
        "rationale": [dc_to_dict(item, round_floats=True) for item in envelope.rationale],
    }


def _data_shape(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {"type": "dict", "keys": sorted(value.keys())[:30]}
    if isinstance(value, list):
        first = value[0] if value else None
        first_keys = sorted(first.keys())[:30] if isinstance(first, dict) else None
        return {"type": "list", "count": len(value), "first_keys": first_keys}
    return {"type": type(value).__name__}


def _emit_log(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False, sort_keys=True), file=sys.stderr, flush=True)


def _run_logged_tool(name: str, operation) -> dict[str, Any]:
    started = time.perf_counter()
    _emit_log("mcp_tool_call_started", tool=name)
    try:
        payload = _envelope_payload(operation())
    except Exception as exc:
        _emit_log(
            "mcp_tool_call_failed",
            tool=name,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise
    _emit_log(
        "mcp_tool_call_finished",
        tool=name,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        warnings_count=len(payload.get("warnings") or []),
        data_shape=_data_shape(payload.get("data")),
    )
    return payload


def _cache_key(name: str, arguments: dict[str, Any]) -> str:
    return json.dumps({"tool": name, "arguments": arguments}, sort_keys=True, separators=(",", ":"), default=str)


def _prune_tool_response_cache(now: float) -> None:
    expired = [key for key, (expires_at, _payload) in _TOOL_RESPONSE_CACHE.items() if expires_at <= now]
    for key in expired:
        _TOOL_RESPONSE_CACHE.pop(key, None)
    while len(_TOOL_RESPONSE_CACHE) >= _TOOL_CACHE_MAX_ENTRIES:
        oldest_key = min(_TOOL_RESPONSE_CACHE, key=lambda key: _TOOL_RESPONSE_CACHE[key][0])
        _TOOL_RESPONSE_CACHE.pop(oldest_key, None)


def _run_cached_logged_tool(name: str, arguments: dict[str, Any], operation) -> dict[str, Any]:
    if name not in _CACHEABLE_TOOL_NAMES:
        return _run_logged_tool(name, operation)

    key = _cache_key(name, arguments)
    now = time.monotonic()
    cached = _TOOL_RESPONSE_CACHE.get(key)
    if cached is not None and cached[0] > now:
        started = time.perf_counter()
        payload = deepcopy(cached[1])
        _emit_log("mcp_tool_call_started", tool=name, cached=True)
        _emit_log(
            "mcp_tool_call_finished",
            tool=name,
            cached=True,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            warnings_count=len(payload.get("warnings") or []),
            data_shape=_data_shape(payload.get("data")),
        )
        return payload

    payload = _run_logged_tool(name, operation)
    _prune_tool_response_cache(now)
    _TOOL_RESPONSE_CACHE[key] = (now + _TOOL_CACHE_TTL_SECONDS, deepcopy(payload))
    return payload


def validate_http_settings(settings: Settings) -> None:
    profile = settings.runtime_profile.strip().lower()
    host = settings.http.host.strip().lower()
    if profile == "local":
        if host in _WILDCARD_HOSTS:
            raise ValueError("Unsafe local bind host; use loopback host for local profile")
        if host not in _SAFE_LOCAL_HOSTS:
            raise ValueError("Unsafe local bind host; local profile requires loopback host")
    if host in _WILDCARD_HOSTS and not (profile == "container" and settings.http.allow_container_bind):
        raise ValueError("Wildcard bind host requires container profile and explicit allow flag")


def build_transport_security(settings: Settings) -> TransportSecuritySettings:
    if not settings.http.allowed_hosts:
        raise ValueError("allowed_hosts must not be empty")
    if not settings.http.allowed_origins:
        raise ValueError("allowed_origins must not be empty")
    for value in settings.http.allowed_hosts:
        if value.strip().lower() in _UNSAFE_TRANSPORT_VALUES:
            raise ValueError("allowed_hosts contains unsafe wildcard entries")
    for value in settings.http.allowed_origins:
        if value.strip().lower() in _UNSAFE_TRANSPORT_VALUES:
            raise ValueError("allowed_origins contains unsafe wildcard entries")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(settings.http.allowed_hosts),
        allowed_origins=list(settings.http.allowed_origins),
    )


def build_mcp_server(settings: Settings | None = None) -> FastMCP:
    resolved_settings = settings or get_settings()
    validate_http_settings(resolved_settings)
    server = FastMCP(
        name="mcp-strava",
        instructions=MCP_INSTRUCTIONS,
        host=resolved_settings.http.host,
        port=resolved_settings.http.port,
        streamable_http_path="/mcp",
        stateless_http=True,
        transport_security=build_transport_security(resolved_settings),
    )

    @server.prompt(
        name="strava_daily_training_brief",
        title="Strava Daily Training Brief",
        description="Daily Russian training brief scenario using factual Strava MCP metrics.",
    )
    def strava_daily_training_brief() -> str:
        return load_prompt("strava_daily_training_brief")

    @server.prompt(
        name="strava_weekly_training_digest",
        title="Strava Weekly Training Digest",
        description="Weekly Russian training digest scenario using period comparison metrics.",
    )
    def strava_weekly_training_digest() -> str:
        return load_prompt("strava_weekly_training_digest")

    @server.prompt(
        name="strava_shoe_mileage_watchdog",
        title="Strava Shoe Mileage Watchdog",
        description="Shoe-mileage review scenario that only reports facts exposed by the MCP surface.",
    )
    def strava_shoe_mileage_watchdog() -> str:
        return load_prompt("strava_shoe_mileage_watchdog")

    @server.tool(
        name="get_fitness_state",
        description="Returns current fitness, load, and model state facts with freshness metadata.",
        annotations=_tool_annotations(),
        structured_output=True,
    )
    def get_fitness_state() -> dict[str, Any]:
        return _run_logged_tool("get_fitness_state", lambda: get_fitness_state_service(signal_first_use=False))

    @server.tool(
        name="list_workouts",
        description="Lists workouts with factual volume and intensity metrics.",
        annotations=_tool_annotations(),
        structured_output=True,
    )
    def list_workouts(
        limit: int = 20,
        start_date: str | None = None,
        end_date: str | None = None,
        sport: str | None = None,
    ) -> dict[str, Any]:
        return _run_logged_tool(
            "list_workouts",
            lambda: list_workouts_service(
                limit=limit,
                start_date=start_date,
                end_date=end_date,
                sport=sport,
                signal_first_use=False,
            ),
        )

    @server.tool(
        name="get_workout_detail",
        description="Returns detailed workout metrics for a specific workout id.",
        annotations=_tool_annotations(),
        structured_output=True,
    )
    def get_workout_detail(workout_id: int) -> dict[str, Any]:
        return _run_logged_tool(
            "get_workout_detail",
            lambda: get_workout_detail_service(workout_id, signal_first_use=False),
        )

    @server.tool(
        name="compare_periods",
        description="Compares factual metrics between two date periods.",
        annotations=_tool_annotations(),
        structured_output=True,
    )
    def compare_periods(
        period_a_start: str,
        period_a_end: str,
        period_b_start: str,
        period_b_end: str,
        sport: str | None = None,
    ) -> dict[str, Any]:
        cache_args = {
            "period_a_start": period_a_start,
            "period_a_end": period_a_end,
            "period_b_start": period_b_start,
            "period_b_end": period_b_end,
            "sport": sport,
        }
        return _run_cached_logged_tool(
            "compare_periods",
            cache_args,
            lambda: compare_periods_service(
                period_a_start=period_a_start,
                period_a_end=period_a_end,
                period_b_start=period_b_start,
                period_b_end=period_b_end,
                sport=sport,
                signal_first_use=False,
            ),
        )

    @server.tool(
        name="project_fitness_state",
        description="Projects fitness-state model facts for named scenarios until target date.",
        annotations=_tool_annotations(),
        structured_output=True,
    )
    def project_fitness_state(
        target_date: str,
        scenarios: list[str],
        custom_daily_trimp: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return _run_logged_tool(
            "project_fitness_state",
            lambda: project_fitness_state_service(
                target_date=target_date,
                scenarios=scenarios,
                custom_daily_trimp=custom_daily_trimp,
                signal_first_use=False,
            ),
        )

    @server.tool(
        name="get_training_aggregates",
        description="Returns bucketed factual training metric aggregates from prepared local facts.",
        annotations=_tool_annotations(),
        structured_output=True,
    )
    def get_training_aggregates(
        end_date: str,
        bucket: str,
        start_date: str | None = None,
        metric_ids: list[str] | None = None,
        metric_bundle: str | None = None,
        scope: str = "global",
        sports: list[str] | None = None,
        include_empty_buckets: bool = False,
        as_of_day: str | None = None,
        window_days: int | None = None,
    ) -> dict[str, Any]:
        sport_filter = _single_sport_filter(sports)
        request = AggregateServiceRequest(
            metric_ids=tuple(metric_ids or ()),
            bundle_id=metric_bundle,
            bucket=bucket,
            start_day=start_date,
            end_day_exclusive=end_date,
            scope=scope,
            sport_filter=sport_filter,
            include_empty_buckets=include_empty_buckets,
            as_of_day=as_of_day,
            window_days=window_days,
        )
        cache_args = {
            "end_date": end_date,
            "bucket": bucket,
            "start_date": start_date,
            "metric_ids": list(metric_ids or []),
            "metric_bundle": metric_bundle,
            "scope": scope,
            "sports": list(sports or []),
            "include_empty_buckets": include_empty_buckets,
            "as_of_day": as_of_day,
            "window_days": window_days,
        }
        return _run_cached_logged_tool(
            "get_training_aggregates",
            cache_args,
            lambda: get_training_aggregates_service(
                request,
                signal_first_use=False,
            ),
        )

    return server


def _single_sport_filter(sports: list[str] | None) -> str | None:
    selected = [sport for sport in (sports or []) if sport]
    if len(selected) > 1:
        raise ValueError("Only one sport filter is supported for aggregate requests")
    return selected[0] if selected else None


def main(argv: list[str] | None = None) -> int:
    args = argv or []
    if "--help" in args or "-h" in args:
        print("Usage: python -m mcp_strava.interfaces.mcp_http [--help] [--version]")
        return 0
    if "--version" in args:
        print("mcp-strava mcp-http")
        return 0

    settings = load_settings()
    validate_http_settings(settings)
    app = build_mcp_server(settings)
    app.run(transport="streamable-http")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
