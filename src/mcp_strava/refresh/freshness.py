"""Pure freshness evaluation over SQLite refresh metadata."""

from __future__ import annotations

from datetime import datetime

from mcp_strava.refresh.policy import RefreshPolicy
from mcp_strava.types import RefreshStateRow


def evaluate_freshness(state: RefreshStateRow, now: datetime, policy: RefreshPolicy) -> str:
    if state.lease_owner is not None and _parse_dt(state.lease_expires_at) and _parse_dt(state.lease_expires_at) > now:
        return "refresh_in_progress"

    if state.backoff_until is not None and _parse_dt(state.backoff_until) and _parse_dt(state.backoff_until) > now:
        return "refresh_delayed"

    if state.last_status == "failed" and state.last_attempt_at:
        last_attempt = _parse_dt(state.last_attempt_at)
        if last_attempt is not None and (now - last_attempt).total_seconds() <= policy.recent_failure_window_seconds:
            return "refresh_failed"

    if not state.last_success_at:
        return "stale"

    last_success = _parse_dt(state.last_success_at)
    if last_success is None:
        return "stale"

    age_hours = (now - last_success).total_seconds() / 3600
    if age_hours < policy.warn_age_hours:
        return "fresh"
    if age_hours < policy.max_age_hours:
        return "aging"
    return "stale"


def enqueue_refresh_request_if_stale(
    repo,
    now: datetime,
    policy: RefreshPolicy,
    *,
    reason: str = "first_use_of_day",
    requested_for_day: str | None = None,
) -> bool:
    state = repo.get_refresh_state()
    freshness = evaluate_freshness(state, now, policy)
    if freshness not in {"aging", "stale"}:
        return False
    day = requested_for_day or now.date().isoformat()
    return repo.enqueue_refresh_request(reason, day, now.isoformat())


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
