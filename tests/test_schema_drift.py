"""The Strava schema-drift journal: detect + log new/Summit fields, no DB writes."""

import json

from mcp_strava.refresh.schema_drift import journal_schema_drift


def _events(capsys):
    out = capsys.readouterr().out.strip()
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def test_journal_emits_on_unknown_field(capsys):
    # average_temp is a real Strava field we do not model -> unknown.
    data = {"id": 1, "name": "Run", "sport_type": "Run", "average_temp": 17.0}
    journal_schema_drift(data, "detailed_activity")
    events = _events(capsys)
    assert len(events) == 1
    ev = events[0]
    assert ev["event"] == "strava_schema_drift"
    assert [f["field"] for f in ev["unknown_fields"]] == ["average_temp"]
    assert ev["unknown_fields"][0]["value_type"] == "float"


def test_journal_silent_on_fully_known_response(capsys):
    data = {"id": 1, "name": "Run", "sport_type": "Run", "distance": 5000.0}
    journal_schema_drift(data, "detailed_activity")
    assert _events(capsys) == []


def test_journal_flags_active_summit_field(capsys):
    # suffer_score is Summit-only (null-value 0); a non-zero value means active.
    data = {"id": 1, "name": "Run", "sport_type": "Run", "suffer_score": 42}
    journal_schema_drift(data, "summary_activity")
    events = _events(capsys)
    assert len(events) == 1
    assert [f["field"] for f in events[0]["active_summit"]] == ["suffer_score"]


def test_journal_batch_dedups_unknown_fields_across_items(capsys):
    page = [
        {"id": 1, "sport_type": "Run", "new_metric": 1},
        {"id": 2, "sport_type": "Run", "new_metric": 2},
    ]
    journal_schema_drift(page, "summary_activity", is_batch=True)
    events = _events(capsys)
    assert len(events) == 1
    fields = [f["field"] for f in events[0]["unknown_fields"]]
    assert fields.count("new_metric") == 1  # deduped across the sampled items


def test_journal_ignores_non_dict_inputs_without_crashing(capsys):
    journal_schema_drift(None, "detailed_activity")
    journal_schema_drift("garbage", "streams")
    journal_schema_drift([], "summary_activity")  # list but not batch -> not a dict -> ignored
    assert _events(capsys) == []


def test_journal_supports_athlete_zones_endpoint(capsys):
    data = {"heart_rate": {"custom_zones": False, "zones": [{"min": 0, "max": 120}]}, "surprise": True}
    journal_schema_drift(data, "athlete_zones")
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]["endpoint"] == "GET /athlete/zones"
    assert [f["field"] for f in events[0]["unknown_fields"]] == ["surprise"]
