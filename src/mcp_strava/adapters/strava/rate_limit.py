"""Strava rate-limit policy across overall and read quota windows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from mcp_strava.adapters.strava.types import StravaRateInfo


@dataclass(frozen=True)
class RateLimitDecision:
    status: str
    wait_until: float | None = None
    reason: str | None = None

    @classmethod
    def proceed(cls) -> "RateLimitDecision":
        return cls(status="proceed")

    @classmethod
    def wait(cls, timestamp: float) -> "RateLimitDecision":
        return cls(status="wait", wait_until=timestamp)

    @classmethod
    def exhausted(cls, reason: str) -> "RateLimitDecision":
        return cls(status="exhausted", reason=reason)


class RateLimitPolicy:
    """Tracks the quota headers Strava returns after each request."""

    def __init__(self) -> None:
        self._rate_info = StravaRateInfo()

    @property
    def rate_info(self) -> StravaRateInfo:
        return self._rate_info

    def update_from_headers(self, headers: Mapping[str, str]) -> StravaRateInfo:
        overall = self._parse_pair(headers.get("X-RateLimit-Limit"), headers.get("X-RateLimit-Usage"))
        read = self._parse_pair(headers.get("X-ReadRateLimit-Limit"), headers.get("X-ReadRateLimit-Usage"))

        self._rate_info = StravaRateInfo(
            overall_short=overall[0] if overall else self._rate_info.overall_short,
            overall_long=overall[1] if overall else self._rate_info.overall_long,
            read_short=read[0] if read else self._rate_info.read_short,
            read_long=read[1] if read else self._rate_info.read_long,
        )
        return self._rate_info

    def mark_rate_limited(self) -> None:
        def _zero(window: tuple[int | None, int | None]) -> tuple[int | None, int | None]:
            used, limit = window
            if limit is None:
                return window
            return (limit, limit)

        self._rate_info = StravaRateInfo(
            overall_short=_zero(self._rate_info.overall_short),
            overall_long=self._rate_info.overall_long,
            read_short=_zero(self._rate_info.read_short),
            read_long=self._rate_info.read_long,
        )

    def decide_next_call(self, now: float) -> RateLimitDecision:
        daily_windows = (self._rate_info.overall_long, self._rate_info.read_long)
        for used, limit in daily_windows:
            if used is not None and limit is not None and used >= limit:
                return RateLimitDecision.exhausted("rate_limited")

        short_windows = (self._rate_info.overall_short, self._rate_info.read_short)
        for used, limit in short_windows:
            if used is not None and limit is not None and used >= limit:
                return RateLimitDecision.wait(self._next_short_reset(now))

        return RateLimitDecision.proceed()

    @staticmethod
    def _parse_csv_pair(value: str | None) -> tuple[int, int] | None:
        if value is None:
            return None
        parts = [part.strip() for part in value.split(",", 1)]
        if len(parts) != 2:
            return None
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None

    @classmethod
    def _parse_pair(
        cls,
        raw_limit: str | None,
        raw_usage: str | None,
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        limits = cls._parse_csv_pair(raw_limit)
        usage = cls._parse_csv_pair(raw_usage)
        if limits is None or usage is None:
            return None
        short_limit, long_limit = limits
        short_used, long_used = usage
        return (short_used, short_limit), (long_used, long_limit)

    @staticmethod
    def _next_short_reset(now: float) -> float:
        window = 15 * 60
        return (int(now) // window + 1) * window
