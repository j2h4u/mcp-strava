"""Strava CLI — thin dispatcher on top of strava_lib."""

import sys
import json
from datetime import datetime, timedelta

from strava_lib.constants import Config
from strava_lib.db import (
    DbConn, refresh_token,
    api_request, get_daily_trimp_history
)
from strava_lib.training import calc_banister, calc_weekly_plan, forward_simulate
from strava_lib.analytics import weekly_digest
from strava_lib.report import daily_report
from strava_lib.types import (
    parse_strava_activity, parse_strava_athlete, dc_to_dict
)
from strava_lib.sync import sync_activities, backfill_activities
from strava_lib.trends import compute_trends


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
            from strava_lib.db import DbConn
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
        backfill_activities()
    except Exception as e:
        import traceback
        print(f"Backfill failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
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
    """Daily training report."""
    report = daily_report()
    print(json.dumps(dc_to_dict(report), indent=2, ensure_ascii=False))


def cmd_weekly(args):
    """Weekly digest."""
    with DbConn() as conn:
        result = weekly_digest(conn)
    if result is None:
        print('{"error": "no data"}')
        return
    print(json.dumps(dc_to_dict(result), indent=2, ensure_ascii=False))


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


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

COMMANDS = {
    'activities': cmd_activities,
    'gear': cmd_gear,
    'stats': cmd_stats,
    'sql': cmd_sql,
    'refresh': cmd_refresh,
    'sync': cmd_sync,
    'backfill': cmd_backfill,
    'backtest': cmd_backtest,
    'trend': cmd_trend,
    'report': cmd_report,
    'weekly': cmd_weekly,
    'raw': cmd_strava_raw,
    'log': cmd_log,
    'kudos': cmd_kudos,
}


def main():
    if len(sys.argv) < 2:
        print(f"Usage: cli.py <command> [args]\nCommands: {', '.join(COMMANDS)}", file=sys.stderr)
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
