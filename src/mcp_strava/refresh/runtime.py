"""Refresh runtime orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from mcp_strava.adapters.duckdb.activity_lookup_queries import latest_activity_at
from mcp_strava.adapters.duckdb.refresh_state_store import RefreshStateStore
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.duckdb.repository_models import SyncLogRecord
from mcp_strava.adapters.duckdb.sync_log_store import append_sync_log
from mcp_strava.adapters.strava import StravaUnavailableError
from mcp_strava.adapters.strava.types import Clock, FetchTransport, Sleeper
from mcp_strava.refresh import _sync_ops
from mcp_strava.refresh.checkpoints import Stage, is_active_backfill_stage, is_stream_channel_backfill_stage
from mcp_strava.refresh.policy import RefreshPolicy, refresh_interval_elapsed

_DAILY_STAGE_ORDER = (
    Stage.SUMMARIES,
    Stage.STREAMS,
    Stage.DETAILS,
    Stage.SCHEMA_VALIDATE,
    Stage.READ_MODEL_MATERIALIZE,
    Stage.KUDOS,
)
_BACKFILL_STAGE_ORDER = (
    Stage.STREAMS_BACKFILL,
    Stage.DETAILS_BACKFILL,
    Stage.READ_MODEL_MATERIALIZE_BACKFILL,
)
_STREAM_CHANNEL_BACKFILL_MIN_LEASE_SECONDS = 30 * 60
_READ_MODEL_LEASE_ERROR = "refresh lease lost during read-model materialization"


@dataclass(frozen=True, slots=True, kw_only=True)
class RefreshCollaborators:
    """Shared infrastructure objects passed to every refresh entry-point."""

    repo: DuckDBRepository
    transport: FetchTransport
    policy: RefreshPolicy
    clock: Clock
    sleeper: Sleeper


@dataclass(frozen=True)
class RefreshResult:
    status: str
    reason: str | None = None
    mode: str = "daily"
    checkpoint_stage: str | None = None
    activities_seen: int = 0
    activities_new: int = 0
    streams_fetched: int = 0
    details_fetched: int = 0
    kudos_fetched: int = 0
    # Diagnostic detail for failures (e.g. rate-limit usage/limit snapshot).
    rate_info: dict[str, int | None] | None = None


@dataclass(frozen=True)
class RefreshSkipped:
    reason: str


def run_once(
    collaborators: RefreshCollaborators,
    *,
    owner: str = "refresh-runtime",
    force: bool = False,
    mode: str = "daily",
) -> RefreshResult | RefreshSkipped:
    repo = collaborators.repo
    transport = collaborators.transport
    policy = collaborators.policy
    clock = collaborators.clock
    refresh_store = RefreshStateStore.from_connection(repo.conn)
    now_iso = _now_iso(clock)
    expires_at = _plus_seconds_iso(clock, policy.lease_duration_seconds)
    if not refresh_store.acquire_refresh_lease(owner, expires_at, now_iso):
        return RefreshSkipped("refresh_in_progress")

    try:
        state = refresh_store.get_refresh_state()
        skip = _check_daily_preconditions(state, now_iso, policy, force)
        if skip is not None:
            return skip

        start_index = _daily_start_index(state.checkpoint_stage)
        refresh_store.record_refresh_attempt(now_iso)
        activities_seen, activities_new, streams_fetched, details_fetched, kudos_fetched = _run_daily_stages(
            collaborators, refresh_store, owner, now_iso, start_index
        )
        refresh_store.set_checkpoint(Stage.COMPLETE.value, None)
        refresh_store.record_refresh_success(now_iso)
        append_sync_log(
            repo,
            SyncLogRecord(
                timestamp=now_iso,
                status="ok",
                activities_seen=activities_seen,
                activities_new=activities_new,
                streams_fetched=streams_fetched,
                details_fetched=details_fetched,
                api_calls=sum(getattr(transport, "calls_by_path", {}).values()) or None,
                error=None,
                kudos_fetched=kudos_fetched,
            ),
        )
        return RefreshResult(
            status="ok",
            mode=mode,
            checkpoint_stage=Stage.COMPLETE.value,
            activities_seen=activities_seen,
            activities_new=activities_new,
            streams_fetched=streams_fetched,
            details_fetched=details_fetched,
            kudos_fetched=kudos_fetched,
        )
    except StravaUnavailableError as exc:
        return _handle_failure(refresh_store, clock, policy, exc.reason, mode, detail=exc.detail or None)
    finally:
        refresh_store.release_refresh_lease(owner)


def run_catchup(
    collaborators: RefreshCollaborators,
    *,
    since: str | None = None,
    owner: str = "refresh-backfill",
) -> RefreshResult | RefreshSkipped:
    repo = collaborators.repo
    transport = collaborators.transport
    policy = collaborators.policy
    clock = collaborators.clock
    refresh_store = RefreshStateStore.from_connection(repo.conn)
    now_iso = _now_iso(clock)
    expires_at = _plus_seconds_iso(clock, policy.lease_duration_seconds)
    if not refresh_store.acquire_refresh_lease(owner, expires_at, now_iso):
        return RefreshSkipped("refresh_in_progress")

    try:
        state = refresh_store.get_refresh_state()
        if state.backoff_until and state.backoff_until > now_iso:
            return RefreshSkipped("refresh_delayed")
        if is_stream_channel_backfill_stage(state.checkpoint_stage):
            raise RuntimeError("incompatible checkpoint - stream-channel backfill must resume via admin catchup")
        start_index = _backfill_start_index(state.checkpoint_stage)
        refresh_store.record_refresh_attempt(now_iso)
        streams_fetched = 0
        details_fetched = 0
        if start_index <= _backfill_stage_index(Stage.STREAMS_BACKFILL):
            refresh_store.set_checkpoint(Stage.STREAMS_BACKFILL.value, None)
            streams_fetched = _sync_ops.sync_streams(
                repo,
                transport,
                since,
                on_activity=lambda activity_id: refresh_store.set_checkpoint(
                    Stage.STREAMS_BACKFILL.value, str(activity_id)
                ),
            )
        if start_index <= _backfill_stage_index(Stage.DETAILS_BACKFILL):
            refresh_store.set_checkpoint(Stage.DETAILS_BACKFILL.value, None)
            details_fetched = _sync_ops.sync_details(
                repo,
                transport,
                since,
                on_activity=lambda activity_id: refresh_store.set_checkpoint(
                    Stage.DETAILS_BACKFILL.value, str(activity_id)
                ),
            )
            _sync_ops.schema_validate(repo)
        if start_index <= _backfill_stage_index(Stage.READ_MODEL_MATERIALIZE_BACKFILL):
            refresh_store.set_checkpoint(Stage.READ_MODEL_MATERIALIZE_BACKFILL.value, None)
            _sync_ops.materialize_read_model_stage(
                repo,
                now_iso,
                _lease_renewer(refresh_store, clock, owner, policy.lease_duration_seconds),
            )
        refresh_store.set_checkpoint(Stage.COMPLETE_BACKFILL.value, None)
        append_sync_log(
            repo,
            SyncLogRecord(
                timestamp=now_iso,
                status="ok",
                activities_seen=None,
                activities_new=None,
                streams_fetched=streams_fetched,
                details_fetched=details_fetched,
                api_calls=sum(getattr(transport, "calls_by_path", {}).values()) or None,
                error=None,
                kudos_fetched=None,
            ),
        )
        return RefreshResult(
            status="ok",
            mode="backfill",
            checkpoint_stage=Stage.COMPLETE_BACKFILL.value,
            streams_fetched=streams_fetched,
            details_fetched=details_fetched,
        )
    except StravaUnavailableError as exc:
        return _handle_failure(refresh_store, clock, policy, exc.reason, "backfill", detail=exc.detail or None)
    finally:
        refresh_store.release_refresh_lease(owner)


def run_stream_channel_catchup(
    collaborators: RefreshCollaborators,
    *,
    since: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    owner: str = "refresh-backfill-stream-channels",
) -> dict | RefreshSkipped:
    repo = collaborators.repo
    transport = collaborators.transport
    policy = collaborators.policy
    clock = collaborators.clock
    refresh_store = RefreshStateStore.from_connection(repo.conn)
    now_iso = _now_iso(clock)
    lease_seconds = max(policy.lease_duration_seconds, _STREAM_CHANNEL_BACKFILL_MIN_LEASE_SECONDS)
    expires_at = _plus_seconds_iso(clock, lease_seconds)
    if not refresh_store.acquire_refresh_lease(owner, expires_at, now_iso):
        return RefreshSkipped("refresh_in_progress")

    def renew_lease() -> None:
        renewed = refresh_store.renew_refresh_lease(owner, _plus_seconds_iso(clock, lease_seconds))
        if not renewed:
            raise RuntimeError("refresh lease lost during stream-channel backfill")

    try:
        state = refresh_store.get_refresh_state()
        if state.backoff_until and state.backoff_until > now_iso:
            return RefreshSkipped("refresh_delayed")
        estimate = _sync_ops.estimate_stream_channel_backfill(repo, since=since, limit=limit)
        if dry_run:
            return {
                "status": "ok",
                "mode": "backfill_stream_channels",
                "checkpoint_stage": state.checkpoint_stage or Stage.STREAM_CHANNELS_BACKFILL.value,
                "activities_considered": estimate["activities_considered"],
                "activities_to_backfill": estimate["activities_to_backfill"],
                "missing_channels": estimate["missing_channels"],
                "metadata_missing": estimate["metadata_missing"],
                "estimated_api_calls": estimate["estimated_api_calls"],
            }
        if estimate["activities_to_backfill"] == 0:
            refresh_store.set_checkpoint(Stage.COMPLETE.value, None)
            return {
                "status": "ok",
                "mode": "backfill_stream_channels",
                "checkpoint_stage": Stage.COMPLETE.value,
                "activities_considered": 0,
                "activities_to_backfill": 0,
                "missing_channels": {},
                "metadata_missing": 0,
                "estimated_api_calls": 0,
                "completed": 0,
            }
        refresh_store.record_refresh_attempt(now_iso)
        refresh_store.set_checkpoint(Stage.STREAM_CHANNELS_BACKFILL.value, state.checkpoint_cursor)
        renew_lease()
        result = _sync_ops.sync_stream_channels_backfill(
            repo,
            transport,
            since=since,
            limit=limit,
            checkpoint_stage=Stage.STREAM_CHANNELS_BACKFILL,
            on_progress=renew_lease,
        )
        _sync_ops.materialize_read_model_stage(
            repo,
            now_iso,
            _lease_renewer(refresh_store, clock, owner, lease_seconds),
        )
        refresh_store.set_checkpoint(Stage.COMPLETE.value, None)
        return {
            "status": "ok",
            "mode": "backfill_stream_channels",
            "checkpoint_stage": Stage.COMPLETE_STREAM_CHANNELS_BACKFILL.value,
            "activities_considered": result["activities_considered"],
            "activities_to_backfill": result["activities_to_backfill"],
            "missing_channels": result["missing_channels"],
            "metadata_missing": result["metadata_missing"],
            "estimated_api_calls": result["estimated_api_calls"],
            "completed": result["completed"],
        }
    except StravaUnavailableError as exc:
        _handle_failure(refresh_store, clock, policy, exc.reason, "backfill_stream_channels", detail=exc.detail or None)
        refresh_store.set_checkpoint(
            Stage.STREAM_CHANNELS_BACKFILL.value, refresh_store.get_refresh_state().checkpoint_cursor
        )
        return {
            "status": "failed",
            "mode": "backfill_stream_channels",
            "reason": exc.reason,
            "rate_info": exc.detail or None,
            "checkpoint_stage": Stage.STREAM_CHANNELS_BACKFILL.value,
            "activities_considered": 0,
            "activities_to_backfill": 0,
            "missing_channels": {},
            "metadata_missing": 0,
            "estimated_api_calls": 0,
        }
    finally:
        refresh_store.release_refresh_lease(owner)


def _check_daily_preconditions(state, now_iso: str, policy: RefreshPolicy, force: bool) -> RefreshSkipped | None:
    """Return a RefreshSkipped (or raise) if run_once should not proceed; else None."""
    if state.backoff_until and state.backoff_until > now_iso:
        return RefreshSkipped("refresh_delayed")
    if is_active_backfill_stage(state.checkpoint_stage):
        if state.checkpoint_stage == Stage.STREAM_CHANNELS_BACKFILL.value:
            raise RuntimeError("incompatible checkpoint - stream-channel backfill in progress, run admin catchup")
        raise RuntimeError("incompatible checkpoint - backfill in progress, run run_catchup")
    if (
        not force
        and state.checkpoint_stage == Stage.COMPLETE.value
        and not refresh_interval_elapsed(
            state.last_success_at,
            now_iso,
            policy.regular_refresh_interval_seconds,
        )
    ):
        return RefreshSkipped("already_complete")
    return None


def _run_daily_stages(
    collaborators: RefreshCollaborators,
    refresh_store,
    owner: str,
    now_iso: str,
    start_index: int,
) -> tuple[int, int, int, int, int]:
    """Execute each daily stage in order, resuming from start_index. Returns counters."""
    repo = collaborators.repo
    transport = collaborators.transport
    policy = collaborators.policy
    clock = collaborators.clock
    activities_seen = 0
    activities_new = 0
    streams_fetched = 0
    details_fetched = 0
    kudos_fetched = 0
    if start_index <= _stage_index(Stage.SUMMARIES):
        refresh_store.set_checkpoint(Stage.SUMMARIES.value, None)
        activities_seen, activities_new = _run_summaries_stage(repo, transport, refresh_store, policy, now_iso)
        _sync_ops.schema_validate(repo)
    if start_index <= _stage_index(Stage.STREAMS):
        refresh_store.set_checkpoint(Stage.STREAMS.value, None)
        streams_fetched = _sync_ops.sync_streams(
            repo,
            transport,
            on_activity=lambda activity_id: refresh_store.set_checkpoint(Stage.STREAMS.value, str(activity_id)),
        )
    if start_index <= _stage_index(Stage.DETAILS):
        refresh_store.set_checkpoint(Stage.DETAILS.value, None)
        details_fetched = _sync_ops.sync_details(
            repo,
            transport,
            on_activity=lambda activity_id: refresh_store.set_checkpoint(Stage.DETAILS.value, str(activity_id)),
        )
    if start_index <= _stage_index(Stage.SCHEMA_VALIDATE):
        refresh_store.set_checkpoint(Stage.SCHEMA_VALIDATE.value, None)
        _sync_ops.schema_validate(repo)
    if start_index <= _stage_index(Stage.READ_MODEL_MATERIALIZE):
        refresh_store.set_checkpoint(Stage.READ_MODEL_MATERIALIZE.value, None)
        _sync_ops.materialize_read_model_stage(
            repo,
            now_iso,
            _lease_renewer(refresh_store, clock, owner, policy.lease_duration_seconds),
        )
    if start_index <= _stage_index(Stage.KUDOS):
        refresh_store.set_checkpoint(Stage.KUDOS.value, None)
        kudos_fetched = _sync_ops._sync_kudos(repo, transport, now_iso)
    return activities_seen, activities_new, streams_fetched, details_fetched, kudos_fetched


def _run_summaries_stage(
    repo,
    transport,
    refresh_store,
    policy: RefreshPolicy,
    now_iso: str,
) -> tuple[int, int]:
    """Determine full-vs-incremental sync window and delegate to sync_summaries."""
    last_full = refresh_store.get_last_full_summary_sync_at()
    do_full = (last_full is None) or refresh_interval_elapsed(last_full, now_iso, policy.full_resync_interval_seconds)
    if do_full:
        after_epoch = None
    else:
        latest_date_str = latest_activity_at(repo)
        if latest_date_str is not None:
            d = date.fromisoformat(latest_date_str[:10])
            after_epoch = int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())
        else:
            after_epoch = None  # empty DB but marker set — treat as full
    activities_seen, activities_new = _sync_ops.sync_summaries(repo, transport, now_iso, after_epoch=after_epoch)
    if do_full:
        refresh_store.set_last_full_summary_sync_at(now_iso)
    return activities_seen, activities_new


def _handle_failure(
    refresh_store, clock, policy: RefreshPolicy, reason: str, mode: str, detail: dict[str, int | None] | None = None
) -> RefreshResult:
    now_iso = _now_iso(clock)
    refresh_store.record_refresh_failure(now_iso, reason, _plus_seconds_iso(clock, _backoff_seconds(reason, policy)))
    return RefreshResult(status="failed", reason=reason, mode=mode, rate_info=detail or None)


def _backoff_seconds(reason: str, policy: RefreshPolicy) -> int:
    if reason == "rate_limited":
        return policy.backoff_seconds_on_rate_limit_default
    if reason == "token_unavailable":
        return policy.backoff_seconds_on_token_failure
    return policy.backoff_seconds_on_network


def _stage_index(stage: Stage) -> int:
    return _DAILY_STAGE_ORDER.index(stage)


def _backfill_stage_index(stage: Stage) -> int:
    return _BACKFILL_STAGE_ORDER.index(stage)


def _daily_start_index(stage: str | None) -> int:
    for index, candidate in enumerate(_DAILY_STAGE_ORDER):
        if stage == candidate.value:
            return index
    return 0


def _backfill_start_index(stage: str | None) -> int:
    for index, candidate in enumerate(_BACKFILL_STAGE_ORDER):
        if stage == candidate.value:
            return index
    return 0


def _lease_renewer(refresh_store, clock, owner: str, lease_seconds: int):
    def renew() -> None:
        renewed = refresh_store.renew_refresh_lease(owner, _plus_seconds_iso(clock, lease_seconds))
        if not renewed:
            raise RuntimeError(_READ_MODEL_LEASE_ERROR)

    return renew


def _now_dt(clock) -> datetime:
    return datetime.fromtimestamp(float(clock.now()), tz=UTC).replace(tzinfo=None)


def _now_iso(clock) -> str:
    return _now_dt(clock).isoformat()


def _plus_seconds_iso(clock, seconds: int) -> str:
    return (_now_dt(clock) + timedelta(seconds=seconds)).isoformat()
