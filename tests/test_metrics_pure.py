"""Unit tests for pure metric functions in mcp_strava.metrics.

All tests use plain dict rows — no database connection, no repository.
"""

from mcp_strava.constants import Config
from mcp_strava.metrics import (
    calc_cardiac_drift,
    calc_hr_recovery,
    calc_hrr_pct,
    calc_vertical_speed,
)

# ─── Helpers ───


def _make_hr_vel_time_rows(n, velocity=3.0, heartrate=140, time_offset_start=0):
    """Build n stream rows with {time_offset, heartrate, velocity}."""
    return [{"time_offset": time_offset_start + i, "heartrate": heartrate, "velocity": velocity} for i in range(n)]


def _make_altitude_rows(n, altitude_start=100.0, ascent_per_step=1.0, time_offset_start=0):
    """Build n stream rows with {time_offset, altitude}."""
    return [
        {"time_offset": time_offset_start + i * 10, "altitude": altitude_start + i * ascent_per_step} for i in range(n)
    ]


def _make_hr_vel_rows(n, velocity=3.0, heartrate=140):
    """Build n stream rows with {heartrate, velocity} (no time_offset)."""
    return [{"heartrate": heartrate, "velocity": velocity} for _ in range(n)]


# ─── calc_hr_recovery ───


def test_calc_hr_recovery():
    """calc_hr_recovery(rows): None guards and pause detection."""
    # Insufficient rows
    rows_short = _make_hr_vel_time_rows(Config.Metrics.MIN_STREAM_POINTS - 1)
    assert calc_hr_recovery(rows_short) is None, "Should return None for < MIN_STREAM_POINTS rows"

    # Sufficient rows but no qualifying pause (always moving at velocity >= VEL_STOP)
    rows_moving = _make_hr_vel_time_rows(Config.Metrics.MIN_STREAM_POINTS + 10, velocity=1.0)
    assert calc_hr_recovery(rows_moving) is None, "Should return None when no pauses found"

    # Build rows with a qualifying pause: first 120 rows moving, then 40 rows stopped
    # HR drops during the pause (simulates recovery)
    MIN = Config.Metrics.MIN_STREAM_POINTS
    STOP = Config.Thresholds.VEL_STOP
    moving = [{"time_offset": i, "heartrate": 160, "velocity": 3.0} for i in range(MIN)]
    # pause: 40 consecutive rows at velocity < VEL_STOP; HR starts at 160 and drops to 130
    pause_len = Config.Metrics.MIN_PAUSE_SEC + 10  # 40s > 30s minimum
    pause = [
        {
            "time_offset": MIN + i,
            "heartrate": max(130, 160 - i),  # drops from 160 towards 130
            "velocity": STOP - 0.01,  # below stop threshold
        }
        for i in range(pause_len)
    ]
    rows_with_pause = moving + pause

    result = calc_hr_recovery(rows_with_pause)
    assert result is not None, "Should detect the pause and return HrRecovery"
    assert result.pauses_found >= 1
    assert result.total_rest_sec > 0
    assert result.median_rate is not None
    print(f"  OK: calc_hr_recovery — pauses={result.pauses_found}, rest={result.total_rest_sec}s")


