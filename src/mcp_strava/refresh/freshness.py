"""Pure freshness evaluation over mirror refresh metadata."""

from __future__ import annotations

from datetime import date, datetime

from mcp_strava.refresh.policy import RefreshPolicy
from mcp_strava.types import RefreshStateRow


def evaluate_freshness(state: RefreshStateRow, now: datetime, policy: RefreshPolicy) -> str:
    _lease_expires = _parse_dt(state.lease_expires_at)
    if state.lease_owner is not None and _lease_expires is not None and _lease_expires > now:
        return "refresh_in_progress"

    _backoff_until = _parse_dt(state.backoff_until)
    if state.backoff_until is not None and _backoff_until is not None and _backoff_until > now:
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
    refresh_store,
    now: datetime,
    policy: RefreshPolicy,
    *,
    reason: str = "first_use_of_day",
    requested_for_day: date | str | None = None,
) -> bool:
    state = refresh_store.get_refresh_state()
    freshness = evaluate_freshness(state, now, policy)
    if freshness not in {"aging", "stale"}:
        return False
    if isinstance(requested_for_day, str):
        day: date = date.fromisoformat(requested_for_day)
    else:
        day = requested_for_day or now.date()
    return refresh_store.enqueue_refresh_request(reason, day, now.isoformat())


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError:
        return None
