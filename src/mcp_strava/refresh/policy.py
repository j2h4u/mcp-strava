"""Refresh runtime policy values."""

from __future__ import annotations

from dataclasses import dataclass

from mcp_strava.settings import Settings


@dataclass(frozen=True)
class RefreshPolicy:
    lease_duration_seconds: int = 600
    backoff_seconds_on_rate_limit_default: int = 900
    backoff_seconds_on_network: int = 60
    backoff_seconds_on_token_failure: int = 3600
    recent_failure_window_seconds: int = 3600
    warn_age_hours: int = 12
    max_age_hours: int = 24

    @classmethod
    def from_settings(cls, settings: Settings) -> "RefreshPolicy":
        return cls(
            warn_age_hours=settings.freshness.warn_age_hours,
            max_age_hours=settings.freshness.max_age_hours,
        )
