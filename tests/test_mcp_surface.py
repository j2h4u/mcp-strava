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
from tests.test_read_model_queries import READ_MODEL_METADATA_KEYS

EXPECTED_TOOL_NAMES = (
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
    "get_training_aggregates",
)

EXPECTED_PROMPT_NAMES = (
    "strava_daily_training_brief",
    "strava_weekly_training_digest",
    "strava_shoe_mileage_watchdog",
)

EXPECTED_PRODUCT_BUNDLES = ("daily_brief", "weekly_digest", "historical_facts")

FORBIDDEN_PRODUCT_FIELDS = {
    "sync",
    "backfill",
    "raw",
    "sql",
    "token",
    "log",
    "debug",
    "admin",
}

FORBIDDEN_ADVICE_PHRASES = (
    "you should",
    "need to",
    "recommended",
    "hydrate",
    "worry",
    "change behavior",
)

EXPECTED_COMPLETENESS_KEYS = {
    "requested_metrics",
    "included_metrics",
    "unavailable_metrics",
    "skipped_metrics",
    "scope_incompatible_metrics",
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
            coverage={
                "sample_size": 1,
                "read_model": {
                    "status": "current",
                    "last_materialized_at": "2026-05-22T09:30:00Z",
                    "dirty_count": 0,
                    "oldest_dirty_day": None,
                    "metric_versions_present": [1],
                    "stale_reason": None,
                },
            },
        ),
        warnings=(
            [ServiceWarning(code="workout_not_found", severity="info", message="Workout not found")]
            if unavailable
            else []
        ),
        rationale=[ServiceRationale(code="facts_only", message="Factual response")],
    )


def _schema_property_names(schema: dict) -> set[str]:
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    assert isinstance(properties, dict)
    return set(properties)


def _bundle_envelope(bundle_id: str) -> ServiceEnvelope:
    completeness = {
        "requested_metrics": ["trimp", "form_zone", "hrr_pct"],
        "included_metrics": ["trimp"],
        "unavailable_metrics": [{"metric_id": "form_zone", "reason_code": "data_absent"}],
        "skipped_metrics": [],
        "scope_incompatible_metrics": [{"metric_id": "hrr_pct", "reason_code": "scope_incompatible"}],
    }
    return _envelope(
        {
            "request": {"bundle_id": bundle_id},
            "rows": [{"metric_id": "trimp", "value": 42.0, "completeness_status": "complete"}],
            "bundle": {
                "bundle_id": bundle_id,
                "sections": {
                    "current_state": {
                        "rows": [{"metric_id": "trimp", "value": 42.0}],
                        "bundle_completeness": completeness,
                    },
                    "read_model": {
                        "facts": {"status": "current"},
                        "bundle_completeness": {
                            "requested_metrics": ["fitness"],
                            "included_metrics": [],
                            "unavailable_metrics": [{"metric_id": "fitness", "reason_code": "data_absent"}],
                            "skipped_metrics": [],
                            "scope_incompatible_metrics": [],
                        },
                    },
                },
                "bundle_completeness": completeness,
            },
        }
    )