def test_calc_hr_recovery_dedups_then_rechecks_guard():
    """calc_hr_recovery de-duplicates time_offset and re-checks the sufficiency guard.

    Regression for WR-01: rows are keyed by time_offset (collapsing duplicates).
    If the raw row count passes the MIN_STREAM_POINTS guard but the *de-duplicated*
    count does not, the function must re-fire the guard and return None — not run
    the pause math over fewer points than the first guard validated, and not crash.
    """
    MIN = Config.Metrics.MIN_STREAM_POINTS
    STOP = Config.Thresholds.VEL_STOP

    # Raw count >= MIN (passes first guard) but only MIN-1 UNIQUE offsets after
    # de-dup (must fail the re-check). Crucially the fixture CONTAINS a real pause:
    # without the re-check, the pause math would run over MIN-1 points and return a
    # (statistically invalid) HrRecovery. The WR-01 re-check is the only thing that
    # turns this into None — so a None result proves the re-check fired.
    unique_count = MIN - 1  # 119 unique offsets (< MIN=120)
    moving_part = unique_count - 39  # 80 moving offsets
    dupy = []
    for off in range(moving_part):
        for _ in range(2):  # duplicate each offset -> raw >= MIN
            dupy.append({"time_offset": off, "heartrate": 160, "velocity": 3.0})
    for k in range(39):  # 39s pause (>= MIN_PAUSE_SEC) within unique set
        off = moving_part + k
        for _ in range(2):
            dupy.append({"time_offset": off, "heartrate": max(130, 160 - k), "velocity": STOP - 0.01})
    assert len(dupy) >= MIN, "fixture must pass the raw-length guard"
    assert len({r["time_offset"] for r in dupy}) == unique_count < MIN
    assert calc_hr_recovery(dupy) is None, (
        "must return None when de-duplicated offsets fall below MIN_STREAM_POINTS "
        "(the re-check must fire even though a pause is present)"
    )

    # Duplicates present but enough UNIQUE offsets AND a real pause: must still
    # compute without crashing (dict-keying picks one row per offset).
    moving = [{"time_offset": i, "heartrate": 160, "velocity": 3.0} for i in range(MIN)]
    pause = [
        {"time_offset": MIN + i, "heartrate": max(130, 160 - i), "velocity": STOP - 0.01}
        for i in range(Config.Metrics.MIN_PAUSE_SEC + 10)
    ]
    with_dups = moving + moving[:20] + pause  # 20 duplicate offsets, unique still >= MIN
    result = calc_hr_recovery(with_dups)
    assert result is not None, "duplicates with sufficient unique offsets must still compute"
    assert result.pauses_found >= 1
    print("  OK: calc_hr_recovery WR-01 — dedup re-check + duplicate-tolerant path")


def test_calc_hr_recovery_start_window_confined_to_pause():
    """calc_hr_recovery's start-HR window never bleeds into post-pause moving rows.

    Regression for WR-02: the start window is sliced from pause_window
    (all_times[pause_start_idx:end_idx+1]), so the first-5s average is taken over
    pause samples only. A pause immediately followed by HIGH-HR moving rows must
    not pull hr_start upward. Sentinel HR=250 on the post-pause rows makes any
    contamination obvious in the resulting rate.
    """
    MIN = Config.Metrics.MIN_STREAM_POINTS
    STOP = Config.Thresholds.VEL_STOP

    moving = [{"time_offset": i, "heartrate": 160, "velocity": 3.0} for i in range(MIN)]
    # 40s contiguous pause (offsets MIN..MIN+39): HR 158 at start window, 123 at end window.
    pause = []
    for i in range(40):
        if i < 5:
            hr = 158  # first-5 window
        elif i >= 35:
            hr = 123  # last-5 window
        else:
            hr = 140  # middle (ignored by start/end avgs)
        pause.append({"time_offset": MIN + i, "heartrate": hr, "velocity": STOP - 0.01})
    # Post-pause moving rows with sentinel HR that MUST NOT enter the start window.
    post = [{"time_offset": MIN + 40 + i, "heartrate": 250, "velocity": 3.0} for i in range(20)]

    result = calc_hr_recovery(moving + pause + post)
    assert result is not None
    assert result.pauses_found == 1
    # drop = 158 - 123 = 35; sampled_rest_sec = len(pause_window) = 40; rate = 35/(40/60) = 52.5
    assert result.median_rate == 52.5, (
        f"start window must be pause-confined (drop≈35 → rate 52.5); got {result.median_rate}. "
        "A higher value means the HR=250 post-pause rows leaked into hr_start."
    )
    print(f"  OK: calc_hr_recovery WR-02 — start window confined to pause (rate={result.median_rate})")


