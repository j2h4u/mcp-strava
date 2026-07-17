from __future__ import annotations

from datetime import datetime

import pytest

from mcp_strava.refresh.freshness import _parse_dt
from mcp_strava.refresh.policy import refresh_interval_elapsed


# ═══════════════════════════════════════════════════════════════
# _parse_dt — datetime parsing from the freshness pipeline
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("2026-05-21T12:00:00", datetime(2026, 5, 21, 12, 0, 0)),
        ("2026-05-21T12:00:00+00:00", datetime(2026, 5, 21, 12, 0, 0)),
        ("2026-05-21T12:00:00+05:00", datetime(2026, 5, 21, 12, 0, 0)),
        ("2026-05-21T12:00:00Z", datetime(2026, 5, 21, 12, 0, 0)),
        ("2026-05-21", datetime(2026, 5, 21, 0, 0, 0)),
        ("not-a-date", None),
    ],
)
def test_parse_dt_handles_edge_cases_and_strips_tzinfo(value: str | None, expected: datetime | None) -> None:
    result = _parse_dt(value)
    assert result == expected
    if result is not None:
        assert result.tzinfo is None


def test_parse_dt_returns_none_on_empty_like_values() -> None:
    assert _parse_dt(None) is None
    assert _parse_dt("") is None


# ═══════════════════════════════════════════════════════════════
# refresh_interval_elapsed — refresh scheduling gate
# ═══════════════════════════════════════════════════════════════


def test_refresh_interval_elapsed_returns_true_when_never_refreshed() -> None:
    assert refresh_interval_elapsed(None, "2026-05-21T12:00:00", 3600) is True


def test_refresh_interval_elapsed_returns_true_with_zero_interval() -> None:
    assert refresh_interval_elapsed("2026-05-21T12:00:00", "2026-05-21T12:00:00", 0) is True


def test_refresh_interval_elapsed_returns_true_with_negative_interval() -> None:
    assert refresh_interval_elapsed("2026-05-21T12:00:00", "2026-05-21T12:00:00", -1) is True


def test_refresh_interval_elapsed_returns_true_when_exactly_at_boundary() -> None:
    assert refresh_interval_elapsed("2026-05-21T12:00:00", "2026-05-21T13:00:00", 3600) is True


def test_refresh_interval_elapsed_returns_false_when_not_yet_elapsed() -> None:
    assert refresh_interval_elapsed("2026-05-21T12:00:00", "2026-05-21T12:59:59", 3600) is False


def test_refresh_interval_elapsed_returns_true_on_invalid_date_as_fail_safe() -> None:
    assert refresh_interval_elapsed("garbage", "2026-05-21T12:00:00", 3600) is True


def test_refresh_interval_elapsed_returns_true_when_sufficiently_elapsed() -> None:
    assert refresh_interval_elapsed("2026-05-21T12:00:00", "2026-05-21T14:00:00", 3600) is True
