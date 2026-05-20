"""Smoke tests for mcp_strava package behavior."""

from datetime import date
from pathlib import Path

import pytest
import sqlite3


def test_imports():
    """All 14 public symbols import without errors — including new Config paths."""
    from mcp_strava.constants import Config
    from mcp_strava.types import DailyReport, WeeklyPlan, BanisterResult, DecouplingResult
    from mcp_strava.types import BySportBreakdown, CompletedDay, PostWeekendSim, SparklineBar
    from mcp_strava.db import DbConn, get_daily_trimp_history
    from mcp_strava.metrics import enrich_activity, calc_decoupling_with_gate, calc_efficiency_factor
    from mcp_strava.training import calc_banister, calc_weekly_plan, forward_simulate, ewma, trend
    from mcp_strava.analytics import weekly_digest
    from mcp_strava.report import daily_report
    from mcp_strava.sync import sync_activities, backfill_activities, RateLimiter
    from mcp_strava.trends import compute_trends

    # Verify Config hierarchy
    assert Config.Model.Banister.TAU_FITNESS == 42
    assert Config.Model.Banister.TAU_FATIGUE == 10
    assert Config.Metrics.MIN_STREAM_POINTS == 120
    assert Config.Metrics.MIN_MOVING_TIME == 300
    assert Config.Metrics.MIN_PAUSE_SEC == 30
    assert Config.Plan.HIKE_TRIMP_TEMPLATE == 515
    assert Config.Plan.TRIMP_EASY == 80
    assert Config.Plan.TRIMP_MEDIUM == 120
    assert Config.Model.PROGRESSIVE_WINDOW == 21
    assert Config.Thresholds.PACE_CV_MAX == 0.25
    assert Config.Plan.Score.TARGET_HIT == 100
    assert Config.Plan.Score.SAFETY_CRITICAL == 30
    import mcp_strava.types as package_types
    expected_suffix = str(Path("src") / "mcp_strava" / "types.py")
    assert str(package_types.__file__).endswith(expected_suffix)
    print("  OK: all imports + Config paths verified")


def test_daily_report():
    """Daily report runs end-to-end: DB → metrics → training → recommendation."""
    db_path = Path("data/strava.db")
    if not db_path.exists():
        pytest.skip("data/strava.db missing; SAFE-04 fail-closed behavior is Phase 2 scope")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='activities'"
        ).fetchone()
    if row is None:
        pytest.skip("data/strava.db missing activities table; SAFE-04 fail-closed behavior is Phase 2 scope")
    from mcp_strava.settings import reset_settings_cache
    reset_settings_cache()
    from mcp_strava.report import daily_report
    report = daily_report()
    assert report is not None, "daily_report() returned None"
    assert report.today, "Report missing today"
    assert report.yesterday, "Report missing yesterday"
    assert len(report.yesterday_activities) >= 0, "yesterday_activities should be a list"
    if report.recommendation:
        assert report.recommendation.confidence in ('low', 'medium', 'high'), \
            f"Invalid confidence: {report.recommendation.confidence}"
    print(f"  OK: {report.today}, {len(report.yesterday_activities)} activities, "
          f"form={report.banister.form if report.banister else 'N/A'}, "
          f"rec={report.recommendation.action if report.recommendation else 'none'}"
          f"({report.recommendation.confidence if report.recommendation else ''})")


def test_forward_simulate():
    """Pure function: Banister simulation produces expected shape (SimDay dataclasses)."""
    from mcp_strava.training import forward_simulate
    from mcp_strava.constants import Config

    alpha_fatigue = 1 - pow(0.5, 1.0 / Config.Model.Banister.TAU_FATIGUE)
    alpha_fitness = 1 - pow(0.5, 1.0 / Config.Model.Banister.TAU_FITNESS)

    result = forward_simulate(50.0, 25.0, [30, 0, 50, 0, 20],
                              date(2026, 5, 4), alpha_fitness, alpha_fatigue)

    assert len(result) == 5
    for day in result:
        assert day.date, "SimDay missing date"
        assert day.fitness is not None
        assert day.fatigue is not None
        assert day.form is not None
        assert day.trimp is not None
        assert abs(day.form - (day.fitness - day.fatigue)) < 0.15
    assert result[-1].fatigue != 25.0, "Fatigue should change with TRIMP input"
    print(f"  OK: {len(result)} days, final form={result[-1].form:.1f}")


