"""Application-level freshness metadata over the local mirror."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime

from mcp_strava.db import DbConn, repository_from_connection
from mcp_strava.refresh.freshness import _parse_dt, evaluate_freshness
from mcp_strava.refresh.policy import RefreshPolicy
from mcp_strava.settings import get_settings
from mcp_strava.types import (
    CompletenessMetadata,
    FreshnessMetadata,
    ServiceEnvelope,
    ServiceRationale,
    ServiceWarning,
)


def _age_seconds(now: datetime, value: str | None) -> int | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    return max(0, int((now - parsed).total_seconds()))


def _refreshed_today(last_success_at: str | None, today: str) -> bool:
    parsed = _parse_dt(last_success_at)
    if parsed is None:
        return False
    return parsed.date().isoformat() == today


def _refresh_blocked(state, now: datetime) -> bool:
    lease_expires_at = _parse_dt(state.lease_expires_at)
    if state.lease_owner is not None and lease_expires_at is not None and lease_expires_at > now:
        return True

    backoff_until = _parse_dt(state.backoff_until)
    return backoff_until is not None and backoff_until > now


def build_freshness_metadata(
    repo,
    now: datetime,
    policy: RefreshPolicy,
    *,
    signal_first_use: bool = True,
) -> FreshnessMetadata:
    """Build factual freshness metadata and optionally signal first use today."""
    state = repo.get_refresh_state()
    last_activity_at = repo.latest_activity_at()
    freshness_state = evaluate_freshness(state, now, policy)
    today = now.date().isoformat()

    refresh_requested = False
    if signal_first_use and not _refresh_blocked(state, now) and not _refreshed_today(state.last_success_at, today):
        refresh_requested = repo.enqueue_refresh_request("first_use_of_day", today, now.isoformat())

    return FreshnessMetadata(
        freshness_state=freshness_state,
        checked_at=now.isoformat(),
        last_successful_refresh_at=state.last_success_at,
        refresh_age_seconds=_age_seconds(now, state.last_success_at),
        last_activity_at=last_activity_at,
        last_activity_age_seconds=_age_seconds(now, last_activity_at),
        refresh_requested=refresh_requested,
        refresh_request_reason="first_use_of_day" if refresh_requested else None,
        last_error_code=state.last_error_code,
        backoff_until=state.backoff_until,
    )


def _warnings_for_freshness(freshness: FreshnessMetadata) -> list[ServiceWarning]:
    warnings: list[ServiceWarning] = []
    if freshness.freshness_state in {"aging", "stale"}:
        warnings.append(
            ServiceWarning(
                code="mirror_stale",
                severity="warning",
                message="Local mirror refresh is not recent.",
                field="last_successful_refresh_at",
            )
        )
    if freshness.freshness_state == "refresh_delayed":
        warnings.append(
            ServiceWarning(
                code="refresh_delayed",
                severity="warning",
                message="Local refresh is delayed by refresh backoff.",
                field="backoff_until",
            )
        )
    if freshness.freshness_state == "refresh_failed":
        warnings.append(
            ServiceWarning(
                code="refresh_failed",
                severity="warning",
                message="The most recent refresh attempt failed.",
                field="last_error_code",
            )
        )
    return warnings


def get_freshness_service(
    *,
    now: datetime | None = None,
    signal_first_use: bool = True,
    connection=None,
) -> ServiceEnvelope:
    """Return local mirror freshness in the shared service envelope."""
    checked_at = now or datetime.now()
    settings = get_settings()
    policy = RefreshPolicy.from_settings(settings)
    conn_context = nullcontext(connection) if connection is not None else DbConn()

    with conn_context as conn:
        repo = repository_from_connection(conn)
        freshness = build_freshness_metadata(
            repo,
            checked_at,
            policy,
            signal_first_use=signal_first_use,
        )

    return ServiceEnvelope(
        data=freshness,
        freshness=freshness,
        completeness=CompletenessMetadata(
            status="complete",
            missing=[],
            coverage={"metadata": "freshness"},
        ),
        warnings=_warnings_for_freshness(freshness),
        rationale=[
            ServiceRationale(
                code="local_mirror_metadata",
                message="Freshness is computed from local refresh_state and activities tables.",
            )
        ],
    )
