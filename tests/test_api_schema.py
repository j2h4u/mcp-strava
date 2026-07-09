from __future__ import annotations

import pytest

from mcp_strava.api_schema import (
    SCHEMA_REGISTRY,
    SUMMARY_ACTIVITY,
    DETAILED_ACTIVITY,
    STREAMS,
    ATHLETE_ZONES,
    EndpointSchema,
    FieldSchema,
    Status,
    ValidationResult,
    validate_batch,
    validate_response,
)


# ── FieldSchema.is_summit_active ──────────────────────────────────────────────


def test_is_summit_active_false_for_non_summit_status() -> None:
    field = FieldSchema("test", "int", Status.FREE_USED)
    assert field.is_summit_active(42) is False
    assert field.is_summit_active(None) is False


def test_is_summit_active_false_for_not_applicable() -> None:
    field = FieldSchema("test", "str", Status.NOT_APPLICABLE)
    assert field.is_summit_active("hello") is False


def test_is_summit_active_null_value_none() -> None:
    field = FieldSchema("test", "int?", Status.SUMMIT, summit_null_value=None)
    assert field.is_summit_active(10) is True
    assert field.is_summit_active(0) is True
    assert field.is_summit_active(None) is False


def test_is_summit_active_null_value_zero_int() -> None:
    field = FieldSchema("test", "int?", Status.SUMMIT, summit_null_value=0)
    assert field.is_summit_active(10) is True
    assert field.is_summit_active(0) is False
    assert field.is_summit_active(None) is False


def test_is_summit_active_null_value_zero_float() -> None:
    field = FieldSchema("test", "float?", Status.SUMMIT, summit_null_value=0.0)
    assert field.is_summit_active(1.5) is True
    assert field.is_summit_active(0.0) is False
    assert field.is_summit_active(None) is False


def test_is_summit_active_null_value_false_bool() -> None:
    field = FieldSchema("test", "bool", Status.SUMMIT, summit_null_value=False)
    assert field.is_summit_active(True) is True
    assert field.is_summit_active(False) is False
    assert field.is_summit_active(None) is False


def test_is_summit_active_null_value_empty_list() -> None:
    field = FieldSchema("test", "list", Status.SUMMIT, summit_null_value=[])
    assert field.is_summit_active([1, 2]) is True
    assert field.is_summit_active([]) is False
    assert field.is_summit_active(None) is False


def test_is_summit_active_null_value_empty_dict() -> None:
    field = FieldSchema("test", "dict", Status.SUMMIT, summit_null_value={})
    assert field.is_summit_active({"key": "val"}) is True
    assert field.is_summit_active({}) is False
    assert field.is_summit_active(None) is False


# ── EndpointSchema.unknown_keys ───────────────────────────────────────────────


def test_unknown_keys_detects_missing_fields() -> None:
    schema = EndpointSchema(
        name="test",
        endpoint="GET /test",
        fields={"id": FieldSchema("id", "int", Status.FREE_USED)},
    )
    data = {"id": 1, "extra_field": "unexpected", "another": None}
    result = schema.unknown_keys(data)
    assert len(result) == 2
    keys = {r["field"] for r in result}
    assert keys == {"extra_field", "another"}


def test_unknown_keys_empty_for_all_known() -> None:
    schema = EndpointSchema(
        name="test",
        endpoint="GET /test",
        fields={
            "id": FieldSchema("id", "int", Status.FREE_USED),
            "name": FieldSchema("name", "str", Status.FREE_USED),
        },
    )
    assert schema.unknown_keys({"id": 1, "name": "test"}) == []


def test_unknown_keys_empty_for_empty_data() -> None:
    schema = EndpointSchema(name="test", endpoint="GET /test", fields={"id": FieldSchema("id", "int", Status.FREE_USED)})
    assert schema.unknown_keys({}) == []


# ── EndpointSchema.active_summit_fields ───────────────────────────────────────


def test_active_summit_detects_suddenly_nonnull() -> None:
    schema = EndpointSchema(
        name="test",
        endpoint="GET /test",
        fields={
            "suffer_score": FieldSchema("suffer_score", "int?", Status.SUMMIT, summit_null_value=0),
            "perceived_exertion": FieldSchema("perceived_exertion", "int?", Status.SUMMIT, summit_null_value=None),
            "name": FieldSchema("name", "str", Status.FREE_USED),
        },
    )
    data = {"suffer_score": 42, "perceived_exertion": None, "name": "run"}
    result = schema.active_summit_fields(data)
    assert len(result) == 1
    assert result[0]["field"] == "suffer_score"


def test_active_summit_empty_when_all_summit_fields_are_default() -> None:
    schema = EndpointSchema(
        name="test",
        endpoint="GET /test",
        fields={
            "suffer_score": FieldSchema("suffer_score", "int?", Status.SUMMIT, summit_null_value=0),
            "perceived_exertion": FieldSchema("perceived_exertion", "int?", Status.SUMMIT, summit_null_value=None),
        },
    )
    data = {"suffer_score": 0, "perceived_exertion": None}
    assert schema.active_summit_fields(data) == []


# ── ValidationResult ──────────────────────────────────────────────────────────


