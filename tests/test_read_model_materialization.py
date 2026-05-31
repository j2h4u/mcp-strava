from pathlib import Path

import pytest

from mcp_strava.adapters.duckdb.read_model_materializer import materialize_read_model
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
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
        def upsert_daily_load_fact(self, *args, **kwargs):
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
        if is_pause:
            heartrate = max(110, 150 - (idx - 50) * 1)
        else:
            heartrate = 140 + (idx % 20)
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
