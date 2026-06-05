from datetime import date, timedelta
from pathlib import Path

import pytest

from mcp_strava.adapters.duckdb.activity_lookup_queries import activity_by_id
from mcp_strava.adapters.duckdb.read_model_materializer import (
    _activity_fact,
    _activity_facts_batched,
    _record_failed_run,
    materialize_read_model,
)
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.hr_zones import get_zone_model
from mcp_strava.settings import get_settings
from tests._fixtures_duckdb import create_empty_fixture_db


def _create_duckdb_read_model_repo(tmp_path: Path) -> tuple[Path, DuckDBRepository]:
    fixture = tmp_path / "read-model.duckdb"
    create_empty_fixture_db(fixture)
    return fixture, DuckDBRepository.from_path(fixture)


def _seed_dirty_activity_with_streams(
    repo: DuckDBRepository,
    *,
    activity_id: int = 920,
    day: str = "2026-05-21",
) -> None:
    # 180 rows, all moving (velocity >= 3.0 m/s), ascending altitude.
    # This fixture has NO pauses (velocity never dips below VEL_STOP=0.15), so
    # hr_recovery_* will remain None/0 until the pause-inclusive fixture is used.
    repo.upsert_activity_summary(
        activity_id=activity_id,
        date=f"{day}T06:00:00Z",
        name=f"Materialized {activity_id}",
        sport_type="Run",
        distance=6000.0,
        moving_time=1800,
        elapsed_time=1900,
        total_elevation_gain=120.0,
        summary_json=(
            f'{{"id":{activity_id},"name":"Materialized","sport_type":"Run","start_date_local":"{day}T06:00:00Z",'
            '"distance":6000,"moving_time":1800,"elapsed_time":1900,"total_elevation_gain":120,'
            '"average_heartrate":145,"max_heartrate":172,"has_heartrate":true}'
        ),
        synced_at=f"{day}T07:00:00Z",
    )
    repo.update_activity_detail(activity_id, f'{{"id": {activity_id}, "resource_state": 3}}')
    rows = []
    for idx in range(180):
        rows.append(
            {
                "time_offset": idx * 10,
                "heartrate": 138 + (idx % 35),
                "velocity": 3.0 + ((idx % 4) * 0.02),
                "altitude": 500.0 + idx * 0.2,
                "cadence": 84,
                "lat": 43.2 + idx * 0.00001,
                "lng": 76.9 + idx * 0.00001,
                "grade": 1.0,
                "gap_speed": 3.1,
                "gap_distance": idx * 30.0,
                "is_moving": 1,
                "values_json": '{"distance": %.1f}' % (idx * 30.0),
            }
        )
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
                "batch_id": "materializer-test",
                "status": "available",
                "error": None,
            }
        ],
    )


def test_duckdb_materializer_writes_fact_tiers_and_clears_dirty_rows(tmp_path: Path) -> None:
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)
    with repo:
        _seed_dirty_activity_with_streams(repo)
        result = materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")

        activity_fact = repo.fetch_activity_metric_fact(920, metric_version=1)
        daily_facts = repo.fetch_daily_load_facts("2026-05-21", "2026-05-22", scope="all")
        model_fact = repo.fetch_latest_training_model_day(1, as_of_day="2026-05-24")
        rolling = repo.fetch_rolling_period_facts("2026-05-24", 7, scope="all")
        run_count = repo.conn.execute("SELECT COUNT(*) FROM read_model_refresh_runs WHERE status = 'ok'").fetchone()[0]
        dirty = repo.dirty_activity_rows(activity_id=920)

    assert result["status"] == "ok"
    assert activity_fact is not None
    assert activity_fact["source_hash"]
    assert activity_fact["trimp"] > 0
    assert activity_fact["stream_sample_count"] == 180
    assert activity_fact["heartrate_sample_count"] == 180
    assert daily_facts and daily_facts[0]["activity_count"] == 1
    assert model_fact is not None and model_fact["fitness"] is not None
    assert rolling is not None and rolling["active_days"] >= 1
    assert run_count == 1
    assert dirty == []


