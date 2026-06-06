"""Operational/admin CLI command handlers."""

from __future__ import annotations

import json
import sys
from dataclasses import is_dataclass
from pathlib import Path
from typing import cast

import duckdb

import mcp_strava.refresh.runtime as refresh_runtime
from mcp_strava.adapters.duckdb.connection import MirrorConn, MirrorDbLocked
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.strava.client import StravaClient
from mcp_strava.adapters.strava.clock import SystemClock, SystemSleeper
from mcp_strava.application.mirror_coverage import get_mirror_coverage_service
from mcp_strava.cli_common import _as_str, _pop_json_flag, _usage_error
from mcp_strava.deploy.preflight import validate_runtime_db
from mcp_strava.maintenance.compact import compact_database
from mcp_strava.refresh import RefreshPolicy, RefreshSkipped
from mcp_strava.refresh.bootstrap import build_refresh_collaborators
from mcp_strava.settings import get_settings
from mcp_strava.sync import backfill_activities
from mcp_strava.types import dc_to_dict

backfill_stream_channels = refresh_runtime.run_stream_channel_catchup


class _DryRunStravaTransport:
    def fetch(self, path: str):
        raise RuntimeError(f"Dry-run stream backfill must not call Strava API: {path}")


def cmd_sql(args):
    query = " ".join(args) if args else ""
    if not query:
        print('Usage: sql "SELECT ..."', file=sys.stderr)
        return
    with MirrorConn() as conn:
        try:
            cursor = conn.execute(query)
            rows = cursor.fetchall()
            if not rows:
                print("No results.")
                return
            cols = [item[0] for item in cursor.description]
            header = "| " + " | ".join(cols) + " |"
            sep = "| " + " | ".join(["---"] * len(cols)) + " |"
            body = ["| " + " | ".join(_as_str(cast(object, r[i])) for i in range(len(cols))) + " |" for r in rows]
            print("\n".join([header, sep, *body]))
        except duckdb.Error as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from None


def cmd_refresh(args):
    token = StravaClient().refresh_token()
    print(json.dumps({"status": "ok", "token": token[:10] + "..."}))


def cmd_strava_raw(args):
    """Raw Strava API call."""
    path = args[0] if args else "/athlete"
    data, _rate = StravaClient().api_request(path)
    print(json.dumps(data, indent=2))


