"""Read-only HTTP MCP surface for metric services."""

from __future__ import annotations

import json
import sys
import time
from copy import deepcopy
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING, Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_strava.application.aggregate_services import (
    AggregateServiceRequest,
    get_training_aggregates_service,
)
from mcp_strava.application.comparison_services import compare_periods_service
from mcp_strava.application.metric_services import (
    get_fitness_state_service,
    get_workout_detail_service,
    list_workouts_service,
)
from mcp_strava.application.projection_services import (
    SUPPORTED_PROJECTION_SCENARIOS,
    project_fitness_state_service,
)
from mcp_strava.mcp_content import MCP_PROMPT_NAMES as MCP_PROMPT_NAMES  # re-exported as part of the MCP surface
from mcp_strava.mcp_content import load_prompt
from mcp_strava.metric_registry import AGGREGATE_METRIC_BUNDLES
from mcp_strava.metric_registry_shared import (
    SUPPORTED_AGGREGATE_BUCKETS,
    SUPPORTED_AGGREGATE_SCOPES,
    SUPPORTED_ROLLING_WINDOW_DAYS,
)
from mcp_strava.settings import Settings, get_settings, load_settings
from mcp_strava.sports import SPORT_ALL
from mcp_strava.types import ServiceEnvelope, ServiceWarning, dc_to_dict

MCP_TOOL_NAMES = (
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
    "get_training_aggregates",
)

# --- Tool parameter enums -------------------------------------------------
# Each enum is DERIVED from its canonical domain constant, so the JSON schema the
# calling agent sees and the values the backend accepts share a single source of
# truth and cannot drift. FastMCP renders these as JSON-schema enums on the params.
# Static checkers cannot infer members of a functionally-built enum, so they see the
# underlying scalar; at runtime these are the real enums that FastMCP/Pydantic render
# as JSON-schema enums. Either way the values come from one canonical source.
if TYPE_CHECKING:
    SportType = str
    BucketName = str
    AggregateScope = str
    ProjectionScenario = str
    MetricBundle = str
    RollingWindowDays = int
else:
    SportType = StrEnum("SportType", {name: name for name in SPORT_ALL})
    BucketName = StrEnum("BucketName", {name: name for name in SUPPORTED_AGGREGATE_BUCKETS})
    AggregateScope = StrEnum("AggregateScope", {name: name for name in SUPPORTED_AGGREGATE_SCOPES})
    ProjectionScenario = StrEnum("ProjectionScenario", {name: name for name in SUPPORTED_PROJECTION_SCENARIOS})
    MetricBundle = StrEnum("MetricBundle", {name: name for name in AGGREGATE_METRIC_BUNDLES})
    RollingWindowDays = IntEnum("RollingWindowDays", {f"days_{days}": days for days in SUPPORTED_ROLLING_WINDOW_DAYS})

_DEFAULT_SCOPE = AggregateScope("global")  # module-level default (avoids a call in arg defaults)

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
_TOOL_RESPONSE_CACHE: dict[str, tuple[float, ServiceEnvelope]] = {}


def _tool_annotations() -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


def _envelope_payload(envelope: ServiceEnvelope) -> ServiceEnvelope:
    """Round the float-bearing ``data`` for output; the metadata carries no floats.

    Returning the typed envelope (instead of a hand-built dict) lets FastMCP publish
    a real output schema from the shared ServiceEnvelope contract, while keeping the
    rounded, agent-friendly numbers in ``data``.
    """
    return ServiceEnvelope(
        data=dc_to_dict(envelope.data, round_floats=True),
        freshness=envelope.freshness,
        completeness=envelope.completeness,
        warnings=envelope.warnings,
        rationale=envelope.rationale,
    )


def _data_shape(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {"type": "dict", "keys": sorted(value.keys())[:30]}
    if isinstance(value, list):
        first: object = value[0] if value else None
        first_keys = sorted(first.keys())[:30] if isinstance(first, dict) else None
        return {"type": "list", "count": len(value), "first_keys": first_keys}
    return {"type": type(value).__name__}


def _warning_codes(warnings: list[ServiceWarning]) -> list[str]:
    """Extract warning ``code`` strings for log lines.

    Logging only ``warnings_count`` tells an operator a warning fired but not
    which one — forcing a source dive. Emitting the codes alongside the count
    keeps the log self-explanatory without bloating it with full messages.
    """
    return [warning.code for warning in warnings]


def _emit_log(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False, sort_keys=True), file=sys.stderr, flush=True)


def _run_logged_tool(name: str, operation) -> ServiceEnvelope:
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
        warnings_count=len(payload.warnings),
        warning_codes=_warning_codes(payload.warnings),
        data_shape=_data_shape(payload.data),
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