def test_duckdb_materializer_rolls_back_facts_and_keeps_dirty_rows_on_failure(tmp_path: Path) -> None:
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)

    class FailingDailyFactRepo(DuckDBRepository):
        def upsert_daily_load_facts(self, *args, **kwargs):
            raise RuntimeError("daily fact failed")

    with repo:
        _seed_dirty_activity_with_streams(repo)
        failing_repo = FailingDailyFactRepo(repo.conn)

        with pytest.raises(RuntimeError, match="daily fact failed"):
            materialize_read_model(failing_repo, metric_version=1, now="2026-05-24T12:00:00")

        assert repo.dirty_activity_rows(activity_id=920)
        success_count = repo.conn.execute(
            "SELECT COUNT(*) FROM read_model_refresh_runs WHERE status = 'ok'"
        ).fetchone()[0]
        activity_fact_count = repo.conn.execute("SELECT COUNT(*) FROM activity_metric_facts").fetchone()[0]

    assert success_count == 0
    assert activity_fact_count == 0


def test_WR_03_record_failed_run_commits_under_process_lock(tmp_path: Path, monkeypatch) -> None:
    """WR-03: the failed-run bookkeeping write must honor duckdb_process_lock().

    Every other repository write commits via _commit_if_standalone / _execute,
    which acquire the single-writer process lock. _record_failed_run previously
    committed via a raw repo.conn.commit() with NO lock, so its INSERT+commit could
    interleave with another writer's transaction. We instrument the shared process
    lock and assert it is HELD at the moment the failed-run record commits.
    """
    import threading

    from mcp_strava.adapters.duckdb import repository as repo_module

    class TrackingLock:
        def __init__(self) -> None:
            self._lock = threading.RLock()
            self.depth = 0

        def acquire(self, *args, **kwargs):
            acquired = self._lock.acquire(*args, **kwargs)
            if acquired:
                self.depth += 1
            return acquired

        def release(self) -> None:
            self.depth -= 1
            self._lock.release()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, *_exc) -> None:
            self.release()

        @property
        def held(self) -> bool:
            return self.depth > 0

    tracking = TrackingLock()
    monkeypatch.setattr(repo_module, "duckdb_process_lock", lambda: tracking)

    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)

    # Record every standalone (depth==0) commit routed through the lock-aware
    # repository helper, and whether the process lock was HELD as it committed. The
    # buggy version committed the failed-run record via a raw repo.conn.commit()
    # and never reached _commit_if_standalone at depth 0, so this list stays empty
    # -> RED. (The success path commits inside repo.begin(), i.e. depth>0.)
    commit_under_lock: list[bool] = []

    class FailingDailyFactRepo(DuckDBRepository):
        def upsert_daily_load_facts(self, *args, **kwargs):
            raise RuntimeError("daily fact failed")

        def _commit_if_standalone(self) -> None:
            if self._transaction_depth == 0:
                # The real helper does `with duckdb_process_lock(): conn.commit()`.
                # Acquire the tracking lock ourselves to record held-state, then
                # delegate (RLock is reentrant, so the nested acquire is fine).
                with tracking:
                    commit_under_lock.append(tracking.held)
                    super()._commit_if_standalone()
            else:
                super()._commit_if_standalone()

    with repo:
        _seed_dirty_activity_with_streams(repo)
        failing_repo = FailingDailyFactRepo(repo.conn)

        with pytest.raises(RuntimeError, match="daily fact failed"):
            materialize_read_model(failing_repo, metric_version=1, now="2026-05-24T12:00:00")

    # The failed-run record must commit through the lock-aware helper under the lock.
    assert commit_under_lock, (
        "_record_failed_run must commit through the lock-aware repository helper "
        "(_commit_if_standalone), not via a raw unlocked repo.conn.commit()"
    )
    assert all(commit_under_lock), "every failed-run commit must run under duckdb_process_lock()"


def test_record_failed_run_logs_when_bookkeeping_fails(caplog) -> None:
    class FailingBookkeepingRepo:
        rolled_back = False

        def record_read_model_refresh_run(self, _values):
            raise RuntimeError("bookkeeping insert failed")

        def _commit_if_standalone(self):
            raise AssertionError("commit should not run after failed insert")

        def rollback(self):
            self.rolled_back = True

    repo = FailingBookkeepingRepo()

    with caplog.at_level("WARNING", logger="mcp_strava.adapters.duckdb.read_model_materializer"):
        _record_failed_run(repo, "2026-05-24T12:00:00", 1, RuntimeError("materialize failed"))  # type: ignore[arg-type]

    assert repo.rolled_back
    assert "read-model failed-run recording failed: bookkeeping insert failed" in caplog.text


# ---------------------------------------------------------------------------
# Helpers for new metric-column tests
# ---------------------------------------------------------------------------


