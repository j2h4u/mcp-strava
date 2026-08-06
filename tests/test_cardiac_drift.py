"""Unit tests for the public cardiac_drift function in mcp_strava.cardiac_drift.

Tests the raw algorithm directly with custom DriftParams, covering code paths
that the calc_cardiac_drift wrapper (metrics.py) never exercises.
"""

from mcp_strava.cardiac_drift import DriftParams, cardiac_drift

# ─── Flat HR — zero drift ───


def test_cardiac_drift_flat_hr_is_zero_drift():
    """Flat HR at constant pace: every cluster's early/late medians are equal → exactly 0.0 drift."""
    n = 600
    hr = [150] * n
    vel = [3.0] * n

    result = cardiac_drift(heartrate=hr, velocity=vel)

    assert result["drift_weighted_pct"] is not None
    assert result["drift_weighted_pct"] == 0.0, f"flat HR must give 0.0 drift; got {result['drift_weighted_pct']}"
    assert result["severity"] == "stable"
    assert result["is_significant"] is False
    print(f"  OK: flat HR — drift_pct={result['drift_weighted_pct']}, severity={result['severity']}")


# ─── Decreasing HR — negative drift (warmup/settling, not fatigue) ───


def test_cardiac_drift_decreasing_hr_is_negative_drift():
    """Monotonically decreasing HR → negative drift → warmup/settling, never significant.

    Branch coverage for _severity_and_significance: ``if drift_weighted_pct <= 0``
    must return ("stable", False) — this path is never exercised by the wrapper tests
    which only test flat (0.0) and rising (>5%) drift.
    """
    n = 600
    hr = [180.0 - (i / (n - 1)) * 60.0 for i in range(n)]
    vel = [3.0] * n

    result = cardiac_drift(heartrate=hr, velocity=vel)

    assert result["drift_weighted_pct"] is not None
    assert result["drift_weighted_pct"] < 0, (
        f"decreasing HR must give negative drift; got {result['drift_weighted_pct']}"
    )
    assert result["severity"] == "stable"
    assert result["is_significant"] is False
    print(f"  OK: decreasing HR — drift_pct={result['drift_weighted_pct']}, severity={result['severity']}")


# ─── Custom DriftParams — threshold and tuning knobs ───


def test_cardiac_drift_custom_threshold_makes_insignificant():
    """Custom DriftParams with a high drift_threshold_pct makes moderate drift insignificant."""
    n = 600
    hr = [140.0 + (i / (n - 1)) * 30.0 for i in range(n)]
    vel = [3.0] * n

    default_result = cardiac_drift(heartrate=hr, velocity=vel)
    assert default_result["drift_weighted_pct"] is not None
    assert default_result["drift_weighted_pct"] > 0

    custom_result = cardiac_drift(
        heartrate=hr,
        velocity=vel,
        params=DriftParams(drift_threshold_pct=50.0),
    )
    assert custom_result["drift_weighted_pct"] is not None
    assert custom_result["is_significant"] is False, (
        "high threshold must suppress significance for moderate drift"
    )
    print(
        f"  OK: custom threshold — drift_pct={custom_result['drift_weighted_pct']}, "
        f"significant={custom_result['is_significant']}"
    )


# ─── Explicit time_offset ───


def test_cardiac_drift_explicit_time_offset():
    """The function accepts and uses an explicit time_offset without crashing."""
    n = 600
    hr = [150] * n
    vel = [3.0] * n
    time_offset = list(range(0, n * 10, 10))

    result = cardiac_drift(heartrate=hr, velocity=vel, time_offset=time_offset)

    assert result["drift_weighted_pct"] == 0.0
    assert result["severity"] == "stable"
    print(f"  OK: explicit time_offset accepted — drift_pct={result['drift_weighted_pct']}")
