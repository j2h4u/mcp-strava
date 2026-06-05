import ast
from pathlib import Path

import pytest

from mcp_strava.adapters.duckdb.kudos_store import kudos_for_activity, list_kudos, upsert_kudos
from mcp_strava.adapters.duckdb.refresh_state_store import RefreshStateStore
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.duckdb.sync_log_store import append_sync_log, read_sync_log
from tests._fixtures_duckdb import create_empty_fixture_db


def _guard_load_paths_do_not_use_raw_activity_stream_sql() -> list[str]:
    repo_root = Path(__file__).resolve().parents[1]
    files = [
        repo_root / "src" / "mcp_strava" / "metrics.py",
    ]
    violations: list[str] = []

    for py_file in files:
        rel = py_file.relative_to(repo_root).as_posix()
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr == "execute"):
                continue
            if not node.args:
                continue
            first = node.args[0]
            sql_literal = None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                sql_literal = first.value
            elif isinstance(first, ast.JoinedStr):
                sql_literal = "".join(
                    part.value
                    for part in first.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                )
            if not sql_literal:
                continue
            lower_sql = " ".join(sql_literal.lower().split())
            if "from streams" in lower_sql or "from activities" in lower_sql:
                violations.append(f"{rel}:{node.lineno}")
    return violations


def test_repository_boundary_covers_activity_stream_zone_kudos_and_synclog(tmp_path: Path) -> None:
    fixture = tmp_path / "repo.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        repo.upsert_activity_summary(
            activity_id=1,
            date="2026-05-21T06:00:00Z",
            name="Morning Run",
            sport_type="Run",
            distance=10000.0,
            moving_time=3600,
            elapsed_time=3700,
            total_elevation_gain=120.0,
            summary_json="{}",
            synced_at="2026-05-21T07:00:00Z",
        )
        rows = repo.recent_activities(limit=5)
        assert rows and rows[0].id == 1

        repo.insert_stream_rows_chunked(
            1,
            [
                {
                    "time_offset": idx,
                    "heartrate": 145,
                    "velocity": 3.5,
                    "altitude": 100.0,
                    "cadence": 85,
                    "lat": 43.2,
                    "lng": 76.9,
                    "grade": 1.0,
                    "gap_speed": 3.6,
                    "gap_distance": 10.0,
                    "is_moving": 1,
                }
                # 11 rows with chunk_size=5 exercises the same multi-chunk +
                # partial-remainder path (5+5+1) as the old 6001/5000, without the
                # ~45s cost of row-by-row DuckDB inserts at scale. This is a
                # coverage test for the chunking boundary, not a performance test.
                for idx in range(11)
            ],
            chunk_size=5,
        )

        stream_rows = repo.activity_stream_rows(1)
        assert len(stream_rows) == 11

        with pytest.raises(KeyError):
            repo.replace_stream_rows_chunked(
                1,
                [
                    {
                        "time_offset": 0,
                        "heartrate": 150,
                        "velocity": 3.5,
                        "altitude": 100.0,
                        "cadence": 85,
                        "lat": 43.2,
                        "lng": 76.9,
                        "grade": 1.0,
                        "gap_speed": 3.6,
                        "gap_distance": 10.0,
                        "is_moving": 1,
                    },
                    {"heartrate": 151},
                ],
                chunk_size=5,
            )
        assert len(repo.activity_stream_rows(1)) == 11

        replaced = repo.replace_stream_rows_chunked(
            1,
            [
                {
                    "time_offset": 0,
                    "heartrate": 150,
                    "velocity": 3.5,
                    "altitude": 100.0,
                    "cadence": 85,
                    "lat": 43.2,
                    "lng": 76.9,
                    "grade": 1.0,
                    "gap_speed": 3.6,
                    "gap_distance": 10.0,
                    "is_moving": 1,
                }
            ],
        )
        assert replaced == 1
        assert len(repo.activity_stream_rows(1)) == 1

        repo.insert_athlete_zones("2026-05-21T07:00:00Z", "[]")
        assert repo.latest_athlete_zones() is not None

        upsert_kudos(repo, 1, "A", "B", "2026-05-21T08:00:00Z")
        assert list_kudos(repo, limit=5)
        assert kudos_for_activity(repo, 1)

        append_sync_log(
            repo,
            timestamp="2026-05-21T09:00:00Z",
            status="ok",
            activities_seen=1,
            activities_new=1,
            streams_fetched=1,
            details_fetched=1,
            api_calls=1,
            error=None,
            kudos_fetched=1,
        )
        assert read_sync_log(repo, limit=5)