def _seed_dirty_activity_with_pauses(
    repo: DuckDBRepository,
    *,
    activity_id: int = 921,
    day: str = "2026-05-21",
) -> None:
    """Seed an activity whose velocity series includes a >=30 s pause below VEL_STOP=0.15.

    Layout (each row = 1 s interval — required because calc_hr_recovery detects
    consecutive rows with gap > 3 s as a data break, not a pause):
    - rows 0-49:   running, velocity=3.0, ascending altitude
    - rows 50-82:  stopped, velocity=0.0  (33 rows × 1 s = 33 s pause ≥ MIN_PAUSE_SEC=30)
    - rows 83-179: running again, velocity=3.0, ascending altitude
    Total = 180 rows ≥ MIN_STREAM_POINTS=120.
    """
    repo.upsert_activity_summary(
        activity_id=activity_id,
        date=f"{day}T07:00:00Z",
        name=f"Pause activity {activity_id}",
        sport_type="Run",
        distance=5000.0,
        moving_time=1500,
        elapsed_time=1800,
        total_elevation_gain=80.0,
        summary_json=(
            f'{{"id":{activity_id},"name":"Pause","sport_type":"Run","start_date_local":"{day}T07:00:00Z",'
            '"distance":5000,"moving_time":1500,"elapsed_time":1800,"total_elevation_gain":80,'
            '"average_heartrate":145,"max_heartrate":170,"has_heartrate":true}'
        ),
        synced_at=f"{day}T08:00:00Z",
    )
    repo.update_activity_detail(activity_id, f'{{"id": {activity_id}, "resource_state": 3}}')
    rows = []
    for idx in range(180):
        is_pause = 50 <= idx <= 82
        velocity = 0.0 if is_pause else 3.0
        # HR drops during the pause so calc_hr_recovery sees a meaningful drop
        heartrate = max(110, 150 - (idx - 50) * 1) if is_pause else 140 + idx % 20
        rows.append(
            {
                "time_offset": idx,  # 1-second intervals — required for gap detection in calc_hr_recovery
                "heartrate": heartrate,
                "velocity": velocity,
                "altitude": 500.0 + idx * 0.2,
                "cadence": 84 if not is_pause else 0,
                "lat": 43.2 + idx * 0.00001,
                "lng": 76.9 + idx * 0.00001,
                "grade": 1.0,
                "gap_speed": velocity,
                "gap_distance": idx * 3.0,
                "is_moving": 0 if is_pause else 1,
                "values_json": '{"distance": %.1f}' % (idx * 3.0),
            }
        )
    repo.replace_stream_rows_and_channel_metadata(
        activity_id,
        rows=rows,
        metadata=[
            {
                "channel_key": "heartrate",
                "original_size": len(rows),
                "resolution": "high",
                "series_type": "distance",
                "fetched_at": f"{day}T08:30:00Z",
                "batch_id": "pause-test",
                "status": "available",
                "error": None,
            }
        ],
    )


def _seed_dirty_activity_no_hr(
    repo: DuckDBRepository,
    *,
    activity_id: int = 922,
    day: str = "2026-05-22",
) -> None:
    """Seed an activity with NO heartrate samples (all heartrate=None).

    Altitude is ascending so vertical_speed_* will be populated — do NOT
    assert vertical_speed_* is None in the no-HR test case.
    """
    repo.upsert_activity_summary(
        activity_id=activity_id,
        date=f"{day}T06:00:00Z",
        name=f"No-HR activity {activity_id}",
        sport_type="Run",
        distance=4000.0,
        moving_time=1200,
        elapsed_time=1300,
        total_elevation_gain=60.0,
        summary_json=(
            f'{{"id":{activity_id},"name":"NoHR","sport_type":"Run","start_date_local":"{day}T06:00:00Z",'
            '"distance":4000,"moving_time":1200,"elapsed_time":1300,"total_elevation_gain":60,'
            '"has_heartrate":false}'
        ),
        synced_at=f"{day}T07:00:00Z",
    )
    repo.update_activity_detail(activity_id, f'{{"id": {activity_id}, "resource_state": 3}}')
    rows = []
    for idx in range(180):
        rows.append(
            {
                "time_offset": idx * 10,
                "heartrate": None,  # ← no HR
                "velocity": 3.0 + ((idx % 4) * 0.02),
                "altitude": 300.0 + idx * 0.3,  # ascending
                "cadence": 80,
                "lat": 43.3 + idx * 0.00001,
                "lng": 76.8 + idx * 0.00001,
                "grade": 1.0,
                "gap_speed": 3.0,
                "gap_distance": idx * 30.0,
                "is_moving": 1,
                "values_json": '{"distance": %.1f}' % (idx * 30.0),
            }
        )
    repo.replace_stream_rows_and_channel_metadata(
        activity_id,
        rows=rows,
        metadata=[
            {
                "channel_key": "altitude",
                "original_size": len(rows),
                "resolution": "high",
                "series_type": "distance",
                "fetched_at": f"{day}T07:30:00Z",
                "batch_id": "no-hr-test",
                "status": "available",
                "error": None,
            }
        ],
    )


