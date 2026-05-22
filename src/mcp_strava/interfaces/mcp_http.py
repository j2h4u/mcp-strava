"""Read-only HTTP MCP surface for metric services."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings
from mcp.types import ToolAnnotations

from mcp_strava.application.metric_services import (
    compare_periods_service,
    get_fitness_state_service,
    get_workout_detail_service,
    list_workouts_service,
    project_fitness_state_service,
)
from mcp_strava.settings import Settings, get_settings, load_settings
from mcp_strava.types import ServiceEnvelope, dc_to_dict

MCP_TOOL_NAMES = (
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
)

FORBIDDEN_TOOL_NAMES = {
    "get_data_status",
    "daily_report",
    "weekly_summary",
    "recent_workouts",
    "workout_analytics",
    "freshness",
    "sync",
    "backfill",
    "sql",
    "raw",
    "token",
    "token_refresh",
    "admin",
    "log",
    "sync_log",
    "db_preflight",
    "db_check",
    "db_migrate",
    "mirror_refresh",
}

_SAFE_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_WILDCARD_HOSTS = {"0.0.0.0", "::"}
_UNSAFE_TRANSPORT_VALUES = {"*", "0.0.0.0", "::"}


def _tool_annotations() -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


def _envelope_payload(envelope: ServiceEnvelope) -> dict[str, Any]:
    return {
        "data": dc_to_dict(envelope.data),
        "freshness": dc_to_dict(envelope.freshness),
        "completeness": dc_to_dict(envelope.completeness),
        "warnings": [dc_to_dict(item) for item in envelope.warnings],
        "rationale": [dc_to_dict(item) for item in envelope.rationale],
    }


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
        instructions="Read-only training metric facts from local Strava mirror.",
        host=resolved_settings.http.host,
        port=resolved_settings.http.port,
        streamable_http_path="/mcp",
        stateless_http=True,
        transport_security=build_transport_security(resolved_settings),
    )

    @server.tool(
        name="get_fitness_state",
        description="Returns current fitness, load, and model state facts with freshness metadata.",
        annotations=_tool_annotations(),
        structured_output=True,
    )
    def get_fitness_state() -> dict[str, Any]:
        return _envelope_payload(get_fitness_state_service(signal_first_use=False))

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
        return _envelope_payload(
            list_workouts_service(
                limit=limit,
                start_date=start_date,
                end_date=end_date,
                sport=sport,
                signal_first_use=False,
            )
        )

    @server.tool(
        name="get_workout_detail",
        description="Returns detailed workout metrics for a specific workout id.",
        annotations=_tool_annotations(),
        structured_output=True,
    )
    def get_workout_detail(workout_id: int) -> dict[str, Any]:
        return _envelope_payload(get_workout_detail_service(workout_id, signal_first_use=False))

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
        return _envelope_payload(
            compare_periods_service(
                period_a_start=period_a_start,
                period_a_end=period_a_end,
                period_b_start=period_b_start,
                period_b_end=period_b_end,
                sport=sport,
                signal_first_use=False,
            )
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
        return _envelope_payload(
            project_fitness_state_service(
                target_date=target_date,
                scenarios=scenarios,
                custom_daily_trimp=custom_daily_trimp,
                signal_first_use=False,
            )
        )

    return server


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
