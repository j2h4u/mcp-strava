from datetime import date

from mcp_strava.adapters.duckdb.source_hashing import semantic_json_hash, summary_payload_changed


def test_summary_payload_changed_ignores_non_semantic_timestamps() -> None:
    stored = '{"id": 1, "name": "Morning Run", "synced_at": "2026-05-01T01:00:00"}'
    incoming = '{"name": "Morning Run", "id": 1, "synced_at": "2026-05-01T02:00:00"}'

    assert not summary_payload_changed(stored, incoming)


def test_summary_payload_changed_ignores_strava_id_string_duplicate() -> None:
    stored = '{"id": 19101786945, "name": "Morning Run"}'
    incoming = '{"id": 19101786945, "id_str": "19101786945", "name": "Morning Run"}'

    assert not summary_payload_changed(stored, incoming)


def test_summary_payload_changed_detects_semantic_delta() -> None:
    stored = '{"id": 1, "name": "Morning Run"}'
    incoming = '{"id": 1, "name": "Evening Run"}'

    assert summary_payload_changed(stored, incoming)


def test_summary_payload_changed_ignores_nested_non_semantic_values() -> None:
    stored = '{"id": 1, "laps": [{"distance": 400, "updated_at": "2026-05-01T01:00:00"}]}'
    incoming = '{"laps": [{"updated_at": "2026-05-01T02:00:00", "distance": 400}], "id": 1}'

    assert not summary_payload_changed(stored, incoming)


def test_semantic_json_hash_normalizes_dates_and_json_strings() -> None:
    value = {"activity_day": date(2026, 5, 1), "id": 1}
    json_value = '{"id": 1, "activity_day": "2026-05-01"}'

    assert semantic_json_hash(value) == semantic_json_hash(json_value)
