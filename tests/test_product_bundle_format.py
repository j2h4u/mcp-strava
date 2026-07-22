"""Unit tests for product_bundle_format pure helper functions."""

from datetime import date

from mcp_strava.application.product_bundle_format import filter_rows, overall_status, season, section_status


def test_filter_rows_keeps_only_matching_metric_ids():
    rows = [
        {"metric_id": "trimp", "value": 100},
        {"metric_id": "fitness", "value": 45.5},
        {"metric_id": "form_zone", "value": "normal"},
        {"metric_id": "weekly_trimp", "value": 350},
    ]
    result = filter_rows(rows, {"trimp", "form_zone"})
    assert len(result) == 2
    result_ids = [row["metric_id"] for row in result]
    assert "trimp" in result_ids
    assert "form_zone" in result_ids
    assert "fitness" not in result_ids
    assert "weekly_trimp" not in result_ids


def test_filter_rows_returns_empty_for_no_match():
    rows = [{"metric_id": "trimp", "value": 100}]
    assert filter_rows(rows, {"fitness"}) == []


def test_filter_rows_returns_empty_for_empty_input():
    assert filter_rows([], {"trimp"}) == []


def test_season_returns_correct_season_for_each_month():
    assert season(date(2026, 1, 15)) == "winter"
    assert season(date(2026, 2, 1)) == "winter"
    assert season(date(2026, 12, 31)) == "winter"

    assert season(date(2026, 3, 1)) == "spring"
    assert season(date(2026, 4, 15)) == "spring"
    assert season(date(2026, 5, 31)) == "spring"

    assert season(date(2026, 6, 1)) == "summer"
    assert season(date(2026, 7, 15)) == "summer"
    assert season(date(2026, 8, 31)) == "summer"

    assert season(date(2026, 9, 1)) == "autumn"
    assert season(date(2026, 10, 15)) == "autumn"
    assert season(date(2026, 11, 30)) == "autumn"


def test_section_status_classifies_completeness():
    complete = section_status(
        {
            "bundle_completeness": {
                "requested_metrics": ["trimp", "fitness", "form_zone"],
                "included_metrics": ["trimp", "fitness", "form_zone"],
            }
        }
    )
    assert complete == "complete"

    partial = section_status(
        {
            "bundle_completeness": {
                "requested_metrics": ["trimp", "fitness", "form_zone"],
                "included_metrics": ["trimp"],
            }
        }
    )
    assert partial == "partial"

    none_included = section_status(
        {
            "bundle_completeness": {
                "requested_metrics": ["trimp", "fitness"],
                "included_metrics": [],
            }
        }
    )
    assert none_included == "unavailable"

    no_requested = section_status(
        {
            "bundle_completeness": {
                "requested_metrics": [],
                "included_metrics": ["trimp"],
            }
        }
    )
    assert no_requested == "unavailable"

    missing_completeness = section_status({"other_key": "value"})
    assert missing_completeness == "unavailable"


def test_overall_status_classifies_envelope_status():
    assert overall_status(["complete", "complete"], {"status": "available"}) == "complete"
    assert overall_status(["complete", "partial"], {"status": "available"}) == "partial"
    assert overall_status(["unavailable", "unavailable"], {"status": "available"}) == "unavailable"
    assert overall_status(["complete", "complete"], {"status": "stale"}) == "stale"
