from __future__ import annotations

import itertools

import duckdb
import pytest

from mcp_strava.adapters.duckdb.stream_metric_queries import activity_trimp
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
    assert all(earlier < later for earlier, later in itertools.pairwise(bounds))


def test_unknown_model_raises_with_known_ids() -> None:
    with pytest.raises(ValueError, match="Unknown HR zone model"):
        get_zone_model("threshold_lactate")


def test_hr_max_must_exceed_hr_rest() -> None:
    with pytest.raises(ValueError, match="must be greater than"):
        KarvonenHRR().zone_bounds(hr_max=50, hr_rest=50)


def test_known_model_ids_includes_karvonen() -> None:
    assert "karvonen_hrr" in known_model_ids()


def test_get_zone_model_happy_path() -> None:
    """get_zone_model("karvonen_hrr") returns a working KarvonenHRR instance."""
    model = get_zone_model("karvonen_hrr")
    assert model.identifier == "karvonen_hrr"
    assert model.zone_bounds(hr_max=191, hr_rest=53) == [122, 136, 150, 163, 177, 300]


def test_zone_bounds_with_explicit_model_id() -> None:
    """zone_bounds with an explicit model_id kwarg produces the same bounds."""
    assert zone_bounds(191, 53, model_id="karvonen_hrr") == [122, 136, 150, 163, 177, 300]


def test_zone_bounds_with_invalid_model_id_raises() -> None:
    """zone_bounds with an unknown model_id propagates the ValueError."""
    with pytest.raises(ValueError, match="Unknown HR zone model"):
        zone_bounds(191, 53, model_id="threshold_lactate")


def test_known_model_ids_returns_sorted_tuple() -> None:
    """known_model_ids returns a sorted tuple with the expected entries."""
    ids = known_model_ids()
    assert isinstance(ids, tuple)
    assert ids == tuple(sorted(ids))
    assert "karvonen_hrr" in ids


def test_karvonen_percentages() -> None:
    """KarvonenHRR.PERCENTAGES must match the documented zone thresholds."""
    assert KarvonenHRR.PERCENTAGES == (0.50, 0.60, 0.70, 0.80, 0.90)


# ── Task 2 additions ──────────────────────────────────────────────────────────


def test_build_trimp_sql_identity() -> None:
    """build_trimp_sql(bounds) produces the expected SQL structure."""
    from mcp_strava.adapters.duckdb.trimp_sql import build_trimp_sql

    sql = build_trimp_sql([122, 136, 150, 163, 177, 300])
    assert "/ 60.0 as trimp" in sql
    assert "122" in sql
    assert "177" in sql
    # Must not reference any Config symbol
    assert "Config" not in sql


def test_build_trimp_sql_alias() -> None:
    """build_trimp_sql with alias='s.' prefixes column references."""
    from mcp_strava.adapters.duckdb.trimp_sql import build_trimp_sql

    sql_plain = build_trimp_sql([122, 136, 150, 163, 177, 300], alias="")
    sql_s = build_trimp_sql([122, 136, 150, 163, 177, 300], alias="s.")
    assert "s.heartrate" in sql_s
    assert "heartrate" in sql_plain
    assert "s.heartrate" not in sql_plain


def test_trimp_regression() -> None:
    """activity_trimp(bounds) for a known HR fixture matches the manual formula.

    Formula (Karvonen TRIMP, hr_rest=53, hr_max=191):
      bounds = [122, 136, 150, 163, 177, 300]
      COEFF  = [0.5, 1, 2, 3, 4, 5]
      10 stream rows at heartrate=160 → all fall in z4 (163 boundary: >= 150 AND < 163? No.
        160 >= 150 and 160 < 163 → z3 (index 2, coeff=2)
        Wait: z1 = HR < 122 (coeff 0.5)
              z2 = 122 <= HR < 136 (coeff 1)
              z3 = 136 <= HR < 150 (coeff 2)
              z4 = 150 <= HR < 163 (coeff 3)
              z5 = HR >= 163 ... but bounds[-2]=177, so z5 = HR >= 177 (coeff 5)?
        Actually the SQL uses: z1=<b[0], z2=b[0]..b[1], ..., z5=>=b[-2]
        So bounds[-2] = 177, z5 = HR >= 177
        For HR=160: 150 <= 160 < 163 → wait, b = [122,136,150,163,177,300]
          zone z1: HR < 122
          zone z2: 122 <= HR < 136
          zone z3: 136 <= HR < 150
          zone z4: 150 <= HR < 163  (coeff index 3 = 3)
          zone z5: HR >= 177        (coeff index 5 = 5)
          (zone between 163..177 is also z5 bucket? No — original code has 5 zones total)
        The _build_trimp_cases generates 6 zones (len(b)=6) but the last is ">=b[-2]"
        which is >= 177. Heartrate=160 falls into range 150..163 (z4, coeff=3).
        Reference: 10 rows * coeff 3 = 30 seconds-weighted / 60 = 0.5 TRIMP.
    """
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository
    from mcp_strava.adapters.duckdb.schema import create_schema

    conn = duckdb.connect()
    create_schema(conn)

    # Insert one activity
    conn.execute(
        "INSERT INTO activities (id, activity_day, name, sport_type, distance, "
        "moving_time, elapsed_time, total_elevation_gain, summary_json, synced_at) "
        "VALUES (1, '2026-01-01', 'Test', 'Run', 5000, 1800, 1800, 0, '{}', '2026-01-01T09:00:00')"
    )
    # 10 stream rows all at heartrate=160 (falls in zone 150..163, coeff=3)
    for i in range(10):
        conn.execute(
            "INSERT INTO streams (activity_id, time_offset, heartrate) VALUES (1, ?, ?)",
            [i, 160],
        )

    repo = DuckDBRepository.from_connection(conn)
    bounds = [122, 136, 150, 163, 177, 300]
    result = activity_trimp(repo, 1, bounds=bounds)

    # Manual: 10 rows in z4 (coeff=3) → 10 * 3 / 60 = 0.5
    assert result == pytest.approx(0.5, abs=0.01), f"Expected ~0.5 but got {result}"
