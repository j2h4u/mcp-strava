"""Typed contracts for the Strava adapter boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class RefreshReason(StrEnum):
    TOKEN_UNAVAILABLE = "token_unavailable"
    RATE_LIMITED = "rate_limited"
    NETWORK_UNSTABLE = "network_unstable"
    REFRESH_INCOMPLETE = "refresh_incomplete"


class StravaUnavailable(Exception):
    """Typed adapter failure with a product-safe reason code."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class StravaRateInfo:
    overall_short: tuple[int | None, int | None] = (None, None)
    overall_long: tuple[int | None, int | None] = (None, None)
    read_short: tuple[int | None, int | None] = (None, None)
    read_long: tuple[int | None, int | None] = (None, None)

    def as_dict(self) -> dict[str, int | None]:
        return {
            "usage_15min": self.overall_short[0],
            "limit_15min": self.overall_short[1],
            "usage_daily": self.overall_long[0],
            "limit_daily": self.overall_long[1],
            "read_usage_15min": self.read_short[0],
            "read_limit_15min": self.read_short[1],
            "read_usage_daily": self.read_long[0],
            "read_limit_daily": self.read_long[1],
        }


@dataclass(frozen=True)
class StravaResponse:
    data: Any
    rate_info: StravaRateInfo
    status: int


@dataclass(frozen=True)
class RefreshedTokens:
    access_token: str
    refresh_token: str
    expires_at: int


class Clock(Protocol):
    def now(self) -> float: ...


class Sleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


Headers = Mapping[str, str]