def test_calc_hr_recovery_rate_uses_sampled_rest_seconds():
    """calc_hr_recovery divides the HR drop by sampled rest seconds, not wall-clock span.

    Regression for WR-05: the inner loop tolerates gaps up to 3s, so the wall-clock
    pause_dur over-counts real rest seconds. The rate denominator is
    len(pause_window) (the count of actually-sampled points), not pause_dur.

    Fixture: a pause sampled every 2s (gaps within the 3s tolerance). 16 points
    span 120..150 → wall-clock pause_dur = 30s but only 16 sampled seconds.
    drop = 150 - 120 = 30.
      new (correct): 30 / (16/60) = 112.5 bpm/min
      old (buggy):   30 / (30/60) =  60.0 bpm/min
    """
    MIN = Config.Metrics.MIN_STREAM_POINTS

    moving = [{"time_offset": i, "heartrate": 150, "velocity": 3.0} for i in range(MIN)]
    # Pause sampled every 2s: offsets 120,122,...,150 → 16 points, spans 30s.
    pause = []
    offsets = list(range(MIN, MIN + 31, 2))  # 120,122,...,150 = 16 points
    assert len(offsets) == 16
    for k, off in enumerate(offsets):
        if k < 5:
            hr = 150  # first-5 window avg = 150
        elif k >= 11:
            hr = 120  # last-5 window avg = 120
        else:
            hr = 135  # middle
        pause.append({"time_offset": off, "heartrate": hr, "velocity": 0.0})
    # Terminate the pause with a moving row 1s later (gap 1 <= 3, but velocity breaks it).
    post = [{"time_offset": MIN + 31 + i, "heartrate": 140, "velocity": 3.0} for i in range(10)]

    result = calc_hr_recovery(moving + pause + post)
    assert result is not None
    assert result.pauses_found == 1
    assert result.median_rate == 112.5, (
        f"rate must use sampled rest seconds (16 → 112.5), not wall-clock 30s (→ 60.0); got {result.median_rate}"
    )
    print(f"  OK: calc_hr_recovery WR-05 — sampled-seconds denominator (rate={result.median_rate})")


# ─── calc_vertical_speed ───


def test_calc_vertical_speed():
    """calc_vertical_speed(rows): None guards and ascending return."""
    # Insufficient rows
    rows_short = _make_altitude_rows(Config.Metrics.MIN_ALT_POINTS - 1)
    assert calc_vertical_speed(rows_short) is None, "Should return None for < MIN_ALT_POINTS rows"

    # Duration too short (< 0.05 hours = < 3 min)
    # 60 rows at 1s intervals = 1 min elapsed (time_offset 0..590)
    rows_short_time = [{"time_offset": i, "altitude": 100.0 + i} for i in range(Config.Metrics.MIN_ALT_POINTS)]
    # last time_offset = MIN_ALT_POINTS - 1 seconds; for MIN_ALT_POINTS=60 → 59s → 0.016h < 0.05
    assert calc_vertical_speed(rows_short_time) is None, "Should return None when duration < 0.05h"

    # Good data: MIN_ALT_POINTS rows over >3 min, ascending
    # Use time_offset spaced 10s apart so total = (n-1)*10 seconds
    rows_ok = _make_altitude_rows(Config.Metrics.MIN_ALT_POINTS + 10, ascent_per_step=2.0)
    # total time = (MIN_ALT_POINTS + 9) * 10 seconds
    result = calc_vertical_speed(rows_ok)
    assert result is not None
    assert result.vmh > 0
    assert result.total_ascent_m > 0
    print(f"  OK: calc_vertical_speed — vmh={result.vmh}, ascent={result.total_ascent_m}m")


