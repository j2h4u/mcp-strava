from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from mcp_strava.adapters.duckdb.connection import open_fixture_db
from mcp_strava.metric_registry import (
    METRIC_REGISTRY,
    STATUS_FACT_REGISTRY,
    metrics_for_aggregate_bundle,
)
from mcp_strava.types import ServiceEnvelope, dc_to_dict
from tests.test_training_aggregates import _aggregate_fixture, _phase9_status_fixture

ALLOWED_BUNDLE_REASON_CODES = {
    "scope_incompatible",
    "unsupported_window",
    "missing_read_model_fact",
    "no_rows",
    "metric_not_registered",
    "data_absent",
    "not_applicable_to_detail",
    "gear_data_not_mirrored",
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


def _payload(envelope: ServiceEnvelope) -> dict[str, object]:
    payload = dc_to_dict(envelope)
    assert isinstance(envelope, ServiceEnvelope)
    assert set(payload) == {"data", "freshness", "completeness", "warnings", "rationale"}
    return payload


def _walk_strings(obj) -> list[str]:
    if isinstance(obj, dict):
        strings: list[str] = []
        for value in obj.values():
            strings.extend(_walk_strings(value))
        return strings
    if isinstance(obj, list):
        strings = []
        for value in obj:
            strings.extend(_walk_strings(value))
        return strings
    if isinstance(obj, str):
        return [obj]
    return []


def _assert_no_advice_text(payload: dict[str, object]) -> None:
    for text in _walk_strings(payload):
        lowered = text.lower()
        assert not any(phrase in lowered for phrase in FORBIDDEN_ADVICE_PHRASES), text


def _assert_metric_ids_registered(metric_ids: set[str]) -> None:
    unknown = metric_ids - set(METRIC_REGISTRY)
    assert not unknown, sorted(unknown)


def _collect_metric_ids(obj) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        metric_id = obj.get("metric_id")
        if isinstance(metric_id, str):
            found.add(metric_id)
        for key, value in obj.items():
            if key in METRIC_REGISTRY:
                found.add(str(key))
            found.update(_collect_metric_ids(value))
    elif isinstance(obj, list):
        for value in obj:
            found.update(_collect_metric_ids(value))
    return found


def _reason_code(item: object) -> str | None:
    if isinstance(item, dict):
        raw = item.get("reason_code") or item.get("reason")
        return str(raw) if raw else None
    return None


def _metric_id(item: object) -> str | None:
    if isinstance(item, dict):
        raw = item.get("metric_id")
        return str(raw) if raw else None
    return None


def _assert_bundle_completeness(section: dict[str, object], *, requested: set[str] | None = None) -> dict[str, object]:
    completeness = section.get("bundle_completeness")
    assert isinstance(completeness, dict)
    assert set(completeness) >= EXPECTED_COMPLETENESS_KEYS

    requested_metrics = set(completeness["requested_metrics"])
    included_metrics = set(completeness["included_metrics"])
    unavailable = completeness["unavailable_metrics"]
    skipped = completeness["skipped_metrics"]
    scope_incompatible = completeness["scope_incompatible_metrics"]

    if requested is not None:
        assert requested_metrics == requested
    for bucket in (unavailable, skipped, scope_incompatible):
        assert isinstance(bucket, list)
        for item in bucket:
            assert _metric_id(item) in requested_metrics
            assert _reason_code(item) in ALLOWED_BUNDLE_REASON_CODES

    accounted = set(included_metrics)
    for bucket in (unavailable, skipped, scope_incompatible):
        accounted.update(str(_metric_id(item)) for item in bucket)
    assert requested_metrics <= accounted
    _assert_metric_ids_registered(requested_metrics)
    _assert_metric_ids_registered(included_metrics)
    return completeness


def _assert_all_sections_have_completeness(payload: dict[str, object]) -> None:
    data = payload["data"]
    assert isinstance(data, dict)
    _assert_bundle_completeness(data)
    sections = data.get("sections")
    assert isinstance(sections, dict)
    for section in sections.values():
        assert isinstance(section, dict)
        _assert_bundle_completeness(section)


def _add_mirrored_gear_fixture(db_path: Path) -> None:
    conn = open_fixture_db(db_path)
    row = conn.execute("SELECT summary_json FROM activities WHERE id = 101").fetchone()
    summary = json.loads(row[0])
    summary["gear_id"] = "shoe-1"
    detail = {
        "gear_id": "shoe-1",
        "gear": {
            "id": "shoe-1",
            "name": "Road Shoe",
            "distance": 123456.0,
            "primary": True,
        },
    }
    conn.execute(
        "UPDATE activities SET summary_json = ?, detail_json = ? WHERE id = 101",
        [json.dumps(summary), json.dumps(detail)],
    )
    conn.close()


def test_daily_brief_facts_service_returns_product_sections_and_completeness(tmp_path: Path) -> None:
    from mcp_strava.application.product_facts import get_daily_brief_facts_service

    db_path = _aggregate_fixture(tmp_path / "daily-brief.duckdb")
    conn = open_fixture_db(db_path)
    try:
        envelope = get_daily_brief_facts_service(
            as_of_day="2026-05-21",
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    payload = _payload(envelope)
    data = payload["data"]
    assert data["bundle_id"] == "daily_brief"
    assert set(data["sections"]) >= {
        "current_state",
        "recent_workouts",
        "daily_load_14d",
        "by_sport",
        "model_context",
        "status_facts",
        "freshness",
        "read_model",
    }
    assert payload["completeness"]["coverage"]["read_model"]["status"] == "current"
    _assert_all_sections_have_completeness(payload)
    _assert_bundle_completeness(data, requested=set(metrics_for_aggregate_bundle("daily_brief")))
    _assert_metric_ids_registered(_collect_metric_ids(payload))
    _assert_no_advice_text(payload)

    recent = data["sections"]["recent_workouts"]["items"]
    assert recent
    assert all("kudos_count" in item for item in recent)


def test_weekly_digest_facts_service_returns_load_volume_efficiency_and_trends(tmp_path: Path) -> None:
    from mcp_strava.application.product_facts import get_weekly_digest_facts_service

    db_path = _aggregate_fixture(tmp_path / "weekly-digest.duckdb")
    conn = open_fixture_db(db_path)
    try:
        envelope = get_weekly_digest_facts_service(
            as_of_day="2026-05-21",
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    payload = _payload(envelope)
    data = payload["data"]
    assert data["bundle_id"] == "weekly_digest"
    assert set(data["sections"]) >= {
        "load",
        "volume",
        "efficiency",
        "by_sport",
        "current_week_activities",
        "period_trends",
        "freshness",
        "read_model",
    }
    assert data["sections"]["current_week_activities"]["items"]
    assert data["sections"]["period_trends"]["periods"]["current"]["start"] == "2026-05-18"
    assert data["sections"]["period_trends"]["periods"]["previous"]["start"] == "2026-05-11"
    _assert_all_sections_have_completeness(payload)
    _assert_bundle_completeness(data, requested=set(metrics_for_aggregate_bundle("weekly_digest")))
    _assert_metric_ids_registered(_collect_metric_ids(payload))
    _assert_no_advice_text(payload)


def test_historical_facts_service_returns_calendar_context_and_coverage(tmp_path: Path) -> None:
    from mcp_strava.application.product_facts import get_historical_facts_service

    db_path = _aggregate_fixture(tmp_path / "historical.duckdb")
    conn = open_fixture_db(db_path)
    try:
        envelope = get_historical_facts_service(
            as_of_day="2026-05-21",
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    payload = _payload(envelope)
    data = payload["data"]
    facts = data["sections"]["activity_context"]["facts"]
    assert data["bundle_id"] == "historical_facts"
    assert facts["activity_streak_days"] is not None
    assert facts["rest_streak_days"] is not None
    assert facts["last_hike_days_ago"] is not None
    assert data["sections"]["calendar_context"]["season"] == "spring"
    assert data["sections"]["calendar_context"]["current_week"] == {
        "week_start": "2026-05-18",
        "window_start": "2026-05-18",
        "window_end_exclusive": "2026-05-22",
    }
    assert data["sections"]["coverage"]["read_model"]["status"] == "current"
    _assert_all_sections_have_completeness(payload)
    _assert_bundle_completeness(data, requested=set(metrics_for_aggregate_bundle("historical_facts")))
    _assert_metric_ids_registered(_collect_metric_ids(payload))
    _assert_no_advice_text(payload)


def test_status_facts_are_machine_readable_and_evidence_backed(tmp_path: Path) -> None:
    from mcp_strava.application.product_facts import get_daily_brief_facts_service

    db_path = _phase9_status_fixture(tmp_path / "status-facts.duckdb")
    conn = open_fixture_db(db_path)
    try:
        envelope = get_daily_brief_facts_service(
            as_of_day="2026-05-20",
            now=datetime.fromisoformat("2026-05-20T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    payload = _payload(envelope)
    status_section = payload["data"]["sections"]["status_facts"]
    facts = {fact["code"]: fact for fact in status_section["items"]}
    assert set(STATUS_FACT_REGISTRY).issubset(facts)
    for fact in facts.values():
        assert {"code", "threshold", "window", "evidence", "completeness", "metric_id"} <= set(fact)
        assert fact["metric_id"] in METRIC_REGISTRY
        assert isinstance(fact["threshold"], dict)
        assert isinstance(fact["window"], dict)
        assert isinstance(fact["evidence"], dict)
        assert isinstance(fact["completeness"], dict)

    hike = facts["consecutive_high_load_hikes"]
    assert hike["status"] == "active"
    assert {"dates", "combined_trimp"} <= set(hike["evidence"])
    assert hike["evidence"]["combined_trimp"] > 800

    running = facts["running_volume_jump"]
    assert running["status"] == "active"
    assert {"current_week_km", "previous_week_km", "pct_change"} <= set(running["evidence"])
    assert running["evidence"]["pct_change"] > 10
    _assert_no_advice_text(payload)


def test_supported_gear_facts_use_only_mirrored_detail_fields(tmp_path: Path) -> None:
    from mcp_strava.application.product_facts import get_daily_brief_facts_service

    with_gear = _aggregate_fixture(tmp_path / "with-gear.duckdb")
    _add_mirrored_gear_fixture(with_gear)
    conn = open_fixture_db(with_gear)
    try:
        envelope = get_daily_brief_facts_service(
            as_of_day="2026-05-21",
            now=datetime.fromisoformat("2026-05-21T09:00:00"),
            signal_first_use=False,
            connection=conn,
        )
    finally:
        conn.close()

    payload = _payload(envelope)
    gear_section = payload["data"]["sections"]["supported_gear"]
    assert gear_section["items"] == [
        {
            "activity_id": 101,
            "gear_id": "shoe-1",
            "gear_name": "Road Shoe",
            "gear_distance_km": 123.456,
            "gear_primary": True,
        }
    ]
    _assert_bundle_completeness(gear_section, requested={"gear_id", "gear_name", "gear_distance_km", "gear_primary"})

    without_gear = _aggregate_fixture(tmp_path / "without-gear.duckdb")
    conn = open_fixture_db(without_gear)
    try:
        no_gear = _payload(
            get_daily_brief_facts_service(
                as_of_day="2026-05-21",
                now=datetime.fromisoformat("2026-05-21T09:00:00"),
                signal_first_use=False,
                connection=conn,
            )
        )
    finally:
        conn.close()
    no_gear_section = no_gear["data"]["sections"]["supported_gear"]
    assert no_gear_section["items"] == []
    skipped_reasons = {item["reason_code"] for item in no_gear_section["bundle_completeness"]["skipped_metrics"]}
    assert "gear_data_not_mirrored" in skipped_reasons