def test_replace_stream_rows_and_channel_metadata_stores_null_values_json_when_no_extra_values(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "repo.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        repo.upsert_activity_summary(
            activity_id=1,
            date="2026-05-21T06:00:00Z",
            name="Morning Run",
            sport_type="Run",
            distance=10000.0,
            moving_time=3600,
            elapsed_time=3700,
            total_elevation_gain=120.0,
            summary_json="{}",
            synced_at="2026-05-21T07:00:00Z",
        )
        repo.replace_stream_rows_and_channel_metadata(
            1,
            rows=[
                {
                    "time_offset": 0,
                    "heartrate": 150,
                    "velocity": 3.5,
                    "altitude": 100.0,
                    "cadence": 85,
                    "lat": 43.2,
                    "lng": 76.9,
                    "grade": 1.0,
                    "gap_speed": 3.6,
                    "gap_distance": 10.0,
                    "is_moving": 1,
                    "values_json": None,
                }
            ],
            metadata=[],
        )

        row = repo.conn.execute("SELECT values_json FROM streams WHERE activity_id = 1 AND time_offset = 0").fetchone()

    assert row is not None
    assert row[0] is None


def test_repository_keeps_refresh_state_out_of_activity_boundary() -> None:
    retired = {
        "get_refresh_state",
        "acquire_refresh_lease",
        "release_refresh_lease",
        "set_checkpoint",
        "record_refresh_attempt",
        "record_refresh_success",
        "record_refresh_failure",
        "enqueue_refresh_request",
        "pending_refresh_requests",
        "mark_refresh_requests_consumed",
    }

    assert not (retired & set(dir(DuckDBRepository)))


def test_refresh_state_store_exposes_refresh_methods() -> None:
    expected = {
        "get_refresh_state",
        "acquire_refresh_lease",
        "release_refresh_lease",
        "set_checkpoint",
        "record_refresh_attempt",
        "record_refresh_success",
        "record_refresh_failure",
        "enqueue_refresh_request",
        "pending_refresh_requests",
        "mark_refresh_requests_consumed",
    }

    assert expected <= set(dir(RefreshStateStore))


