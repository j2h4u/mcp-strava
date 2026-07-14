"""Unit tests for projection service helpers."""

from mcp_strava.application.projection_services import _next_day


class TestNextDay:
    def test_normal_day_increment(self) -> None:
        assert _next_day("2026-01-15") == "2026-01-16"

    def test_month_boundary(self) -> None:
        assert _next_day("2026-01-31") == "2026-02-01"

    def test_year_boundary(self) -> None:
        assert _next_day("2025-12-31") == "2026-01-01"

    def test_leap_day_2024(self) -> None:
        assert _next_day("2024-02-28") == "2024-02-29"

    def test_leap_day_feb_29(self) -> None:
        assert _next_day("2024-02-29") == "2024-03-01"

    def test_non_leap_year_feb(self) -> None:
        assert _next_day("2025-02-28") == "2025-03-01"
