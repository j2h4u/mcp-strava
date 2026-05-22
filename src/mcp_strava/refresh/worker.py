"""Background worker that consumes local refresh requests."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

import mcp_strava.refresh.runtime as refresh_runtime
from mcp_strava.adapters.sqlite.migrations import run_preflight
from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.db import DbConn
from mcp_strava.refresh import RefreshSkipped
from mcp_strava.settings import get_settings
from mcp_strava.sync import build_refresh_collaborators, ensure_refresh_schema, record_refresh_misconfigured


def _now_iso() -> str:
    return datetime.now().isoformat()


def _emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def _pending_request_count() -> int:
    settings = get_settings()
    ensure_refresh_schema(run_preflight(settings.database_path))
    with DbConn() as conn:
        repo = SQLiteRepository.from_connection(conn)
        return len(repo.pending_refresh_requests())


def run_pending_once(*, emit_idle: bool = True) -> int:
    """Run one refresh cycle when pending requests exist."""
    pending_count = _pending_request_count()
    if pending_count == 0:
        if emit_idle:
            _emit("refresh_idle")
        return 0

    settings = get_settings()
    try:
        _, clock, sleeper, transport, refresh_policy = build_refresh_collaborators(settings)
    except RuntimeError:
        record_refresh_misconfigured(settings)
        _emit("refresh_failed", reason="refresh_misconfigured", pending_requests=pending_count)
        return 1

    with DbConn() as conn:
        repo = SQLiteRepository.from_connection(conn)
        if not repo.pending_refresh_requests():
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
            mode="daily",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consume mcp-strava refresh requests")
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=_poll_seconds(os.environ.get("MCP_STRAVA_REFRESH_POLL_SECONDS")),
    )
    args = parser.parse_args(argv)

    if args.once:
        return run_pending_once()

    _emit("refresh_worker_started", poll_seconds=args.poll_seconds)
    while True:
        run_pending_once(emit_idle=False)
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("refresh worker interrupted", file=sys.stderr)
        raise SystemExit(130)