def test_calc_vertical_speed_nonzero_leading_offset():
    """calc_vertical_speed uses the elapsed span, not the absolute last time_offset.

    Regression for CR-01: altitude sampling may begin partway into the activity
    (the leading samples have NULL altitude and are filtered out by the repository
    query). The denominator must be (last - first) time_offset, not last alone.

    Window: altitude present only for time_offset 1800..3600 (a 30-min climb,
    30 min into a ride). The true elapsed span is (3600 - 1800) = 1800s = 0.5h,
    not 3600s = 1.0h. With the absolute-offset bug the reported vmh is HALF the
    true ascent rate.
    """
    n = Config.Metrics.MIN_ALT_POINTS + 10
    # Spread n rows evenly across the 1800..3600 window (10s spacing), each +2.0 m.
    rows = [{"time_offset": 1800 + i * 10, "altitude": 100.0 + i * 2.0} for i in range(n)]
    span_sec = rows[-1]["time_offset"] - rows[0]["time_offset"]
    elapsed_hours = span_sec / 3600
    total_ascent = (n - 1) * 2.0
    expected_vmh = round(total_ascent / elapsed_hours, 0)

    result = calc_vertical_speed(rows)
    assert result is not None
    # The buggy implementation divides by rows[-1]['time_offset']/3600 (the
    # absolute offset including the 1800s lead-in), which inflates the
    # denominator and roughly halves vmh.
    assert result.duration_hours == round(elapsed_hours, 2), (
        f"duration_hours must be the elapsed span {round(elapsed_hours, 2)}h, got {result.duration_hours}h"
    )
    assert result.vmh == int(expected_vmh), (
        f"vmh must be computed over the elapsed span: expected {int(expected_vmh)}, got {result.vmh}"
    )
    print(f"  OK: calc_vertical_speed nonzero-offset — vmh={result.vmh}, duration={result.duration_hours}h")


# ─── calc_cardiac_drift ───


def test_calc_cardiac_drift():
    """calc_cardiac_drift(rows, sport_type=None): None guards and result shape."""
    # Insufficient rows
    rows_short = _make_hr_vel_rows(Config.Metrics.MIN_STREAM_POINTS - 1)
    assert calc_cardiac_drift(rows_short) is None, "Should return None for < MIN_STREAM_POINTS rows"

    # Sufficient rows — expect a CardiacDriftResult (drift_pct may be None on low-quality data)
    rows_ok = _make_hr_vel_rows(Config.Metrics.MIN_STREAM_POINTS + 50, velocity=3.0, heartrate=145)
    result = calc_cardiac_drift(rows_ok)
    assert result is not None, "Should return CardiacDriftResult for sufficient data"
    # Result fields must be present (values may vary based on algorithm)
    assert hasattr(result, "drift_pct")
    assert hasattr(result, "is_significant")
    assert hasattr(result, "quality")

    # sport_type kwarg accepted — does not crash
    result2 = calc_cardiac_drift(rows_ok, sport_type="Run")
    assert result2 is not None
    print(f"  OK: calc_cardiac_drift — drift_pct={result.drift_pct}, quality={result.quality}")


# ─── calc_hrr_pct ───


def test_calc_hrr_pct():
    """calc_hrr_pct(median_hr, hr_rest, hr_max): None guards and formula."""
    # Any None input → None
    assert calc_hrr_pct(None, 50, 200) is None
    assert calc_hrr_pct(150, None, 200) is None
    assert calc_hrr_pct(150, 50, None) is None
    assert calc_hrr_pct(None, None, None) is None

    # hr_max <= hr_rest → None
    assert calc_hrr_pct(150, 200, 200) is None  # equal
    assert calc_hrr_pct(150, 210, 200) is None  # hr_rest > hr_max

    # Known value: (150 - 50) / (200 - 50) * 100 = 100/150 * 100 = 66.666... → 66.7
    result = calc_hrr_pct(150, 50, 200)
    assert result == 66.7, f"Expected 66.7, got {result}"

    # Additional sanity: low effort
    low = calc_hrr_pct(80, 50, 200)  # (80-50)/(200-50)*100 = 30/150*100 = 20.0
    assert low == 20.0, f"Expected 20.0, got {low}"

    print("  OK: calc_hrr_pct — 66.7 confirmed, None guards pass")
