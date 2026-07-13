"""Unit-тесты для чистых вспомогательных функций из mcp_strava.cardiac_drift.

Все тесты детерминированы, без зависимостей от БД, сети, времени или случайности.
"""

from mcp_strava.cardiac_drift import (
    _quality_label,
    _resolve_segments,
    _severity_and_significance,
    extract_contiguous_runs,
)
from mcp_strava.constants import Config


class TestExtractContiguousRuns:
    def test_empty_list(self):
        assert extract_contiguous_runs([]) == []

    def test_all_false(self):
        assert extract_contiguous_runs([False] * 10) == []

    def test_all_true_below_min_duration(self):
        assert extract_contiguous_runs([True] * 30, min_duration=60) == []

    def test_single_run_at_min_duration(self):
        runs = extract_contiguous_runs([True] * 60, min_duration=60)
        assert runs == [(0, 60, 60)]

    def test_single_run_above_min_duration(self):
        runs = extract_contiguous_runs([True] * 100, min_duration=60)
        assert runs == [(0, 100, 100)]

    def test_multiple_runs(self):
        mask = [True] * 3 + [False] * 3 + [True] * 80 + [False] + [True] * 5
        runs = extract_contiguous_runs(mask, min_duration=3)
        assert len(runs) == 3
        assert runs[0] == (0, 3, 3)
        assert runs[1] == (6, 86, 80)
        assert runs[2] == (87, 92, 5)

    def test_run_at_end_of_list(self):
        mask = [False] * 5 + [True] * 3
        runs = extract_contiguous_runs(mask, min_duration=3)
        assert runs == [(5, 8, 3)]

    def test_single_element_true(self):
        assert extract_contiguous_runs([True], min_duration=1) == [(0, 1, 1)]

    def test_default_min_duration(self):
        runs = extract_contiguous_runs([True] * 60, min_duration=60)
        assert runs == [(0, 60, 60)]


class TestResolveSegments:
    def test_zero_segments_returns_none(self):
        assert _resolve_segments([]) is None

    def test_one_segment_splits_in_half(self):
        segs = _resolve_segments([(0, 100, 100)])
        assert segs is not None
        assert len(segs) == 2
        assert segs[0] == (0, 50, 50)
        assert segs[1] == (50, 100, 50)

    def test_one_segment_odd_duration_splits(self):
        segs = _resolve_segments([(0, 99, 99)])
        assert segs is not None
        assert len(segs) == 2
        assert segs[0] == (0, 49, 49)
        assert segs[1] == (49, 99, 50)

    def test_two_segments_passes_through(self):
        segs = [(0, 50, 50), (50, 100, 50)]
        assert _resolve_segments(segs) == segs

    def test_many_segments_passes_through(self):
        segs = [(0, 50, 50), (50, 100, 50), (100, 150, 50)]
        assert _resolve_segments(segs) == segs

    def test_short_segment_still_splits_and_passes(self):
        segs = _resolve_segments([(0, 3, 3)])
        assert segs is not None
        assert len(segs) == 2


class TestSeverityAndSignificance:
    def test_negative_drift_always_stable_not_significant(self):
        severity, is_significant = _severity_and_significance(-5.0, 1.0, 3.0)
        assert severity == "stable"
        assert is_significant is False

    def test_zero_drift_stable_not_significant(self):
        severity, is_significant = _severity_and_significance(0.0, 1.0, 3.0)
        assert severity == "stable"
        assert is_significant is False

    def test_below_stable_max(self):
        severity, _ = _severity_and_significance(2.0, 1.0, 3.0)
        assert severity == "stable"

    def test_at_stable_max(self):
        severity, _ = _severity_and_significance(3.0, 1.0, 3.0)
        assert severity == "borderline"

    def test_borderline_range(self):
        severity, _ = _severity_and_significance(4.0, 1.0, 3.0)
        assert severity == "borderline"

    def test_at_borderline_max(self):
        severity, _ = _severity_and_significance(5.0, 1.0, 3.0)
        assert severity == "moderate"

    def test_moderate_range(self):
        severity, _ = _severity_and_significance(7.0, 1.0, 3.0)
        assert severity == "moderate"

    def test_at_moderate_max(self):
        severity, _ = _severity_and_significance(8.0, 1.0, 3.0)
        assert severity == "significant"

    def test_significant_range(self):
        severity, _ = _severity_and_significance(10.0, 1.0, 3.0)
        assert severity == "significant"

    def test_at_significant_max(self):
        severity, _ = _severity_and_significance(12.0, 1.0, 3.0)
        assert severity == "severe"

    def test_above_significant_max(self):
        severity, _ = _severity_and_significance(20.0, 1.0, 3.0)
        assert severity == "severe"

    def test_significant_when_above_threshold_and_good_consistency(self):
        drift_threshold = Config.Drift.SEVERITY_STABLE_MAX
        _, is_significant = _severity_and_significance(5.0, 0.8, drift_threshold)
        assert is_significant is True

    def test_not_significant_when_below_threshold(self):
        drift_threshold = Config.Drift.SEVERITY_SIGNIFICANT_MAX
        _, is_significant = _severity_and_significance(5.0, 0.8, drift_threshold)
        assert is_significant is False

    def test_not_significant_when_low_consistency(self):
        drift_threshold = Config.Drift.SEVERITY_STABLE_MAX
        _, is_significant = _severity_and_significance(5.0, Config.Drift.MIN_DRIFT_CONSISTENCY - 0.01, drift_threshold)
        assert is_significant is False

    def test_significant_at_consistency_boundary(self):
        drift_threshold = Config.Drift.SEVERITY_STABLE_MAX
        _, is_significant = _severity_and_significance(5.0, Config.Drift.MIN_DRIFT_CONSISTENCY, drift_threshold)
        assert is_significant is True


class TestQualityLabel:
    def test_good_quality_at_threshold(self):
        label = _quality_label([[(0, 600, 600)]], subsample_step=1)
        assert label == "good"

    def test_good_quality_above_threshold(self):
        label = _quality_label([[(0, 1000, 1000)]], subsample_step=1)
        assert label == "good"

    def test_fair_quality_at_threshold(self):
        label = _quality_label([[(0, 300, 300)]], subsample_step=1)
        assert label == "fair"

    def test_fair_quality_between_boundaries(self):
        label = _quality_label([[(0, 500, 500)]], subsample_step=1)
        assert label == "fair"

    def test_low_quality_below_fair_threshold(self):
        label = _quality_label([[(0, 200, 200)]], subsample_step=1)
        assert label == "low"

    def test_empty_segments_quality_low(self):
        label = _quality_label([], subsample_step=1)
        assert label == "low"

    def test_quality_with_subsample_step(self):
        label = _quality_label([[(0, 10, 10), (10, 20, 10)]], subsample_step=30)
        assert label == "good"

    def test_quality_multiple_clusters(self):
        label = _quality_label(
            [
                [(0, 100, 100)],
                [(100, 200, 100)],
            ],
            subsample_step=2,
        )
        assert label == "fair"
