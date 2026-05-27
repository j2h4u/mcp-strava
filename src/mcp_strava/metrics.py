"""Per-activity metrics: decoupling, efficiency factor, HR recovery,
vertical speed, and the enrichment wrapper that computes all of them."""

from mcp_strava.constants import Config
from mcp_strava.db import repository_from_connection
from mcp_strava.types import (HrRecovery, VerticalSpeed, DecouplingResult,
                               EnrichedActivity, CardiacDriftResult, parse_strava_activity)
from mcp_strava.cardiac_drift import cardiac_drift as _drift_algo
import json


# Cached HRmax from streams — query once, reuse across enrichment calls.
# Reset on new connection (module reload or explicit clear).
_hr_max_cache: float | None = None


def _get_hr_max(conn) -> float:
    """Max heartrate ever observed in streams. Falls back to Config.Athlete.HR_MAX."""
    global _hr_max_cache
    if _hr_max_cache is not None:
        return _hr_max_cache
    repo = repository_from_connection(conn)
    hr_max = repo.max_heartrate()
    if hr_max is not None:
        _hr_max_cache = float(hr_max)
    else:
        _hr_max_cache = float(Config.Athlete.HR_MAX)
    return _hr_max_cache


# ─── Decoupling validity gate ───

def _decoupling_invalid(velocities):
    """Pure: True if decoupling metric is invalid for this activity.

    Decoupling (Pa:HR) is defined for steady-state efforts only.
    Returns True when:
    - Fewer than 2 velocity points (can't assess variability)
    - Mean velocity below movement threshold (standing still)
    - Coefficient of variation exceeds PACE_CV_MAX (structural pace changes)

    When True, decoupling is not computed — the activity doesn't meet
    the steady-state requirement.
    """
    if len(velocities) < 2:
        return True
    mean_v = sum(velocities) / len(velocities)
    if mean_v < Config.Thresholds.VEL_MOVING:
        return True
    variance = sum((v - mean_v) ** 2 for v in velocities) / len(velocities)
    cv = (variance ** 0.5) / mean_v
    return cv > Config.Thresholds.PACE_CV_MAX


# ─── Decoupling ───

def _fetch_decoupling_rows(conn, activity_id):
    """Fetch stream rows needed for decoupling (HR + velocity, in motion)."""
    repo = repository_from_connection(conn)
    return repo.stream_hr_velocity_rows(activity_id, Config.Thresholds.VEL_MOVING)


def calc_decoupling(rows):
    """Pure: HR/Pace decoupling from pre-fetched rows — TrainingPeaks Pa:HR method.
    
    Compares HR/pace ratio between first and second half of activity.
    Decoupling = (ratio₂ / ratio₁ − 1) × 100%

    Positive = HR drifting up relative to pace = cardiac drift / fatigue.
    <5% = solid aerobic endurance. >10% = accumulating fatigue.

    Does NOT check decoupling validity — caller should gate with _decoupling_invalid()
    before calling. Returns None if data insufficient.

    NOTE: GAP correction was tested (Minetti 2002, empirical) but found unnecessary
    for this athlete's data — they naturally adjust pace on hills, so raw HR/vel
    already captures the terrain effect correctly.
    """
    if len(rows) < Config.Metrics.MIN_STREAM_POINTS:
        return None

    mid = len(rows) // 2

    def hr_vel_ratio(segment):
        hr_avg = sum(r['heartrate'] for r in segment) / len(segment)
        vel_avg = sum(r['velocity'] for r in segment) / len(segment)
        if vel_avg < Config.Thresholds.VEL_MOVING:
            return None
        return hr_avg / vel_avg

    r1 = hr_vel_ratio(rows[:mid])
    r2 = hr_vel_ratio(rows[mid:])
    if r1 is None or r2 is None or r1 == 0:
        return None

    return DecouplingResult(
        decoupling_pct=round((r2 / r1 - 1) * 100, 1),
    )


def calc_decoupling_with_gate(conn, activity_id):
    """Fetch rows, gate by pace variability, compute decoupling if valid.
    
    Returns DecouplingResult (possibly with decoupling_pct=None + pace_too_variable=True)
    or None if insufficient data.
    """
    rows = _fetch_decoupling_rows(conn, activity_id)
    if not rows:
        return None

    velocities = [r['velocity'] for r in rows]
    if _decoupling_invalid(velocities):
        return DecouplingResult(
            decoupling_pct=None,
            pace_too_variable=True,
        )

    return calc_decoupling(rows)