def test_acquire_refresh_lease_is_single_writer(tmp_path: Path) -> None:
    fixture = tmp_path / "repo.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        store = RefreshStateStore.from_connection(repo.conn)
        assert store.acquire_refresh_lease("owner-a", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")
        assert not store.acquire_refresh_lease("owner-b", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")
        store.release_refresh_lease("owner-a")
        assert store.acquire_refresh_lease("owner-b", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")


def test_enqueue_refresh_request_is_idempotent_per_D19(tmp_path: Path) -> None:
    fixture = tmp_path / "repo.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        store = RefreshStateStore.from_connection(repo.conn)
        assert store.enqueue_refresh_request("first_use_of_day", "2026-05-21")
        assert not store.enqueue_refresh_request("first_use_of_day", "2026-05-21")
        assert not store.enqueue_refresh_request("first_use_of_day", "2026-05-21")
        assert len(store.pending_refresh_requests()) == 1
        assert store.mark_refresh_requests_consumed("2026-05-21T12:00:00Z") == 1
        assert store.enqueue_refresh_request("first_use_of_day", "2026-05-21")
        assert len(store.pending_refresh_requests()) == 1


def test_mark_refresh_requests_consumed_marks_all_pending_per_D19(tmp_path: Path) -> None:
    from inspect import signature

    fixture = tmp_path / "repo.duckdb"
    create_empty_fixture_db(fixture)

    assert list(signature(RefreshStateStore.mark_refresh_requests_consumed).parameters) == ["self", "consumed_at"]
    with DuckDBRepository.from_path(fixture) as repo:
        store = RefreshStateStore.from_connection(repo.conn)
        store.enqueue_refresh_request("first_use_of_day", "2026-05-21")
        store.enqueue_refresh_request("manual", "2026-05-21")
        store.enqueue_refresh_request("timer", "2026-05-21")
        assert store.mark_refresh_requests_consumed("2026-05-21T12:00:00Z") == 3
        assert store.pending_refresh_requests() == []
        assert store.mark_refresh_requests_consumed("2026-05-21T12:01:00Z") == 0


def test_record_refresh_failure_rejects_unknown_reason_code(tmp_path: Path) -> None:
    fixture = tmp_path / "repo.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        store = RefreshStateStore.from_connection(repo.conn)
        store.record_refresh_failure("2026-05-21T12:00:00Z", "rate_limited", "2026-05-21T12:15:00Z")
        with pytest.raises(ValueError):
            store.record_refresh_failure("2026-05-21T12:00:00Z", "secret-token-leak", None)


def test_pending_refresh_requests_and_mark_consumed_roundtrip(tmp_path: Path) -> None:
    fixture = tmp_path / "repo.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        store = RefreshStateStore.from_connection(repo.conn)
        assert store.enqueue_refresh_request("first_use_of_day", "2026-05-21")
        pending = store.pending_refresh_requests()
        assert len(pending) == 1
        assert pending[0].reason == "first_use_of_day"
        assert pending[0].consumed_at is None
        assert store.mark_refresh_requests_consumed("2026-05-21T12:00:00Z") == 1
        assert store.pending_refresh_requests() == []


def test_activities_missing_streams_filters_by_since_per_D16(tmp_path: Path) -> None:
    fixture = tmp_path / "repo.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        repo.upsert_activity_summary(
            activity_id=101,
            date="2026-05-20T06:00:00Z",
            name="Missing Streams",
            sport_type="Run",
            distance=1000,
            moving_time=600,
            elapsed_time=700,
            total_elevation_gain=10,
            summary_json="{}",
            synced_at="2026-05-20T07:00:00Z",
        )
        rows = repo.activities_missing_streams("2026-05-19")

    assert [row.id for row in rows] == [101]


def test_activities_missing_details_filters_by_since_per_D16(tmp_path: Path) -> None:
    fixture = tmp_path / "repo.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        repo.upsert_activity_summary(
            activity_id=101,
            date="2026-05-20T06:00:00Z",
            name="Missing Details",
            sport_type="Run",
            distance=1000,
            moving_time=600,
            elapsed_time=700,
            total_elevation_gain=10,
            summary_json="{}",
            synced_at="2026-05-20T07:00:00Z",
        )
        rows = repo.activities_missing_details("2026-05-19")

    assert [row.id for row in rows] == [101]


def test_repository_module_does_not_call_strava_network(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture = tmp_path / "repo.duckdb"
    create_empty_fixture_db(fixture)

    import mcp_strava.adapters.strava.client as strava_client

    def _boom(*_args, **_kwargs):
        raise AssertionError("network auth/api must not be touched by repository tests")

    monkeypatch.setattr(strava_client.StravaClient, "api_request", _boom)
    monkeypatch.setattr(strava_client.StravaClient, "refresh_token", _boom)

    with DuckDBRepository.from_path(fixture) as repo:
        repo.recent_activities(limit=1)


def test_load_paths_use_repository_instead_of_raw_activity_stream_sql() -> None:
    violations = _guard_load_paths_do_not_use_raw_activity_stream_sql()
    assert violations == []


def test_runtime_dbconn_and_repository_factory_route_duckdb_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcp_strava.adapters.duckdb.connection import MirrorConn
    from mcp_strava.settings import reset_settings_cache

    fixture = tmp_path / "strava.duckdb"
    create_empty_fixture_db(fixture)

    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(fixture))
    reset_settings_cache()
    try:
        with MirrorConn() as conn:
            repo = DuckDBRepository.from_connection(conn)
            assert isinstance(repo, DuckDBRepository)
            assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 0
    finally:
        reset_settings_cache()
