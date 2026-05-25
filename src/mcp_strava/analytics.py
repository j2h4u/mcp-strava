"""Weekly analytics — rolling-window metrics, trends, year-over-year."""

from collections import defaultdict
from datetime import datetime, timedelta
from itertools import accumulate

from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.constants import (
    Config,
    RUNNING_SPORTS,
    SPORT_RUN, SPORT_WALK, SPORT_TRAILRUN,
    build_eff_config,
)
from mcp_strava.types import ActivityMetrics, RollingEfficiency, WeeklyDigest


# ─── Generic Helpers ───

def median(vals):
    """Median of a list, returns None for empty."""
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    return (s[n // 2 - 1] + s[n // 2]) / 2 if n % 2 == 0 else s[n // 2]


def pct_change(curr, prev):
    """Percent change, returns None if prev is 0/None."""
    if prev is None or prev == 0 or curr is None:
        return None
    return round((curr / prev - 1) * 100, 1)


def _active_sports(acts_by_date, filter_set=None):
    """
    Return set of sport types actually present in the data.
    Optionally intersect with filter_set.

    Works with both dict entries and dataclass objects (ActivityMetrics).
    """
    sports = set()
    for acts in acts_by_date.values():
        for a in acts:
            sport = a.get('sport', a.get('sport_type', '')) if isinstance(a, dict) else getattr(a, 'sport', '')
            if sport:
                sports.add(sport)
    if filter_set:
        sports &= filter_set
    return sports


def _prefix_sums(series):
    """Pre-compute prefix sums for O(1) rolling window queries."""
    return [0] + list(accumulate(series))


def rolling_avg_from_prefix(prefix, window, end_idx):
    """O(1) rolling average using pre-computed prefix sums.
    prefix is [0] + accumulate(series). end_idx is 0-based index in original series.
    """
    n = len(prefix) - 1
    if n == 0 or end_idx < 0:
        return 0
    start_idx = max(0, end_idx - window + 1)
    if start_idx > end_idx:
        return 0
    actual_window = end_idx - start_idx + 1
    total = prefix[end_idx + 1] - prefix[start_idx]
    return total / actual_window if actual_window > 0 else 0



# ─── Per-Activity Efficiency from Streams ───

def get_activity_metrics(conn):
    """Query all activities with cardiac efficiency metrics.
    
    Returns list of ActivityMetrics indexed by date via build_acts_by_date().
    EF, bkm, VO2max removed from regular analytics (coach review #2, #4).
    """
    repo = SQLiteRepository.from_connection(conn)
    cur = repo.activity_efficiency_rows()
    result = []
    for row in cur:
        day, sport, dist_km, time_min, elev, avg_hr, avg_vel = (
            row["day"],
            row["sport_type"],
            row["dist_km"],
            row["time_min"],
            row["elev"],
            row["avg_hr"],
            row["avg_vel"],
        )
        cc = avg_hr / avg_vel
        epkm = (elev or 0) / dist_km if dist_km > 0 else 0
        cc_adj = cc - Config.Efficiency.CC_ELEV_COEFF * epkm
        result.append(ActivityMetrics(
            date=day, sport=sport,
            cc=round(cc, 2),
            cc_adj=round(cc_adj, 2),
            bkm=None, ef=None, vo2max_est=None,
            dist_km=round(dist_km, 2),
            time_min=round(time_min, 1),
            elev=elev or 0,
            epkm=round(epkm, 1),
        ))
    return result


def build_acts_by_date(act_metrics):
    """Index activity metrics by date string."""
    by_date = defaultdict(list)
    for a in act_metrics:
        by_date[a.date].append(a)
    return by_date


# ─── Rolling Efficiency ───

def rolling_eff(acts_by_date, end_date, window_days, sports=None):
    """Compute median efficiency metrics over a rolling window.
    
    Args:
        acts_by_date: dict {date_str: [activity_metrics, ...]}
        end_date: date object — end of window
        window_days: int — window length
        sports: set of sport_type strings to include (None = all)
    
    Returns RollingEfficiency or None.
    CC-only (May 2026): EF, bkm, and VO2max removed.
    """
    cc_v, cc_adj_v, epkm_v = [], [], []
    dist_t, time_t, elev_t, count = 0, 0, 0, 0
    active_days = set()
    
    d = end_date - timedelta(days=window_days - 1)
    while d <= end_date:
        ds = d.isoformat()
        for a in acts_by_date.get(ds, []):
            if sports and a.sport not in sports:
                continue
            cc_v.append(a.cc)
            cc_adj_v.append(a.cc_adj)
            if a.epkm is not None:
                epkm_v.append(a.epkm)
            dist_t += a.dist_km
            time_t += a.time_min
            elev_t += a.elev
            count += 1
            active_days.add(ds)
        d += timedelta(days=1)
    
    if not cc_v:
        return None
    return RollingEfficiency(
        count=count,
        active_days=len(active_days),
        total_km=round(dist_t, 1),
        total_time_h=round(time_t / 60, 1),
        total_elev_m=round(elev_t, 0),
        median_epkm=round(median(epkm_v), 1) if epkm_v else None,
        median_cc=round(median(cc_v), 1),
        median_cc_adj=round(median(cc_adj_v), 1),
    )


# ─── Weekly Digest ───

def weekly_digest(conn, today=None):
    """Compute the full weekly analytics digest.
    
    Returns WeeklyDigest with: period, current_state (load/efficiency/volume), trends, yoy, context, this_week.
    """
    today = today or datetime.now().date()
    repo = SQLiteRepository.from_connection(conn)
    
    # 1) Daily TRIMP series (full history, gaps filled with 0)
    first_day = repo.first_activity_day(sport_filter="training")
    raw_daily = repo.effective_trimp_history(first_day, today.isoformat(), sport_filter="training") if first_day else {}
    
    if not raw_daily:
        return None
    
    all_dates_sorted = sorted(raw_daily.keys())
    first_date = datetime.strptime(all_dates_sorted[0], '%Y-%m-%d').date()
    
    daily_trimp = []
    d = first_date
    while d <= today:
        daily_trimp.append(raw_daily.get(d.isoformat(), 0))
        d += timedelta(days=1)
    
    # 2) Per-activity efficiency metrics
    act_metrics = get_activity_metrics(conn)
    acts_by_date = build_acts_by_date(act_metrics)
    
    # 3) Current state — prefix sums for O(1) rolling windows
    today_idx = len(daily_trimp) - 1
    trimp_prefix = _prefix_sums(daily_trimp)
    
    load_7d = rolling_avg_from_prefix(trimp_prefix, 7, today_idx)
    load_28d = rolling_avg_from_prefix(trimp_prefix, 28, today_idx)
    load_90d = rolling_avg_from_prefix(trimp_prefix, 90, today_idx)
    # ACWR removed from weekly_digest (May 2026) — report.py uses EWMA-based ACWR,
    # which is the industry standard (TrainingPeaks/Golden Cheetah).
    # Simple rolling-average ACWR was a duplicate that could confuse the athlete.
    
    # Efficiency per sport — use registry, filtered to user's actual sports
    eff_config = {s: w for s, w in build_eff_config().items()
                  if s in _active_sports(acts_by_date)}
    efficiency = {}
    for sport, windows in eff_config.items():
        se = {}
        for w in windows:
            m = rolling_eff(acts_by_date, today, w, sports={sport})
            if m:
                se[f'{w}d'] = m
        if se:
            efficiency[sport] = se
    
    # Volume per sport
    volume = {}
    for sport in sorted(_active_sports(acts_by_date)):
        v7 = rolling_eff(acts_by_date, today, 7, sports={sport})
        v28 = rolling_eff(acts_by_date, today, 28, sports={sport})
        volume[sport] = {}
        if v7:
            volume[sport]['7d'] = {k: getattr(v7, k) for k in ('count', 'total_km', 'total_time_h', 'active_days')}
        if v28:
            volume[sport]['28d'] = {k: getattr(v28, k) for k in ('count', 'total_km', 'total_time_h', 'active_days')}
        if not volume[sport]:
            del volume[sport]
    
    # 4) Trends
    trends = {}
    for label, window, shift in [('load_7d', 7, 7), ('load_28d', 28, 28), ('load_90d', 90, 90)]:
        shifted_idx = today_idx - shift
        if shifted_idx >= 0:
            prev = rolling_avg_from_prefix(trimp_prefix, window, shifted_idx)
            current = {'load_7d': load_7d, 'load_28d': load_28d, 'load_90d': load_90d}[label]
            trends[label] = pct_change(current, prev)
    
    for sport in sorted(_active_sports(acts_by_date, filter_set={SPORT_RUN, SPORT_TRAILRUN, SPORT_WALK})):
        eff_now = rolling_eff(acts_by_date, today, 28, sports={sport})
        eff_prev = rolling_eff(acts_by_date, today - timedelta(days=28), 28, sports={sport})
        if eff_now and eff_prev:
            for m in ['median_cc', 'median_cc_adj']:
                if getattr(eff_now, m, None) and getattr(eff_prev, m, None):
                    trends[f'{sport}_28d_{m}'] = pct_change(getattr(eff_now, m), getattr(eff_prev, m))

    eff_run_now = rolling_eff(acts_by_date, today, 90, sports=RUNNING_SPORTS)
    eff_run_prev = rolling_eff(acts_by_date, today - timedelta(days=90), 90, sports=RUNNING_SPORTS)
    if eff_run_now and eff_run_prev:
        trends['run_90d_median_cc'] = pct_change(eff_run_now.median_cc, eff_run_prev.median_cc)
    
    trends = {k: v for k, v in trends.items() if v is not None}
    
    # 5) Year-over-year — removed (May 2026, coach review #7).
    # YoY comparisons are noisy for aging athletes: season, health, motivation,
    # weight all confound a 364-day-apart comparison. Replaced by 90d CC trend.
    yoy = {}
    
    # 6) Context
    season = {12: 'winter', 1: 'winter', 2: 'winter',
              3: 'spring', 4: 'spring', 5: 'spring',
              6: 'summer', 7: 'summer', 8: 'summer',
              9: 'autumn', 10: 'autumn', 11: 'autumn'}.get(today.month, 'unknown')

    last_hike = None
    for a in reversed(act_metrics):
        if a.sport == 'Hike':
            last_hike = (today - datetime.strptime(a.date, '%Y-%m-%d').date()).days
            break

    streak = 0
    d = today
    while d.isoformat() in raw_daily:
        streak += 1
        d -= timedelta(days=1)

    rest_streak = 0
    d = today
    while d.isoformat() not in raw_daily:
        rest_streak += 1
        d -= timedelta(days=1)
    
    week_start = today - timedelta(days=today.weekday())
    week_acts = sorted(
        [a for a in act_metrics if a.date >= week_start.isoformat()],
        key=lambda x: x.date
    )
    
    return WeeklyDigest(
        period={
            'today': today.isoformat(),
            'weekday': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][today.weekday()],
            'data_days': len(daily_trimp),
            'first_activity': first_date.isoformat(),
        },
        current_state={
            'load': {
                'daily_avg_trimp_7d': round(load_7d, 1),
                'daily_avg_trimp_28d': round(load_28d, 1),
                'daily_avg_trimp_90d': round(load_90d, 1),
            },
            'efficiency': efficiency,
            'volume': volume,
        },
        trends=trends,
        yoy=yoy,
        context={
            'season': season,
            'last_hike_days_ago': last_hike,
            'activity_streak': streak,
            'rest_streak': rest_streak,
        },
        this_week=[
            {
                'date': a.date,
                'sport': a.sport,
                'distance_km': a.dist_km,
                'time_min': a.time_min,
                'elevation_m': a.elev,
            }
            for a in week_acts
        ],
    )
