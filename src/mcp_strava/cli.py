"""Strava CLI — thin dispatcher on top of mcp_strava modules."""

import json
import sys
from dataclasses import is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import mcp_strava.refresh.runtime as refresh_runtime
from mcp_strava.adapters.duckdb.connection import MirrorConn, MirrorDbLocked
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.strava.client import StravaClient
from mcp_strava.adapters.strava.clock import SystemClock, SystemSleeper
from mcp_strava.application.freshness import get_freshness_service
from mcp_strava.application.metric_services import get_workout_detail_service, list_workouts_service
from mcp_strava.application.mirror_coverage import get_mirror_coverage_service
from mcp_strava.application.product_facts import get_daily_brief_facts_service, get_weekly_digest_facts_service
from mcp_strava.deploy.preflight import validate_runtime_db
from mcp_strava.maintenance.compact import compact_database
from mcp_strava.refresh import RefreshPolicy, RefreshSkipped
from mcp_strava.refresh.bootstrap import build_refresh_collaborators
from mcp_strava.settings import get_settings
from mcp_strava.sync import (
    backfill_activities,
)
from mcp_strava.types import dc_to_dict

backfill_stream_channels = refresh_runtime.run_stream_channel_catchup


class _DryRunStravaTransport:
    def fetch(self, path: str):
        raise RuntimeError(f"Dry-run stream backfill must not call Strava API: {path}")


# ═══════════════════════════════════════════════════════════════
#  CLI Commands
# ═══════════════════════════════════════════════════════════════


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
            body = ["| " + " | ".join(str(r[i]) for i in range(len(cols))) + " |" for r in rows]
            print("\n".join([header, sep] + body))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)


def cmd_refresh(args):
    token = StravaClient().refresh_token()
    print(json.dumps({"status": "ok", "token": token[:10] + "..."}))


def cmd_report(args):
    """Daily training report product command."""
    json_output = _pop_json_flag(args)
    if not args or args[0] != "daily":
        _usage_error("Usage: python -m mcp_strava report daily [--json]")
    envelope = get_daily_brief_facts_service(as_of_day=_today_day())
    _print_product_envelope(envelope, json_output=json_output, title="Daily Report", renderer=_render_bundle_report)


def cmd_weekly(args):
    """Weekly summary product command."""
    json_output = _pop_json_flag(args)
    if args:
        _usage_error("Usage: python -m mcp_strava weekly [--json]")
    envelope = get_weekly_digest_facts_service(as_of_day=_today_day())
    _print_product_envelope(envelope, json_output=json_output, title="Weekly Summary", renderer=_render_bundle_report)


def cmd_workouts(args):
    """Recent workouts product command."""
    json_output = _pop_json_flag(args)
    if not args or args[0] != "recent":
        _usage_error(
            "Usage: python -m mcp_strava workouts recent [--limit N] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] [--sport SPORT] [--json]"
        )
    options = _parse_workouts_recent_options(args[1:])
    envelope = list_workouts_service(**options)
    _print_product_envelope(
        envelope, json_output=json_output, title="Recent Workouts", renderer=_render_recent_workouts
    )


def cmd_workout(args):
    """Single workout analytics product command."""
    json_output = _pop_json_flag(args)
    if len(args) < 2 or args[0] != "analyze":
        _usage_error("Usage: python -m mcp_strava workout analyze <id|latest> [--json]")
    envelope = get_workout_detail_service(args[1])
    _print_product_envelope(
        envelope, json_output=json_output, title="Workout Analytics", renderer=_render_workout_analytics
    )


def cmd_freshness(args):
    """Freshness product command."""
    json_output = _pop_json_flag(args)
    if args:
        _usage_error("Usage: python -m mcp_strava freshness [--json]")
    envelope = get_freshness_service()
    _print_product_envelope(envelope, json_output=json_output, title="Freshness", renderer=_render_freshness)


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
    rows: list[dict[str, Any]] = [dict(zip(_log_cols, row, strict=False)) for row in raw_rows]
    if not rows:
        print("No sync log entries yet.")
        return
    for r in rows:
        ok = "✓" if r["status"] == "ok" else "✗"
        parts = [f"{str(r['timestamp'])[:19]} {ok}"]
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
            parts.append(str(r["error"])[:80])
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
        return dc_to_dict(result)
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


def _pop_json_flag(args):
    if "--json" not in args:
        return False
    args.remove("--json")
    return True


def _today_day() -> str:
    return datetime.now().date().isoformat()


def _parse_workouts_recent_options(args):
    options = {
        "limit": 20,
        "start_date": None,
        "end_date": None,
        "sport": None,
    }
    if len(args) == 1 and args[0].isdigit():
        options["limit"] = int(args[0])
        return options

    index = 0
    while index < len(args):
        token = args[index]
        if token == "--limit":
            if index + 1 >= len(args) or not args[index + 1].isdigit():
                _usage_error("Usage: --limit N")
            options["limit"] = int(args[index + 1])
            index += 2
            continue
        if token in {"--start-date", "--end-date", "--sport"}:
            if index + 1 >= len(args):
                _usage_error("Usage: --start-date YYYY-MM-DD --end-date YYYY-MM-DD --sport SPORT")
            key = token[2:].replace("-", "_")
            options[key] = args[index + 1]
            index += 2
            continue
        _usage_error(
            "Usage: python -m mcp_strava workouts recent [--limit N] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] [--sport SPORT] [--json]"
        )
    return options


