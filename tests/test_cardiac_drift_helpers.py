"""Unit tests for pure helper functions in mcp_strava.cardiac_drift."""

from mcp_strava.cardiac_drift import _quality_label, _severity_and_significance, extract_contiguous_runs
from mcp_strava.constants import Config

# ─── _severity_and_significance ──────────────────────────────────────────


def test_severity_stable_at_zero():
    """Zero drift is stable and not significant regardless of consistency."""
    severity, is_sig = _severity_and_significance(0.0, 1.0, Config.Drift.THRESHOLD_DEFAULT)
    assert severity == "stable"
    assert is_sig is False


def test_severity_negative_drift_always_stable():
    """Negative drift (warmup settling) is always stable and not significant."""
    severity, is_sig = _severity_and_significance(-5.0, 1.0, Config.Drift.THRESHOLD_DEFAULT)
    assert severity == "stable"
    assert is_sig is False


def test_severity_borderline():
    """Drift between STABLE_MAX and BORDERLINE_MAX is borderline."""
    ad = (Config.Drift.SEVERITY_STABLE_MAX + Config.Drift.SEVERITY_BORDERLINE_MAX) / 2
    severity, _is_sig = _severity_and_significance(ad, 1.0, Config.Drift.THRESHOLD_DEFAULT)
    assert severity == "borderline"


def test_severity_moderate():
    """Drift between BORDERLINE_MAX and MODERATE_MAX is moderate."""
    ad = (Config.Drift.SEVERITY_BORDERLINE_MAX + Config.Drift.SEVERITY_MODERATE_MAX) / 2
    severity, _is_sig = _severity_and_significance(ad, 1.0, Config.Drift.THRESHOLD_DEFAULT)
    assert severity == "moderate"


def test_severity_significant():
    """Drift between MODERATE_MAX and SIGNIFICANT_MAX is significant severity."""
    ad = (Config.Drift.SEVERITY_MODERATE_MAX + Config.Drift.SEVERITY_SIGNIFICANT_MAX) / 2
    severity, _is_sig = _severity_and_significance(ad, 1.0, Config.Drift.THRESHOLD_DEFAULT)
    assert severity == "significant"


def test_severity_severe():
    """Drift above SIGNIFICANT_MAX is severe."""
    ad = Config.Drift.SEVERITY_SIGNIFICANT_MAX + 1.0
    severity, _is_sig = _severity_and_significance(ad, 0.0, Config.Drift.THRESHOLD_DEFAULT)
    assert severity == "severe"


def test_severity_boundary_stable_borderline():
    """At SEVERITY_STABLE_MAX the branch is ad < STABLE_MAX (not <=), so 3.0 is borderline."""
    ad = float(Config.Drift.SEVERITY_STABLE_MAX)
    severity, _is_sig = _severity_and_significance(ad, 1.0, Config.Drift.THRESHOLD_DEFAULT)
    assert severity == "borderline"

    # Just below STABLE_MAX should still be stable.
    severity_below, _ = _severity_and_significance(ad - 0.01, 1.0, Config.Drift.THRESHOLD_DEFAULT)
    assert severity_below == "stable"


def test_significance_depends_on_consistency():
    """is_significant is False when consistency is below MIN_DRIFT_CONSISTENCY even if drift exceeds threshold."""
    ad = Config.Drift.THRESHOLD_DEFAULT + 2.0
    _severity, is_sig = _severity_and_significance(
        ad, Config.Drift.MIN_DRIFT_CONSISTENCY - 0.1, Config.Drift.THRESHOLD_DEFAULT
    )
    assert is_sig is False


def test_significance_both_conditions_required():
    """is_significant is True only when drift >= threshold AND consistency >= MIN_DRIFT_CONSISTENCY."""
    ad = Config.Drift.THRESHOLD_DEFAULT + 1.0
    _severity, is_sig = _severity_and_significance(
        ad, Config.Drift.MIN_DRIFT_CONSISTENCY, Config.Drift.THRESHOLD_DEFAULT
    )
    assert is_sig is True


