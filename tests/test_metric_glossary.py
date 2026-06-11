"""Contract tests for the metric glossary and its hard link to the registry."""

import asyncio

import pytest

from mcp_strava.interfaces import mcp_http
from mcp_strava.metric_glossary import (
    CONCEPT_BY_METRIC_ID,
    CONCEPT_GLOSSARY,
    Concept,
    _build_concept_by_metric_id,
    render_glossary_markdown,
    validate_concept_links,
)
from mcp_strava.metric_registry import METRIC_REGISTRY, metric_catalog_payload

# Regression guard: these jargon metrics must keep resolving to their concept.
_EXPECTED_CONCEPT = {
    "trimp": "trimp",
    "weekly_trimp": "trimp",
    "fitness": "ctl",
    "projected_fitness": "ctl",
    "fatigue": "atl",
    "form": "tsb",
    "form_zone": "tsb",
    "acwr": "acwr",
    "cardiac_cost": "cardiac_cost",
    "cardiac_drift_pct": "cardiac_drift",
    "hrr_pct": "hrr",
    "hr_recovery_median_bpm_per_min": "hr_recovery",
    "time_in_hr_zones_min": "hr_zones",
    "volume_7d": "volume",
}


def test_glossary_links_resolve_to_real_metrics() -> None:
    # validate_concept_links is the import-time guard; assert it is satisfied by the live registry.
    validate_concept_links(frozenset(METRIC_REGISTRY))
    for metric_id in CONCEPT_BY_METRIC_ID:
        assert metric_id in METRIC_REGISTRY, metric_id


def test_every_concept_covers_at_least_one_metric() -> None:
    for key, concept in CONCEPT_GLOSSARY.items():
        assert concept.metric_ids, key
        assert concept.key == key


def test_concept_fk_is_stamped_on_every_metric_definition() -> None:
    for metric_id, definition in METRIC_REGISTRY.items():
        assert definition.concept == CONCEPT_BY_METRIC_ID.get(metric_id, ""), metric_id


def test_known_jargon_maps_to_expected_concept() -> None:
    for metric_id, expected in _EXPECTED_CONCEPT.items():
        assert METRIC_REGISTRY[metric_id].concept == expected, metric_id


def test_validate_concept_links_rejects_unknown_metric_id() -> None:
    # Drop a metric the glossary references; the guard must fail fast.
    known = frozenset(METRIC_REGISTRY) - {"trimp"}
    with pytest.raises(ValueError, match="absent from the registry"):
        validate_concept_links(known)


def test_inversion_rejects_a_metric_in_two_concepts() -> None:
    clashing = {
        "a": Concept(key="a", term="A", expansion="A", definition="d", metric_ids=("shared",)),
        "b": Concept(key="b", term="B", expansion="B", definition="d", metric_ids=("shared",)),
    }
    with pytest.raises(ValueError, match="bound to two concepts"):
        _build_concept_by_metric_id(clashing)


def test_glossary_markdown_expands_the_abbreviations() -> None:
    body = render_glossary_markdown()
    for expansion in (
        "Training Impulse",
        "Chronic Training Load",
        "Acute Training Load",
        "Training Stress Balance",
        "Acute:Chronic Workload Ratio",
        "Heart Rate Reserve",
    ):
        assert expansion in body, expansion


def test_catalog_payload_carries_the_concept_link() -> None:
    payload = metric_catalog_payload()
    for metric in payload["metrics"]:
        assert metric["concept"] == METRIC_REGISTRY[metric["metric_id"]].concept


def test_mcp_resources_are_registered_and_readable() -> None:
    server = mcp_http.build_mcp_server()
    resources = asyncio.run(server.list_resources())
    by_uri = {str(resource.uri): resource for resource in resources}
    assert {"strava://glossary", "strava://metric-catalog"} <= set(by_uri)
    assert by_uri["strava://glossary"].mimeType == "text/markdown"
    assert by_uri["strava://metric-catalog"].mimeType == "application/json"

    glossary = next(iter(asyncio.run(server.read_resource("strava://glossary")))).content
    assert "Training Impulse" in glossary
    catalog = next(iter(asyncio.run(server.read_resource("strava://metric-catalog")))).content
    assert '"concept"' in catalog


def test_instructions_point_at_both_resources() -> None:
    assert "strava://glossary" in mcp_http.MCP_INSTRUCTIONS
    assert "strava://metric-catalog" in mcp_http.MCP_INSTRUCTIONS


def test_glossary_documents_times_and_timezones() -> None:
    body = render_glossary_markdown()
    assert "## Times & timezones" in body
    # the three distinct references must be spelled out
    assert "LOCAL to where the activity happened" in body
    assert "Operational timestamps are UTC" in body
    assert "last_activity_at` is a LOCAL calendar date" in body
    assert "user's / calling agent's own timezone is deliberately **not** applied" in body
