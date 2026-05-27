from __future__ import annotations

import pytest

from mcp_strava.hr_zones import (
    DEFAULT_MODEL_ID,
    ZONE_CAP_BPM,
    KarvonenHRR,
    get_zone_model,
    known_model_ids,
    zone_bounds,
)


def test_karvonen_reproduces_historical_bounds() -> None:
    # hr_rest=53, hr_max=191 must reproduce the previously hard-coded literals
    # so existing TRIMP values are unchanged.
    assert KarvonenHRR().zone_bounds(hr_max=191, hr_rest=53) == [122, 136, 150, 163, 177, 300]


def test_zone_bounds_default_model_is_karvonen() -> None:
    assert DEFAULT_MODEL_ID == "karvonen_hrr"
    assert zone_bounds(191, 53) == [122, 136, 150, 163, 177, 300]


def test_bounds_are_strictly_increasing_and_capped() -> None:
    bounds = zone_bounds(180, 50)
    assert bounds[-1] == ZONE_CAP_BPM
    assert all(earlier < later for earlier, later in zip(bounds, bounds[1:]))


def test_unknown_model_raises_with_known_ids() -> None:
    with pytest.raises(ValueError, match="Unknown HR zone model"):
        get_zone_model("threshold_lactate")


def test_hr_max_must_exceed_hr_rest() -> None:
    with pytest.raises(ValueError, match="must be greater than"):
        KarvonenHRR().zone_bounds(hr_max=50, hr_rest=50)


def test_known_model_ids_includes_karvonen() -> None:
    assert "karvonen_hrr" in known_model_ids()