def cmd_log(args):
    """Show recent sync log entries."""
    limit = int(args[0]) if args else 10
    _log_cols = (
        "timestamp",
        "status",
        "activities_seen",
        "activities_new",
        "streams_fetched",
        "details_fetched",
        "kudos_fetched",
        "api_calls",
        "error",
    )
    with MirrorConn() as conn:
        raw_rows = conn.execute(
            "SELECT timestamp, status, activities_seen, activities_new, "
            "streams_fetched, details_fetched, kudos_fetched, api_calls, error "
            "FROM sync_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    rows: list[dict[str, object]] = [dict(zip(_log_cols, row, strict=False)) for row in raw_rows]
    if not rows:
        print("No sync log entries yet.")
        return
    for r in rows:
        ok = "✓" if r["status"] == "ok" else "✗"
        parts = [f"{_as_str(r['timestamp'])[:19]} {ok}"]
        if r["activities_new"]:
            parts.append(f"+{r['activities_new']} new")
        if r["streams_fetched"]:
            parts.append(f"{r['streams_fetched']} streams")
        if r["details_fetched"]:
            parts.append(f"{r['details_fetched']} details")
        if r["kudos_fetched"]:
            parts.append(f"{r['kudos_fetched']} kudos")
        parts.append(f"{r['api_calls'] or 0} calls")
        if r["error"]:
            parts.append(_as_str(r["error"])[:80])
        print("  ".join(parts))


def _preflight_to_dict(report):
    return dict(report)


def cmd_db_preflight(args):
    _ = args
    report = validate_runtime_db(get_settings().database_path)
    print(json.dumps({"status": "ok", "preflight": _preflight_to_dict(report)}, indent=2, ensure_ascii=False))


def cmd_db_check(args):
    _ = args
    report = validate_runtime_db(get_settings().database_path)
    print(json.dumps({"status": "ok", "check": _preflight_to_dict(report)}, indent=2, ensure_ascii=False))


def cmd_mirror_coverage(args):
    json_output = _pop_json_flag(args)
    db_path: Path | None = None
    if "--db" in args:
        idx = args.index("--db")
        if idx + 1 >= len(args):
            _usage_error("Usage: python -m mcp_strava admin mirror-coverage [--db <path>] [--json]")
        db_path = Path(args[idx + 1])
        del args[idx : idx + 2]
    if args:
        _usage_error("Usage: python -m mcp_strava admin mirror-coverage [--db <path>] [--json]")

    if db_path is None:
        payload = get_mirror_coverage_service()
    else:
        with DuckDBRepository.from_path(db_path) as repo:
            payload = get_mirror_coverage_service(connection=repo.conn)

    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print("Mirror Coverage")
    for key in (
        "status",
        "activities_total",
        "activities_with_streams",
        "stream_points",
        "gps_points",
        "channels",
        "backfill_needed",
    ):
        print(f"- {key}: {payload.get(key)}")


_CATCHUP_USAGE = (
    "Usage: python -m mcp_strava admin catchup [--since YYYY-MM-DD] [--limit N] [--dry-run] [--db <path>] [--json]"
)


def _phase_payload(result) -> dict:
    """Normalise a refresh-runtime result (dataclass or dict) to a plain dict."""
    if isinstance(result, RefreshSkipped):
        return {"status": "skipped", "reason": result.reason}
    if is_dataclass(result):
        converted = dc_to_dict(result)
        return converted if isinstance(converted, dict) else {}
    return result


def _print_catchup(payload: dict, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print("Catchup")
    for section in ("activities", "stream_channels"):
        print(f"- {section}:")
        for key, value in payload[section].items():
            print(f"    {key}: {value}")
    print(f"- status: {payload['status']}")


def cmd_catchup(args):
    """Fetch missing activities, then missing stream channels, in one pass.

    Replaces the former ``backfill`` + ``backfill-streams`` admin commands.
    ``--dry-run`` previews the stream-channel phase only; activity backfill has
    no preview mode and is skipped under ``--dry-run``. ``--db`` is a dry-run
    fixture affordance and is rejected without ``--dry-run``.
    """
    json_output = _pop_json_flag(args)
    dry_run = False
    since = None
    limit = None
    db_path: Path | None = None

    index = 0
    while index < len(args):
        token = args[index]
        if token == "--dry-run":
            dry_run = True
            index += 1
            continue
        if token == "--since":
            if index + 1 >= len(args):
                _usage_error(_CATCHUP_USAGE)
            since = args[index + 1]
            index += 2
            continue
        if token == "--limit":
            if index + 1 >= len(args) or not args[index + 1].isdigit():
                _usage_error("Usage: --limit N")
            limit = int(args[index + 1])
            index += 2
            continue
        if token == "--db":
            if index + 1 >= len(args):
                _usage_error("Usage: --db <path>")
            db_path = Path(args[index + 1])
            index += 2
            continue
        _usage_error(_CATCHUP_USAGE)

    if db_path is not None and not dry_run:
        _usage_error("--db is only valid together with --dry-run")

    if dry_run:
        clock = SystemClock()
        sleeper = SystemSleeper()
        transport = _DryRunStravaTransport()
        refresh_policy = RefreshPolicy()
        conn_context = MirrorConn() if db_path is None else DuckDBRepository.from_path(db_path)
        with conn_context as conn:
            # MirrorConn yields a raw DuckDBConn (wrap it in a repository);
            # DuckDBRepository.from_path yields the repository itself.
            repo = conn if isinstance(conn, DuckDBRepository) else DuckDBRepository.from_connection(conn)
            stream_result = backfill_stream_channels(
                repo,
                transport,
                refresh_policy,
                clock,
                sleeper,
                since=since,
                limit=limit,
                dry_run=True,
            )
        payload = {
            "status": "ok",
            "dry_run": True,
            "activities": {"status": "skipped", "reason": "activity_backfill_has_no_dry_run"},
            "stream_channels": _phase_payload(stream_result),
        }
        _print_catchup(payload, json_output)
        return

    activities_result = backfill_activities(since=since)

    _settings, clock, sleeper, transport, refresh_policy = build_refresh_collaborators()
    with MirrorConn() as conn:
        repo = DuckDBRepository.from_connection(conn)
        stream_result = backfill_stream_channels(
            repo,
            transport,
            refresh_policy,
            clock,
            sleeper,
            since=since,
            limit=limit,
            dry_run=False,
        )

    activities_payload = _phase_payload(activities_result)
    stream_payload = _phase_payload(stream_result)
    statuses = {activities_payload.get("status"), stream_payload.get("status")}
    if "failed" in statuses:
        overall = "failed"
    elif statuses == {"skipped"}:
        overall = "skipped"
    else:
        overall = "ok"

    payload = {
        "status": overall,
        "activities": activities_payload,
        "stream_channels": stream_payload,
    }
    _print_catchup(payload, json_output)
    if overall == "failed":
        raise SystemExit(1)


def cmd_compact(args):
    """Reclaim disk space by rewriting the DuckDB mirror into a fresh file.

    Must run against a stopped owner (use ``just admin compact``); a pre-compact
    backup is kept unless ``--no-backup`` is given.
    """
    json_output = _pop_json_flag(args)
    backup = True
    for token in args:
        if token == "--no-backup":
            backup = False
            continue
        _usage_error("Usage: python -m mcp_strava admin compact [--no-backup] [--json]")

    result = compact_database(get_settings().database_path, backup=backup)

    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    print("Compact")
    for key, value in result.items():
        print(f"- {key}: {value}")


ADMIN_COMMANDS = {
    "mirror-coverage": cmd_mirror_coverage,
    "token-refresh": cmd_refresh,
    "catchup": cmd_catchup,
    "compact": cmd_compact,
    "sql": cmd_sql,
    "raw": cmd_strava_raw,
    "log": cmd_log,
    "db-preflight": cmd_db_preflight,
    "db-check": cmd_db_check,
}


def cmd_admin(args):
    if not args or args[0] in {"--help", "-h"}:
        print(
            "Usage: python -m mcp_strava admin <command> [args]\n"
            f"Admin commands: {', '.join(ADMIN_COMMANDS)}\n"
            "catchup: fetch missing activities + stream channels in one pass",
            file=sys.stderr,
        )
        raise SystemExit(1)
    command = args[0]
    handler = ADMIN_COMMANDS.get(command)
    if handler is None:
        print(
            f"Unknown admin command: {command}\nAdmin commands: {', '.join(ADMIN_COMMANDS)}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        handler(args[1:])
    except MirrorDbLocked as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "hint: the running MCP container holds an exclusive DuckDB lock.\n"
            "      stop the owner before running admin commands, e.g.:\n"
            "        just admin " + command + " " + " ".join(args[1:]) + "\n"
            "      (stops the container, runs the command, restarts it)",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
