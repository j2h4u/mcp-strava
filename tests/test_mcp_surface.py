import asyncio
from types import SimpleNamespace

import pytest

from mcp_strava.types import (
    CompletenessMetadata,
    FreshnessMetadata,
    ServiceEnvelope,
    ServiceRationale,
    ServiceWarning,
)


EXPECTED_TOOL_NAMES = (
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


def _envelope(data: dict, *, unavailable: bool = False) -> ServiceEnvelope:
    return ServiceEnvelope(
        data=data,
        freshness=FreshnessMetadata(
            freshness_state="fresh",
            checked_at="2026-05-22T10:00:00Z",
            last_successful_refresh_at="2026-05-22T09:00:00Z",
            refresh_age_seconds=3600,
            last_activity_at="2026-05-22T08:30:00Z",
            last_activity_age_seconds=5400,
        ),
        completeness=CompletenessMetadata(
            status="unavailable" if unavailable else "complete",
            missing=["workout_not_found"] if unavailable else [],
            coverage={"sample_size": 1},
        ),
        warnings=(
            [ServiceWarning(code="workout_not_found", severity="info", message="Workout not found")]
            if unavailable
            else []
        ),
        rationale=[ServiceRationale(code="facts_only", message="Factual response")],
    )


def test_mcp_tool_allowlist_is_exact() -> None:
    from mcp_strava.interfaces import mcp_http

    assert mcp_http.MCP_TOOL_NAMES == EXPECTED_TOOL_NAMES
    assert FORBIDDEN_TOOL_NAMES.isdisjoint(set(mcp_http.MCP_TOOL_NAMES))


def test_validate_http_settings_and_transport_security() -> None:
    from mcp_strava.interfaces import mcp_http

    local_unsafe = SimpleNamespace(
        runtime_profile="local",
        http=SimpleNamespace(
            host="0.0.0.0",
            allow_container_bind=False,
            allowed_hosts=("127.0.0.1",),
            allowed_origins=("http://127.0.0.1",),
        ),
    )
    with pytest.raises(ValueError):
        mcp_http.validate_http_settings(local_unsafe)

    local_safe = SimpleNamespace(
        runtime_profile="local",
        http=SimpleNamespace(
            host="127.0.0.1",
            allow_container_bind=False,
            allowed_hosts=("127.0.0.1", "localhost", "mcp-strava"),
            allowed_origins=("http://127.0.0.1", "http://localhost"),
        ),
    )
    mcp_http.validate_http_settings(local_safe)

    container_allowed = SimpleNamespace(
        runtime_profile="container",
        http=SimpleNamespace(
            host="0.0.0.0",
            allow_container_bind=True,
            allowed_hosts=("127.0.0.1", "localhost", "mcp-strava"),
            allowed_origins=("http://127.0.0.1", "http://localhost"),
        ),
    )
    mcp_http.validate_http_settings(container_allowed)

    ts = mcp_http.build_transport_security(container_allowed)
    assert ts.allowed_hosts
    assert ts.allowed_origins


def test_mcp_tools_have_annotations_and_structured_output(monkeypatch) -> None:
    from mcp_strava.interfaces import mcp_http

    monkeypatch.setattr(
        mcp_http,
        "get_fitness_state_service",
        lambda **_: _envelope({"fitness": 1.0}),
    )
    monkeypatch.setattr(
        mcp_http,
        "list_workouts_service",
        lambda **_: _envelope({"items": [{"workout_id": 10}]}),
    )
    monkeypatch.setattr(
        mcp_http,
        "get_workout_detail_service",
        lambda workout_id, **_: _envelope({"workout_id": workout_id}),
    )
    monkeypatch.setattr(
        mcp_http,
        "compare_periods_service",
        lambda **_: _envelope({"global": {"metrics": {}}}),
    )
    monkeypatch.setattr(
        mcp_http,
        "project_fitness_state_service",
        lambda **_: _envelope({"projection": []}),
    )

    server = mcp_http.build_mcp_server()
    tools = asyncio.run(server.list_tools())
    assert tuple(tool.name for tool in tools) == EXPECTED_TOOL_NAMES
    assert FORBIDDEN_TOOL_NAMES.isdisjoint({tool.name for tool in tools})
    for tool in tools:
        annotations = tool.annotations
        assert annotations.readOnlyHint is True
        assert annotations.destructiveHint is False
        assert annotations.idempotentHint is True
        assert annotations.openWorldHint is False
        assert tool.inputSchema is not None

    for tool_name, arguments in (
        ("get_fitness_state", {}),
        ("list_workouts", {}),
        ("get_workout_detail", {"workout_id": 10}),
        ("compare_periods", {"period_a_start": "2026-05-01", "period_a_end": "2026-05-07", "period_b_start": "2026-04-24", "period_b_end": "2026-04-30"}),
        ("project_fitness_state", {"target_date": "2026-05-30", "scenarios": ["rest"]}),
    ):
        content, payload = asyncio.run(server.call_tool(tool_name, arguments))
        assert payload is not None
        assert set(payload.keys()) == {"data", "freshness", "completeness", "warnings", "rationale"}
        assert len(content) <= 1


def test_get_workout_detail_missing_id_is_unavailable(monkeypatch) -> None:
    from mcp_strava.interfaces import mcp_http

    monkeypatch.setattr(
        mcp_http,
        "get_fitness_state_service",
        lambda **_: _envelope({"fitness": 1.0}),
    )
    monkeypatch.setattr(
        mcp_http,
        "list_workouts_service",
        lambda **_: _envelope({"items": []}),
    )
    monkeypatch.setattr(
        mcp_http,
        "get_workout_detail_service",
        lambda workout_id, **_: _envelope({"workout_id": workout_id}, unavailable=True),
    )
    monkeypatch.setattr(
        mcp_http,
        "compare_periods_service",
        lambda **_: _envelope({"global": {"metrics": {}}}),
    )
    monkeypatch.setattr(
        mcp_http,
        "project_fitness_state_service",
        lambda **_: _envelope({"projection": []}),
    )

    server = mcp_http.build_mcp_server()
    content, payload = asyncio.run(server.call_tool("get_workout_detail", {"workout_id": 999999}))
    assert len(content) <= 1
    assert payload["completeness"]["status"] == "unavailable"
    assert any(warning["code"] == "workout_not_found" for warning in payload["warnings"])
