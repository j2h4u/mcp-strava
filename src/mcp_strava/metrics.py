"""Per-activity metrics: pure domain functions over plain stream data.

All functions take pre-fetched plain dict rows and return dataclasses or None.
No storage imports — callers are responsible for fetching rows via the repository.
"""

from collections.abc import Mapping
from datetime import datetime

from mcp_strava.cardiac_drift import cardiac_drift as _drift_algo
from mcp_strava.constants import SPORT_WALK, WALK_TRIMP_DISCOUNT, Config
from mcp_strava.types import CardiacDriftResult, HrRecovery, VerticalSpeed

# ─── Local time-of-day (HH:MM) from a Strava start_date_local ───


def parse_local_hhmm(start_date_local: str | None) -> str | None:
    """Pure: the local time-of-day "HH:MM" from a Strava start_date_local string.

    The input is the activity's full LOCAL start timestamp (e.g.
    "2026-05-21T07:16:00", possibly with a trailing "Z" or an offset like
    "+05:00"). We parse it with datetime.fromisoformat and format strftime("%H:%M")
    — deliberately NOT a fragile string slice ([11:16]) that would break on a
    space separator, fractional seconds, or any non-canonical layout.

    The wall-clock time is read AS WRITTEN: no timezone conversion is applied, so
    an offset-bearing value reports its own local clock, not UTC. A trailing "Z"
    is normalized to "+00:00" for parser portability before parsing.

    Returns None when the input is missing, empty, or unparseable (the caller
    treats that as "no start time" rather than raising).
    """
    if not start_date_local:
        return None
    text = start_date_local.strip()
    if not text:
        return None
    # Normalize a trailing UTC "Z" designator to an explicit offset so the value
    # parses uniformly. fromisoformat accepts "Z" on 3.14, but normalizing keeps
    # the parse identical across the offset-bearing and Z-bearing forms.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError, TypeError:
        return None
    return parsed.strftime("%H:%M")


# ─── Intra-Activity Cardiac Drift ───


def calc_cardiac_drift(rows, sport_type=None):
    """Pure: Intra-activity cardiac drift using Jenks pace clustering.

    Takes pre-fetched stream rows ({heartrate, velocity}) and returns
    a CardiacDriftResult, or None if insufficient data.

    Unlike calc_decoupling (first vs second half, CV ≤ 25%),
    this works with variable pace by clustering pace first.
    """
    if len(rows) < Config.Metrics.MIN_STREAM_POINTS:
        return None

    hr = [r["heartrate"] for r in rows]
    vel = [r["velocity"] for r in rows]

    threshold = Config.Drift.THRESHOLD_BY_SPORT.get(sport_type or "", Config.Drift.THRESHOLD_DEFAULT)

    result = _drift_algo(
        heartrate=hr,
        velocity=vel,
        min_cluster_size=Config.Drift.MIN_CLUSTER_SIZE,
        min_segment_duration=Config.Drift.MIN_SEGMENT_DURATION,
        drift_threshold_pct=threshold,
        outlier_iqr_mult=Config.Drift.OUTLIER_IQR_MULT,
        max_k=Config.Drift.MAX_K,
        gvf_threshold=Config.Drift.GVF_THRESHOLD,
    )

    if result.get("error"):
        return CardiacDriftResult(
            drift_pct=None,
            severity=None,
            quality="low",
            is_significant=False,
            n_clusters=result.get("n_clusters", 0),
            gvf=result.get("gvf", 0.0),
            cluster_count=len(result.get("cluster_details", [])),
            error=result["error"],
        )

    return CardiacDriftResult(
        drift_pct=result["drift_weighted_pct"],
        severity=result["severity"],
        quality=result.get("quality", "low"),
        is_significant=result["is_significant"],
        n_clusters=result["n_clusters"],
        gvf=result["gvf"],
        cluster_count=len(result.get("cluster_details", [])),
        error=None,
    )


# ─── HR Recovery ───


def _dedup_stream_points(rows) -> tuple[dict, list] | None:
    """De-duplicate rows by time_offset and return (by_time, sorted_times), or None if insufficient."""
    by_time = {r["time_offset"]: r for r in rows}
    all_times = sorted(by_time.keys())
    if len(all_times) < Config.Metrics.MIN_STREAM_POINTS:
        return None
    return by_time, all_times


