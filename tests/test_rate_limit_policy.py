from __future__ import annotations

from mcp_strava.adapters.strava.rate_limit import (
    RateLimitDecision,
    RateLimitPolicy,
)


class TestParseCsvPair:
    def test_valid_pair(self) -> None:
        assert RateLimitPolicy._parse_csv_pair("5, 100") == (5, 100)

    def test_single_value_returns_none(self) -> None:
        assert RateLimitPolicy._parse_csv_pair("5") is None

    def test_three_values_returns_none(self) -> None:
        assert RateLimitPolicy._parse_csv_pair("5, 10, 15") is None

    def test_none_input_returns_none(self) -> None:
        assert RateLimitPolicy._parse_csv_pair(None) is None

    def test_non_numeric_returns_none(self) -> None:
        assert RateLimitPolicy._parse_csv_pair("abc, def") is None

    def test_empty_string_returns_none(self) -> None:
        assert RateLimitPolicy._parse_csv_pair("") is None


class TestParsePair:
    def test_full_pair(self) -> None:
        # "5, 100" = limit (short=5, long=100); "2, 100" = usage (short=2, long=100)
        # result: ((short_used, short_limit), (long_used, long_limit))
        result = RateLimitPolicy._parse_pair("5, 100", "2, 100")
        assert result is not None
        assert result == ((2, 5), (100, 100))

    def test_none_limit_returns_none(self) -> None:
        assert RateLimitPolicy._parse_pair(None, "2, 100") is None

    def test_none_usage_returns_none(self) -> None:
        assert RateLimitPolicy._parse_pair("5, 100", None) is None

    def test_both_none_returns_none(self) -> None:
        assert RateLimitPolicy._parse_pair(None, None) is None

    def test_invalid_limit_returns_none(self) -> None:
        assert RateLimitPolicy._parse_pair("abc", "2, 100") is None


class TestDecideNextCall:
    def test_no_limits_proceed(self) -> None:
        policy = RateLimitPolicy()
        assert policy.decide_next_call(0.0) == RateLimitDecision.proceed()

    def test_daily_exhausted(self) -> None:
        policy = RateLimitPolicy()
        policy.update_from_headers({"X-RateLimit-Limit": "100, 1000", "X-RateLimit-Usage": "100, 1000"})
        decision = policy.decide_next_call(0.0)
        assert decision.status == "exhausted"
        assert decision.reason == "rate_limited"

    def test_short_exhausted_daily_ok(self) -> None:
        policy = RateLimitPolicy()
        policy.update_from_headers({"X-RateLimit-Limit": "100, 1000", "X-RateLimit-Usage": "100, 50"})
        decision = policy.decide_next_call(1000.0)
        assert decision.status == "wait"
        assert decision.wait_until is not None
        # 15-minute window aligned: floor(1000/900)=1, (1+1)*900=1800
        assert decision.wait_until == 1800.0

    def test_read_exhausted_takes_precedence(self) -> None:
        policy = RateLimitPolicy()
        policy.update_from_headers(
            {
                "X-RateLimit-Limit": "100, 1000",
                "X-RateLimit-Usage": "0, 0",
                "X-ReadRateLimit-Limit": "100, 1000",
                "X-ReadRateLimit-Usage": "100, 1000",
            }
        )
        decision = policy.decide_next_call(0.0)
        assert decision.status == "exhausted"

    def test_read_short_exhausted(self) -> None:
        policy = RateLimitPolicy()
        policy.update_from_headers(
            {
                "X-RateLimit-Limit": "100, 1000",
                "X-RateLimit-Usage": "0, 0",
                "X-ReadRateLimit-Limit": "100, 1000",
                "X-ReadRateLimit-Usage": "100, 0",
            }
        )
        decision = policy.decide_next_call(900.0)
        assert decision.status == "wait"


class TestMarkRateLimited:
    def test_sets_short_used_to_limit(self) -> None:
        policy = RateLimitPolicy()
        policy.update_from_headers(
            {
                "X-RateLimit-Limit": "50, 1000",
                "X-RateLimit-Usage": "10, 100",
                "X-ReadRateLimit-Limit": "100, 1000",
                "X-ReadRateLimit-Usage": "5, 200",
            }
        )
        policy.mark_rate_limited()
        info = policy.rate_info
        assert info.overall_short == (50, 50)
        assert info.read_short == (100, 100)

    def test_leaves_none_limits_unchanged(self) -> None:
        policy = RateLimitPolicy()
        # No headers set, so all windows are (None, None)
        policy.mark_rate_limited()
        info = policy.rate_info
        assert info.overall_short == (None, None)
        assert info.overall_long == (None, None)


class TestUpdateFromHeaders:
    def test_preserves_previous_when_headers_missing(self) -> None:
        policy = RateLimitPolicy()
        policy.update_from_headers({"X-RateLimit-Limit": "50, 1000", "X-RateLimit-Usage": "10, 100"})
        info_before = policy.rate_info
        assert info_before.overall_short == (10, 50)
        assert info_before.overall_long == (100, 1000)

        # Update with different overall-only headers; read must NOT reset
        policy.update_from_headers({"X-RateLimit-Limit": "60, 2000", "X-RateLimit-Usage": "5, 200"})
        info_after = policy.rate_info
        assert info_after.overall_short == (5, 60)
        assert info_after.overall_long == (200, 2000)
        # Read windows carry forward from prior update
        assert info_after.read_short == (None, None)
        assert info_after.read_long == (None, None)


class TestNextShortReset:
    def test_mid_window(self) -> None:
        # 100 seconds into a 15-min window
        result = RateLimitPolicy._next_short_reset(100.0)
        assert result == 900.0

    def test_window_boundary(self) -> None:
        # At exactly window boundary
        result = RateLimitPolicy._next_short_reset(900.0)
        assert result == 1800.0

    def test_late_in_window(self) -> None:
        result = RateLimitPolicy._next_short_reset(899.0)
        assert result == 900.0