# ---------------------------------------------------------------------------
# Task 1 RED tests — these FAIL until _activity_fact is wired (Task 2 GREEN)
# ---------------------------------------------------------------------------


def test_duckdb_materializer_populates_metric_columns_not_defaults(tmp_path: Path) -> None:
    """After materialization the 14 previously-default columns must be non-default.

    The existing seed has ascending altitude (vertical_speed_vmh > 0), HR data
    (hrr_pct not None, cardiac_drift_quality not None), and TRIMP > 0 (regression).
    """
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)
    with repo:
        _seed_dirty_activity_with_streams(repo)
        materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")

        fact = repo.fetch_activity_metric_fact(920, metric_version=1)

    assert fact is not None
    # Regression: existing computed columns still work
    assert fact["trimp"] > 0
    # Previously-hardcoded defaults must now be populated
    assert fact["vertical_speed_vmh"] is not None
    assert fact["vertical_speed_vmh"] > 0
    assert fact["cardiac_drift_quality"] is not None
    assert fact["hrr_pct"] is not None


def test_duckdb_materializer_pause_inclusive_hr_recovery(tmp_path: Path) -> None:
    """Pause-inclusive fixture: hr_recovery_median_rate not None, pause_count >= 1."""
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)
    with repo:
        _seed_dirty_activity_with_pauses(repo)
        materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")

        fact = repo.fetch_activity_metric_fact(921, metric_version=1)

    assert fact is not None
    assert fact["hr_recovery_median_rate"] is not None
    assert fact["hr_recovery_pause_count"] >= 1


def test_duckdb_materializer_rolling_median_populates(tmp_path: Path) -> None:
    """Rolling-median assertion: after materializing an activity with non-null
    hr_recovery_median_rate, rolling_median_hr_recovery must be non-None.

    This proves _materialize_rolling_facts SELECTs the column name
    'hr_recovery_median_rate' (matching the source column) rather than assuming it.
    """
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)
    with repo:
        _seed_dirty_activity_with_pauses(repo, activity_id=921, day="2026-05-21")
        materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")

        rolling = repo.fetch_rolling_period_facts("2026-05-24", 7, scope="all")

    assert rolling is not None
    # The pause-inclusive activity should have produced a non-null hr_recovery_median_rate,
    # which _materialize_rolling_facts should carry through to median_hr_recovery.
    assert rolling["median_hr_recovery"] is not None


def test_duckdb_materializer_no_hr_columns_stay_at_defaults(tmp_path: Path) -> None:
    """No-HR activity: HR-derived columns stay at their defaults; no exception raised.

    vertical_speed_* are altitude-derived and INDEPENDENT of HR — do NOT assert them None.
    """
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)
    with repo:
        # Seed the no-HR activity on a day after a prior activity so max_heartrate_to_date
        # may or may not return a value (we must not crash either way).
        _seed_dirty_activity_no_hr(repo, activity_id=922, day="2026-05-22")
        # No exception must be raised
        materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")

        fact = repo.fetch_activity_metric_fact(922, metric_version=1)

    assert fact is not None
    # HR-derived columns stay at defaults
    assert fact["hrr_pct"] is None
    assert fact["hr_recovery_median_rate"] is None
    assert fact["hr_recovery_best_rate"] is None
    assert fact["hr_recovery_worst_rate"] is None
    assert fact["hr_recovery_avg_rate"] is None
    assert fact["hr_recovery_pause_count"] == 0
    assert fact["hr_recovery_total_rest_sec"] == 0
    assert fact["cardiac_drift_pct"] is None