def _find_pause_segments(all_times: list, by_time: dict) -> list[dict]:
    """Scan the sorted time series and return all rest pauses meeting MIN_PAUSE_SEC.

    Each pause dict carries: time, duration, hr_start, hr_end, drop, rate (bpm/min).
    """
    MIN_PAUSE_SEC = Config.Metrics.MIN_PAUSE_SEC
    STOP_VEL = Config.Thresholds.VEL_STOP  # m/s (~0.5 km/h) — actual standing, not slow walking

    pauses = []
    i = 0
    while i < len(all_times):
        t = all_times[i]
        r = by_time[t]
        v = r["velocity"] or 0

        if v < STOP_VEL:
            # Start of potential pause — find how long it lasts
            pause_start = t
            pause_start_idx = i
            j = i + 1
            while j < len(all_times):
                t2 = all_times[j]
                r2 = by_time[t2]
                # Allow small gaps between consecutive data points
                if t2 - all_times[j - 1] > Config.Metrics.MAX_PAUSE_GAP_S:
                    break
                v2 = r2["velocity"] or 0
                if v2 >= STOP_VEL:
                    break
                j += 1

            pause_end = all_times[j - 1]
            pause_dur = pause_end - pause_start

            if pause_dur >= MIN_PAUSE_SEC:
                end_idx = j - 1
                # Restrict both HR windows to the pause itself. Slicing the
                # global timeline for the start window could reach past
                # pause_end into moving rows when a pause is shorter than 5
                # samples (only possible via gaps), biasing hr_start toward the
                # moving HR and corrupting the drop (see WR-02).
                pause_window = all_times[pause_start_idx : end_idx + 1]

                # Get HR at start of pause (avg of first 5s within the pause)
                start_times = pause_window[:5]
                hr_start = sum(by_time[t]["heartrate"] for t in start_times) / len(start_times)

                # Get HR at end of pause (avg of last 5s within the pause)
                end_times = pause_window[-5:]
                hr_end = sum(by_time[t]["heartrate"] for t in end_times) / len(end_times)

                drop = round(hr_start - hr_end, 1)
                # Rate (bpm/min) is divided by the count of actually-sampled rest
                # seconds, not the wall-clock span (pause_dur). The inner loop
                # tolerates gaps up to 3s, so pause_dur can over-count the real
                # rest seconds and deflate the recovery rate; len(pause_window)
                # is the true number of sampled points in the pause (see WR-05).
                sampled_rest_sec = len(pause_window)
                rate = round(drop / (sampled_rest_sec / 60), 1) if sampled_rest_sec > 0 else 0

                pauses.append(
                    {
                        "time": pause_start,
                        "duration": pause_dur,
                        "hr_start": round(hr_start),
                        "hr_end": round(hr_end),
                        "drop": drop,
                        "rate": rate,  # bpm/min
                    }
                )

            i = j  # skip past this pause
        else:
            i += 1

    return pauses