def test_validation_result_clean_when_no_findings() -> None:
    result = ValidationResult(endpoint="GET /test")
    assert result.is_clean is True
    assert result.has_findings is False


def test_validation_result_has_findings_with_unknown_fields() -> None:
    result = ValidationResult(
        endpoint="GET /test",
        unknown_fields=[{"field": "extra", "value_type": "str", "is_null": False}],
    )
    assert result.is_clean is False
    assert result.has_findings is True


def test_validation_result_has_findings_with_active_summit() -> None:
    result = ValidationResult(
        endpoint="GET /test",
        active_summit=[{"field": "suffer_score", "value": "42", "expected_null": "0"}],
    )
    assert result.is_clean is False
    assert result.has_findings is True


# ── Schema registry integrity ─────────────────────────────────────────────────


def test_schema_registry_has_all_four_endpoints() -> None:
    assert set(SCHEMA_REGISTRY.keys()) == {"summary_activity", "detailed_activity", "streams", "athlete_zones"}


def test_detailed_activity_inherits_summary_fields() -> None:
    summary_keys = set(SUMMARY_ACTIVITY.fields.keys())
    detailed_keys = set(DETAILED_ACTIVITY.fields.keys())
    extra = detailed_keys - summary_keys
    assert len(extra) > 0, "DetailedActivity should have extra fields beyond SummaryActivity"
    # All summary fields must be present in detailed
    for key in summary_keys:
        assert key in detailed_keys, f"Missing SummaryActivity field '{key}' in DetailedActivity"


def test_schema_fields_have_valid_status() -> None:
    valid_statuses = {Status.FREE_USED, Status.FREE_UNUSED, Status.SUMMIT, Status.NOT_APPLICABLE}
    for schema_name, schema in SCHEMA_REGISTRY.items():
        for field_name, field_schema in schema.fields.items():
            assert field_schema.status in valid_statuses, (
                f"{schema_name}.{field_name}: invalid status {field_schema.status!r}"
            )


# ── validate_response ─────────────────────────────────────────────────────────


def test_validate_response_unknown_endpoint() -> None:
    result = validate_response({"id": 1}, "nonexistent_endpoint")
    assert result.endpoint.startswith("unknown:")
    assert result.has_findings is True


def test_validate_response_known_endpoint_with_unknown_key() -> None:
    result = validate_response({"id": 1, "brand_new_field": "surprise"}, "summary_activity")
    assert result.endpoint == "GET /athlete/activities"
    assert len(result.unknown_fields) == 1
    assert result.unknown_fields[0]["field"] == "brand_new_field"


def test_validate_response_clean_for_valid_data() -> None:
    result = validate_response({"id": 1, "name": "Morning Run", "sport_type": "Run"}, "summary_activity")
    assert result.is_clean is True


# ── validate_batch ────────────────────────────────────────────────────────────


def test_validate_batch_unknown_endpoint() -> None:
    result = validate_batch([], "nonexistent")
    assert result.endpoint.startswith("unknown:")


def test_validate_batch_detects_unknown_keys_across_items() -> None:
    items = [
        {"id": 1, "extra_a": "a"},
        {"id": 2, "extra_b": "b"},
    ]
    result = validate_batch(items, "summary_activity", max_samples=2)
    assert len(result.unknown_fields) == 2


def test_validate_batch_skips_non_dict_items() -> None:
    items = [
        {"id": 1, "extra_a": "a"},
        None,  # type: ignore[list-item]
        "not_a_dict",  # type: ignore[list-item]
    ]
    result = validate_batch(items, "summary_activity", max_samples=5)
    assert len(result.unknown_fields) == 1  # Only from the first valid item


def test_validate_batch_respects_max_samples() -> None:
    items = [{"id": i, f"extra_{i}": i} for i in range(10)]
    result = validate_batch(items, "summary_activity", max_samples=3)
    assert len(result.unknown_fields) == 3


def test_validate_batch_detects_active_summit() -> None:
    items = [
        {"id": 1, "suffer_score": 100},
        {"id": 2, "suffer_score": 200},
    ]
    result = validate_batch(items, "summary_activity", max_samples=5)
    assert len(result.active_summit) == 1
    assert result.active_summit[0]["field"] == "suffer_score"


# ── Specific known fields ─────────────────────────────────────────────────────


def test_summary_activity_has_core_fields() -> None:
    essential = {"id", "name", "sport_type", "distance", "moving_time", "elapsed_time", "total_elevation_gain"}
    for field_name in essential:
        assert field_name in SUMMARY_ACTIVITY.fields, f"Missing essential field: {field_name}"


def test_streams_has_consumed_fields() -> None:
    consumed = {"time", "heartrate", "velocity_smooth", "altitude", "cadence", "latlng", "grade_smooth", "distance", "moving"}
    for field_name in consumed:
        assert field_name in STREAMS.fields, f"Missing consumed stream field: {field_name}"


def test_athlete_zones_has_heart_rate() -> None:
    assert "heart_rate" in ATHLETE_ZONES.fields
    assert ATHLETE_ZONES.fields["heart_rate"].status == Status.FREE_UNUSED