def _seed_activity_with_hr(
    repo: DuckDBRepository,
    *,
    activity_id: int,
    day: str,
    heartrates: list[int],
) -> None:
    """Seed one dirty activity whose stream HR samples are exactly ``heartrates``.

    Lets a test pin the activity's own min/max/median HR (and thus the running
    cross-activity max) to deterministic values. All samples are moving
    (velocity 3.0) so no pauses are detected.
    """
    hr_max = max(heartrates)
    hr_avg = round(sum(heartrates) / len(heartrates))
    n = len(heartrates)
    repo.upsert_activity_summary(
        activity_id=activity_id,
        date=f"{day}T06:00:00Z",
        name=f"HR fixture {activity_id}",
        sport_type="Run",
        distance=6000.0,
        moving_time=n,
        elapsed_time=n + 100,
        total_elevation_gain=80.0,
        summary_json=(
            f'{{"id":{activity_id},"name":"HR fixture","sport_type":"Run",'
            f'"start_date_local":"{day}T06:00:00Z","distance":6000,'
            f'"moving_time":{n},"elapsed_time":{n + 100},'
            f'"total_elevation_gain":80,"average_heartrate":{hr_avg},'
            f'"max_heartrate":{hr_max},"has_heartrate":true}}'
        ),
        synced_at=f"{day}T07:00:00Z",
    )
    repo.update_activity_detail(activity_id, f'{{"id": {activity_id}, "resource_state": 3}}')
    rows = [
        {
            "time_offset": idx,
            "heartrate": hr,
            "velocity": 3.0,
            "altitude": 500.0 + idx * 0.1,
            "cadence": 84,
            "lat": 43.2,
            "lng": 76.9,
            "grade": 1.0,
            "gap_speed": 3.1,
            "gap_distance": idx * 3.0,
            "is_moving": 1,
            "values_json": "{}",
        }
        for idx, hr in enumerate(heartrates)
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
                "batch_id": "wr03-test",
                "status": "available",
                "error": None,
            }
        ],
    )


def test_duckdb_materializer_hrr_uses_per_activity_max_not_running_max(tmp_path: Path) -> None:
    """%HRR uses the activity's OWN observed max, not the running cross-activity max.

    Regression for WR-03: an easy effort that follows a hard peak day must not
    have its %HRR deflated by the running cross-activity max. Day-1 is a hard
    activity (max HR 190, which raises the running max). Day-2 is an easy
    activity with its own max 150 and median 120. With hr_rest=53:
        correct (per-activity max 150): (120-53)/(150-53)*100 = 69.1
        buggy   (running max 190):      (120-53)/(190-53)*100 = 48.9
    """
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)
    with repo:
        # Day 1 — hard activity pushes the running max HR to 190.
        _seed_activity_with_hr(repo, activity_id=801, day="2026-05-20", heartrates=[150] * 160 + [190] * 20)
        # Day 2 — easy activity: own max 150, median 120.
        _seed_activity_with_hr(repo, activity_id=802, day="2026-05-21", heartrates=[120] * 175 + [150] * 5)
        materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")

        easy_fact = repo.fetch_activity_metric_fact(802, metric_version=1)
        running_max = repo.max_heartrate_to_date("2026-05-21")
        per_activity_max = repo.activity_hr_range(802)[1]

    assert running_max == 190, "running cross-activity max should be 190 (from day-1 hard effort)"
    assert per_activity_max == 150, "day-2 activity's own observed max should be 150"
    assert easy_fact is not None
    assert easy_fact["hrr_pct"] == 69.1, (
        f"hrr_pct must use per-activity max 150 (=69.1), not running max 190 (=48.9); got {easy_fact['hrr_pct']}"
    )


def test_materializer_extracts_calories_from_detail_json(tmp_path: Path) -> None:
    """activity_metric_facts.calories_kcal is populated from detail_json.calories.

    Calories live only in DetailedActivity (detail_json), never in the summary,
    so the materializer parses them out. Activities whose detail has no calories
    field get NULL (the column is nullable).
    """
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)
    with repo:
        # Activity with a calories value in its detail (update re-enqueues dirty).
        _seed_dirty_activity_with_streams(repo, activity_id=930, day="2026-05-21")
        repo.update_activity_detail(930, '{"id": 930, "resource_state": 3, "calories": 612.5}')
        materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")
        with_cal = repo.fetch_activity_metric_fact(930, metric_version=1)

        # Activity whose detail has no calories field -> NULL.
        _seed_dirty_activity_with_streams(repo, activity_id=931, day="2026-05-22")
        materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")
        without_cal = repo.fetch_activity_metric_fact(931, metric_version=1)

    assert with_cal is not None and with_cal["calories_kcal"] == 612.5
    assert without_cal is not None and without_cal["calories_kcal"] is None


