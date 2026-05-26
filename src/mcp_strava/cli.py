"""Strava CLI — thin dispatcher on top of mcp_strava modules."""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

from mcp_strava.constants import Config
from mcp_strava.adapters.duckdb.migrations import (
    CANONICAL_DUCKDB_RUNTIME_PATH,
    DuckDBMigrationError,
    run_duckdb_cutover,
)
from mcp_strava.adapters.sqlite.migrations import run_migrations, run_preflight
from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.application.freshness import get_freshness_service
from mcp_strava.application.mirror_coverage import get_mirror_coverage_service
from mcp_strava.application.reports import get_daily_report_service, get_weekly_summary_service
from mcp_strava.application.workouts import get_recent_workouts_service, get_workout_analytics_service
import mcp_strava.refresh.runtime as refresh_runtime
from mcp_strava.db import (
    DbConn, refresh_token,
    api_request, get_daily_trimp_history
)
from mcp_strava.refresh import RefreshPolicy, RefreshSkipped
from mcp_strava.training import calc_banister, calc_weekly_plan, forward_simulate
from mcp_strava.analytics import weekly_digest
from mcp_strava.report import daily_report
from mcp_strava.types import (
    parse_strava_activity, parse_strava_athlete, dc_to_dict
)
from mcp_strava.refresh.bootstrap import (
    RealClock,
    RealSleeper,
    build_refresh_collaborators,
    ensure_refresh_schema,
    record_refresh_misconfigured,
)
from mcp_strava.sync import (
    backfill_activities,
    sync_activities,
)
from mcp_strava.trends import compute_trends
from mcp_strava.settings import get_settings

backfill_stream_channels = refresh_runtime.run_backfill_stream_channels


class _DryRunStravaTransport:
    def fetch(self, path: str):
        raise RuntimeError(f"Dry-run stream backfill must not call Strava API: {path}")

# ═══════════════════════════════════════════════════════════════
#  CLI Commands
# ═══════════════════════════════════════════════════════════════