def _aggregate_pauses(pauses: list[dict]):
    """Compute HrRecovery aggregate stats from a non-empty pause list, or None if no rated pauses."""
    # Single contract: rates, best, and worst all operate on the same
    # rate-bearing subset. Today rate is always numeric, but keeping the filter
    # and the best/worst selection in sync prevents a future nullable rate from
    # making max()/min() raise on None while rates silently excluded it (WR-06).
    rated = [p for p in pauses if p["rate"] is not None]
    rates = sorted(p["rate"] for p in rated)
    total_rest = sum(p["duration"] for p in pauses)

    best = max(rated, key=lambda p: p["rate"]) if rated else None
    worst = min(rated, key=lambda p: p["rate"]) if rated else None

    n = len(rates)
    if n == 0:
        return None
    # Median (robust to outliers from short/noisy pauses)
    median = rates[n // 2] if n % 2 else round((rates[n // 2 - 1] + rates[n // 2]) / 2, 1)

    return HrRecovery(
        pauses_found=len(pauses),
        total_rest_sec=total_rest,
        median_rate=median,
        best_rate=best["rate"] if best else None,
        worst_rate=worst["rate"] if worst else None,
        avg_rate=round(sum(rates) / len(rates), 1) if rates else None,
    )


def calc_hr_recovery(rows):
    """Pure: HR recovery over pre-fetched stream rows ({time_offset, heartrate, velocity}).

    Finds ALL rest pauses in the activity and measures HR drop at each.

    A "pause" = MIN_PAUSE_SEC+ consecutive seconds where velocity < VEL_STOP m/s (~0.5 km/h).
    That's standing still, not slow walking (which is ~0.5+ m/s).
    For each pause, measures HR drop over the pause duration.
    Returns aggregate stats: best/worst/avg recovery, count of pauses, total rest time.
    Returns None if no pauses found or insufficient data.

    Precondition: `time_offset` values are expected to be unique. The repository
    query returns one row per (activity_id, time_offset), but DuckDB does not
    enforce that here, so duplicate offsets are de-duplicated below and the
    sufficiency guard is re-checked against the de-duplicated point count to keep
    the pause-detection math consistent (see WR-01).
    """
    if len(rows) < Config.Metrics.MIN_STREAM_POINTS:
        return None

    # Build time-indexed lookup; keying by time_offset collapses duplicate-offset
    # rows — re-validate sufficiency against the de-duplicated count (see WR-01).
    deduped = _dedup_stream_points(rows)
    if deduped is None:
        return None
    by_time, all_times = deduped

    pauses = _find_pause_segments(all_times, by_time)
    if not pauses:
        return None

    return _aggregate_pauses(pauses)


# ─── Vertical Speed ───


def calc_vertical_speed(rows):
    """Pure: Vertical ascent speed in m/h from pre-fetched altitude rows ({time_offset, altitude}).

    Only counts ascending segments.
    Returns None if insufficient data or duration too short.
    """
    if len(rows) < Config.Metrics.MIN_ALT_POINTS:
        return None

    total_ascent = 0
    for i in range(1, len(rows)):
        diff = rows[i]["altitude"] - rows[i - 1]["altitude"]
        if diff > 0:
            total_ascent += diff

    # Use the elapsed SPAN of the altitude series (last - first time_offset),
    # not the absolute last offset. The repository query filters altitude IS NOT
    # NULL and orders by time_offset, so the first returned row is not guaranteed
    # to be at offset 0 (e.g. the barometer warms up partway into a ride). Using
    # the absolute last offset would inflate the denominator and understate vmh.
    # Pauses within the span are part of the climbing effort, so the full span is
    # the right denominator.
    elapsed_sec = rows[-1]["time_offset"] - rows[0]["time_offset"]
    duration_hours = elapsed_sec / 3600
    if duration_hours < Config.Metrics.MIN_VMH_HOURS:
        return None

    vmh = round(total_ascent / duration_hours, 0)
    return VerticalSpeed(
        vmh=int(vmh),
        total_ascent_m=round(total_ascent, 0),
        duration_hours=round(duration_hours, 2),
    )


# ─── %HRR ───


def calc_hrr_pct(median_hr, hr_rest, hr_max):
    """Pure: Average %HRR (Heart Rate Reserve percentage).

    How much of the heart's reserve was used.
    Uses MEDIAN heartrate (more robust to sensor spikes than mean).

    Returns None if any input is None, or if hr_max <= hr_rest.
    Returns round((median_hr - hr_rest) / (hr_max - hr_rest) * 100, 1) otherwise.

    Example: calc_hrr_pct(150, 50, 200) == 66.7
    """
    if median_hr is None or hr_rest is None or hr_max is None:
        return None
    # Coerce all three inputs consistently. The materializer passes ints, but
    # coercing only hr_max (as before) left hr_rest un-coerced, so a numeric
    # string hr_rest would raise TypeError mid-formula instead of being handled
    # by the guard. Float all of them up front (WR-04).
    median_hr_f = float(median_hr)
    hr_rest_f = float(hr_rest)
    hr_max_f = float(hr_max)
    if hr_max_f <= hr_rest_f:
        return None
    return round((median_hr_f - hr_rest_f) / (hr_max_f - hr_rest_f) * 100, 1)


# ─── Walk TRIMP discount (per-sport daily effective TRIMP) ───


def discounted_effective_trimp(by_sport: Mapping[str, float]) -> float:
    """Pure: a single day's EFFECTIVE TRIMP from its per-sport RAW daily TRIMP.

    Each sport's raw TRIMP is multiplied by WALK_TRIMP_DISCOUNT if the sport is a
    Walk, else by 1.0 (full load). The multiplied values are summed and rounded
    ONCE at the end — no per-sport intermediate rounding, so there is no rounding
    drift when several sports share a day.

    Args:
        by_sport: {sport_type -> observed raw daily TRIMP} for ONE day.

    Returns:
        The discounted daily effective TRIMP (float). Empty input -> 0.0.

    Examples (WALK_TRIMP_DISCOUNT == 0.5):
        {"Run": 100}             -> 100.0   (unchanged)
        {"Walk": 80}             -> 40.0    (0.5x)
        {"Run": 100, "Walk": 80} -> 140.0   (100 + 40)
        {}                       -> 0.0
    """
    total = sum(raw * (WALK_TRIMP_DISCOUNT if sport == SPORT_WALK else 1.0) for sport, raw in by_sport.items())
    return round(float(total), 1)
