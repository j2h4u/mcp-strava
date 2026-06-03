"""Application-level freshness metadata over the local mirror."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime

from mcp_strava.adapters.duckdb.connection import MirrorConn
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
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


def _freshness_now() -> datetime:
    """The default 'now' for freshness/staleness comparisons — a UTC-naive instant.

    WR-02: freshness compares `now` against last_success_at, which is stored
    UTC-naive (refresh writes datetime.now(UTC); _parse_dt normalizes Z->+00:00).
    The comparison is between INSTANTS, so the clock must be UTC end-to-end — a
    plain datetime.now() (server-local, e.g. Asia/Almaty +6h) would skew the
    computed age by the UTC offset and misclassify a fresh mirror as aging/stale.
    We strip tzinfo to match the UTC-naive basis the stored timestamps are parsed
    into. Display/calendar values (start_time_local, as_of_day) stay local; only
    this instant-comparison clock is UTC.
    """
    return datetime.now(UTC).replace(tzinfo=None)


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
    """Report how fresh the local Strava mirror is, as a standalone envelope.

    Answers "how stale is our local copy": last successful refresh time + age,
    last activity time + age, a freshness_state label (fresh/aging/stale/
    refresh_delayed/refresh_failed), whether a first-use-of-day refresh was just
    enqueued, and the last error/backoff. The same data is embedded as the
    ``freshness`` field of every product tool's envelope via
    ``build_freshness_metadata``; this service exposes only that status on its
    own. Reached from the ``freshness`` CLI command / capability registry, not
    from the six MCP product tools.
    """
    checked_at = now if now is not None else _freshness_now()
    settings = get_settings()
    policy = RefreshPolicy.from_settings(settings)
    # MirrorConn (open-per-call), not ReadConn: this is a CLI/registry read on a
    # one-shot process, so connection reuse buys nothing. The reused thread-local
    # ReadConn is reserved for the long-lived MCP server read tools.
    conn_context = nullcontext(connection) if connection is not None else MirrorConn()

    with conn_context as conn:
        repo = DuckDBRepository.from_connection(conn)
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