# ─── Pure function unit tests ───

def test_ewma():
    """EWMA: empty, single value, decay behavior."""
    from mcp_strava.training import ewma

    # Empty input
    assert ewma({}, tau=7) == {}
    assert ewma({}, tau=42) == {}

    # Single value — EWMA starts from 0, so first value is alpha * val
    r = ewma({"2026-01-01": 100}, tau=7, end_date="2026-01-01")
    assert 5 < r["2026-01-01"] < 15, f"EWMA(100) day 1 ≈ 9.4, got {r['2026-01-01']}"

    # Decay: after 7 days of zeros, EWMA halves (~4.7 = 9.4 × 0.5)
    r = ewma({"2026-01-01": 100}, tau=7, end_date="2026-01-08")
    assert 3 < r["2026-01-08"] < 7, f"Expected ~4.7, got {r['2026-01-08']}"

    # Gaps filled with 0 — EWMA decays toward 0
    r = ewma({"2026-01-01": 100, "2026-01-03": 50}, tau=7, end_date="2026-01-03")
    assert r["2026-01-03"] < 100, "Should decay from 100 through gap day"
    print("  OK: ewma — empty, single, decay, gaps")


def test_form_zone():
    """Form zone classification — boundary values."""
    from mcp_strava.training import _form_zone, _form_zone_short

    # Simplified 3-zone (May 2026)
    assert _form_zone(-31) == 'tired'
    assert _form_zone(-6) == 'tired'
    assert _form_zone(-5) == 'normal'
    assert _form_zone(0) == 'normal'
    assert _form_zone(9) == 'normal'
    assert _form_zone(10) == 'fresh'
    assert _form_zone(50) == 'fresh'

    # Short form
    assert _form_zone_short(-31) == '🟠'
    assert _form_zone_short(5) == '🟢'
    assert _form_zone_short(30) == '🔵'
    print("  OK: _form_zone — 3-zone boundaries correct")


def test_trend():
    """Trend: <4 values, rising, falling, stable, zero denominator."""
    from mcp_strava.training import trend

    # Insufficient data
    assert trend([1, 2, 3]) is None
    assert trend([]) is None

    # Stable (<10% change)
    r = trend([10, 10, 10, 10])
    assert r and r.startswith('→')

    # Rising (>10%)
    r = trend([10, 10, 15, 15])
    assert r and r.startswith('↑')

    # Falling (>10%)
    r = trend([15, 15, 10, 10])
    assert r and r.startswith('↓')

    # Zero denominator (avg of first half = 0)
    assert trend([0, 0, 1, 1]) is None

    # Negative values
    r = trend([-20, -20, -10, -10])
    assert r and r.startswith('↑'), f"Rising (less negative) should be ↑, got {r}"

    # Near-zero values with tiny shift — should be stable (not ↓-100%)
    # avg1 = (−4+3)/2 = −0.5, avg2 = (−5+6)/2 = 0.5, diff = 1pp → noise
    r = trend([-4, 3, -5, 6])
    assert r == '→0%', f"Near-zero tiny shift should be →0%, got {r}"

    # Near-zero values with genuine shift → floor denominator
    # avg1 = (−2+2)/2 = 0.0 → returns None (zero denominator guard)
    # Use avg1 = 3: (−2+8)/2 = 3.0, avg2 = (12+14)/2 = 13.0
    # abs(3) < 5 → near-zero mode, abs_diff = 10 > 5 → pct = 10/5*100 = 200%
    r = trend([-2, 8, 12, 14])
    assert r and r.startswith('↑'), f"Near-zero genuine shift should be ↑, got {r}"
    print("  OK: trend — edges, rise, fall, stable, zero denom, near-zero clamp")


def test_sim_one_day():
    """_sim_one_day: formula correctness, fatigue responds faster than fitness."""
    from mcp_strava.training import _sim_one_day

    # Zero TRIMP — state should decay toward 0
    f, fa, form = _sim_one_day(50.0, 25.0, 0, 0.016, 0.094)
    assert f < 50.0, "Fitness should decay with zero TRIMP"
    assert fa < 25.0, "Fatigue should decay with zero TRIMP"

    # Fatigue decays faster (larger alpha)
    f, fa, form = _sim_one_day(100.0, 100.0, 50, 0.016, 0.094)
    # Both move toward 50, but fatigue moves faster
    fitness_move = abs(f - 100.0)
    fatigue_move = abs(fa - 100.0)
    assert fatigue_move > fitness_move, \
        f"Fatigue ({fatigue_move:.2f}) should move more than fitness ({fitness_move:.2f})"

    # Rounding: result has 1 decimal
    assert f == round(f, 1)
    assert fa == round(fa, 1)
    print(f"  OK: _sim_one_day — f={f:.1f} fa={fa:.1f} form={form:.1f}")