# ─── Intra-Activity Cardiac Drift ───

def calc_cardiac_drift(conn, activity_id, sport_type=None):
    """Intra-activity cardiac drift using Jenks pace clustering.
    
    Fetches stream rows, clusters velocity into homogeneous pace zones
    via Jenks natural breaks, then compares median HR in early vs late
    temporal segments within each cluster.
    
    Unlike calc_decoupling_with_gate (first vs second half, CV ≤ 25%),
    this works with variable pace by clustering pace first.
    
    Returns CardiacDriftResult or None if insufficient data.
    """
    repo = repository_from_connection(conn)
    rows = repo.stream_hr_velocity_simple_rows(activity_id, Config.Thresholds.VEL_MOVING)

    if len(rows) < Config.Metrics.MIN_STREAM_POINTS:
        return None

    hr = [r['heartrate'] for r in rows]
    vel = [r['velocity'] for r in rows]

    threshold = Config.Drift.THRESHOLD_BY_SPORT.get(
        sport_type or '', Config.Drift.THRESHOLD_DEFAULT
    )

    result = _drift_algo(
        heartrate=hr, velocity=vel,
        min_cluster_size=Config.Drift.MIN_CLUSTER_SIZE,
        min_segment_duration=Config.Drift.MIN_SEGMENT_DURATION,
        drift_threshold_pct=threshold,
        outlier_iqr_mult=Config.Drift.OUTLIER_IQR_MULT,
        max_k=Config.Drift.MAX_K,
        gvf_threshold=Config.Drift.GVF_THRESHOLD,
    )

    if result.get('error'):
        return CardiacDriftResult(
            drift_pct=None, severity=None, quality='low',
            is_significant=False, n_clusters=result.get('n_clusters', 0),
            gvf=result.get('gvf', 0.0),
            cluster_count=len(result.get('cluster_details', [])),
            error=result['error'],
        )

    return CardiacDriftResult(
        drift_pct=result['drift_weighted_pct'],
        severity=result['severity'],
        quality=result.get('quality', 'low'),
        is_significant=result['is_significant'],
        n_clusters=result['n_clusters'],
        gvf=result['gvf'],
        cluster_count=len(result.get('cluster_details', [])),
        error=None,
    )


# ─── Efficiency Factor ───

def calc_efficiency_factor(conn, activity_id):
    """Efficiency Factor: normalized speed / avg HR.
    Higher = more economical movement. Computed as (distance_m / moving_time_s) / avg_hr.
    """
    repo = repository_from_connection(conn)
    moving_time = repo.activity_moving_time(activity_id)
    if moving_time is None or moving_time < Config.Metrics.MIN_MOVING_TIME:
        return None

    avg_hr, n_hr = repo.activity_hr_summary(activity_id)
    if avg_hr is None or avg_hr <= 0 or n_hr < Config.Metrics.MIN_HR_POINTS:
        return None

    # Use velocity from streams for actual pace
    avg_vel = repo.activity_avg_velocity(activity_id)
    if avg_vel is None or avg_vel < Config.Thresholds.VEL_MOVING:
        return None

    # EF = speed_m_s / avg_hr × 100 (scale for readability)
    ef = round(avg_vel / avg_hr * 100, 3)
    return ef


# ─── HR Recovery ───

