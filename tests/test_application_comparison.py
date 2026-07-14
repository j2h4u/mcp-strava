"""Unit tests for comparison service helpers."""

from mcp_strava.application.comparison_services import _is_number


class TestIsNumber:
    def test_int_returns_true(self) -> None:
        assert _is_number(0) is True
        assert _is_number(42) is True
        assert _is_number(-1) is True

    def test_float_returns_true(self) -> None:
        assert _is_number(0.0) is True
        assert _is_number(3.14) is True
        assert _is_number(-2.5) is True

    def test_boolean_true_is_not_number(self) -> None:
        assert _is_number(True) is False

    def test_boolean_false_is_not_number(self) -> None:
        assert _is_number(False) is False

    def test_none_is_not_number(self) -> None:
        assert _is_number(None) is False

    def test_string_is_not_number(self) -> None:
        assert _is_number("42") is False

    def test_list_is_not_number(self) -> None:
        assert _is_number([1, 2, 3]) is False

    def test_complex_is_not_number(self) -> None:
        assert _is_number(1 + 2j) is False