def test_materializer_populates_start_time_local_from_start_date_local(tmp_path: Path) -> None:
    """activity_metric_facts.start_time_local is the HH:MM parsed from start_date_local.

    The materializer parses summary_json.start_date_local with fromisoformat +
    strftime (not a [11:16] slice). The seed fixture starts at T06:00:00Z, so the
    materialized fact carries "06:00".
    """
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)
    with repo:
        _seed_dirty_activity_with_streams(repo, activity_id=940, day="2026-05-21")
        materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")
        fact = repo.fetch_activity_metric_fact(940, metric_version=1)

    assert fact is not None
    assert fact["start_time_local"] == "06:00"


def test_WR_04_partial_batch_does_not_undercount_daily_facts(tmp_path: Path) -> None:
    """WR-04: a limited recompute batch must not write an UNDER-COUNTED daily fact.

    The daily/rolling rollups sum activity_metric_facts at the target metric_version.
    If a day's activities are split across batches (some already at N+1, some still
    queued), summing only the materialized subset under-counts that day. The
    materializer must never roll up a day while some of that day's activities are
    still unmaterialized at the target version: whole days are processed atomically.

    Seed two HR-bearing activities on the SAME day and materialize with limit=1. A
    naive limit would materialize one activity and write a daily fact with
    activity_count=1 (the other activity's load missing). The correct behavior keeps
    the day whole: the daily fact counts BOTH activities.
    """
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)
    with repo:
        _seed_dirty_activity_with_streams(repo, activity_id=920, day="2026-05-21")
        _seed_dirty_activity_with_streams(repo, activity_id=921, day="2026-05-21")

        # limit=1 would, naively, materialize only one of the two same-day activities.
        result = materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00", limit=1)

        # fetch_daily_load_facts uses an exclusive upper bound (day < end_day).
        daily_facts = repo.fetch_daily_load_facts("2026-05-21", "2026-05-22", scope="all")
        fact_920 = repo.fetch_activity_metric_fact(920, metric_version=1)
        fact_921 = repo.fetch_activity_metric_fact(921, metric_version=1)

    assert result["status"] == "ok"
    assert daily_facts, "the 2026-05-21 daily fact must exist"
    assert daily_facts[0]["activity_count"] == 2, (
        "daily fact must count BOTH same-day activities, not a half-materialized subset "
        f"(got activity_count={daily_facts[0]['activity_count']}) — partial-batch under-count"
    )
    assert fact_920 is not None and fact_921 is not None, (
        "both same-day activities must be materialized before their day is rolled up"
    )


def test_materialize_batched_fact_upserts_match_sequential(tmp_path, monkeypatch):
    """Batched fact upserts are byte-identical to single-row upserts.

    Parity gate for the batching refactor: materialize the SAME multi-day fixture twice —
    once with the per-statement row cap forced to 1 (the old single-row-per-statement
    behaviour) and once at the default 250 (batched) — and assert every row of all four
    fact tables matches. Catches silent column-level drift the value-asserting tests miss.
    """
    from mcp_strava.adapters.duckdb import repository as repo_module

    fact_tables = ("activity_metric_facts", "daily_load_facts", "training_model_daily", "rolling_period_facts")

    def _materialize_and_dump(cap: int) -> dict[str, list]:
        monkeypatch.setattr(repo_module, "_FACT_UPSERT_BATCH_ROWS", cap)
        run_dir = tmp_path / f"cap{cap}"
        run_dir.mkdir()
        _fixture, repo = _create_duckdb_read_model_repo(run_dir)
        try:
            _seed_dirty_activity_with_streams(repo, activity_id=920, day="2026-05-21")
            _seed_dirty_activity_with_streams(repo, activity_id=921, day="2026-05-10")
            materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")
            return {table: repo.conn.execute(f"SELECT * FROM {table} ORDER BY ALL").fetchall() for table in fact_tables}
        finally:
            repo.close()

    sequential = _materialize_and_dump(1)
    batched = _materialize_and_dump(250)
    for table in fact_tables:
        assert batched[table] == sequential[table], f"{table} diverged between batched and sequential upserts"
        assert len(batched[table]) > 0, f"{table} should have rows (fixture is non-empty)"