def _run_cached_logged_tool(name: str, arguments: dict[str, Any], operation) -> ServiceEnvelope:
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
            warnings_count=len(payload.warnings),
            warning_codes=_warning_codes(payload.warnings),
            data_shape=_data_shape(payload.data),
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
    """Build transport-layer guards for the MCP HTTP surface.

    THREAT MODEL (single-user, local): there is NO per-request authentication on
    this surface — any process that can reach the bound address may call every
    tool. That is acceptable only because the service is deployed for one user
    behind these load-bearing assumptions:
      - the container binds loopback by default; a wildcard bind requires the
        container profile AND an explicit allow flag (see validate_http_settings);
      - the compose file exposes the port to the internal Docker network only
        (`expose`, not `ports`) — it is not published to the LAN;
      - DNS-rebinding protection plus host/origin allowlists (below) block
        browser-driven cross-origin access.
    If this ever becomes multi-user or network-reachable, add per-request auth —
    the transport guards here are not a substitute for it.
    """
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
        description="Daily training brief scenario using factual Strava MCP metrics.",
    )
    def strava_daily_training_brief() -> str:
        return load_prompt("strava_daily_training_brief", resolved_settings.prompt_language)

    @server.prompt(
        name="strava_weekly_training_digest",
        title="Strava Weekly Training Digest",
        description="Weekly training digest scenario using period comparison metrics.",
    )
    def strava_weekly_training_digest() -> str:
        return load_prompt("strava_weekly_training_digest", resolved_settings.prompt_language)

    @server.prompt(
        name="strava_shoe_mileage_watchdog",
        title="Strava Shoe Mileage Watchdog",
        description="Shoe-mileage review scenario that only reports facts exposed by the MCP surface.",
    )
    def strava_shoe_mileage_watchdog() -> str:
        return load_prompt("strava_shoe_mileage_watchdog", resolved_settings.prompt_language)

    @server.tool(
        name="get_fitness_state",
        description="Returns current fitness, load, and model state facts with freshness metadata.",
        annotations=_tool_annotations(),
        structured_output=True,
    )
    def get_fitness_state() -> ServiceEnvelope:
        return _run_logged_tool("get_fitness_state", lambda: get_fitness_state_service(signal_first_use=False))

    @server.tool(
        name="list_workouts",
        description="Lists workouts with factual volume and intensity metrics.",
        annotations=_tool_annotations(),
        structured_output=True,
    )
    def list_workouts(
        limit: Annotated[int, Field(description="Maximum number of workouts to return.", examples=[20])] = 20,
        start_date: Annotated[
            str | None,
            Field(description="Earliest workout date, inclusive, ISO YYYY-MM-DD.", examples=["2026-01-01"]),
        ] = None,
        end_date: Annotated[
            str | None,
            Field(description="Latest workout date, inclusive, ISO YYYY-MM-DD.", examples=["2026-06-01"]),
        ] = None,
        sport: Annotated[SportType | None, Field(description="Filter to one Strava sport type.")] = None,
    ) -> ServiceEnvelope:
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
    def get_workout_detail(
        workout_id: Annotated[int, Field(description="Strava activity id.", examples=[1234567890])],
    ) -> ServiceEnvelope:
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
        period_a_start: Annotated[
            str, Field(description="Period A start, inclusive, ISO YYYY-MM-DD.", examples=["2026-05-01"])
        ],
        period_a_end: Annotated[
            str, Field(description="Period A end, inclusive, ISO YYYY-MM-DD.", examples=["2026-05-31"])
        ],
        period_b_start: Annotated[
            str, Field(description="Period B start, inclusive, ISO YYYY-MM-DD.", examples=["2026-04-01"])
        ],
        period_b_end: Annotated[
            str, Field(description="Period B end, inclusive, ISO YYYY-MM-DD.", examples=["2026-04-30"])
        ],
        sport: Annotated[SportType | None, Field(description="Filter to one Strava sport type.")] = None,
    ) -> ServiceEnvelope:
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
        target_date: Annotated[
            str,
            Field(
                description="Projection horizon end, inclusive, ISO YYYY-MM-DD. Must be today or later.",
                examples=["2026-07-01"],
            ),
        ],
        scenarios: Annotated[
            list[ProjectionScenario],
            Field(description="Training scenarios to project forward."),
        ],
        custom_daily_trimp: Annotated[
            list[dict[str, Any]] | None,
            Field(
                description=(
                    "Per-day TRIMP overrides, used only with the 'custom' scenario. Each item is "
                    "{date: YYYY-MM-DD, trimp: number >= 0}; dates unique and within today..target_date."
                ),
            ),
        ] = None,
    ) -> ServiceEnvelope:
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
        end_date: Annotated[
            str,
            Field(description="Exclusive end of the date range, ISO YYYY-MM-DD.", examples=["2026-06-01"]),
        ],
        bucket: Annotated[
            BucketName,
            Field(
                description=(
                    "Aggregation bucket. day/week/month/year are CALENDAR-aligned (weeks start "
                    "Monday); all_time collapses the whole range into one bucket. For rolling "
                    "'last-N-days', use window_days instead."
                ),
            ),
        ],
        start_date: Annotated[
            str | None,
            Field(
                description="Inclusive start of the date range, ISO YYYY-MM-DD. Omit to start at the earliest local activity.",
                examples=["2026-01-01"],
            ),
        ] = None,
        metric_ids: Annotated[
            list[str] | None,
            Field(
                description="Registry metric ids to include (e.g. trimp, distance_km, avg_hr). Omit to use the bundle's default set."
            ),
        ] = None,
        metric_bundle: Annotated[
            MetricBundle | None,
            Field(description="Prepared metric bundle selecting a predefined metric set."),
        ] = None,
        scope: Annotated[
            AggregateScope,
            Field(description="Aggregate globally, per sport, or both."),
        ] = _DEFAULT_SCOPE,
        sports: Annotated[
            list[SportType] | None,
            Field(description="Filter to a single Strava sport type (only one is supported)."),
        ] = None,
        include_empty_buckets: Annotated[
            bool,
            Field(description="Include buckets with no activity as empty rows."),
        ] = False,
        as_of_day: Annotated[
            str | None,
            Field(
                description="Rolling-window anchor day, ISO YYYY-MM-DD. Use together with window_days.",
                examples=["2026-06-01"],
            ),
        ] = None,
        window_days: Annotated[
            RollingWindowDays | None,
            Field(
                description="Rolling-window length in days; only materialized windows (7, 14, 28, 42, 90) are valid."
            ),
        ] = None,
    ) -> ServiceEnvelope:
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


def _single_sport_filter(sports: list[SportType] | None) -> str | None:
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
