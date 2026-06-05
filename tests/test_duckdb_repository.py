from pathlib import Path
from typing import ClassVar

import pytest

from mcp_strava.adapters.duckdb.connection import open_expected_mirror_db, open_fixture_db
from mcp_strava.adapters.duckdb.daily_load_queries import (
    daily_load_points_between,
    observed_trimp_history,
    observed_trimp_history_by_sport,
)
from mcp_strava.adapters.duckdb.kudos_store import activities_missing_kudos, upsert_kudos
from mcp_strava.adapters.duckdb.schema import create_schema


def _create_duckdb_fixture(path: Path) -> None:
    conn = open_fixture_db(path)
    try:
        create_schema(conn)
    finally:
        conn.close()


def _activity_fact_values(activity_id: int = 100) -> dict[str, object]:
    return {
        "activity_id": activity_id,
        "activity_day": "2026-05-21",
        "sport_type": "Run",
        "source_hash": "hash-a",
        "source_revision": 1,
        "metric_version": 1,
        "computed_at": "2026-05-24T12:00:00",
        "completeness_status": "complete",
        "missing_reasons_json": "[]",
        "trimp": 42.5,
        "zone1_seconds": 10,
        "zone2_seconds": 20,
        "zone3_seconds": 30,
        "zone4_seconds": 40,
        "zone5_seconds": 50,
        "hr_recovery_pause_count": 0,
        "hr_recovery_total_rest_sec": 0,
        "hr_recovery_median_rate": None,
        "hr_recovery_best_rate": None,
        "hr_recovery_worst_rate": None,
        "hr_recovery_avg_rate": None,
        "vertical_speed_vmh": None,
        "vertical_speed_total_ascent_m": None,
        "vertical_speed_duration_hours": None,
        "cardiac_cost": 48.2,
        "adjusted_cardiac_cost": 47.8,
        "cardiac_drift_pct": None,
        "cardiac_drift_severity": None,
        "cardiac_drift_significant": 0,
        "cardiac_drift_quality": None,
        "hrr_pct": None,
        "anomaly_count": 0,
        "distance_m": 6000.0,
        "moving_time_s": 1800,
        "elapsed_time_s": 1900,
        "elevation_gain_m": 120.0,
        "heartrate_sample_count": 180,
        "stream_sample_count": 180,
    }


def test_expected_duckdb_open_fails_closed_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Expected DuckDB mirror does not exist"):
        open_expected_mirror_db(tmp_path / "missing.duckdb")


def test_duckdb_repository_serializes_transactions_and_reads(monkeypatch) -> None:
    from mcp_strava.adapters.duckdb import repository

    events: list[str] = []

    class FakeLock:
        def acquire(self) -> None:
            events.append("lock_acquire")

        def release(self) -> None:
            events.append("lock_release")

        def __enter__(self) -> FakeLock:
            self.acquire()
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb
            self.release()

    class FakeResult:
        description: ClassVar = [("value",)]

        def fetchone(self):
            return (1,)

    class FakeConn:
        def execute(self, sql: str, params=None):
            del params
            events.append(f"execute:{sql}")
            return FakeResult()

        def commit(self) -> None:
            events.append("commit")

    monkeypatch.setattr(repository, "duckdb_process_lock", lambda: FakeLock())

    repo = repository.DuckDBRepository(conn=FakeConn())
    repo.begin()
    assert repo._fetchone("SELECT 1") == {"value": 1}
    repo.commit()
    assert repo._fetchone("SELECT 1") == {"value": 1}

    assert events == [
        "lock_acquire",
        "execute:BEGIN",
        "execute:SELECT 1",
        "commit",
        "lock_release",
        "lock_acquire",
        "execute:SELECT 1",
        "lock_release",
    ]


