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
    STRAVA_APPLICATION_INACTIVE = "strava_application_inactive"
    REFRESH_INCOMPLETE = "refresh_incomplete"


class StravaUnavailableError(Exception):
    """Typed adapter failure with a product-safe reason code.

    ``detail`` carries optional diagnostic context for operator logs (e.g. the
    rate-limit usage/limit snapshot when ``reason == "rate_limited"``). It is
    never surfaced to end users — only the opaque ``reason`` code is. ``status``
    carries the upstream HTTP status when the adapter can preserve it without
    leaking transport details across the boundary.
    """

    def __init__(self, reason: str, detail: dict[str, Any] | None = None, status: int | None = None):
        self.reason = reason
        self.detail: dict[str, Any] = detail or {}
        self.status = status
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
    data: object
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


class FetchTransport(Protocol):
    """Structural protocol for any object with a Strava-style fetch method."""

    def fetch(self, path: str) -> StravaResponse: ...


Headers = Mapping[str, str]