def test_decoupling_invalid():
    """_decoupling_invalid: <2 points, low velocity, high CV, normal."""
    from mcp_strava.metrics import _decoupling_invalid

    # Too few points
    assert _decoupling_invalid([]) is True
    assert _decoupling_invalid([1.5]) is True

    # Standing still (mean < VEL_MOVING=0.3)
    assert _decoupling_invalid([0.1, 0.2]) is True

    # Normal steady pace (CV ~0) — should be valid
    assert _decoupling_invalid([3.0] * 10) is False

    # High variability (run→walk, CV > 0.25)
    # 2.5 m/s (~9 km/h) + 1.0 m/s (~3.6 km/h): mean=1.75, σ≈0.75, CV≈0.43 > 0.25
    assert _decoupling_invalid([2.5, 2.5, 1.0, 1.0]) is True
    print("  OK: _decoupling_invalid — edges, standing, steady, variable")


def test_calc_decoupling():
    """calc_decoupling: empty, insufficient, positive decoupling, negative."""
    from mcp_strava.metrics import calc_decoupling

    # Insufficient rows
    assert calc_decoupling([]) is None
    assert calc_decoupling([{'heartrate': 140, 'velocity': 3.0}]) is None

    # Make 120 rows (minimum): first half faster, second half slower → positive decoupling
    rows = []
    for i in range(120):
        hr = 140 if i < 60 else 150       # HR rises in second half
        vel = 3.0 if i < 60 else 2.8       # pace drops in second half
        rows.append({'heartrate': hr, 'velocity': vel})

    result = calc_decoupling(rows)
    assert result is not None
    assert result.decoupling_pct > 0, f"Expected positive decoupling, got {result.decoupling_pct}"
    print(f"  OK: calc_decoupling — pct={result.decoupling_pct}%")


def test_median_pct_change():
    """median and pct_change: empty, odd/even, None/zero edge cases."""
    from mcp_strava.analytics import median, pct_change

    # median
    assert median([]) is None
    assert median([5]) == 5
    assert median([1, 3]) == 2.0           # even
    assert median([1, 2, 3]) == 2           # odd

    # pct_change
    assert pct_change(None, 100) is None    # curr is None
    assert pct_change(100, None) is None    # prev is None
    assert pct_change(100, 0) is None       # prev is zero
    assert pct_change(120, 100) == 20.0     # +20%
    assert pct_change(80, 100) == -20.0     # -20%
    print("  OK: median + pct_change — all edge cases")


def test_sports_registry():
    """Sports registry: known types classify correctly, unknown types detected."""
    from mcp_strava.sports import is_training, is_running, get_eff_windows, detect_new_types

    # Known training types
    assert is_training('Run') is True
    assert is_training('Hike') is True
    assert is_training('TrailRun') is True

    # Non-training (not sustained cardio)
    assert is_training('Workout') is True   # generic workout = training per registry
    assert is_training('Walk') is False     # excluded from training metrics

    # Running biomechanics
    assert is_running('Run') is True
    assert is_running('TrailRun') is True
    assert is_running('VirtualRun') is True
    assert is_running('Hike') is False

    # Efficiency windows (returned as tuple)
    assert get_eff_windows('Run') == (7, 28, 90)
    assert get_eff_windows('Walk') == (7, 28)
    assert get_eff_windows('Workout') == (7, 28)

    # Unknown type detection — returns [(sport_type, count), ...]
    unknown = detect_new_types(['Run', 'Hike', 'FlyingSquirrel'])
    assert len(unknown) == 1
    assert unknown[0][0] == 'FlyingSquirrel'

    unknown2 = detect_new_types(['Run', 'Hike', 'Walk'])
    assert len(unknown2) == 0
    print("  OK: sports_registry — training, running, eff_windows, detect_new")


def test_settings_loads_defaults_under_pytest(tmp_path):
    from mcp_strava.settings import load_settings

    settings = load_settings(environ={}, project_root=tmp_path)
    assert str(settings.database_path).endswith("data/strava.db")