def test_duckdb_repository_refresh_source_dirty_and_status_roundtrip(tmp_path: Path) -> None:
    from mcp_strava.adapters.duckdb.refresh_state_store import RefreshStateStore
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository

    fixture = tmp_path / "strava.duckdb"
    _create_duckdb_fixture(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        store = RefreshStateStore.from_connection(repo.conn)
        state = store.get_refresh_state()
        assert state.id == 1
        assert store.acquire_refresh_lease("owner-a", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")
        assert not store.acquire_refresh_lease("owner-b", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")
        store.release_refresh_lease("owner-a")
        assert store.acquire_refresh_lease("owner-b", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")
        store.release_refresh_lease("owner-b")

        assert store.enqueue_refresh_request("first_use_of_day", "2026-05-21")
        assert not store.enqueue_refresh_request("first_use_of_day", "2026-05-21")
        assert len(store.pending_refresh_requests()) == 1
        assert store.mark_refresh_requests_consumed("2026-05-21T12:00:00Z") == 1

        repo.upsert_activity_summary(
            activity_id=100,
            date="2026-05-21T06:00:00Z",
            name="DuckDB Run",
            sport_type="Run",
            distance=6000.0,
            moving_time=1800,
            elapsed_time=1900,
            total_elevation_gain=120.0,
            summary_json='{"id":100,"name":"DuckDB Run","synced_at":"ignored"}',
            synced_at="2026-05-21T07:00:00Z",
        )
        source = repo.source_state_for_activity(100)
        dirty = repo.dirty_activity_rows()

        assert source is not None
        assert source["activity_day"] == "2026-05-21"
        assert source["source_revision"] == 1
        assert len(dirty) == 1
        assert dirty[0]["reason"] == "source_changed"
        assert repo.read_model_status(metric_version=1)["status"] == "stale"


def test_duckdb_repository_fact_upserts_queries_and_dirty_clear(tmp_path: Path) -> None:
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository

    fixture = tmp_path / "strava.duckdb"
    _create_duckdb_fixture(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        repo.upsert_activity_summary(
            activity_id=100,
            date="2026-05-21T06:00:00Z",
            name="DuckDB Run",
            sport_type="Run",
            distance=6000.0,
            moving_time=1800,
            elapsed_time=1900,
            total_elevation_gain=120.0,
            summary_json="{}",
            synced_at="2026-05-21T07:00:00Z",
        )
        dirty = repo.dirty_activity_rows_for_materialization(metric_version=1)
        assert dirty

        repo.upsert_activity_metric_fact(_activity_fact_values())
        repo.upsert_daily_load_fact(
            {
                "day": "2026-05-21",
                "scope": "all",
                "sport_type": "all",
                "metric_version": 1,
                "computed_at": "2026-05-24T12:00:00",
                "completeness_status": "complete",
                "missing_reasons_json": "[]",
                "activity_count": 1,
                "stream_point_count": 180,
                "heartrate_point_count": 180,
                "observed_trimp": 42.5,
                "effective_trimp": 42.5,
                "distance_m": 6000.0,
                "moving_time_s": 1800,
                "elevation_gain_m": 120.0,
                "zone4_seconds": 40,
                "zone5_seconds": 50,
                "high_zone_seconds": 90,
                "anomaly_count": 0,
            }
        )
        repo.upsert_training_model_daily_fact(
            {
                "day": "2026-05-21",
                "scope": "all",
                "sport_type": "all",
                "metric_version": 1,
                "computed_at": "2026-05-24T12:00:00",
                "completeness_status": "complete",
                "missing_reasons_json": "[]",
                "effective_trimp": 42.5,
                "observed_trimp": 42.5,
                "fitness": 10.0,
                "fatigue": 12.0,
                "form": -2.0,
                "form_zone": "normal",
                "acwr_zone": "sweet_spot",
                "acwr": 1.2,
                "load_7d": 12.0,
                "load_28d": None,
                "load_42d": 10.0,
                "input_days": 1,
                "missing_days": 0,
            }
        )
        repo.upsert_rolling_period_fact(
            {
                "as_of_day": "2026-05-21",
                "window_days": 7,
                "scope": "all",
                "sport_type": "all",
                "metric_version": 1,
                "computed_at": "2026-05-24T12:00:00",
                "completeness_status": "complete",
                "missing_reasons_json": "[]",
                "activity_count": 1,
                "active_days": 1,
                "rest_days": 6,
                "observed_trimp": 42.5,
                "effective_trimp": 42.5,
                "distance_m": 6000.0,
                "moving_time_s": 1800,
                "elevation_gain_m": 120.0,
                "high_zone_seconds": 90,
                "anomaly_count": 0,
                "fitness": 10.0,
                "fatigue": 12.0,
                "form": -2.0,
                "form_zone": "normal",
                "acwr_zone": "sweet_spot",
                "acwr": 1.2,
                "median_cardiac_cost": 48.2,
                "median_adjusted_cardiac_cost": 47.8,
                "median_hr_recovery": None,
                "median_cardiac_drift_pct": None,
            }
        )
        repo.record_read_model_refresh_run(
            {
                "started_at": "2026-05-24T12:00:00",
                "finished_at": "2026-05-24T12:00:00",
                "status": "ok",
                "metric_version": 1,
                "trigger_reason": "test",
                "activities_considered": 1,
                "activities_materialized": 1,
                "daily_facts_materialized": 1,
                "model_facts_materialized": 1,
                "rolling_facts_materialized": 1,
                "dirty_rows_claimed": 1,
                "dirty_rows_cleared": 1,
                "attempt_count": 1,
                "last_error": None,
            }
        )
        cleared = repo.clear_dirty_activity_rows(dirty)
        repo.conn.commit()

        assert cleared == 1
        assert repo.fetch_activity_metric_fact(100, metric_version=1)["trimp"] == 42.5
        assert len(repo.fetch_daily_load_facts("2026-05-21", "2026-05-22", scope="all")) == 1
        assert repo.fetch_latest_training_model_day(1, as_of_day="2026-05-21")["fitness"] == 10.0
        assert repo.fetch_rolling_period_facts("2026-05-21", 7, scope="all")["active_days"] == 1
        rolling_by_window = repo.fetch_rolling_period_facts_by_windows("2026-05-21", (7, 14), scope="all")
        assert sorted(rolling_by_window) == [7]
        assert rolling_by_window[7]["active_days"] == 1
        assert repo.read_model_status(metric_version=1)["status"] == "current"


def test_safe_identifier_rejects_sql_injection() -> None:
    """safe_identifier accepts bare identifiers and rejects anything else.

    Panel Security finding (defense-in-depth): a handful of internal queries
    interpolate table/column names because DuckDB cannot parameterize
    identifiers. All current callers pass schema literals, but the guard makes a
    future Strava-sourced string fail loudly instead of injecting.
    """
    from mcp_strava.adapters.duckdb.repository_utils import safe_identifier

    assert safe_identifier("activity_metric_facts") == "activity_metric_facts"
    assert safe_identifier("observed_max_hr") == "observed_max_hr"
    for bad in ["facts; DROP TABLE x", "a'b", "a b", "a-b", "", "1abc", "x)", "a,b"]:
        with pytest.raises(ValueError):
            safe_identifier(bad)


def _fresh_logic_version_repo():
    """Fresh in-memory mirror with full schema + a seeded logic-version sidecar."""
    import duckdb

    from mcp_strava.adapters.duckdb.repository import DuckDBRepository

    conn = duckdb.connect(":memory:")
    create_schema(conn)
    return DuckDBRepository.from_connection(conn), conn


def test_logic_version_seed_adopts_current_fingerprint_on_fresh_db() -> None:
    """Fresh DB: from_connection seeds exactly one sidecar row whose fingerprint
    equals the live compute_logic_fingerprint() and whose version is >= 1.

    Seed = current by construction means the first refresh after deploy sees
    stored == live and does NOT recompute (no recompute side effect from deploy).
    """
    from mcp_strava.metric_registry import compute_logic_fingerprint

    repo, conn = _fresh_logic_version_repo()
    count = conn.execute("SELECT COUNT(*) FROM read_model_logic_version").fetchone()[0]
    assert count == 1

    stored = repo.current_logic_version()
    assert stored is not None
    assert stored["logic_fingerprint"] == compute_logic_fingerprint()
    assert int(stored["metric_version"]) >= 1
    assert repo.current_metric_version() == int(stored["metric_version"])


def test_logic_version_helpers_round_trip_via_bump() -> None:
    """bump_logic_version advances both fields; the read helpers reflect them."""
    repo, _conn = _fresh_logic_version_repo()
    v = repo.current_metric_version()

    repo.bump_logic_version(v + 1, "deadbeef", "2026-06-03T01:02:03")

    stored = repo.current_logic_version()
    assert stored is not None
    assert int(stored["metric_version"]) == v + 1
    assert stored["logic_fingerprint"] == "deadbeef"
    assert stored["changed_at"] == "2026-06-03T01:02:03"
    assert repo.current_metric_version() == v + 1


def test_bump_logic_version_invalidates_current_metric_version_memo() -> None:
    """cycle-2 HIGH: populating the memo at v then bumping to v+1 on the SAME
    repo must yield v+1 — the memo cannot serve the stale pre-bump version.

    Without memo invalidation, materialize would run at v while dirty rows queue
    at v+1 and the self-invalidation would silently no-op.
    """
    repo, _conn = _fresh_logic_version_repo()

    v = repo.current_metric_version()  # populates the memo at v
    repo.bump_logic_version(v + 1, "feedface", "2026-06-03T02:00:00")

    # Same instance, memo must have been cleared inside bump_logic_version().
    assert repo.current_metric_version() == v + 1


def test_logic_version_seed_is_idempotent_across_constructions() -> None:
    """Calling from_connection twice on the same DB does not insert a 2nd row."""
    import duckdb

    from mcp_strava.adapters.duckdb.repository import DuckDBRepository

    conn = duckdb.connect(":memory:")
    create_schema(conn)
    DuckDBRepository.from_connection(conn)
    DuckDBRepository.from_connection(conn)

    count = conn.execute("SELECT COUNT(*) FROM read_model_logic_version").fetchone()[0]
    assert count == 1


def test_logic_version_seed_fails_loud_on_import_error(monkeypatch) -> None:
    """Fail-loud: if compute_logic_fingerprint raises inside the seed, it
    propagates out of from_connection() rather than silently leaving the sidecar
    unseeded. On this deployment getsource always works; a real failure should
    crash, not hide. Only the table-absent case is tolerated (see the
    schema-missing fail-soft test).
    """
    import duckdb

    import mcp_strava.metric_registry as mr
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository

    def _boom() -> str:
        raise ImportError("simulated missing compute module")

    monkeypatch.setattr(mr, "compute_logic_fingerprint", _boom)

    conn = duckdb.connect(":memory:")
    create_schema(conn)
    with pytest.raises(ImportError, match="simulated missing compute module"):
        DuckDBRepository.from_connection(conn)


# ─── Walk TRIMP discount: per-sport daily aggregation + effective-trimp wiring ───


def _seed_hr_activity_with_streams(
    repo,
    *,
    activity_id: int,
    day: str,
    sport_type: str,
    heartrate: int = 150,
) -> None:
    """Seed one HR-bearing activity (summary + 180 HR stream points) so its day is
    OBSERVED. Constant heartrate keeps the per-activity TRIMP deterministic and
    lets a Walk and a Run on the same day produce comparable raw TRIMP."""
    repo.upsert_activity_summary(
        activity_id=activity_id,
        date=f"{day}T06:00:00Z",
        name=f"{sport_type} {activity_id}",
        sport_type=sport_type,
        distance=6000.0,
        moving_time=1800,
        elapsed_time=1900,
        total_elevation_gain=120.0,
        summary_json=(
            f'{{"id":{activity_id},"name":"{sport_type}","sport_type":"{sport_type}",'
            f'"start_date_local":"{day}T06:00:00Z","distance":6000,"moving_time":1800,'
            '"elapsed_time":1900,"total_elevation_gain":120,"has_heartrate":true}'
        ),
        synced_at=f"{day}T07:00:00Z",
    )
    repo.update_activity_detail(activity_id, f'{{"id": {activity_id}, "resource_state": 3}}')
    rows = [
        {
            "time_offset": idx * 10,
            "heartrate": heartrate,
            "velocity": 3.0,
            "altitude": 500.0,
            "cadence": 84,
            "lat": 43.2,
            "lng": 76.9,
            "grade": 1.0,
            "gap_speed": 3.1,
            "gap_distance": idx * 30.0,
            "is_moving": 1,
            "values_json": "{}",
        }
        for idx in range(180)
    ]
    repo.replace_stream_rows_and_channel_metadata(
        activity_id,
        rows=rows,
        metadata=[
            {
                "channel_key": "heartrate",
                "original_size": len(rows),
                "resolution": "high",
                "series_type": "distance",
                "fetched_at": f"{day}T07:30:00Z",
                "batch_id": "walk-discount-test",
                "status": "available",
                "error": None,
            }
        ],
    )


def _zone_bounds_for(repo, end_day: str):
    """Resolve the same session-level zone bounds the materializer uses, so test
    TRIMP math matches production aggregation."""
    from mcp_strava.hr_zones import get_zone_model
    from mcp_strava.settings import get_settings

    athlete = get_settings().athlete
    global_hr_max = repo.max_heartrate_to_date(end_day)
    return get_zone_model(athlete.hr_zone_model).zone_bounds(hr_max=int(global_hr_max), hr_rest=athlete.hr_rest)


def test_observed_trimp_history_by_sport_breaks_down_same_range_as_total(tmp_path: Path) -> None:
    """observed_trimp_history_by_sport returns {day -> {sport -> raw trimp}} over
    the SAME date range / bounds as observed_trimp_history, and the per-sport raw
    values for a day sum (rounded) to that day's undiscounted observed total."""
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository
    from tests._fixtures_duckdb import create_empty_fixture_db

    fixture = tmp_path / "by_sport.duckdb"
    create_empty_fixture_db(fixture)
    with DuckDBRepository.from_path(fixture) as repo:
        _seed_hr_activity_with_streams(repo, activity_id=801, day="2026-05-21", sport_type="Run")
        _seed_hr_activity_with_streams(repo, activity_id=802, day="2026-05-21", sport_type="Walk")
        bounds = _zone_bounds_for(repo, "2026-05-21")

        total = observed_trimp_history(repo, bounds=bounds, since_day="2026-05-21", until_day="2026-05-21")
        by_sport = observed_trimp_history_by_sport(repo, bounds=bounds, since_day="2026-05-21", until_day="2026-05-21")

    assert set(by_sport) == set(total), "by-sport and total must cover the same days"
    day_map = by_sport["2026-05-21"]
    assert set(day_map) == {"Run", "Walk"}
    # The undiscounted per-day sum (rounded) equals the observed total for that day.
    assert round(sum(day_map.values()), 1) == total["2026-05-21"]


def test_daily_load_points_discount_walk_portion_only(tmp_path: Path) -> None:
    """For an OBSERVED day with a Run + a Walk, effective_trimp is the Run TRIMP
    (full) plus 0.5 * the Walk TRIMP, while observed_trimp stays the undiscounted
    daily sum. A Run-only day is unchanged (effective == observed)."""
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository
    from mcp_strava.constants import WALK_TRIMP_DISCOUNT
    from tests._fixtures_duckdb import create_empty_fixture_db

    fixture = tmp_path / "discount.duckdb"
    create_empty_fixture_db(fixture)
    with DuckDBRepository.from_path(fixture) as repo:
        # Walk day (2026-05-21): Run + Walk. Run-only day (2026-05-22): control.
        _seed_hr_activity_with_streams(repo, activity_id=811, day="2026-05-21", sport_type="Run")
        _seed_hr_activity_with_streams(repo, activity_id=812, day="2026-05-21", sport_type="Walk")
        _seed_hr_activity_with_streams(repo, activity_id=813, day="2026-05-22", sport_type="Run")
        bounds = _zone_bounds_for(repo, "2026-05-22")

        by_sport = observed_trimp_history_by_sport(repo, bounds=bounds, since_day="2026-05-21", until_day="2026-05-22")
        points = {p.date: p for p in daily_load_points_between(repo, "2026-05-21", "2026-05-22", bounds=bounds)}

    run_raw = by_sport["2026-05-21"]["Run"]
    walk_raw = by_sport["2026-05-21"]["Walk"]
    expected_walk_day_effective = round(run_raw + WALK_TRIMP_DISCOUNT * walk_raw, 1)
    expected_walk_day_observed = round(run_raw + walk_raw, 1)

    walk_day = points["2026-05-21"]
    assert walk_day.status == "OBSERVED"
    assert walk_day.effective_trimp == expected_walk_day_effective
    assert walk_day.observed_trimp == expected_walk_day_observed
    # The discount actually lowered effective below observed (the Walk was present).
    assert walk_day.effective_trimp < walk_day.observed_trimp

    run_day = points["2026-05-22"]
    assert run_day.status == "OBSERVED"
    assert run_day.effective_trimp == run_day.observed_trimp  # Run-only day unchanged


def test_walk_discount_recomputes_end_to_end_on_fingerprint_mismatch(tmp_path: Path) -> None:
    """Zero-knob END-TO-END proof (option a): a forced stored!=live logic-fingerprint
    mismatch at the materialize chokepoint must FIRE the full recompute PIPELINE —
    not merely re-run the discount arithmetic. Concretely:

      1. Seed a Walk-containing day + a Run, materialize once at version N (=1).
      2. Write a DELIBERATELY-WRONG stored logic_fingerprint into the sidecar so
         stored != live (compute_logic_fingerprint()).
      3. Drive materialize_read_model_stage and assert the recompute actually fires:
         (1) current_metric_version() advances to N+1,
         (2) activities were enqueued for recompute (dirty/enqueued > 0),
         (3) the re-materialized daily effective_trimp for the walk day equals
             discounted_effective_trimp(...) for the current WALK_TRIMP_DISCOUNT.

    This proves the fingerprint -> bump -> enqueue -> re-materialize PIPELINE, which
    a patched-constant test (option b) cannot — monkeypatching the in-memory constant
    does not change inspect.getsource text, so it cannot drive a real mismatch.
    """
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository
    from mcp_strava.metrics import discounted_effective_trimp
    from mcp_strava.refresh._sync_ops import materialize_read_model_stage
    from tests._fixtures_duckdb import create_empty_fixture_db

    fixture = tmp_path / "walk_e2e.duckdb"
    create_empty_fixture_db(fixture)
    with DuckDBRepository.from_path(fixture) as repo:
        _seed_hr_activity_with_streams(repo, activity_id=821, day="2026-05-21", sport_type="Run")
        _seed_hr_activity_with_streams(repo, activity_id=822, day="2026-05-21", sport_type="Walk")
        bounds = _zone_bounds_for(repo, "2026-05-21")
        by_sport = observed_trimp_history_by_sport(repo, bounds=bounds, since_day="2026-05-21", until_day="2026-05-21")
        expected_effective = discounted_effective_trimp(by_sport["2026-05-21"])

        # First cycle: stored == live (seed adopted current) -> normal materialize at N=1.
        materialize_read_model_stage(repo, "2026-05-24T12:00:00", None)
        assert repo.current_metric_version() == 1

        # Force a logic-edit signal: overwrite the stored fingerprint with a wrong
        # value so the next chokepoint sees stored != live (exactly how editing
        # WALK_TRIMP_DISCOUNT in source would look — stored stale, live moved on).
        repo.bump_logic_version(1, "STALE_WRONG_FINGERPRINT", "2026-05-24T12:30:00")

        # The N=1 cycle already cleared the dirty queue, so it is empty here; the
        # mass-enqueue we are proving happens INSIDE the stage (the chokepoint
        # re-queues every activity at N+1 before re-materializing). We assert the
        # enqueue + recompute fired via the run record below, not a pre-stage count.
        result = materialize_read_model_stage(repo, "2026-05-24T13:00:00", None)

        # Activities the chokepoint re-materialized at the bumped version (proves
        # the mass-enqueue then ran through materialization, not a stale no-op).
        materialized_at_bump = int(
            repo.conn.execute(
                """
                SELECT activities_materialized FROM read_model_refresh_runs
                WHERE status = 'ok' AND metric_version = 2 ORDER BY id DESC LIMIT 1
                """
            ).fetchone()[0]
        )

        bumped = repo.current_metric_version()
        # The re-materialized daily fact at the BUMPED version carries the discount.
        # Pin to metric_version=2 — the table still holds the v1 row from the first
        # cycle, and an unpinned fetch would ambiguously return both versions.
        walk_day_facts = repo.fetch_daily_load_facts("2026-05-21", "2026-05-22", scope="all", metric_version=2)
        walk_day_fact = next(f for f in walk_day_facts if str(f["day"]) == "2026-05-21")

    # (1) version advanced to N+1
    assert bumped == 2, "fingerprint mismatch must bump metric_version to N+1"
    # (2) the mass-enqueue + recompute fired: both seed activities re-materialized at N+1
    assert materialized_at_bump >= 2
    assert result.get("activities_materialized", 0) >= 1
    # (3) the re-materialized walk-day effective_trimp reflects the current discount
    assert walk_day_fact["metric_version"] == 2
    assert walk_day_fact["effective_trimp"] == expected_effective
    assert walk_day_fact["effective_trimp"] < walk_day_fact["observed_trimp"]


def test_activities_missing_kudos_filters_and_returns_typed_ids(tmp_path: Path) -> None:
    """activities_missing_kudos returns plain int ids, only for activities that
    have kudos upstream (kudos_count > 0) and none mirrored locally yet."""
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository

    fixture = tmp_path / "strava.duckdb"
    _create_duckdb_fixture(fixture)

    def _seed(repo: DuckDBRepository, activity_id: int, kudos_count: int) -> None:
        repo.upsert_activity_summary(
            activity_id=activity_id,
            date="2026-05-21T06:00:00Z",
            name=f"Run {activity_id}",
            sport_type="Run",
            distance=6000.0,
            moving_time=1800,
            elapsed_time=1900,
            total_elevation_gain=120.0,
            summary_json=f'{{"id":{activity_id},"kudos_count":{kudos_count}}}',
            synced_at="2026-05-21T07:00:00Z",
        )

    with DuckDBRepository.from_path(fixture) as repo:
        _seed(repo, 201, kudos_count=3)  # has kudos upstream, none mirrored -> included
        _seed(repo, 202, kudos_count=0)  # no kudos upstream -> excluded
        _seed(repo, 203, kudos_count=5)  # already mirrored below -> excluded
        upsert_kudos(repo, 203, "Ada", "Lovelace", "2026-05-21T07:00:00Z")

        ids = activities_missing_kudos(repo)

        assert ids == [201]
        assert all(isinstance(i, int) for i in ids)


def test_mirror_coverage_count_methods_return_typed_values(tmp_path: Path) -> None:
    """The mirror-coverage repo methods own every query the application layer used
    to run via raw conn.execute. Seed one activity with 180 HR stream points (each
    carrying lat/lng and an empty values_json) plus one channel metadata row, then
    assert each method returns a plain, correctly-typed value."""
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository
    from mcp_strava.adapters.duckdb.stream_coverage_queries import (
        count_activities,
        count_activities_missing_channel_metadata,
        count_activities_with_streams,
        count_stream_gps_points,
        count_stream_points,
        count_streams_missing_extra_values,
        mirror_table_exists,
        stream_table_columns,
    )

    fixture = tmp_path / "strava.duckdb"
    _create_duckdb_fixture(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        _seed_hr_activity_with_streams(repo, activity_id=301, day="2026-05-21", sport_type="Run")

        # Column introspection: canonical schema has lat/lng/values_json, no latlng.
        columns = stream_table_columns(repo)
        assert isinstance(columns, set)
        assert {"lat", "lng", "values_json"} <= columns
        assert "latlng" not in columns

        # Table existence via information_schema.
        assert mirror_table_exists(repo, "streams") is True
        assert mirror_table_exists(repo, "stream_channels") is True
        assert mirror_table_exists(repo, "table_that_does_not_exist") is False

        # Counts (180 stream points seeded for one activity).
        assert count_activities(repo) == 1
        assert count_activities_with_streams(repo) == 1
        assert count_stream_points(repo) == 180
        assert all(
            isinstance(v, int)
            for v in (count_activities(repo), count_activities_with_streams(repo), count_stream_points(repo))
        )

        # GPS: every seeded point has lat/lng set. has_latlng=False (the canonical
        # schema case — no latlng column) must count via lat/lng only and never
        # reference the absent column. The application only passes has_latlng=True
        # after confirming the column exists via stream_table_columns(), so the
        # widened predicate is exercised in test_count_stream_gps_points_widens... .
        assert count_stream_gps_points(repo, has_latlng=False) == 180

        # The seeded activity has exactly one channel metadata row, so it is NOT
        # missing channel metadata entirely.
        assert count_activities_missing_channel_metadata(repo) == 0

        # values_json is "{}" for every seeded point (present, non-empty), so none
        # are missing extra values; with has_values_json False, all 180 count.
        assert count_streams_missing_extra_values(repo, has_values_json=True) == 0
        assert count_streams_missing_extra_values(repo, has_values_json=False) == 180


def test_count_stream_gps_points_widens_predicate_when_latlng_column_present(tmp_path: Path) -> None:
    """When a variant DB carries a combined ``latlng`` column, has_latlng=True
    widens the WHERE so points with only latlng set are also counted. Simulate the
    variant by adding the column post-create (the schema-drift case the branch
    defends against) and seeding a point whose lat/lng are NULL but latlng is set."""
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository
    from mcp_strava.adapters.duckdb.stream_coverage_queries import count_stream_gps_points, stream_table_columns

    fixture = tmp_path / "strava.duckdb"
    _create_duckdb_fixture(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        _seed_hr_activity_with_streams(repo, activity_id=401, day="2026-05-21", sport_type="Run")
        # Variant column + one point that has ONLY latlng (lat/lng NULL).
        repo._execute("ALTER TABLE streams ADD COLUMN latlng VARCHAR")
        repo._execute(
            "INSERT INTO streams (activity_id, time_offset, lat, lng, latlng) VALUES (401, 9999, NULL, NULL, '43.2,76.9')"
        )

        assert "latlng" in stream_table_columns(repo)
        # lat/lng-only count: the 180 seeded points (the latlng-only point excluded).
        assert count_stream_gps_points(repo, has_latlng=False) == 180
        # Widened: the extra latlng-only point is now also counted.
        assert count_stream_gps_points(repo, has_latlng=True) == 181


def test_mirror_coverage_counts_on_empty_mirror_are_zero(tmp_path: Path) -> None:
    """On a freshly-created empty mirror the count methods return 0 (never None),
    confirming the centralized _scalar_int NULL->0 collapse."""
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository
    from mcp_strava.adapters.duckdb.stream_coverage_queries import (
        count_activities,
        count_activities_missing_channel_metadata,
        count_activities_with_streams,
        count_stream_gps_points,
        count_stream_points,
        count_streams_missing_extra_values,
    )

    fixture = tmp_path / "strava.duckdb"
    _create_duckdb_fixture(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        assert count_activities(repo) == 0
        assert count_activities_with_streams(repo) == 0
        assert count_stream_points(repo) == 0
        assert count_stream_gps_points(repo, has_latlng=False) == 0
        assert count_activities_missing_channel_metadata(repo) == 0
        assert count_streams_missing_extra_values(repo, has_values_json=True) == 0