def test_daily_fact_sums_between_matches_per_day_reads(tmp_path: Path) -> None:
    """Batched daily-fact range read == N single-day reads (Phase 2 read-batching gate).

    daily_fact_sums_between collapses the materializer's former per-day daily_fact_sums()
    loop into one GROUP BY scan. Prove the grouped result equals an independent no-GROUP-BY
    per-day aggregate for every day with facts, and that days with no facts are simply
    absent from the dict — the shape the materializer maps to a zeroed daily fact.
    """
    cols = ("distance_m", "moving_time_s", "elevation_gain_m", "zone4_seconds", "zone5_seconds", "anomaly_count")
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)
    with repo:
        _seed_dirty_activity_with_streams(repo, activity_id=920, day="2026-05-21")
        _seed_dirty_activity_with_streams(repo, activity_id=921, day="2026-05-10")
        materialize_read_model(repo, metric_version=1, now="2026-05-24T12:00:00")

        start, end = "2026-05-10", "2026-05-24"
        batched = repo.daily_fact_sums_between(start, end, 1)

        per_day_sql = (
            f"SELECT {', '.join(f'SUM({c})' for c in cols)} "
            "FROM activity_metric_facts WHERE activity_day = CAST(? AS DATE) AND metric_version = ?"
        )
        days_with_facts: list[str] = []
        current, last = date.fromisoformat(start), date.fromisoformat(end)
        while current <= last:
            day = current.isoformat()
            reference = repo.conn.execute(per_day_sql, [day, 1]).fetchone()
            assert reference is not None  # no-GROUP-BY aggregate always returns one row
            if any(value is not None for value in reference):
                days_with_facts.append(day)
                assert day in batched, f"{day} has facts but is absent from the batched read"
                assert tuple(batched[day][col] for col in cols) == tuple(reference), (
                    f"{day} batched sums diverge from the per-day reference"
                )
            else:
                assert day not in batched, f"{day} has no facts but appears in the batched read"
            current += timedelta(days=1)

    assert days_with_facts == ["2026-05-10", "2026-05-21"], "fixture should populate exactly the two seeded days"


def test_activity_materialization_batch_reads_match_per_activity_methods(tmp_path: Path) -> None:
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)
    settings = get_settings()
    athlete = settings.athlete
    assert athlete.hr_rest is not None
    with repo:
        _seed_activity_with_hr(repo, activity_id=801, day="2026-05-20", heartrates=[150] * 160 + [190] * 20)
        _seed_activity_with_hr(repo, activity_id=802, day="2026-05-21", heartrates=[120] * 175 + [150] * 5)
        _seed_dirty_activity_no_hr(repo, activity_id=803, day="2026-05-22")
        dirty_rows = repo.dirty_activity_rows_for_materialization(1)
        activity_ids = [int(row["activity_id"]) for row in dirty_rows]

        sources = repo.activity_materialization_sources(activity_ids)
        scalars = repo.activity_stream_scalars_for_materialization(activity_ids, 0.5)
        hr_max_by_day = repo.max_heartrate_to_dates(str(row["activity_day"]) for row in dirty_rows)

        bounds_by_activity_id = {}
        for row in dirty_rows:
            activity_id = int(row["activity_id"])
            scalar = scalars[activity_id]
            hr_max = hr_max_by_day[str(row["activity_day"])]
            if hr_max is not None and scalar.hr_count > 0:
                bounds_by_activity_id[activity_id] = get_zone_model(athlete.hr_zone_model).zone_bounds(
                    hr_max=hr_max,
                    hr_rest=athlete.hr_rest,
                )
        zones = repo.activity_zone_trimp_for_bounds(bounds_by_activity_id)

        for row in dirty_rows:
            activity_id = int(row["activity_id"])
            assert sources[activity_id].activity == activity_by_id(repo, activity_id)
            assert sources[activity_id].source_hash == repo.source_state_for_activity(activity_id)["source_hash"]

            stream_count, hr_count = repo.stream_counts_for_activity(activity_id)
            min_hr, max_hr = repo.activity_hr_range(activity_id)
            scalar = scalars[activity_id]
            assert (scalar.stream_count, scalar.hr_count) == (stream_count, hr_count)
            assert (scalar.min_hr, scalar.max_hr) == (min_hr, max_hr)
            assert scalar.cardiac_cost == repo.activity_cc(activity_id, 0.5)
            assert scalar.median_hr == repo.activity_median_heartrate(activity_id)
            assert hr_max_by_day[str(row["activity_day"])] == repo.max_heartrate_to_date(str(row["activity_day"]))

            if activity_id in bounds_by_activity_id:
                expected_zones = repo.zone_seconds_for_activity(activity_id, bounds_by_activity_id[activity_id])
                expected_trimp = repo.activity_trimp(activity_id, bounds=bounds_by_activity_id[activity_id])
                actual_zones = zones[activity_id]
                assert (
                    actual_zones.zone1_seconds,
                    actual_zones.zone2_seconds,
                    actual_zones.zone3_seconds,
                    actual_zones.zone4_seconds,
                    actual_zones.zone5_seconds,
                ) == expected_zones
                assert actual_zones.trimp == expected_trimp


