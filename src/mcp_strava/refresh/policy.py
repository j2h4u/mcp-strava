"""Refresh runtime policy values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

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
    regular_refresh_interval_seconds: int = 3600
    stream_backfill_batch_size: int = 50
    full_resync_interval_seconds: int = 604800

    @classmethod
    def from_settings(cls, settings: Settings) -> RefreshPolicy:
        return cls(
            warn_age_hours=settings.freshness.warn_age_hours,
            max_age_hours=settings.freshness.max_age_hours,
            regular_refresh_interval_seconds=settings.refresh.interval_seconds,
            stream_backfill_batch_size=settings.refresh.stream_backfill_batch_size,
            full_resync_interval_seconds=settings.refresh.full_resync_interval_seconds,
        )


def refresh_interval_elapsed(last_success_at: str | None, now_iso: str, interval_seconds: int) -> bool:
    if not last_success_at:
        return True
    if interval_seconds <= 0:
        return True
    try:
        last_success = datetime.fromisoformat(last_success_at)
        now = datetime.fromisoformat(now_iso)
    except ValueError:
        return True
    return now - last_success >= timedelta(seconds=interval_seconds)
