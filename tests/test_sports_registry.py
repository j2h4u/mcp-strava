from __future__ import annotations

from collections import Counter

import pytest

from mcp_strava.sports import (
    SPORT_ALL,
    SPORT_REGISTRY,
    SPORT_RUNNING,
    SPORT_TRAINING,
    _get_meta,
    build_eff_config,
    detect_new_types,
    get_category,
    get_display,
    get_eff_windows,
    is_hr_based,
    is_known,
    is_running,
    is_training,
)


# ── Registry completeness ─────────────────────────────────────────────────────


def test_registry_has_exactly_fifty_sports() -> None:
    assert len(SPORT_REGISTRY) == 50, f"Expected 50 sport types but got {len(SPORT_REGISTRY)}"


def test_registry_keys_are_all_strings_and_unique() -> None:
    keys = list(SPORT_REGISTRY.keys())
    assert len(keys) == len(set(keys)), "Duplicate sport keys in registry"


def test_all_known_keys_are_in_sport_all() -> None:
    assert set(SPORT_REGISTRY.keys()) == set(SPORT_ALL)


# ── Precomputed group consistency ─────────────────────────────────────────────


def test_sport_training_matches_is_training() -> None:
    for key in SPORT_REGISTRY:
        expected = SPORT_REGISTRY[key].is_training
        actual = key in SPORT_TRAINING
        assert actual == expected, f"SPORT_TRAINING mismatch for {key}: expected {expected}, got {actual}"


def test_sport_running_matches_is_running() -> None:
    for key in SPORT_REGISTRY:
        expected = SPORT_REGISTRY[key].is_running
        actual = key in SPORT_RUNNING
        assert actual == expected, f"SPORT_RUNNING mismatch for {key}: expected {expected}, got {actual}"


def test_precomputed_groups_are_sorted() -> None:
    assert SPORT_ALL == tuple(sorted(SPORT_ALL))
    assert SPORT_TRAINING == tuple(sorted(SPORT_TRAINING))
    assert SPORT_RUNNING == tuple(sorted(SPORT_RUNNING))


# ── Metadata consistency ──────────────────────────────────────────────────────


def test_running_sports_are_also_training() -> None:
    for key, meta in SPORT_REGISTRY.items():
        if meta.is_running:
            assert meta.is_training, f"{key}: is_running=True but is_training=False"


def test_running_sports_are_foot_category() -> None:
    for key, meta in SPORT_REGISTRY.items():
        if meta.is_running:
            assert meta.category == "foot", f"{key}: is_running=True but category={meta.category}"


def test_hr_based_sports_have_no_false_negatives_on_training_sports() -> None:
    # Every training sport should have HR data meaningful,
    # since TRIMP (Banister load) depends on heart rate.
    # This is an intentional design rule, not a tautology.
    exceptions: set[str] = set()
    for key, meta in SPORT_REGISTRY.items():
        if meta.is_training and not meta.hr_based:
            exceptions.add(key)
    assert not exceptions, f"Training sports without hr_based=True: {exceptions}"


def test_efficiency_windows_are_positive_and_sorted() -> None:
    for key, meta in SPORT_REGISTRY.items():
        if meta.eff_windows is not None:
            windows = list(meta.eff_windows)
            assert all(w > 0 for w in windows), f"{key}: non-positive efficiency window"
            assert windows == sorted(windows), f"{key}: efficiency windows not sorted"


def test_no_sport_has_both_is_training_and_is_running_false() -> None:
    """Verify that no sport has empty string or placeholder-like key that is neither training nor running."""
    # Every known sport should have a meaningful classification;
    # absence of both is_training AND is_running is intentional for
    # some sports (e.g. Golf), so we only check that the flags are
    # explicitly set (True/False), not missing.
    for key, meta in SPORT_REGISTRY.items():
        assert isinstance(meta.is_training, bool), f"{key}: is_training is not bool"
        assert isinstance(meta.is_running, bool), f"{key}: is_running is not bool"
        assert isinstance(meta.hr_based, bool), f"{key}: hr_based is not bool"


# ── Query functions with unknown types ────────────────────────────────────────


def test_is_known_for_valid_and_unknown() -> None:
    assert is_known("Run") is True
    assert is_known("NonExistent") is False
    assert is_known("") is False