def cmd_activities(args):
    limit = int(args[0]) if args and args[0].isdigit() else 15
    with DbConn() as conn:
        rows = conn.execute("""
            SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
                   total_elevation_gain, summary_json
            FROM activities ORDER BY date DESC LIMIT ?
        """, (limit,)).fetchall()
        result = []
        for row in rows:
            raw_summary = json.loads(row['summary_json']) if row['summary_json'] else {}
            summary = parse_strava_activity(raw_summary) if raw_summary else None
            trimp_row = conn.execute(f"SELECT {Config.SQL.TRIMP} FROM streams WHERE activity_id=?", (row['id'],)).fetchone()
            trimp = round(trimp_row['trimp'], 1) if trimp_row and trimp_row['trimp'] else 0
            act = {
                'id': row['id'], 'date': row['date'][:10], 'name': row['name'],
                'sport_type': row['sport_type'],
                'distance_km': round(row['distance']/1000, 2),
                'moving_time_min': round(row['moving_time']/60, 1),
                'trimp': trimp,
            }
            if summary:
                act['avg_hr'] = summary.average_heartrate
                act['max_hr'] = int(round(summary.max_heartrate)) if summary.max_heartrate else None
            result.append(act)
        by_type = {}
        for a in result:
            by_type.setdefault(a['sport_type'], []).append(a)
        weekly = [a for a in result if a['date'] >= (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')]
        print(json.dumps({
            'activities': result, 'by_type': by_type,
            'total_weekly_trimp': round(sum(a['trimp'] for a in weekly), 1),
            'all_types': list(by_type.keys()),
        }, indent=2, ensure_ascii=False))


def cmd_gear(args):
    data, _rate = api_request('/athlete')
    if isinstance(data, dict) and data.get('_rate_limited'):
        print('{"error": "rate limited"}')
        return
    athlete = parse_strava_athlete(data)
    result = []
    for s in athlete.shoes:
        km = round(s.distance/1000, 1)
        result.append({'id': s.id, 'name': s.name, 'distance_km': km, 'primary': s.primary})
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_stats(args):
    data, _rate = api_request('/athlete/stats')
    print(json.dumps(data, indent=2))


def cmd_sql(args):
    query = ' '.join(args) if args else ''
    if not query:
        print("Usage: sql \"SELECT ...\"", file=sys.stderr)
        return
    with DbConn() as conn:
        try:
            rows = conn.execute(query).fetchall()
            if not rows:
                print("No results.")
                return
            cols = rows[0].keys()
            header = "| " + " | ".join(cols) + " |"
            sep = "| " + " | ".join(["---"]*len(cols)) + " |"
            body = ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
            print("\n".join([header, sep] + body))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)


def cmd_refresh(args):
    token = refresh_token()
    print(json.dumps({"status": "ok", "token": token[:10]+"..."}))


def cmd_sync(args):
    full = '--full' in args
    try:
        sync_activities(quick=not full)
    except Exception as e:
        import traceback
        print(f"Sync failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        # Try to log the failure — don't crash if DB is unavailable
        try:
            from mcp_strava.db import DbConn
            from datetime import datetime
            with DbConn() as conn:
                conn.execute(
                    "INSERT INTO sync_log (timestamp, status, error) VALUES (?, 'error', ?)",
                    (datetime.now().isoformat(), str(e)[:500]))
                conn.commit()
        except Exception:
            pass
        raise SystemExit(1)


def cmd_backfill(args):
    try:
        since = args[0] if args else None
        backfill_activities(since=since)
    except Exception as e:
        import traceback
        print(f"Backfill failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1)


def cmd_db_refresh(args):
    if "--help" in args or "-h" in args:
        print(
            "Usage: python -m mcp_strava admin mirror-refresh [--force]\n\n"
            "--force  Run a mid-day refresh; bypasses daily idempotency but honours lease/backoff."
        )
        return

    unknown = [arg for arg in args if arg != "--force"]
    if unknown:
        print(f"Unknown db-refresh option: {unknown[0]}", file=sys.stderr)
        raise SystemExit(1)

    force = "--force" in args
    settings = get_settings()
    ensure_refresh_schema(run_preflight(settings.database_path))
    try:
        settings, clock, sleeper, transport, refresh_policy = build_refresh_collaborators()
    except RuntimeError:
        record_refresh_misconfigured(settings)
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "refresh_misconfigured",
                    "checkpoint_stage": None,
                    "forced": force,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        raise SystemExit(1)
    with DbConn() as conn:
        repo = SQLiteRepository.from_connection(conn)
        result = refresh_runtime.run_once(
            repo,
            transport,
            refresh_policy,
            clock,
            sleeper,
            force=force,
            mode="daily",
        )

    if isinstance(result, RefreshSkipped):
        payload = {
            "status": "skipped",
            "reason": result.reason,
            "checkpoint_stage": None,
            "forced": force,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        raise SystemExit(2)

    payload = {
        "status": result.status,
        "reason": result.reason,
        "checkpoint_stage": result.checkpoint_stage,
        "forced": force,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if result.status == "failed":
        raise SystemExit(1)


def cmd_backtest(args):
    """Backtest the weekly planner against historical data."""
    weeks = int(args[0]) if args else 12
    with DbConn() as conn:
        daily_trimp = get_daily_trimp_history(conn)
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')

    alpha_fatigue = Config.Model.Banister.ALPHA_FATIGUE
    alpha_fitness = Config.Model.Banister.ALPHA_FITNESS
    from datetime import date

    results = []
    for w in range(1, weeks + 1):
        monday = now - timedelta(weeks=w)
        monday_str = monday.strftime('%Y-%m-%d')
        saturday = monday + timedelta(days=5)
        saturday_str = saturday.strftime('%Y-%m-%d')

        monday_date = date(monday.year, monday.month, monday.day)
        days = [(monday + timedelta(days=i)) for i in range(7)]
        day_strs = [d.strftime('%Y-%m-%d') for d in days]

        # Trimps for this week's Mon-Fri
        past_trimps = [daily_trimp.get(ds, 0) for ds in day_strs[:5]]
        # Actual Saturday trimp
        sat_trimp = daily_trimp.get(saturday_str, 0)

        # Baseline fitness/fatigue on Monday
        ban_monday = calc_banister(daily_trimp, monday_str)
        if not ban_monday:
            continue
        base_f = ban_monday.fitness
        base_fa = ban_monday.fatigue

        # Simulate what actually happened Mon-Fri
        actual_proj = forward_simulate(base_f, base_fa, past_trimps,
                                       monday_date, alpha_fitness, alpha_fatigue)
        actual_sat_form = actual_proj[-1].form if actual_proj else 0

        # What the planner would recommend
        plan = calc_weekly_plan(daily_trimp, monday_str, load_bonus=0)
        plan_trimps = [d.trimp for d in plan.plan_days] if plan.plan_days else [0]*5
        plan_proj = forward_simulate(base_f, base_fa, plan_trimps[:5],
                                     monday_date, alpha_fitness, alpha_fatigue)
        plan_sat_form = plan_proj[-1].form if plan_proj else 0

        results.append({
            'week': monday_str,
            'actual_saturday_form': round(actual_sat_form, 1),
            'planned_saturday_form': round(plan_sat_form, 1),
            'actual_trimp': round(sum(past_trimps), 1),
            'planned_trimp': round(sum(plan_trimps[:5]), 1),
            'saturday_trimp': round(sat_trimp, 1),
        })

    if not results:
        print("Not enough historical data for backtest.")
        return

    total = len(results)
    planned_in_target = sum(1 for r in results if -5 <= r['planned_saturday_form'] <= 15)
    actual_in_target = sum(1 for r in results if -5 <= r['actual_saturday_form'] <= 15)
    would_be_better = sum(1 for r in results if r['planned_saturday_form'] > r['actual_saturday_form'])
    plan_errors = [abs(r['planned_saturday_form'] - r['actual_saturday_form']) for r in results]
    plan_error = round(sum(plan_errors) / len(plan_errors), 1) if plan_errors else 0

    composite_score = round(
        (planned_in_target / total * 40) +
        (would_be_better / total * 30) +
        (max(0, 30 - plan_error * 2)),
        1
    )

    print(json.dumps({
        'composite_score': composite_score,
        'total_weeks': total,
        'planned_in_target': f"{planned_in_target}/{total}",
        'actual_in_target': f"{actual_in_target}/{total}",
        'would_be_better': f"{would_be_better}/{total}",
        'avg_error': plan_error,
        'results': results,
    }, indent=2, ensure_ascii=False))


def cmd_trend(args):
    weeks = int(args[0]) if args else 52
    compute_trends(weeks)


def cmd_report(args):
    """Daily training report product command."""
    json_output = _pop_json_flag(args)
    if not args or args[0] != "daily":
        _usage_error("Usage: python -m mcp_strava report daily [--json]")
    envelope = get_daily_report_service()
    _print_product_envelope(envelope, json_output=json_output, title="Daily Report", renderer=_render_daily_report)


def cmd_weekly(args):
    """Weekly summary product command."""
    json_output = _pop_json_flag(args)
    envelope = get_weekly_summary_service()
    _print_product_envelope(envelope, json_output=json_output, title="Weekly Summary", renderer=_render_weekly_summary)


def cmd_workouts(args):
    """Recent workouts product command."""
    json_output = _pop_json_flag(args)
    if not args or args[0] != "recent":
        _usage_error("Usage: python -m mcp_strava workouts recent [--limit N] [--json]")
    limit = _parse_limit(args[1:], default=15)
    envelope = get_recent_workouts_service(limit=limit)
    _print_product_envelope(envelope, json_output=json_output, title="Recent Workouts", renderer=_render_recent_workouts)


def cmd_workout(args):
    """Single workout analytics product command."""
    json_output = _pop_json_flag(args)
    if len(args) < 2 or args[0] != "analyze":
        _usage_error("Usage: python -m mcp_strava workout analyze <id|latest> [--json]")
    envelope = get_workout_analytics_service(args[1])
    _print_product_envelope(envelope, json_output=json_output, title="Workout Analytics", renderer=_render_workout_analytics)


def cmd_freshness(args):
    """Freshness product command."""
    json_output = _pop_json_flag(args)
    if args:
        _usage_error("Usage: python -m mcp_strava freshness [--json]")
    envelope = get_freshness_service()
    _print_product_envelope(envelope, json_output=json_output, title="Freshness", renderer=_render_freshness)


def cmd_strava_raw(args):
    """Raw Strava API call."""
    path = args[0] if args else '/athlete'
    data, _rate = api_request(path)
    print(json.dumps(data, indent=2))


def cmd_log(args):
    """Show recent sync log entries."""
    limit = int(args[0]) if args else 10
    with DbConn() as conn:
        rows = conn.execute(
            "SELECT timestamp, status, activities_seen, activities_new, "
            "streams_fetched, details_fetched, kudos_fetched, api_calls, error "
            "FROM sync_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    if not rows:
        print("No sync log entries yet.")
        return
    for r in rows:
        ok = "✓" if r['status'] == 'ok' else "✗"
        parts = [f"{r['timestamp'][:19]} {ok}"]
        if r['activities_new']:
            parts.append(f"+{r['activities_new']} new")
        if r['streams_fetched']:
            parts.append(f"{r['streams_fetched']} streams")
        if r['details_fetched']:
            parts.append(f"{r['details_fetched']} details")
        if r['kudos_fetched']:
            parts.append(f"{r['kudos_fetched']} kudos")
        parts.append(f"{r['api_calls'] or 0} calls")
        if r['error']:
            parts.append(r['error'][:80])
        print("  ".join(parts))


def cmd_kudos(args):
    """Show recent kudos (likes) grouped by activity."""
    days = int(args[0]) if args else 30
    with DbConn() as conn:
        rows = conn.execute("""
            SELECT a.date, a.name, a.sport_type,
                   CAST(json_extract(a.summary_json, '$.kudos_count') AS INTEGER) as total,
                   k.firstname, k.lastname
            FROM kudos k
            JOIN activities a ON a.id = k.activity_id
            WHERE a.date >= date('now', ?)
            ORDER BY a.date DESC, k.lastname
        """, (f'-{days} days',)).fetchall()
    if not rows:
        print(f"No kudos synced in last {days} days.")
        return
    cur_act = None
    for r in rows:
        if r['date'] != cur_act:
            cur_act = r['date']
            print(f"\n{r['date']}  {r['name']} ({r['sport_type']})  — {r['total']} kudos")
        print(f"  {r['firstname']} {r['lastname']}")


def _preflight_to_dict(report):
    return {
        "path": str(report.path),
        "user_version": report.user_version,
        "row_counts": report.row_counts,
        "integrity_result": report.integrity_result,
    }


def cmd_db_preflight(args):
    _ = args
    report = run_preflight(get_settings().database_path)
    print(json.dumps({"status": "ok", "preflight": _preflight_to_dict(report)}, indent=2, ensure_ascii=False))


def cmd_db_check(args):
    _ = args
    report = run_preflight(get_settings().database_path)
    print(json.dumps({"status": "ok", "check": _preflight_to_dict(report)}, indent=2, ensure_ascii=False))


def cmd_db_migrate(args):
    _ = args
    db_path = Path(get_settings().database_path)
    backups_dir = db_path.parent / "backups"
    before = set(backups_dir.glob("strava-*.db")) if backups_dir.exists() else set()
    post = run_migrations(db_path)
    after = set(backups_dir.glob("strava-*.db")) if backups_dir.exists() else set()
    new_files = sorted(after - before, key=lambda p: p.name)
    backup_path = new_files[-1] if new_files else (sorted(after, key=lambda p: p.name)[-1] if after else None)

    backup_status = None
    if backup_path is not None:
        st = backup_path.stat()
        backup_status = {
            "path": str(backup_path),
            "openable": True,
            "size_bytes": st.st_size,
            "mode_octal": oct(st.st_mode & 0o777),
        }

    print(
        json.dumps(
            {
                "status": "ok",
                "migration": _preflight_to_dict(post),
                "backup": backup_status,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def _duckdb_cutover_usage() -> str:
    return (
        "Usage: python -m mcp_strava admin duckdb-cutover "
        "--source-sqlite <path> --target-duckdb <path> --backup-dir <path> "
        "[--apply --confirm-live-cutover] [--json]\n\n"
        f"Canonical Docker/runtime DuckDB target: {CANONICAL_DUCKDB_RUNTIME_PATH}\n"
        "This is a local admin storage cutover command. It creates a pinned SQLite backup, "
        "migrates from that backup into DuckDB, verifies parity, and reports rollback metadata."
    )


def _pop_required_path_option(args: list[str], option: str) -> Path:
    if option not in args:
        _usage_error(_duckdb_cutover_usage())
    idx = args.index(option)
    if idx + 1 >= len(args):
        _usage_error(_duckdb_cutover_usage())
    value = Path(args[idx + 1])
    del args[idx : idx + 2]
    return value


def _live_looking_duckdb_target(path: Path) -> bool:
    rendered = str(path)
    return rendered == CANONICAL_DUCKDB_RUNTIME_PATH or rendered.startswith("/runtime/")


def _cutover_report_to_dict(report) -> dict[str, object]:
    if hasattr(report, "to_dict"):
        return report.to_dict()
    return {
        "backup_path": str(report.backup_path),
        "duckdb_path": str(report.duckdb_path),
        "parity_ok": bool(report.parity_ok),
        "cast_failures": list(report.cast_failures),
        "rollback": dict(report.rollback),
    }


def cmd_duckdb_cutover(args):
    if "--help" in args or "-h" in args:
        print(_duckdb_cutover_usage())
        return

    json_output = _pop_json_flag(args)
    apply = "--apply" in args
    if apply:
        args.remove("--apply")
    confirm_live = "--confirm-live-cutover" in args
    if confirm_live:
        args.remove("--confirm-live-cutover")

    source_path = _pop_required_path_option(args, "--source-sqlite")
    target_path = _pop_required_path_option(args, "--target-duckdb")
    backup_dir = _pop_required_path_option(args, "--backup-dir")
    if args:
        _usage_error(_duckdb_cutover_usage())

    if _live_looking_duckdb_target(target_path) and (not apply or not confirm_live):
        print(
            "Refusing live-looking DuckDB cutover target without --apply --confirm-live-cutover.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if not apply:
        payload = {
            "backup_path": None,
            "duckdb_path": str(target_path),
            "parity_ok": False,
            "cast_failures": [],
            "rollback": {
                "sqlite_backup_path": None,
                "duckdb_path": str(target_path),
                "instructions": [
                    "rerun with --apply after stopping writers and confirming the target path",
                ],
            },
            "status": "dry_run",
        }
    else:
        try:
            report = run_duckdb_cutover(
                source_sqlite_path=source_path,
                target_duckdb_path=target_path,
                backup_dir=backup_dir,
                now=None,
                owner="cli-admin",
            )
        except DuckDBMigrationError as exc:
            if exc.report is not None:
                payload = _cutover_report_to_dict(exc.report)
                payload["status"] = "failed"
                payload["error"] = str(exc)
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(json.dumps({"status": "failed", "error": str(exc)}, indent=2, ensure_ascii=False))
            raise SystemExit(1) from exc
        payload = _cutover_report_to_dict(report)

    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print("DuckDB Cutover")
    for key in ("backup_path", "duckdb_path", "parity_ok", "cast_failures", "rollback"):
        print(f"- {key}: {payload.get(key)}")


def cmd_mirror_coverage(args):
    json_output = _pop_json_flag(args)
    db_path: str | None = None
    if "--db" in args:
        idx = args.index("--db")
        if idx + 1 >= len(args):
            _usage_error("Usage: python -m mcp_strava admin mirror-coverage [--db <path>] [--json]")
        db_path = args[idx + 1]
        del args[idx : idx + 2]
    if args:
        _usage_error("Usage: python -m mcp_strava admin mirror-coverage [--db <path>] [--json]")

    if db_path is None:
        payload = get_mirror_coverage_service()
    else:
        with SQLiteRepository.from_path(Path(db_path)) as repo:
            payload = get_mirror_coverage_service(connection=repo.conn)

    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print("Mirror Coverage")
    for key in ("status", "activities_total", "activities_with_streams", "stream_points", "gps_points", "channels", "backfill_needed"):
        print(f"- {key}: {payload.get(key)}")


def cmd_backfill_streams(args):
    json_output = _pop_json_flag(args)
    dry_run = False
    since = None
    limit = None
    db_path: str | None = None

    index = 0
    while index < len(args):
        token = args[index]
        if token == "--dry-run":
            dry_run = True
            index += 1
            continue
        if token == "--since":
            if index + 1 >= len(args):
                _usage_error("Usage: python -m mcp_strava admin backfill-streams [--dry-run] [--since YYYY-MM-DD] [--limit N] [--db <path>] [--json]")
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
            db_path = args[index + 1]
            index += 2
            continue
        _usage_error("Usage: python -m mcp_strava admin backfill-streams [--dry-run] [--since YYYY-MM-DD] [--limit N] [--db <path>] [--json]")

    if dry_run:
        clock = RealClock()
        sleeper = RealSleeper()
        transport = _DryRunStravaTransport()
        refresh_policy = RefreshPolicy()
    else:
        _settings, clock, sleeper, transport, refresh_policy = build_refresh_collaborators()
    if db_path is None:
        conn_context = DbConn()
    else:
        conn_context = SQLiteRepository.from_path(Path(db_path))
    with conn_context as conn:
        repo = SQLiteRepository.from_connection(conn) if db_path is None else conn
        result = backfill_stream_channels(
            repo,
            transport,
            refresh_policy,
            clock,
            sleeper,
            since=since,
            limit=limit,
            dry_run=dry_run,
        )
    if isinstance(result, RefreshSkipped):
        payload = {"status": "skipped", "reason": result.reason, "mode": "backfill_stream_channels"}
    else:
        payload = result
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("Backfill Streams")
        for key, value in payload.items():
            print(f"- {key}: {value}")


def _pop_json_flag(args):
    if "--json" not in args:
        return False
    args.remove("--json")
    return True


def _parse_limit(args, default):
    if not args:
        return default
    if len(args) == 1 and args[0].isdigit():
        return int(args[0])
    if len(args) == 2 and args[0] == "--limit" and args[1].isdigit():
        return int(args[1])
    _usage_error("Usage: --limit N")


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


def _render_daily_report(data):
    data = data or {}
    print("Status")
    print(f"- today: {data.get('today')}")
    banister = data.get("banister") or {}
    if banister:
        print(f"- form: {banister.get('form')}")
    recommendation = data.get("recommendation") or {}
    print()
    print("Recommendation")
    if recommendation:
        action = recommendation.get("action") or recommendation.get("message") or recommendation.get("summary")
        confidence = recommendation.get("confidence")
        print(f"- action: {action}")
        if confidence:
            print(f"- confidence: {confidence}")
    else:
        print("- none")
    print()
    print("Activities")
    activities = data.get("yesterday_activities") or data.get("activities_14d") or []
    if not activities:
        print("- none")
    for item in activities[:10]:
        print(f"- {item.get('date')} {item.get('name')} {item.get('sport_type')} trimp={item.get('trimp')}")


def _render_weekly_summary(data):
    data = data or {}
    print("Period")
    for key, value in (data.get("period") or {}).items():
        print(f"- {key}: {value}")
    print()
    print("Current State")
    current = data.get("current_state") or {}
    if current:
        for key, value in current.items():
            print(f"- {key}: {value}")
    else:
        print("- none")
    print()
    print("Trends")
    trends = data.get("trends") or {}
    if trends:
        for key, value in trends.items():
            print(f"- {key}: {value}")
    else:
        print("- none")


def _render_recent_workouts(data):
    rows = data or []
    if not rows:
        print("No workouts.")
        return
    print("| date | id | sport | distance_km | moving_min | trimp | name |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        print(
            f"| {row.get('date')} | {row.get('id')} | {row.get('sport_type')} | "
            f"{row.get('distance_km')} | {row.get('moving_time_min')} | "
            f"{row.get('trimp')} | {row.get('name')} |"
        )


def _render_workout_analytics(data):
    data = data or {}
    if not data:
        print("Workout not found.")
        return
    print(f"- id: {data.get('id')}")
    print(f"- date: {data.get('date')}")
    print(f"- name: {data.get('name')}")
    print(f"- sport_type: {data.get('sport_type')}")
    print(f"- distance_km: {data.get('distance_km')}")
    print(f"- moving_time_min: {data.get('moving_time_min')}")
    print(f"- trimp: {data.get('trimp')}")
    print(f"- avg_hr: {data.get('avg_hr')}")
    print(f"- max_hr: {data.get('max_hr')}")
    print(f"- cardiac_drift: {data.get('cardiac_drift')}")


def _render_freshness(data):
    data = data or {}
    if data:
        for key, value in data.items():
            print(f"- {key}: {value}")
    else:
        print("- no additional freshness data")


def cmd_admin(args):
    if not args or args[0] in {"--help", "-h"}:
        print(
            "Usage: python -m mcp_strava admin <command> [args]\n"
            f"Admin commands: {', '.join(ADMIN_COMMANDS)}\n"
            "backfill: legacy full streams/details backfill\n"
            "backfill-streams: phase-6 stream channel/metadata backfill",
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
    handler(args[1:])


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

ADMIN_COMMANDS = {
    "mirror-refresh": cmd_db_refresh,
    "mirror-coverage": cmd_mirror_coverage,
    "token-refresh": cmd_refresh,
    "duckdb-cutover": cmd_duckdb_cutover,
    "backfill": cmd_backfill,
    "backfill-streams": cmd_backfill_streams,
    "sql": cmd_sql,
    "raw": cmd_strava_raw,
    "log": cmd_log,
    "db-preflight": cmd_db_preflight,
    "db-check": cmd_db_check,
    "db-migrate": cmd_db_migrate,
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


if __name__ == '__main__':
    main()
