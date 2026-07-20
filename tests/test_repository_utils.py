from __future__ import annotations

from datetime import date

import pytest

from mcp_strava.adapters.duckdb.repository_utils import (
    as_float,
    as_int,
    normalize_cell,
    placeholders,
    safe_identifier,
)


class TestSafeIdentifier:
    def test_simple_name(self) -> None:
        assert safe_identifier("activities") == "activities"

    def test_snake_case(self) -> None:
        assert safe_identifier("activity_id") == "activity_id"

    def test_allowed_patterns(self) -> None:
        assert safe_identifier("Table_Name_01") == "Table_Name_01"

    def test_spaces_raise(self) -> None:
        with pytest.raises(ValueError, match="unsafe SQL identifier"):
            safe_identifier("drop table")

    def test_semicolons_raise(self) -> None:
        with pytest.raises(ValueError, match="unsafe SQL identifier"):
            safe_identifier("x; DROP TABLE users;--")

    def test_dashes_raise(self) -> None:
        with pytest.raises(ValueError, match="unsafe SQL identifier"):
            safe_identifier("my-table")

    def test_dots_raise(self) -> None:
        with pytest.raises(ValueError, match="unsafe SQL identifier"):
            safe_identifier("schema.table")


class TestNormalizeCell:
    def test_date_to_isoformat(self) -> None:
        d = date(2026, 5, 21)
        assert normalize_cell(d) == "2026-05-21"

    def test_int_passthrough(self) -> None:
        assert normalize_cell(42) == 42

    def test_str_passthrough(self) -> None:
        assert normalize_cell("hello") == "hello"

    def test_float_passthrough(self) -> None:
        assert normalize_cell(3.14) == 3.14

    def test_none_passthrough(self) -> None:
        assert normalize_cell(None) is None


class TestAsInt:
    def test_int(self) -> None:
        assert as_int(42) == 42

    def test_bool_converts(self) -> None:
        assert as_int(True) == 1
        assert as_int(False) == 0

    def test_float_converts(self) -> None:
        assert as_int(3.9) == 3

    def test_str_converts(self) -> None:
        assert as_int("42") == 42

    def test_none_returns_default(self) -> None:
        assert as_int(None) == 0
        assert as_int(None, default=-1) == -1

    def test_dict_raises(self) -> None:
        with pytest.raises(TypeError, match="expected an int-like cell"):
            as_int({})

    def test_list_raises(self) -> None:
        with pytest.raises(TypeError, match="expected an int-like cell"):
            as_int([1, 2, 3])


class TestAsFloat:
    def test_float(self) -> None:
        assert as_float(3.14) == pytest.approx(3.14)

    def test_int_converts(self) -> None:
        assert as_float(42) == pytest.approx(42.0)

    def test_str_converts(self) -> None:
        assert as_float("3.14") == pytest.approx(3.14)

    def test_none_returns_default(self) -> None:
        assert as_float(None) == pytest.approx(0.0)
        assert as_float(None, default=1.5) == pytest.approx(1.5)

    def test_dict_raises(self) -> None:
        with pytest.raises(TypeError, match="expected a float-like cell"):
            as_float({})


class TestPlaceholders:
    def test_zero(self) -> None:
        assert placeholders(0) == ""

    def test_one(self) -> None:
        assert placeholders(1) == "?"

    def test_three(self) -> None:
        assert placeholders(3) == "?, ?, ?"

    def test_five(self) -> None:
        assert placeholders(5) == "?, ?, ?, ?, ?"
