"""Training quality metrics over time — form, TiZ, velocity, crash rate."""

import json
from datetime import datetime, timedelta
from collections import defaultdict

from mcp_strava.constants import Config
from mcp_strava.db import DbConn, get_daily_trimp_history
from mcp_strava.training import calc_banister_series


def compute_trends(weeks=52):
    """Compute multi-week training quality trends.

    Returns JSON with: weeks (list of weekly metrics), avg_tiz, crash_rate.
    """
    with DbConn() as conn:
        daily_trimp = get_daily_trimp_history(conn)

        if not daily_trimp:
            print("No activity data available.")
            return

    # Use shared Banister series from training.py (single source of truth)
    banister_series = calc_banister_series(daily_trimp)
    daily_form = {d['date']: d for d in banister_series}

    # Aggregate by week
    weeks_data = defaultdict(lambda: {'forms': [], 'trimps': [], 'count': 0})

    sorted_dates = sorted(daily_form.keys())
    for ds in sorted_dates:
        dt = datetime.strptime(ds, '%Y-%m-%d')
        week_key = dt.strftime('%Y-W%U')
        weeks_data[week_key]['forms'].append(daily_form[ds]['form'])
        weeks_data[week_key]['trimps'].append(daily_form[ds]['trimp'])
        weeks_data[week_key]['count'] += 1

    # Calculate weekly metrics
    week_list = []
    prev_fitness = None
    for wk in sorted(weeks_data.keys()):
        wd = weeks_data[wk]
        if wd['count'] < 3:
            continue
        avg_form = sum(wd['forms']) / len(wd['forms'])
        min_form = min(wd['forms'])
        max_form = max(wd['forms'])
        total_trimp = sum(wd['trimps'])
        avg_fitness = sum(daily_form[ds]['fitness'] for ds in sorted_dates
                         if ds.startswith(wk[:4]) and datetime.strptime(ds, '%Y-%m-%d').strftime('%Y-W%U') == wk) / wd['count'] if wd['count'] else 0

        delta_fitness = avg_fitness - prev_fitness if prev_fitness is not None else 0
        prev_fitness = avg_fitness

        # TiZ: % of days where form is in -10..+20
        tiz_count = sum(1 for fm in wd['forms'] if -10 <= fm <= 20)
        tiz = tiz_count / wd['count']

        week_list.append({
            'week': wk,
            'avg_form': round(avg_form, 1),
            'min_form': round(min_form, 1),
            'max_form': round(max_form, 1),
            'total_trimp': round(total_trimp, 1),
            'tiz': round(tiz, 2),
            'delta_fitness': round(delta_fitness, 2),
            'days': wd['count'],
        })

    # Trim to requested weeks
    week_list = week_list[-weeks:]

    # 4-week rolling TiZ
    for i in range(len(week_list)):
        window = week_list[max(0, i - 3):i + 1]
        week_list[i]['rolling_tiz'] = round(sum(w['tiz'] for w in window) / len(window), 2)

    # Form velocity (slope over last 4 weeks)
    for i in range(len(week_list)):
        if i >= 3:
            x = list(range(4))
            y = [week_list[i - 3 + j]['avg_form'] for j in range(4)]
            n = len(x)
            sx = sum(x)
            sy = sum(y)
            sxy = sum(x[j] * y[j] for j in range(n))
            sx2 = sum(x[j] ** 2 for j in range(n))
            denom = n * sx2 - sx * sx
            slope = (n * sxy - sx * sy) / denom if denom != 0 else 0
            week_list[i]['form_velocity'] = round(slope, 2)
        else:
            week_list[i]['form_velocity'] = None

    # Crash rate
    crash_weeks = sum(1 for w in week_list if w['avg_form'] < -30)
    crash_rate = crash_weeks / len(week_list) if week_list else 0

    avg_tiz = sum(w['tiz'] for w in week_list) / len(week_list) if week_list else 0

    print(json.dumps({
        'weeks': week_list,
        'avg_tiz': round(avg_tiz, 2),
        'crash_rate': round(crash_rate, 2),
        'crash_weeks': crash_weeks,
        'total_weeks': len(week_list),
    }, indent=2, ensure_ascii=False))