def test_significance_false_below_threshold():
    """is_significant is False when drift is below the sport-specific threshold even with high consistency."""
    _severity, is_sig = _severity_and_significance(
        Config.Drift.THRESHOLD_DEFAULT - 0.1, 1.0, Config.Drift.THRESHOLD_DEFAULT
    )
    assert is_sig is False


# ─── _quality_label ──────────────────────────────────────────────────────


def test_quality_good_large_duration():
    """Duration >= QUALITY_GOOD_S (600s) returns good."""
    # One cluster with segments totalling >= 600s
    segments_by_cluster = [[(0, Config.Drift.QUALITY_GOOD_S, Config.Drift.QUALITY_GOOD_S)]]
    assert _quality_label(segments_by_cluster, subsample_step=1) == "good"


def test_quality_fair_mid_duration():
    """Duration between FAIR and GOOD thresholds returns fair."""
    dur = (Config.Drift.QUALITY_FAIR_S + Config.Drift.QUALITY_GOOD_S) // 2
    segments_by_cluster = [[(0, dur, dur)]]
    assert _quality_label(segments_by_cluster, subsample_step=1) == "fair"


def test_quality_low_short_duration():
    """Duration < QUALITY_FAIR_S (300s) returns low."""
    segments_by_cluster = [[(0, Config.Drift.QUALITY_FAIR_S - 1, Config.Drift.QUALITY_FAIR_S - 1)]]
    assert _quality_label(segments_by_cluster, subsample_step=1) == "low"


def test_quality_multiple_clusters():
    """Quality sums duration across all clusters."""
    half = Config.Drift.QUALITY_GOOD_S // 2
    segments_by_cluster = [
        [(0, half, half)],
        [(half, half * 2, half)],
    ]
    assert _quality_label(segments_by_cluster, subsample_step=1) == "good"


def test_quality_subsample_step_scales_duration():
    """Subsampling step applies to each segment duration."""
    segments_by_cluster = [[(0, 10, 10)]]
    # 10 points * subsample_step=30 => 300s => fair threshold
    assert _quality_label(segments_by_cluster, subsample_step=30) == "fair"


def test_quality_uses_segment_duration_not_end_offset():
    """Quality uses (e - s) not the end index; a segment at high offset with short span is low."""
    segments_by_cluster = [[(1000, 1010, 10)]]
    assert _quality_label(segments_by_cluster, subsample_step=1) == "low"


# ─── extract_contiguous_runs ─────────────────────────────────────────────


def test_extract_runs_basic():
    """Basic contiguous True runs are extracted."""
    mask = [True, True, False, True, True, True, False]
    runs = extract_contiguous_runs(mask, min_duration=1)
    assert runs == [(0, 2, 2), (3, 6, 3)]


def test_extract_runs_min_duration_filters():
    """Runs shorter than min_duration are excluded."""
    mask = [True, True, False, True, True, True]
    runs = extract_contiguous_runs(mask, min_duration=3)
    assert runs == [(3, 6, 3)]


def test_extract_runs_no_runs():
    """All-False mask returns empty list."""
    assert extract_contiguous_runs([False, False, False]) == []


def test_extract_runs_all_true():
    """All-True mask returns one run covering the entire span."""
    assert extract_contiguous_runs([True, True, True], min_duration=1) == [(0, 3, 3)]


def test_extract_runs_empty_mask():
    """Empty mask returns empty list."""
    assert extract_contiguous_runs([]) == []


def test_extract_runs_single_element():
    """Single True element at min_duration=1 is extracted."""
    assert extract_contiguous_runs([True], min_duration=1) == [(0, 1, 1)]


def test_extract_runs_single_element_filtered():
    """Single True element is excluded when min_duration > 1."""
    assert extract_contiguous_runs([True], min_duration=2) == []


def test_extract_runs_boundary_from_plan():
    """Original test plan: empty mask, all-true, boundary at min_duration."""
    assert extract_contiguous_runs([], min_duration=60) == []
    assert extract_contiguous_runs([True] * 100, min_duration=1) == [(0, 100, 100)]
    # Exactly at min_duration: included
    assert extract_contiguous_runs([True] * 60, min_duration=60) == [(0, 60, 60)]
    # One below min_duration: excluded
    assert extract_contiguous_runs([True] * 59, min_duration=60) == []