def calc_hr_recovery(conn, activity_id):
    """HR recovery: finds ALL rest pauses in the activity and measures HR drop at each.
    
    A \"pause\" = 20+ consecutive seconds where velocity < 0.15 m/s (~0.5 km/h).
    That's standing still, not slow walking (which is ~0.5+ m/s).
    For each pause, measures HR drop over the pause duration.
    Returns aggregate stats: best/worst/avg recovery, count of pauses, total rest time.
    Returns None if no pauses found (e.g. continuous run with no stops).
    """
    repo = repository_from_connection(conn)
    rows = repo.stream_hr_velocity_time_rows(activity_id)
    if len(rows) < Config.Metrics.MIN_STREAM_POINTS:
        return None

    MIN_PAUSE_SEC = Config.Metrics.MIN_PAUSE_SEC
    STOP_VEL = Config.Thresholds.VEL_STOP  # m/s (~0.5 km/h) — actual standing, not slow walking
    
    # Build time-indexed lookup for fast access
    by_time = {r['time_offset']: r for r in rows}
    all_times = sorted(by_time.keys())

    # Find all pause segments
    pauses = []
    i = 0
    while i < len(all_times):
        t = all_times[i]
        r = by_time[t]
        v = r['velocity'] or 0
        
        if v < STOP_VEL:
            # Start of potential pause — find how long it lasts
            pause_start = t
            pause_start_idx = i
            j = i + 1
            while j < len(all_times):
                t2 = all_times[j]
                r2 = by_time[t2]
                # Allow small gaps (up to 3s) between consecutive data points
                if t2 - all_times[j-1] > 3:
                    break
                v2 = r2['velocity'] or 0
                if v2 >= STOP_VEL:
                    break
                j += 1
            
            pause_end = all_times[j-1]
            pause_dur = pause_end - pause_start
            
            if pause_dur >= MIN_PAUSE_SEC:
                # Get HR at start of pause (avg of first 5s)
                start_times = all_times[pause_start_idx:pause_start_idx+5]
                hr_start = sum(by_time[t]['heartrate'] for t in start_times) / len(start_times)
                
                # Get HR at end of pause (avg of last 5s)
                end_idx = j - 1
                end_times = all_times[max(0, end_idx-4):end_idx+1]
                hr_end = sum(by_time[t]['heartrate'] for t in end_times) / len(end_times)
                
                drop = round(hr_start - hr_end, 1)
                rate = round(drop / (pause_dur / 60), 1) if pause_dur > 0 else 0
                
                pauses.append({
                    'time': pause_start,
                    'duration': pause_dur,
                    'hr_start': round(hr_start),
                    'hr_end': round(hr_end),
                    'drop': drop,
                    'rate': rate,  # bpm/min
                })
            
            i = j  # skip past this pause
        else:
            i += 1

    if not pauses:
        return None

    rates = sorted(p['rate'] for p in pauses if p['rate'] is not None)
    total_rest = sum(p['duration'] for p in pauses)

    best = max(pauses, key=lambda p: p['rate']) if pauses else None
    worst = min(pauses, key=lambda p: p['rate']) if pauses else None

    # Median (robust to outliers from short/noisy pauses)
    n = len(rates)
    if n == 0:
        return None
    median = rates[n // 2] if n % 2 else round((rates[n // 2 - 1] + rates[n // 2]) / 2, 1)

    return HrRecovery(
        pauses_found=len(pauses),
        total_rest_sec=total_rest,
        median_rate=median,
        best_rate=best['rate'] if best else None,
        worst_rate=worst['rate'] if worst else None,
        avg_rate=round(sum(rates) / len(rates), 1) if rates else None,
    )


# ─── Vertical Speed ───

def calc_vertical_speed(conn, activity_id):
    """Vertical ascent speed in m/h. Only counts ascending segments."""
    repo = repository_from_connection(conn)
    rows = repo.stream_altitude_rows(activity_id)
    if len(rows) < Config.Metrics.MIN_ALT_POINTS:
        return None

    total_ascent = 0
    for i in range(1, len(rows)):
        diff = rows[i]['altitude'] - rows[i-1]['altitude']
        if diff > 0:
            total_ascent += diff

    # Use elapsed time (last time_offset) — pauses are part of the climbing effort
    duration_hours = rows[-1]['time_offset'] / 3600
    if duration_hours < 0.05:  # < 3 min
        return None

    vmh = round(total_ascent / duration_hours, 0)
    # Also: total ascent for context
    return VerticalSpeed(
        vmh=int(vmh),
        total_ascent_m=round(total_ascent, 0),
        duration_hours=round(duration_hours, 2),
    )


# ─── Activity Enrichment ───

def enrich_activity(conn, act_row):
    """Compute all metrics for a single activity row.
    
    May 2026: decoupling and EF removed from enrichment — decoupling almost always
    N/A (pace too variable), EF replaced by CC in progressive signal.
    """
    def _field(name, default=None):
        if isinstance(act_row, dict):
            return act_row.get(name, default)
        return getattr(act_row, name, default)

    raw_summary = json.loads(_field("summary_json")) if _field("summary_json") else {}
    summary = parse_strava_activity(raw_summary) if raw_summary else None

    # TRIMP
    repo = repository_from_connection(conn)
    trimp = repo.activity_trimp(_field("id"))

    # HR Recovery
    hr_recovery = calc_hr_recovery(conn, _field("id"))

    # Vertical Speed
    vertical_speed = calc_vertical_speed(conn, _field("id"))

    # Cardiac Cost (CC) = avg_HR / avg_velocity — for progressive signal
    cc = repo.activity_cc(_field("id"), Config.Thresholds.VEL_MOVING)

    # Average %HRR: how much of the heart's reserve was used.
    # Uses MEDIAN heartrate from streams (more robust to sensor spikes than mean).
    # HRmax from streams (live), HRrest from config (Samsung Health).
    hrr_pct = None
    median_hr = repo.activity_median_heartrate(_field("id"))
    if median_hr:
        hr_max = _get_hr_max(conn)
        hrr_pct = round(
            (median_hr - Config.Athlete.HR_REST)
            / (hr_max - Config.Athlete.HR_REST) * 100, 1
        )

    # Start time from summary_json (local time, HH:MM)
    start_time = None
    if raw_summary:
        sdl = raw_summary.get('start_date_local', '')
        # Strava format: "2026-05-11T00:50:30Z" (Z suffix but it's local time)
        if sdl and 'T' in sdl:
            time_part = sdl.split('T')[1]
            start_time = time_part[:5]  # "HH:MM"

    # Intra-activity cardiac drift (Jenks-based)
    cardiac_drift = calc_cardiac_drift(conn, _field("id"), _field("sport_type"))

    return EnrichedActivity(
        id=_field("id"),
        date=_field("date")[:10],
        name=_field("name"),
        sport_type=_field("sport_type"),
        distance_km=round(_field("distance") / 1000, 2),
        moving_time_min=round(_field("moving_time") / 60, 1),
        elapsed_time_min=round(_field("elapsed_time") / 60, 1),
        elevation_m=_field("total_elevation_gain"),
        trimp=trimp,
        avg_hr=summary.average_heartrate if summary else None,
        max_hr=int(round(summary.max_heartrate)) if summary and summary.max_heartrate else None,
        hr_recovery=hr_recovery,
        vertical_speed=vertical_speed,
        cc=cc,
        cardiac_drift=cardiac_drift,
        hrr_pct=hrr_pct,
        start_time=start_time,
    )


def check_z5_minutes(conn, activity_id, z5_threshold=None, warn_seconds=300):
    """Safety check: minutes spent in Z5 (≥threshold bpm). Warns if >5 minutes.
    For 50+ athletes, prolonged Z5 is a cardiac risk factor.
    Returns (z5_seconds, warning_reason) or (None, None)."""
    if z5_threshold is None:
        z5_threshold = Config.Zones.BOUNDS[-2]  # Z5 lower bound (penultimate element)
    repo = repository_from_connection(conn)
    z5_sec = repo.activity_z5_seconds(activity_id, z5_threshold)
    if z5_sec == 0:
        return None, None
    if z5_sec > warn_seconds:
        return z5_sec, f"⚠️ {z5_sec // 60} мин в Z5 (HR≥{z5_threshold}) — для 50+ это высокая нагрузка на сердце"
    return z5_sec, None


def check_hr_anomalies(conn, activity_id, jump_threshold=30, min_anomalies=3):
    """Check for HR jumps >threshold bpm between consecutive stream points.
    
    Sports medicine review #12: inter-point HR jumps >30 bpm may indicate
    arrhythmia (AFib prevalence 3-5% at 50+) or sensor artifact. Isolated
    single jumps are likely noise — flag only when multiple anomalies found.
    
    Returns (anomaly_count, warning_reason) or (0, None).
    """
    repo = repository_from_connection(conn)
    rows = repo.stream_hr_time_rows(activity_id)
    
    if len(rows) < 2:
        return 0, None
    
    anomalies = 0
    for i in range(1, len(rows)):
        jump = abs(rows[i]['heartrate'] - rows[i-1]['heartrate'])
        if jump > jump_threshold:
            anomalies += 1
    
    if anomalies >= min_anomalies:
        return anomalies, (
            f"⚠️ {anomalies} скачков пульса >{jump_threshold} bpm за секунду. "
            "Возможна аритмия или артефакт датчика. "
            "Если Samsung Health — проверь контакты; если грудной ремень — к кардиологу."
        )
    return anomalies, None
