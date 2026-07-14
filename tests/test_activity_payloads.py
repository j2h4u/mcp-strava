"""Unit tests for activity payload assembly helpers."""

from datetime import datetime

from mcp_strava.application.activity_payloads import kudos_count, parse_start_dt


class TestParseStartDt:
    def test_parses_iso_with_z_suffix(self) -> None:
        result = parse_start_dt("2026-01-15T08:30:00Z")
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 8
        assert result.minute == 30

    def test_parses_iso_without_timezone(self) -> None:
        result = parse_start_dt("2026-06-01T14:45:00")
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.month == 6
        assert result.day == 1

    def test_parses_iso_with_positive_offset(self) -> None:
        result = parse_start_dt("2026-12-25T10:00:00+03:00")
        assert isinstance(result, datetime)
        assert result.hour == 10
        assert result.tzinfo is not None

    def test_returns_none_for_none(self) -> None:
        assert parse_start_dt(None) is None

    def test_returns_none_for_empty_string(self) -> None:
        assert parse_start_dt("") is None

    def test_returns_none_for_whitespace_string(self) -> None:
        assert parse_start_dt("   ") is None

    def test_returns_none_for_invalid_iso(self) -> None:
        assert parse_start_dt("not-a-date") is None
        assert parse_start_dt("2026-13-01T00:00:00Z") is None
        assert parse_start_dt("Monday") is None


class TestKudosCount:
    def test_extracts_valid_int(self) -> None:
        assert kudos_count({"kudos_count": 5}) == 5

    def test_returns_zero_for_missing_key(self) -> None:
        assert kudos_count({}) == 0

    def test_returns_zero_for_none_value(self) -> None:
        assert kudos_count({"kudos_count": None}) == 0

    def test_truncates_float_to_int(self) -> None:
        assert kudos_count({"kudos_count": 3.7}) == 3

    def test_returns_zero_for_uncastable_string(self) -> None:
        assert kudos_count({"kudos_count": "many"}) == 0

    def test_extracts_from_boolean_true(self) -> None:
        assert kudos_count({"kudos_count": True}) == 1

    def test_extracts_from_boolean_false(self) -> None:
        assert kudos_count({"kudos_count": False}) == 0

    def test_extracts_from_numeric_string(self) -> None:
        assert kudos_count({"kudos_count": "12"}) == 12