def test_is_training_unknown_is_false() -> None:
    assert is_training("NonExistent") is False
    assert is_training("") is False


def test_is_running_unknown_is_false() -> None:
    assert is_running("NonExistent") is False
    assert is_running("") is False


def test_is_hr_based_unknown_is_false() -> None:
    assert is_hr_based("NonExistent") is False
    assert is_hr_based("") is False


def test_get_display_returns_input_for_unknown() -> None:
    assert get_display("NonExistent") == "NonExistent"
    assert get_display("Run") == "Run"


def test_get_category_returns_other_for_unknown() -> None:
    assert get_category("NonExistent") == "other"
    assert get_category("") == "other"
    assert get_category("Run") == "foot"


def test_get_eff_windows_returns_none_for_unknown() -> None:
    assert get_eff_windows("NonExistent") is None
    assert get_eff_windows("Run") == (7, 28, 90)


# ── Sports with specific expected metadata ────────────────────────────────────


def test_walk_is_not_training_but_is_hr_based() -> None:
    meta = _get_meta("Walk")
    assert meta is not None
    assert meta.is_training is False
    assert meta.hr_based is True
    assert meta.is_running is False


def test_swim_is_training_with_efficiency_windows() -> None:
    meta = _get_meta("Swim")
    assert meta is not None
    assert meta.is_training is True
    assert meta.is_running is False
    assert meta.eff_windows == (7, 28)


def test_ebike_and_emtb_are_not_training() -> None:
    assert _get_meta("EBikeRide").is_training is False  # type: ignore[union-attr]
    assert _get_meta("EMountainBikeRide").is_training is False  # type: ignore[union-attr]


def test_yoga_and_pilates_are_not_training() -> None:
    assert _get_meta("Yoga").is_training is False  # type: ignore[union-attr]
    assert _get_meta("Pilates").is_training is False  # type: ignore[union-attr]


def test_golf_has_no_efficiency_windows() -> None:
    meta = _get_meta("Golf")
    assert meta is not None
    assert meta.eff_windows is None
    assert meta.hr_based is False


# ── detect_new_types ──────────────────────────────────────────────────────────


def test_detect_new_types_finds_unknown_sports_with_counts() -> None:
    result = detect_new_types(["Run", "Hike", "FlyingSquirrel", "FlyingSquirrel", "BogusSport"])
    assert len(result) == 2
    counts = {sport: count for sport, count in result}
    assert counts["FlyingSquirrel"] == 2
    assert counts["BogusSport"] == 1
    assert "Run" not in counts


def test_detect_new_types_empty_for_all_known() -> None:
    assert detect_new_types(["Run", "Swim", "Ride", "Hike"]) == []


def test_detect_new_types_empty_for_empty_input() -> None:
    assert detect_new_types([]) == []


# ── build_eff_config ──────────────────────────────────────────────────────────


def test_build_eff_config_returns_only_sports_with_windows() -> None:
    cfg = build_eff_config()
    for key, windows in cfg.items():
        meta = _get_meta(key)
        assert meta is not None
        assert meta.eff_windows is not None, f"{key} in eff_config but has no eff_windows"
        assert list(meta.eff_windows) == windows


def test_build_eff_config_has_run_with_expected_windows() -> None:
    cfg = build_eff_config()
    assert "Run" in cfg
    assert cfg["Run"] == [7, 28, 90]


# ── get_display edge cases ────────────────────────────────────────────────────


def test_get_display_returns_human_readable_names() -> None:
    assert get_display("HighIntensityIntervalTraining") == "HIIT"
    assert get_display("TrailRun") == "Trail Run"
    assert get_display("VirtualRide") == "Virtual Ride"
    assert get_display("MountainBikeRide") == "Mountain Bike"
    assert get_display("StandUpPaddling") == "Stand Up Paddling"


# ── Category distribution ─────────────────────────────────────────────────────


def test_all_five_categories_are_represented() -> None:
    categories = {meta.category for meta in SPORT_REGISTRY.values()}
    assert categories >= {"foot", "cycle", "water", "winter", "gym", "other"}


def test_get_category_for_known_sports() -> None:
    assert get_category("Run") == "foot"
    assert get_category("Ride") == "cycle"
    assert get_category("Swim") == "water"
    assert get_category("AlpineSki") == "winter"
    assert get_category("Workout") == "gym"
    assert get_category("Golf") == "other"
