"""Focused unit tests for the deterministic Strava rate-limit policy."""

from __future__ import annotations

from mcp_strava.adapters.strava.rate_limit import RateLimitPolicy


def test_update_from_headers_preserves_last_valid_rate_info_for_malformed_headers() -> None:
    policy = RateLimitPolicy()

    rate_info = policy.update_from_headers(
        {
            "X-RateLimit-Limit": "100,1000",
            "X-RateLimit-Usage": "5,50",
            "X-ReadRateLimit-Limit": "50,500",
            "X-ReadRateLimit-Usage": "3,30",
        }
    )
    updated = policy.update_from_headers(
        {
            "X-RateLimit-Limit": "not-a-pair",
            "X-RateLimit-Usage": "7,70",
            "X-ReadRateLimit-Limit": "50,500",
            "X-ReadRateLimit-Usage": "invalid",
        }
    )

    assert rate_info.overall_short == (5, 100)
    assert rate_info.overall_long == (50, 1000)
    assert rate_info.read_short == (3, 50)
    assert rate_info.read_long == (30, 500)
    assert updated == rate_info


def test_decide_next_call_exhausts_daily_quota_before_short_window_wait() -> None:
    policy = RateLimitPolicy()
    policy.update_from_headers(
        {
            "X-RateLimit-Limit": "100,1000",
            "X-RateLimit-Usage": "100,1000",
        }
    )

    decision = policy.decide_next_call(now=1_800)

    assert decision.status == "exhausted"
    assert decision.reason == "rate_limited"
    assert decision.wait_until is None


def test_decide_next_call_waits_until_next_short_window_boundary() -> None:
    policy = RateLimitPolicy()
    policy.update_from_headers(
        {
            "X-RateLimit-Limit": "100,1000",
            "X-RateLimit-Usage": "100,999",
        }
    )

    decision = policy.decide_next_call(now=1_800)

    assert decision.status == "wait"
    assert decision.wait_until == 2_700
    assert decision.reason is None
