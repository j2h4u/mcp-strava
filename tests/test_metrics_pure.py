"""Unit tests for pure metric functions in mcp_strava.metrics.

All tests use plain dict rows — no database connection, no repository.
"""

from mcp_strava.constants import Config
from mcp_strava.metrics import (
    calc_hr_recovery,
    calc_vertical_speed,
    calc_cardiac_drift,
    calc_hrr_pct,
)


# ─── Helpers ───

def _make_hr_vel_time_rows(n, velocity=3.0, heartrate=140, time_offset_start=0):
    """Build n stream rows with {time_offset, heartrate, velocity}."""
    return [
        {'time_offset': time_offset_start + i, 'heartrate': heartrate, 'velocity': velocity}
        for i in range(n)
    ]


def _make_altitude_rows(n, altitude_start=100.0, ascent_per_step=1.0, time_offset_start=0):
    """Build n stream rows with {time_offset, altitude}."""
    return [
        {'time_offset': time_offset_start + i * 10, 'altitude': altitude_start + i * ascent_per_step}
        for i in range(n)
    ]


def _make_hr_vel_rows(n, velocity=3.0, heartrate=140):
    """Build n stream rows with {heartrate, velocity} (no time_offset)."""
    return [{'heartrate': heartrate, 'velocity': velocity} for _ in range(n)]


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
    moving = [{'time_offset': i, 'heartrate': 160, 'velocity': 3.0} for i in range(MIN)]
    # pause: 40 consecutive rows at velocity < VEL_STOP; HR starts at 160 and drops to 130
    pause_len = Config.Metrics.MIN_PAUSE_SEC + 10  # 40s > 30s minimum
    pause = [
        {
            'time_offset': MIN + i,
            'heartrate': max(130, 160 - i),  # drops from 160 towards 130
            'velocity': STOP - 0.01,         # below stop threshold
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


# ─── calc_vertical_speed ───

def test_calc_vertical_speed():
    """calc_vertical_speed(rows): None guards and ascending return."""
    # Insufficient rows
    rows_short = _make_altitude_rows(Config.Metrics.MIN_ALT_POINTS - 1)
    assert calc_vertical_speed(rows_short) is None, "Should return None for < MIN_ALT_POINTS rows"

    # Duration too short (< 0.05 hours = < 3 min)
    # 60 rows at 1s intervals = 1 min elapsed (time_offset 0..590)
    rows_short_time = [
        {'time_offset': i, 'altitude': 100.0 + i}
        for i in range(Config.Metrics.MIN_ALT_POINTS)
    ]
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
    rows = [
        {'time_offset': 1800 + i * 10, 'altitude': 100.0 + i * 2.0}
        for i in range(n)
    ]
    span_sec = rows[-1]['time_offset'] - rows[0]['time_offset']
    elapsed_hours = span_sec / 3600
    total_ascent = (n - 1) * 2.0
    expected_vmh = round(total_ascent / elapsed_hours, 0)

    result = calc_vertical_speed(rows)
    assert result is not None
    # The buggy implementation divides by rows[-1]['time_offset']/3600 (the
    # absolute offset including the 1800s lead-in), which inflates the
    # denominator and roughly halves vmh.
    assert result.duration_hours == round(elapsed_hours, 2), (
        f"duration_hours must be the elapsed span {round(elapsed_hours, 2)}h, "
        f"got {result.duration_hours}h"
    )
    assert result.vmh == int(expected_vmh), (
        f"vmh must be computed over the elapsed span: expected {int(expected_vmh)}, "
        f"got {result.vmh}"
    )
    print(f"  OK: calc_vertical_speed nonzero-offset — vmh={result.vmh}, "
          f"duration={result.duration_hours}h")


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
    assert hasattr(result, 'drift_pct')
    assert hasattr(result, 'is_significant')
    assert hasattr(result, 'quality')

    # sport_type kwarg accepted — does not crash
    result2 = calc_cardiac_drift(rows_ok, sport_type='Run')
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

    print(f"  OK: calc_hrr_pct — 66.7 confirmed, None guards pass")
