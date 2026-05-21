"""Refresh runtime orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from mcp_strava.adapters.strava import StravaUnavailable
from mcp_strava.refresh import _sync_ops
from mcp_strava.refresh.checkpoints import Stage, is_backfill_stage
from mcp_strava.refresh.policy import RefreshPolicy


@dataclass(frozen=True)
class RefreshResult:
    status: str
    reason: str | None = None
    mode: str = "daily"
    checkpoint_stage: str | None = None


@dataclass(frozen=True)
class RefreshSkipped:
    reason: str


def run_once(
    repo,
    transport,
    policy: RefreshPolicy,
    clock,
    sleeper,
    *,
    owner: str = "refresh-runtime",
    force: bool = False,
    mode: str = "daily",
) -> RefreshResult | RefreshSkipped:
    now_iso = _now_iso(clock)
    expires_at = _plus_seconds_iso(clock, policy.lease_duration_seconds)
    if not repo.acquire_refresh_lease(owner, expires_at, now_iso):
        return RefreshSkipped("refresh_in_progress")

    try:
        state = repo.get_refresh_state()
        if state.backoff_until and state.backoff_until > now_iso:
            return RefreshSkipped("refresh_delayed")
        if is_backfill_stage(state.checkpoint_stage):
            raise RuntimeError("incompatible checkpoint - backfill in progress, run run_backfill")
        if not force and state.last_success_at and state.last_success_at[:10] == now_iso[:10] and state.checkpoint_stage == Stage.COMPLETE.value:
            return RefreshSkipped("already_complete")

        repo.record_refresh_attempt(now_iso)
        repo.set_checkpoint(Stage.SUMMARIES.value, None)
        activities_seen, activities_new = _sync_ops.sync_summaries(repo, transport, now_iso)
        repo.set_checkpoint(Stage.STREAMS.value, None)
        streams_fetched = _sync_ops.sync_streams(repo, transport)
        repo.set_checkpoint(Stage.DETAILS.value, None)
        details_fetched = _sync_ops.sync_details(repo, transport)
        repo.set_checkpoint(Stage.SCHEMA_VALIDATE.value, None)
        _sync_ops.schema_validate(repo)
        repo.set_checkpoint(Stage.KUDOS.value, None)
        kudos_fetched = _sync_ops._sync_kudos(repo, transport, now_iso)
        repo.set_checkpoint(Stage.COMPLETE.value, None)
        repo.record_refresh_success(now_iso)
        repo.append_sync_log(
            timestamp=now_iso,
            status="ok",
            activities_seen=activities_seen,
            activities_new=activities_new,
            streams_fetched=streams_fetched,
            details_fetched=details_fetched,
            api_calls=sum(getattr(transport, "calls_by_path", {}).values()) or None,
            error=None,
            kudos_fetched=kudos_fetched,
        )
        return RefreshResult(status="ok", mode=mode, checkpoint_stage=Stage.COMPLETE.value)
    except StravaUnavailable as exc:
        return _handle_failure(repo, clock, policy, exc.reason, mode)
    finally:
        repo.release_refresh_lease(owner)


def run_backfill(
    repo,
    transport,
    policy: RefreshPolicy,
    clock,
    sleeper,
    *,
    since: str | None = None,
    owner: str = "refresh-backfill",
) -> RefreshResult | RefreshSkipped:
    now_iso = _now_iso(clock)
    expires_at = _plus_seconds_iso(clock, policy.lease_duration_seconds)
    if not repo.acquire_refresh_lease(owner, expires_at, now_iso):
        return RefreshSkipped("refresh_in_progress")

    try:
        state = repo.get_refresh_state()
        if state.backoff_until and state.backoff_until > now_iso:
            return RefreshSkipped("refresh_delayed")
        repo.record_refresh_attempt(now_iso)
        repo.set_checkpoint(Stage.STREAMS_BACKFILL.value, None)
        streams_fetched = _sync_ops.sync_streams(repo, transport, since)
        repo.set_checkpoint(Stage.DETAILS_BACKFILL.value, None)
        details_fetched = _sync_ops.sync_details(repo, transport, since)
        repo.set_checkpoint(Stage.COMPLETE_BACKFILL.value, None)
        repo.append_sync_log(
            timestamp=now_iso,
            status="ok",
            activities_seen=None,
            activities_new=None,
            streams_fetched=streams_fetched,
            details_fetched=details_fetched,
            api_calls=sum(getattr(transport, "calls_by_path", {}).values()) or None,
            error=None,
            kudos_fetched=None,
        )
        return RefreshResult(status="ok", mode="backfill", checkpoint_stage=Stage.COMPLETE_BACKFILL.value)
    except StravaUnavailable as exc:
        return _handle_failure(repo, clock, policy, exc.reason, "backfill")
    finally:
        repo.release_refresh_lease(owner)


def _handle_failure(repo, clock, policy: RefreshPolicy, reason: str, mode: str) -> RefreshResult:
    now_iso = _now_iso(clock)
    repo.record_refresh_failure(now_iso, reason, _plus_seconds_iso(clock, _backoff_seconds(reason, policy)))
    return RefreshResult(status="failed", reason=reason, mode=mode)


def _backoff_seconds(reason: str, policy: RefreshPolicy) -> int:
    if reason == "rate_limited":
        return policy.backoff_seconds_on_rate_limit_default
    if reason == "token_unavailable":
        return policy.backoff_seconds_on_token_failure
    return policy.backoff_seconds_on_network


def _now_dt(clock) -> datetime:
    return datetime.fromtimestamp(float(clock.now()), tz=timezone.utc).replace(tzinfo=None)


def _now_iso(clock) -> str:
    return _now_dt(clock).isoformat()


def _plus_seconds_iso(clock, seconds: int) -> str:
    return (_now_dt(clock) + timedelta(seconds=seconds)).isoformat()