def _usage_error(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _print_product_envelope(envelope, *, json_output, title, renderer):
    payload = dc_to_dict(envelope)
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(title)
    print("=" * len(title))
    renderer(payload.get("data"))
    _render_metadata(payload)


def _render_metadata(payload):
    freshness = payload.get("freshness") or {}
    completeness = payload.get("completeness") or {}
    warnings = payload.get("warnings") or []
    rationale = payload.get("rationale") or []

    print()
    print("Freshness")
    print(f"- state: {freshness.get('freshness_state')}")
    print(f"- checked_at: {freshness.get('checked_at')}")
    print(f"- last_successful_refresh_at: {freshness.get('last_successful_refresh_at')}")
    print(f"- refresh_age_seconds: {freshness.get('refresh_age_seconds')}")
    print(f"- last_activity_at: {freshness.get('last_activity_at')}")
    print(f"- last_activity_age_seconds: {freshness.get('last_activity_age_seconds')}")
    if freshness.get("refresh_requested"):
        print(f"- refresh_requested: {freshness.get('refresh_request_reason')}")

    print()
    print("Completeness")
    print(f"- status: {completeness.get('status')}")
    missing = completeness.get("missing") or []
    print(f"- missing: {', '.join(missing) if missing else 'none'}")

    print()
    print("Warnings")
    if warnings:
        for warning in warnings:
            print(f"- {warning.get('code')}: {warning.get('message')}")
    else:
        print("- none")

    if rationale:
        print()
        print("Rationale")
        for item in rationale:
            print(f"- {item.get('code')}: {item.get('message')}")


def _render_bundle_report(data):
    data = data or {}
    _render_bundle_sections(data)


def _render_recent_workouts(data):
    rows = data or []
    if not rows:
        print("No workouts.")
        return
    print("| date | id | sport | distance_km | moving_min | trimp | name |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        print(
            f"| {row.get('activity_date') or row.get('date')} | "
            f"{row.get('activity_id') or row.get('id')} | {row.get('sport_type')} | "
            f"{row.get('distance_km')} | {row.get('moving_time_min')} | "
            f"{row.get('trimp')} | {row.get('activity_name') or row.get('name')} |"
        )


def _render_workout_analytics(data):
    data = data or {}
    if not data:
        print("Workout not found.")
        return
    print(f"- id: {data.get('activity_id') or data.get('id')}")
    print(f"- date: {data.get('activity_date') or data.get('date')}")
    print(f"- name: {data.get('activity_name') or data.get('name')}")
    print(f"- sport_type: {data.get('sport_type')}")
    print(f"- distance_km: {data.get('distance_km')}")
    print(f"- moving_time_min: {data.get('moving_time_min')}")
    print(f"- trimp: {data.get('trimp')}")
    print(f"- avg_hr: {data.get('avg_hr')}")
    print(f"- max_hr: {data.get('max_hr')}")
    print(f"- cardiac_drift_pct: {data.get('cardiac_drift_pct') or data.get('cardiac_drift')}")
    if data.get("kudos_count") is not None:
        print(f"- kudos_count: {data.get('kudos_count')}")
    if data.get("kudos_names"):
        print(f"- kudos_names: {', '.join(data.get('kudos_names') or [])}")
    if data.get("gear_id") or data.get("gear_name"):
        print(f"- gear: {data.get('gear_name') or data.get('gear_id')}")


def _render_freshness(data):
    data = data or {}
    if data:
        for key, value in data.items():
            print(f"- {key}: {value}")
    else:
        print("- no additional freshness data")


def _render_bundle_sections(data):
    print(f"Bundle: {data.get('bundle_id')}")
    if data.get("as_of_day"):
        print(f"As of: {data.get('as_of_day')}")
    sections = data.get("sections") or {}
    if not isinstance(sections, dict) or not sections:
        print("- no sections")
        return
    for section_id, section in sections.items():
        print()
        print(str(section_id).replace("_", " ").title())
        if not isinstance(section, dict):
            print(f"- {section}")
            continue
        metrics = section.get("metrics") or section.get("facts")
        if isinstance(metrics, dict) and metrics:
            for key, value in list(metrics.items())[:8]:
                print(f"- {key}: {value}")
        rows = section.get("rows")
        if isinstance(rows, list) and rows:
            for row in rows[:5]:
                if isinstance(row, dict):
                    print(f"- {row.get('metric_id')}: {row.get('value', row.get('completeness_status'))}")
        items = section.get("items")
        if isinstance(items, list) and items:
            for item in items[:5]:
                if isinstance(item, dict):
                    label = item.get("activity_name") or item.get("activity_id") or item.get("gear_name") or item
                    print(f"- {label}")
        comparison = section.get("comparison")
        if isinstance(comparison, dict):
            global_metrics = (comparison.get("global") or {}).get("metrics") or {}
            for metric_id, payload in list(global_metrics.items())[:5]:
                if isinstance(payload, dict):
                    print(f"- {metric_id}: delta={payload.get('delta')} trend={payload.get('trend_direction')}")


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


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

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

COMMANDS = {
    "report": cmd_report,
    "weekly": cmd_weekly,
    "workouts": cmd_workouts,
    "workout": cmd_workout,
    "freshness": cmd_freshness,
    "admin": cmd_admin,
}


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python -m mcp_strava <command> [args]\nCommands: {', '.join(COMMANDS)}", file=sys.stderr)
        sys.exit(1)
    cmd = sys.argv[1]
    args = sys.argv[2:]
    if cmd in COMMANDS:
        COMMANDS[cmd](args)
    else:
        print(f"Unknown command: {cmd}\nCommands: {', '.join(COMMANDS)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
