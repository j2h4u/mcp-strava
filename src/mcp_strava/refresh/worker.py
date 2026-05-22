"""Background worker that maintains the local Strava mirror."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from threading import Event

import mcp_strava.refresh.runtime as refresh_runtime
from mcp_strava.adapters.sqlite.migrations import run_preflight
from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.db import DbConn
from mcp_strava.refresh import RefreshSkipped, Stage
from mcp_strava.refresh.bootstrap import build_refresh_collaborators, ensure_refresh_schema, record_refresh_misconfigured
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
    if state.checkpoint_stage is not None and state.checkpoint_stage != Stage.COMPLETE.value:
        return True
    return refresh_interval_elapsed(
        state.last_success_at,
        now_iso,
        policy.regular_refresh_interval_seconds,
    )


def run_pending_once(*, emit_idle: bool = True) -> int:
    """Run one refresh cycle when interval policy or queued requests require it."""
    settings = get_settings()
    ensure_refresh_schema(run_preflight(settings.database_path))
    now_iso = _now_iso()

    refresh_policy = RefreshPolicy.from_settings(settings)

    with DbConn() as conn:
        repo = SQLiteRepository.from_connection(conn)
        state = repo.get_refresh_state()
        pending_count = len(repo.pending_refresh_requests())
        blocked_reason = _refresh_blocked_reason(state, now_iso)
        if blocked_reason is not None:
            if emit_idle:
                _emit("refresh_skipped", reason=blocked_reason)
            return 0
        refresh_due = _regular_refresh_due(state, now_iso, refresh_policy)

    if pending_count == 0 and not refresh_due:
        if emit_idle:
            _emit("refresh_idle")
        return 0

    try:
        _, clock, sleeper, transport, refresh_policy = build_refresh_collaborators(settings)
    except RuntimeError:
        record_refresh_misconfigured(settings)
        _emit("refresh_failed", reason="refresh_misconfigured", pending_requests=pending_count)
        return 1

    with DbConn() as conn:
        repo = SQLiteRepository.from_connection(conn)
        pending_count = len(repo.pending_refresh_requests())
        if pending_count == 0 and not refresh_due:
            if emit_idle:
                _emit("refresh_idle")
            return 0

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
                return 0
            _emit("refresh_skipped", reason=result.reason)
            return 0

        if result.status == "ok":
            consumed = repo.mark_refresh_requests_consumed(_now_iso())
            _emit("refresh_ok", consumed=consumed, checkpoint_stage=result.checkpoint_stage)
            return 0

        _emit("refresh_failed", reason=result.reason or "unknown", checkpoint_stage=result.checkpoint_stage)
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
            run_pending_once(emit_idle=False)
        except Exception as exc:  # noqa: BLE001
            _emit("refresh_worker_error", error_type=type(exc).__name__)
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

    if args.once:
        return run_pending_once()

    run_forever(poll_seconds=args.poll_seconds)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("refresh worker interrupted", file=sys.stderr)
        raise SystemExit(130)
