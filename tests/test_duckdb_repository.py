from pathlib import Path

import pytest

from mcp_strava.adapters.duckdb.connection import open_expected_mirror_db, open_fixture_db
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
        description = [("value",)]

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
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository

    fixture = tmp_path / "strava.duckdb"
    _create_duckdb_fixture(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        state = repo.get_refresh_state()
        assert state.id == 1
        assert repo.acquire_refresh_lease("owner-a", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")
        assert not repo.acquire_refresh_lease("owner-b", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")
        repo.release_refresh_lease("owner-a")
        assert repo.acquire_refresh_lease("owner-b", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")
        repo.release_refresh_lease("owner-b")

        assert repo.enqueue_refresh_request("first_use_of_day", "2026-05-21")
        assert not repo.enqueue_refresh_request("first_use_of_day", "2026-05-21")
        assert len(repo.pending_refresh_requests()) == 1
        assert repo.mark_refresh_requests_consumed("2026-05-21T12:00:00Z") == 1

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


def test_ensure_schema_extensions_swallows_missing_table_but_surfaces_real_errors(monkeypatch) -> None:
    """_ensure_schema_extensions ignores the fresh-DB CatalogException, not real errors.

    Panel SRE/QA finding: the previous `except Exception: pass` hid genuine
    failures (permission, IO, corruption) behind the expected fresh-DB case.
    The narrowed catch must swallow only the missing-table CatalogException and
    let any other failure propagate.
    """
    import duckdb

    from mcp_strava.adapters.duckdb import repository as repo_mod
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository

    # Fresh in-memory connection with no schema: the provenance ALTER hits a
    # missing activity_metric_facts table -> CatalogException, which is expected
    # and must be swallowed so construction still succeeds.
    repo = DuckDBRepository.from_connection(duckdb.connect(":memory:"))
    assert repo is not None

    # A non-catalog failure must propagate, not be silently swallowed.
    def _boom(_conn) -> None:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(repo_mod, "ensure_provenance_columns", _boom)
    with pytest.raises(RuntimeError, match="disk on fire"):
        DuckDBRepository.from_connection(duckdb.connect(":memory:"))


def test_ensure_provenance_columns_adds_registry_owned_late_activity_columns() -> None:
    import duckdb

    from mcp_strava.adapters.duckdb.schema import ACTIVITY_METRIC_FACT_LATE_COLUMNS, ensure_provenance_columns
    from mcp_strava.metric_registry import MATERIALIZED_FACT_COLUMN_REGISTRY

    expected_late_columns = (
        "observed_min_hr",
        "observed_max_hr",
        "hr_zone_model",
        "hr_max_used",
        "hr_rest_used",
        "calories_kcal",
    )
    assert ACTIVITY_METRIC_FACT_LATE_COLUMNS == expected_late_columns

    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE activity_metric_facts (
            activity_id BIGINT NOT NULL,
            metric_version BIGINT NOT NULL,
            PRIMARY KEY (activity_id, metric_version)
        )
        """
    )

    ensure_provenance_columns(conn)

    rows = conn.execute(
        """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'activity_metric_facts'
          AND column_name IN (
              'observed_min_hr',
              'observed_max_hr',
              'hr_zone_model',
              'hr_max_used',
              'hr_rest_used',
              'calories_kcal'
          )
        ORDER BY ordinal_position
        """
    ).fetchall()
    added_columns = {
        str(name): (str(data_type), str(is_nullable) == "YES", default_sql)
        for name, data_type, is_nullable, default_sql in rows
    }

    assert tuple(added_columns) == expected_late_columns
    registry_columns = MATERIALIZED_FACT_COLUMN_REGISTRY["activity_metric_facts"]
    for column_name in expected_late_columns:
        registry_column = registry_columns[column_name]
        assert added_columns[column_name] == (
            registry_column.sql_type,
            registry_column.nullable,
            registry_column.default_sql,
        )


def test_activity_metric_fact_late_columns_are_safe_for_additive_migration() -> None:
    from mcp_strava.adapters.duckdb.schema import ACTIVITY_METRIC_FACT_LATE_COLUMNS
    from mcp_strava.metric_registry import materialized_fact_column_definition

    for column_name in ACTIVITY_METRIC_FACT_LATE_COLUMNS:
        definition = materialized_fact_column_definition("activity_metric_facts", column_name)
        assert definition.nullable or definition.default_sql is not None, column_name


def test_safe_identifier_rejects_sql_injection() -> None:
    """_safe_identifier accepts bare identifiers and rejects anything else.

    Panel Security finding (defense-in-depth): a handful of internal queries
    interpolate table/column names because DuckDB cannot parameterize
    identifiers. All current callers pass schema literals, but the guard makes a
    future Strava-sourced string fail loudly instead of injecting.
    """
    from mcp_strava.adapters.duckdb.repository import _safe_identifier

    assert _safe_identifier("activity_metric_facts") == "activity_metric_facts"
    assert _safe_identifier("observed_max_hr") == "observed_max_hr"
    for bad in ["facts; DROP TABLE x", "a'b", "a b", "a-b", "", "1abc", "x)", "a,b"]:
        with pytest.raises(ValueError):
            _safe_identifier(bad)


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


def test_logic_version_seed_skips_on_import_error_and_reads_fall_back(monkeypatch) -> None:
    """ImportError safety: if compute_logic_fingerprint raises inside the seed,
    from_connection() still succeeds (does not propagate), the sidecar is left
    unseeded, and current_metric_version() returns the fact-table fallback (1 on
    an empty DB) rather than crashing. Adoption then self-heals at 15-03.
    """
    import duckdb

    import mcp_strava.metric_registry as mr
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository

    def _boom() -> str:
        raise ImportError("simulated missing compute module")

    monkeypatch.setattr(mr, "compute_logic_fingerprint", _boom)

    conn = duckdb.connect(":memory:")
    create_schema(conn)
    repo = DuckDBRepository.from_connection(conn)  # must NOT raise

    assert repo.current_logic_version() is None  # left unseeded
    count = conn.execute("SELECT COUNT(*) FROM read_model_logic_version").fetchone()[0]
    assert count == 0
    assert repo.current_metric_version() == 1  # fact-table-max (empty) -> 1, no crash