def _walk_payload(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key, value
            yield from _walk_payload(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_payload(value)


def _assert_no_forbidden_product_surface(payload: dict) -> None:
    for key, value in _walk_payload(payload):
        lowered_key = str(key).lower()
        assert not any(fragment == lowered_key or fragment in lowered_key for fragment in FORBIDDEN_PRODUCT_FIELDS), key
        if isinstance(value, str):
            lowered_value = value.lower()
            assert not any(phrase in lowered_value for phrase in FORBIDDEN_ADVICE_PHRASES), value


def _assert_completeness_reason_codes(completeness: dict) -> None:
    assert EXPECTED_COMPLETENESS_KEYS <= set(completeness)
    requested = set(completeness["requested_metrics"])
    for bucket_name in ("unavailable_metrics", "skipped_metrics", "scope_incompatible_metrics"):
        bucket = completeness[bucket_name]
        assert isinstance(bucket, list)
        for item in bucket:
            assert item["metric_id"] in requested
            assert item["reason_code"]


def _assert_bundle_payload_contract(payload: dict, *, bundle_id: str) -> None:
    data = payload["data"]
    assert data["rows"]
    bundle = data["bundle"]
    assert bundle["bundle_id"] == bundle_id
    assert bundle["sections"]
    _assert_completeness_reason_codes(bundle["bundle_completeness"])
    for section in bundle["sections"].values():
        _assert_completeness_reason_codes(section["bundle_completeness"])
    assert payload["freshness"]
    assert READ_MODEL_METADATA_KEYS <= set(payload["completeness"]["coverage"]["read_model"])
    _assert_no_forbidden_product_surface(payload)


def test_mcp_tool_allowlist_is_exact() -> None:
    from mcp_strava.interfaces import mcp_http

    assert mcp_http.MCP_TOOL_NAMES == EXPECTED_TOOL_NAMES
    assert mcp_http.MCP_PROMPT_NAMES == EXPECTED_PROMPT_NAMES
    assert "sync" in mcp_http.MCP_INSTRUCTIONS
    assert "raw SQL" in mcp_http.MCP_INSTRUCTIONS
    assert "medical diagnoses" in mcp_http.MCP_INSTRUCTIONS


def test_get_training_aggregates_schema_is_product_only() -> None:
    from mcp_strava.interfaces import mcp_http

    server = mcp_http.build_mcp_server()
    tools = asyncio.run(server.list_tools())
    aggregate_tool = next(tool for tool in tools if tool.name == "get_training_aggregates")
    properties = _schema_property_names(aggregate_tool.inputSchema)

    expected_properties = {
        "start_date",
        "end_date",
        "bucket",
        "metric_ids",
        "metric_bundle",
        "scope",
        "sports",
        "include_empty_buckets",
        "as_of_day",
        "window_days",
    }
    assert properties <= expected_properties
    assert {"start_date", "end_date", "bucket", "scope"}.issubset(properties)
    assert {"metric_ids", "metric_bundle"} & properties

    forbidden_fragments = {
        "sql",
        "table",
        "query",
        "plan",
        "migration",
        "sync",
        "backfill",
        "recompute",
        "dirty",
        "queue",
        "token",
        "raw",
        "debug",
        "admin",
        "gear",
    }
    for name in properties:
        lowered = name.lower()
        assert not any(fragment in lowered for fragment in forbidden_fragments), name


def test_mcp_prompts_are_content_backed_and_do_not_expand_tool_surface() -> None:
    from mcp_strava.interfaces import mcp_http

    server = mcp_http.build_mcp_server()
    prompts = asyncio.run(server.list_prompts())
    tools = asyncio.run(server.list_tools())

    assert tuple(prompt.name for prompt in prompts) == EXPECTED_PROMPT_NAMES
    assert tuple(tool.name for tool in tools) == EXPECTED_TOOL_NAMES

    daily = asyncio.run(server.get_prompt("strava_daily_training_brief"))
    text = daily.messages[0].content.text
    assert "list_workouts" in text
    assert "get_fitness_state" in text
    assert "kudos_count" in text
    assert "scripts/cli.py" not in text
    assert "/opt/data/skills" not in text


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

    unsafe_host = SimpleNamespace(
        runtime_profile="container",
        http=SimpleNamespace(
            host="0.0.0.0",
            allow_container_bind=True,
            allowed_hosts=("*",),
            allowed_origins=("http://localhost",),
        ),
    )
    with pytest.raises(ValueError, match="allowed_hosts"):
        mcp_http.build_transport_security(unsafe_host)

    unsafe_origin = SimpleNamespace(
        runtime_profile="container",
        http=SimpleNamespace(
            host="0.0.0.0",
            allow_container_bind=True,
            allowed_hosts=("mcp-strava",),
            allowed_origins=("*",),
        ),
    )
    with pytest.raises(ValueError, match="allowed_origins"):
        mcp_http.build_transport_security(unsafe_origin)


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
    monkeypatch.setattr(
        mcp_http,
        "get_training_aggregates_service",
        lambda *_args, **_kwargs: _envelope({"rows": []}),
        raising=False,
    )

    server = mcp_http.build_mcp_server()
    tools = asyncio.run(server.list_tools())
    assert tuple(tool.name for tool in tools) == EXPECTED_TOOL_NAMES
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
        (
            "compare_periods",
            {
                "period_a_start": "2026-05-01",
                "period_a_end": "2026-05-07",
                "period_b_start": "2026-04-24",
                "period_b_end": "2026-04-30",
            },
        ),
        ("project_fitness_state", {"target_date": "2026-05-30", "scenarios": ["rest"]}),
        (
            "get_training_aggregates",
            {
                "start_date": "2026-05-01",
                "end_date": "2026-06-01",
                "bucket": "week",
                "metric_bundle": "weekly_digest",
                "scope": "global",
            },
        ),
    ):
        content, payload = asyncio.run(server.call_tool(tool_name, arguments))
        assert payload is not None
        assert set(payload.keys()) == {"data", "freshness", "completeness", "warnings", "rationale"}
        assert READ_MODEL_METADATA_KEYS <= set(payload["completeness"]["coverage"]["read_model"])
        assert len(content) <= 1


def test_mcp_payload_rounds_floats_at_surface(monkeypatch) -> None:
    from mcp_strava.interfaces import mcp_http

    monkeypatch.setattr(
        mcp_http,
        "get_fitness_state_service",
        lambda **_: _envelope({"fitness": 42.5678, "tiny": 0.006789}),
    )
    monkeypatch.setattr(mcp_http, "list_workouts_service", lambda **_: _envelope([]))
    monkeypatch.setattr(mcp_http, "get_workout_detail_service", lambda workout_id, **_: _envelope({}))
    monkeypatch.setattr(mcp_http, "compare_periods_service", lambda **_: _envelope({}))
    monkeypatch.setattr(mcp_http, "project_fitness_state_service", lambda **_: _envelope({}))
    monkeypatch.setattr(
        mcp_http,
        "get_training_aggregates_service",
        lambda *_args, **_kwargs: _envelope({"rows": []}),
        raising=False,
    )

    server = mcp_http.build_mcp_server()
    _, payload = asyncio.run(server.call_tool("get_fitness_state", {}))

    assert payload["data"]["fitness"] == 43
    assert payload["data"]["tiny"] == 0.0068


def test_expensive_mcp_tools_use_short_lived_response_cache(monkeypatch) -> None:
    from mcp_strava.interfaces import mcp_http

    calls = 0

    def operation() -> ServiceEnvelope:
        nonlocal calls
        calls += 1
        return _envelope({"rows": [{"metric_id": "trimp"}]})

    monkeypatch.setattr(mcp_http, "_TOOL_CACHE_TTL_SECONDS", 30.0)

    first = mcp_http._run_cached_logged_tool(
        "get_training_aggregates",
        {"metric_ids": ["trimp"], "bucket": "week"},
        operation,
    )
    second = mcp_http._run_cached_logged_tool(
        "get_training_aggregates",
        {"metric_ids": ["trimp"], "bucket": "week"},
        operation,
    )

    assert calls == 1
    assert first == second


def test_training_aggregate_bundle_payloads_keep_rows_sections_metadata_and_reasons(monkeypatch) -> None:
    from mcp_strava.interfaces import mcp_http

    monkeypatch.setattr(
        mcp_http,
        "get_training_aggregates_service",
        lambda request, **_: _bundle_envelope(request.bundle_id),
    )
    server = mcp_http.build_mcp_server()

    for bundle_id in EXPECTED_PRODUCT_BUNDLES:
        _, payload = asyncio.run(
            server.call_tool(
                "get_training_aggregates",
                {
                    "start_date": "2026-05-01",
                    "end_date": "2026-05-25",
                    "bucket": "all_time",
                    "metric_bundle": bundle_id,
                    "scope": "both",
                    "as_of_day": "2026-05-24",
                    "window_days": 28,
                },
            )
        )
        _assert_bundle_payload_contract(payload, bundle_id=bundle_id)


def test_daily_brief_mcp_composition_keeps_workout_facts_on_workout_tools(monkeypatch) -> None:
    from mcp_strava.interfaces import mcp_http

    monkeypatch.setattr(
        mcp_http, "get_training_aggregates_service", lambda request, **_: _bundle_envelope(request.bundle_id)
    )
    monkeypatch.setattr(
        mcp_http,
        "list_workouts_service",
        lambda **_: _envelope({"items": [{"activity_id": 701, "kudos_count": 2}]}),
    )
    monkeypatch.setattr(
        mcp_http,
        "get_workout_detail_service",
        lambda workout_id, **_: _envelope({"activity_id": workout_id, "gear_name": "Road Shoe"}),
    )
    server = mcp_http.build_mcp_server()

    _, aggregate_payload = asyncio.run(
        server.call_tool(
            "get_training_aggregates",
            {
                "start_date": "2026-05-11",
                "end_date": "2026-05-25",
                "bucket": "all_time",
                "metric_bundle": "daily_brief",
                "scope": "both",
                "as_of_day": "2026-05-24",
                "window_days": 14,
            },
        )
    )
    _, workouts_payload = asyncio.run(server.call_tool("list_workouts", {"limit": 1}))
    _, detail_payload = asyncio.run(server.call_tool("get_workout_detail", {"workout_id": 701}))

    aggregate_data = aggregate_payload["data"]
    assert aggregate_data["rows"]
    assert "recent_workouts" not in aggregate_data["bundle"]["sections"]
    assert all("activity_id" not in row for row in aggregate_data["rows"])
    assert workouts_payload["data"]["items"][0]["activity_id"] == 701
    assert detail_payload["data"]["gear_name"] == "Road Shoe"
    assert tuple(tool.name for tool in asyncio.run(server.list_tools())) == EXPECTED_TOOL_NAMES


def test_training_aggregate_cache_identity_includes_full_product_request(monkeypatch) -> None:
    from mcp_strava.interfaces import mcp_http

    captured: list[dict] = []

    def capture_cached_call(name: str, arguments: dict, operation):
        captured.append({"name": name, "arguments": arguments})
        return mcp_http._envelope_payload(operation())

    monkeypatch.setattr(mcp_http, "_run_cached_logged_tool", capture_cached_call)
    monkeypatch.setattr(
        mcp_http,
        "get_training_aggregates_service",
        lambda request, **_: _bundle_envelope(request.bundle_id),
    )
    server = mcp_http.build_mcp_server()

    asyncio.run(
        server.call_tool(
            "get_training_aggregates",
            {
                "start_date": "2026-05-01",
                "end_date": "2026-05-25",
                "bucket": "week",
                "metric_bundle": "weekly_digest",
                "scope": "both",
                "sports": ["Run"],
                "include_empty_buckets": True,
                "as_of_day": "2026-05-24",
                "window_days": 28,
            },
        )
    )

    assert captured == [
        {
            "name": "get_training_aggregates",
            "arguments": {
                "end_date": "2026-05-25",
                "bucket": "week",
                "start_date": "2026-05-01",
                "metric_ids": [],
                "metric_bundle": "weekly_digest",
                "scope": "both",
                "sports": ["Run"],
                "include_empty_buckets": True,
                "as_of_day": "2026-05-24",
                "window_days": 28,
            },
        }
    ]


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
    monkeypatch.setattr(
        mcp_http,
        "get_training_aggregates_service",
        lambda *_args, **_kwargs: _envelope({"rows": []}),
        raising=False,
    )

    server = mcp_http.build_mcp_server()
    content, payload = asyncio.run(server.call_tool("get_workout_detail", {"workout_id": 999999}))
    assert len(content) <= 1
    assert payload["completeness"]["status"] == "unavailable"
    assert any(warning["code"] == "workout_not_found" for warning in payload["warnings"])


def test_warning_codes_surface_codes_for_logs() -> None:
    from mcp_strava.interfaces.mcp_http import _warning_codes

    warnings = [
        {"code": "aggregate_rows_incomplete", "severity": "warning", "message": "ignored"},
        {"code": "read_model_not_current", "severity": "warning"},
    ]
    assert _warning_codes(warnings) == ["aggregate_rows_incomplete", "read_model_not_current"]
    assert _warning_codes([]) == []
    assert _warning_codes(None) == []
