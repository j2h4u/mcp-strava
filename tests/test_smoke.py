"""Smoke tests for mcp_strava package behavior."""

from datetime import date
from pathlib import Path


def test_imports():
    """All public symbols import without errors — including new Config paths."""
    import mcp_strava.interfaces.mcp_http as mcp_http
    import mcp_strava.metric_registry as metric_registry
    from mcp_strava.application.freshness import get_freshness_service
    from mcp_strava.application.metric_services import get_workout_detail_service, list_workouts_service
    from mcp_strava.application.mirror_coverage import get_mirror_coverage_service
    from mcp_strava.application.product_facts import (
        get_daily_brief_facts_service,
        get_historical_facts_service,
        get_weekly_digest_facts_service,
    )
    from mcp_strava.constants import Config

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

    assert get_daily_brief_facts_service is not None
    assert get_weekly_digest_facts_service is not None
    assert get_historical_facts_service is not None
    assert list_workouts_service is not None
    assert get_workout_detail_service is not None
    assert get_freshness_service is not None
    assert get_mirror_coverage_service is not None
    assert metric_registry is not None
    assert mcp_http is not None
    expected_suffix = str(Path("src") / "mcp_strava" / "types.py")
    assert str(package_types.__file__).endswith(expected_suffix)
    print("  OK: all imports + Config paths verified")


def test_forward_simulate():
    """Pure function: Banister simulation produces expected shape (SimDay dataclasses)."""
    from mcp_strava.constants import Config
    from mcp_strava.training import forward_simulate

    alpha_fatigue = 1 - pow(0.5, 1.0 / Config.Model.Banister.TAU_FATIGUE)
    alpha_fitness = 1 - pow(0.5, 1.0 / Config.Model.Banister.TAU_FITNESS)

    result = forward_simulate(50.0, 25.0, [30, 0, 50, 0, 20], date(2026, 5, 4), alpha_fitness, alpha_fatigue)

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
    assert fatigue_move > fitness_move, (
        f"Fatigue ({fatigue_move:.2f}) should move more than fitness ({fitness_move:.2f})"
    )

    # Rounding: result has 1 decimal
    assert f == round(f, 1)
    assert fa == round(fa, 1)
    print(f"  OK: _sim_one_day — f={f:.1f} fa={fa:.1f} form={form:.1f}")


def test_sports_registry():
    """Sports registry: known types classify correctly, unknown types detected."""
    from mcp_strava.sports import detect_new_types, get_eff_windows, is_running, is_training

    # Known training types
    assert is_training("Run") is True
    assert is_training("Hike") is True
    assert is_training("TrailRun") is True

    # Non-training (not sustained cardio)
    assert is_training("Workout") is True  # generic workout = training per registry
    assert is_training("Walk") is False  # excluded from training metrics

    # Running biomechanics
    assert is_running("Run") is True
    assert is_running("TrailRun") is True
    assert is_running("VirtualRun") is True
    assert is_running("Hike") is False

    # Efficiency windows (returned as tuple)
    assert get_eff_windows("Run") == (7, 28, 90)
    assert get_eff_windows("Walk") == (7, 28)
    assert get_eff_windows("Workout") == (7, 28)

    # Unknown type detection — returns [(sport_type, count), ...]
    unknown = detect_new_types(["Run", "Hike", "FlyingSquirrel"])
    assert len(unknown) == 1
    assert unknown[0][0] == "FlyingSquirrel"

    unknown2 = detect_new_types(["Run", "Hike", "Walk"])
    assert len(unknown2) == 0
    print("  OK: sports_registry — training, running, eff_windows, detect_new")


def test_settings_loads_defaults_under_pytest(tmp_path):
    from mcp_strava.settings import load_settings

    settings = load_settings(environ={}, project_root=tmp_path)
    assert str(settings.database_path).endswith("data/strava.duckdb")
