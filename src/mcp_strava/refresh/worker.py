"""Background worker that maintains the local Strava mirror."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from threading import Event

import mcp_strava.refresh.runtime as refresh_runtime
from mcp_strava.adapters.duckdb.connection import MirrorConn
from mcp_strava.adapters.duckdb.repository import CURRENT_METRIC_VERSION, DuckDBRepository
from mcp_strava.maintenance.compact import storage_stats
from mcp_strava.refresh import RefreshSkipped, Stage, _sync_ops, health
from mcp_strava.refresh.bootstrap import (
    build_refresh_collaborators,
    ensure_runtime_refresh_schema,
    record_refresh_misconfigured,
)
from mcp_strava.refresh.policy import RefreshPolicy, refresh_interval_elapsed
from mcp_strava.settings import get_settings


def _now_iso() -> str:
    return datetime.now().isoformat()


def _emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def _refresh_blocked_reason(state, now_iso: str) -> str | None:
    if state.lease_owner is not None and state.lease_expires_at is not None and state.lease_expires_at > now_iso:
        return "refresh_in_progress"
    if state.backoff_until is not None and state.backoff_until > now_iso:
        return "refresh_delayed"
    return None


def _regular_refresh_due(state, now_iso: str, policy: RefreshPolicy) -> bool:
    if state.checkpoint_stage == Stage.STREAM_CHANNELS_BACKFILL.value:
        return False
    if state.checkpoint_stage is not None and state.checkpoint_stage != Stage.COMPLETE.value:
        return True
    return refresh_interval_elapsed(
        state.last_success_at,
        now_iso,
        policy.regular_refresh_interval_seconds,
    )


def _stream_channel_backfill_due(state) -> bool:
    return state.checkpoint_stage == Stage.STREAM_CHANNELS_BACKFILL.value


def _materialize_dirty_read_model(batch_size: int) -> int:
    with MirrorConn() as conn:
        repo = DuckDBRepository.from_connection(conn)
        status = repo.read_model_status(metric_version=CURRENT_METRIC_VERSION)
        dirty_count = int(status.get("dirty_count") or 0)
        if dirty_count == 0:
            return 0
        claim_count = min(dirty_count, batch_size)
        _emit("read_model_materialize_started", dirty_count=dirty_count, batch_size=claim_count)
        result = _sync_ops.materialize_read_model_stage(
            repo,
            CURRENT_METRIC_VERSION,
            _now_iso(),
            None,
            limit=claim_count,
        )
        cleared = int(result.get("dirty_rows_cleared") or 0)
        remaining = max(dirty_count - cleared, 0)
        _emit("read_model_materialize_ok", dirty_rows_cleared=cleared, dirty_count_remaining=remaining)
        return cleared


def _run_stream_channel_backfill(repo, transport, refresh_policy, clock, sleeper):
    return refresh_runtime.run_stream_channel_catchup(
        repo,
        transport,
        refresh_policy,
        clock,
        sleeper,
        limit=refresh_policy.stream_backfill_batch_size,
        owner="refresh-worker-stream-backfill",
    )


_prev_free_blocks: int | None = None


def _emit_mirror_storage() -> None:
    """Emit the DuckDB reclaimable-space indicator with a per-cycle delta.

    Fires on every cycle (including idle) so the mirror size is a continuous
    series independent of refresh outcome — `free_blocks_delta` shows growth per
    cycle. Best-effort: never disrupts the worker.
    """
    global _prev_free_blocks
    try:
        with MirrorConn() as conn:
            stats = storage_stats(conn)
    except Exception as exc:
        _emit("mirror_storage_error", error_type=type(exc).__name__, error=str(exc)[:200])
        return
    free = int(stats["free_blocks"])
    stats["free_blocks_delta"] = None if _prev_free_blocks is None else free - _prev_free_blocks
    _prev_free_blocks = free
    _emit("mirror_storage", **stats)


def run_pending_once(*, emit_idle: bool = True) -> int:
    """Run one refresh cycle, then always emit the storage indicator."""
    try:
        return _run_pending_cycle(emit_idle=emit_idle)
    finally:
        _emit_mirror_storage()


def _run_pending_cycle(*, emit_idle: bool = True) -> int:
    """Run one refresh cycle when interval policy or queued requests require it."""
    settings = get_settings()
    ensure_runtime_refresh_schema(settings)
    _materialize_dirty_read_model(settings.refresh.read_model_batch_size)
    now_iso = _now_iso()

    refresh_policy = RefreshPolicy.from_settings(settings)

    with MirrorConn() as conn:
        repo = DuckDBRepository.from_connection(conn)
        state = repo.get_refresh_state()
        pending_count = len(repo.pending_refresh_requests())
        blocked_reason = _refresh_blocked_reason(state, now_iso)
        if blocked_reason is not None:
            if emit_idle:
                _emit("refresh_skipped", reason=blocked_reason)
            return 0
        refresh_due = _regular_refresh_due(state, now_iso, refresh_policy)
        stream_backfill_due = _stream_channel_backfill_due(state)

    if pending_count == 0 and not refresh_due and not stream_backfill_due:
        if emit_idle:
            _emit("refresh_idle")
        return 0

    try:
        _, clock, sleeper, transport, refresh_policy = build_refresh_collaborators(settings)
    except RuntimeError:
        record_refresh_misconfigured(settings)
        _emit("refresh_failed", reason="refresh_misconfigured", pending_requests=pending_count)
        return 1

    with MirrorConn() as conn:
        repo = DuckDBRepository.from_connection(conn)
        pending_count = len(repo.pending_refresh_requests())
        state = repo.get_refresh_state()
        stream_backfill_due = _stream_channel_backfill_due(state)
        if pending_count == 0 and not refresh_due and not stream_backfill_due:
            if emit_idle:
                _emit("refresh_idle")
            return 0

        if pending_count > 0 or refresh_due:
            result = refresh_runtime.run_once(
                repo,
                transport,
                refresh_policy,
                clock,
                sleeper,
                owner="refresh-worker",
                force=False,
                mode="periodic",
            )

            if isinstance(result, RefreshSkipped):
                if result.reason == "already_complete":
                    consumed = repo.mark_refresh_requests_consumed(_now_iso())
                    _emit("refresh_request_consumed", result="already_complete", consumed=consumed)
                else:
                    _emit("refresh_skipped", reason=result.reason)
                    return 0
            elif result.status == "ok":
                consumed = repo.mark_refresh_requests_consumed(_now_iso())
                _emit(
                    "refresh_ok",
                    consumed=consumed,
                    checkpoint_stage=result.checkpoint_stage,
                    activities_seen=result.activities_seen,
                    activities_new=result.activities_new,
                    streams_fetched=result.streams_fetched,
                    details_fetched=result.details_fetched,
                    kudos_fetched=result.kudos_fetched,
                )
            else:
                _emit(
                    "refresh_failed",
                    reason=result.reason or "unknown",
                    checkpoint_stage=result.checkpoint_stage,
                    # Rate-limit usage/limit snapshot when reason == "rate_limited".
                    **(result.rate_info or {}),
                )
                return 1

        backfill_result = _run_stream_channel_backfill(repo, transport, refresh_policy, clock, sleeper)
        if isinstance(backfill_result, RefreshSkipped):
            _emit("stream_backfill_skipped", reason=backfill_result.reason)
            return 0
        if backfill_result["status"] == "ok":
            _emit(
                "stream_backfill_ok",
                completed=backfill_result.get("completed", 0),
                activities_to_backfill=backfill_result["activities_to_backfill"],
                checkpoint_stage=backfill_result["checkpoint_stage"],
            )
            return 0
        _emit(
            "stream_backfill_failed",
            reason=backfill_result.get("reason", "unknown"),
            checkpoint_stage=backfill_result.get("checkpoint_stage"),
        )
        return 1


def _poll_seconds(raw: str | None) -> int:
    if raw is None:
        return 60
    value = int(raw)
    if value < 5:
        raise ValueError("poll seconds must be >= 5")
    return value


def run_forever(
    *,
    poll_seconds: int | None = None,
    stop_event: Event | None = None,
    emit_start: bool = True,
) -> None:
    resolved_poll_seconds = poll_seconds
    if resolved_poll_seconds is None:
        resolved_poll_seconds = _poll_seconds(os.environ.get("MCP_STRAVA_REFRESH_POLL_SECONDS"))
    if emit_start:
        _emit("refresh_worker_started", poll_seconds=resolved_poll_seconds)

    while stop_event is None or not stop_event.is_set():
        try:
            return_code = run_pending_once(emit_idle=False)
            health.record_cycle("ok" if return_code == 0 else "error")
        except Exception as exc:
            _emit("refresh_worker_error", error_type=type(exc).__name__, error=str(exc))
            traceback.print_exc(file=sys.stderr)
            health.record_cycle("error", error_type=type(exc).__name__, error=str(exc))
        if stop_event is not None:
            if stop_event.wait(resolved_poll_seconds):
                break
        else:
            time.sleep(resolved_poll_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the mcp-strava mirror refresh worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=_poll_seconds(os.environ.get("MCP_STRAVA_REFRESH_POLL_SECONDS")),
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if settings.database_path.suffix.lower() == ".duckdb" and settings.runtime_profile in {
        "container",
        "docker",
        "live",
    }:
        print(
            "standalone refresh worker is disabled for live DuckDB runtime; use the mcp-strava owner process",
            file=sys.stderr,
        )
        return 1

    if args.once:
        return run_pending_once()

    run_forever(poll_seconds=args.poll_seconds)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("refresh worker interrupted", file=sys.stderr)
        raise SystemExit(130) from None