def test_activity_facts_batched_match_sequential_reference(tmp_path: Path) -> None:
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)
    with repo:
        _seed_dirty_activity_with_streams(repo, activity_id=920, day="2026-05-21")
        _seed_dirty_activity_with_pauses(repo, activity_id=921, day="2026-05-21")
        _seed_dirty_activity_no_hr(repo, activity_id=922, day="2026-05-22")
        dirty_rows = repo.dirty_activity_rows_for_materialization(1)
        settings = get_settings()
        computed_at = "2026-05-24T12:00:00"

        sequential = [_activity_fact(repo, row, 1, computed_at, settings) for row in dirty_rows]
        batched = _activity_facts_batched(repo, dirty_rows, 1, computed_at, settings)

    assert batched == sequential


def test_materializer_avoids_per_activity_scalar_read_fanout(tmp_path: Path) -> None:
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)

    class CountingRepo(DuckDBRepository):
        hot_scalar_reads = 0

        def _fetchone(self, sql, params=None):
            compact = " ".join(sql.split())
            if (
                ("FROM activities" in compact and "WHERE id = ?" in compact)
                or "FROM activity_source_state WHERE activity_id = ?" in compact
                or ("FROM streams" in compact and "WHERE activity_id = ?" in compact)
            ):
                self.hot_scalar_reads += 1
            return super()._fetchone(sql, params)

    with repo:
        for idx in range(5):
            _seed_dirty_activity_with_streams(repo, activity_id=950 + idx, day=f"2026-05-{10 + idx:02d}")
        counting_repo = CountingRepo(repo.conn)

        materialize_read_model(counting_repo, metric_version=1, now="2026-05-24T12:00:00")

    assert counting_repo.hot_scalar_reads == 0


def test_materializer_batch_reads_run_before_write_transaction(tmp_path: Path) -> None:
    _fixture, repo = _create_duckdb_read_model_repo(tmp_path)

    class TransactionDepthRepo(DuckDBRepository):
        batch_read_depths: list[int]

        def __init__(self, conn):
            super().__init__(conn)
            self.batch_read_depths = []

        def _record_batch_read_depth(self) -> None:
            self.batch_read_depths.append(self._transaction_depth)

        def activity_materialization_sources(self, *args, **kwargs):
            self._record_batch_read_depth()
            return super().activity_materialization_sources(*args, **kwargs)

        def activity_stream_scalars_for_materialization(self, *args, **kwargs):
            self._record_batch_read_depth()
            return super().activity_stream_scalars_for_materialization(*args, **kwargs)

        def max_heartrate_to_dates(self, *args, **kwargs):
            self._record_batch_read_depth()
            return super().max_heartrate_to_dates(*args, **kwargs)

        def activity_zone_trimp_for_bounds(self, *args, **kwargs):
            self._record_batch_read_depth()
            return super().activity_zone_trimp_for_bounds(*args, **kwargs)

        def stream_hr_velocity_simple_rows_for_activities(self, *args, **kwargs):
            self._record_batch_read_depth()
            return super().stream_hr_velocity_simple_rows_for_activities(*args, **kwargs)

        def stream_hr_velocity_time_rows_for_activities(self, *args, **kwargs):
            self._record_batch_read_depth()
            return super().stream_hr_velocity_time_rows_for_activities(*args, **kwargs)

        def stream_altitude_rows_for_activities(self, *args, **kwargs):
            self._record_batch_read_depth()
            return super().stream_altitude_rows_for_activities(*args, **kwargs)

    with repo:
        _seed_dirty_activity_with_streams(repo, activity_id=980, day="2026-05-21")
        depth_repo = TransactionDepthRepo(repo.conn)

        materialize_read_model(depth_repo, metric_version=1, now="2026-05-24T12:00:00")

    assert depth_repo.batch_read_depths
    assert set(depth_repo.batch_read_depths) == {0}
