"""Unit-тесты для пограничных случаев модели Бэнистера и EWMA."""

from mcp_strava.training import calc_banister, calc_banister_series, ewma


def test_ewma_end_before_start_returns_empty() -> None:
    """ewma возвращает {} когда end_date предшествует первой дате в серии."""
    result = ewma({"2026-06-01": 100}, tau=7, end_date="2026-05-01")
    assert result == {}


def test_calc_banister_empty_input_returns_none() -> None:
    """calc_banister возвращает None при пустом словаре daily_trimp."""
    assert calc_banister({}) is None


def test_calc_banister_series_empty_input_returns_empty_list() -> None:
    """calc_banister_series возвращает [] при пустом словаре daily_trimp."""
    assert calc_banister_series({}) == []
