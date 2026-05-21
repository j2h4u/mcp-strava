import ast
import sqlite3
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mcp_strava.adapters.sqlite.migrations import run_migrations
from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.adapters.strava import StravaResponse, StravaUnavailable
from mcp_strava.adapters.strava.types import StravaRateInfo


@pytest.fixture(autouse=True)
def forbid_live_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise RuntimeError("live network forbidden")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)


class FakeClock:
    def __init__(self, value: float = 1_716_206_400.0):
        self.value = value

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds

    def iso(self) -> str:
        return datetime.fromtimestamp(self.value, tz=timezone.utc).replace(tzinfo=None).isoformat()


class FakeSleeper:
    def __init__(self, clock: FakeClock | None = None):
        self.clock = clock
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if self.clock is not None:
            self.clock.advance(seconds)


class FakeStravaTransport:
    def __init__(self, failures: dict[str, Exception] | None = None):
        self.failures = failures or {}
        self.calls_by_path: dict[str, int] = defaultdict(int)

    def fetch(self, path: str) -> StravaResponse:
        self.calls_by_path[path] += 1
        for needle, exc in self.failures.items():
            if needle in path:
                raise exc
        if path.startswith("/athlete/activities"):
            return StravaResponse(
                data=[
                    {
                        "id": 500,
                        "name": "Morning Run",
                        "sport_type": "Run",
                        "start_date_local": "2026-05-21T06:00:00Z",
                        "distance": 1000,
                        "moving_time": 600,
                        "elapsed_time": 620,
                        "total_elevation_gain": 10,
                    }
                ],
                rate_info=StravaRateInfo(),
                status=200,
            )
        if path.startswith("/activities/500/streams"):
            return StravaResponse(
                data={
                    "time": {"data": [0, 1]},
                    "heartrate": {"data": [140, 141]},
                    "velocity_smooth": {"data": [3.0, 3.1]},
                    "moving": {"data": [1, 1]},
                },
                rate_info=StravaRateInfo(),
                status=200,
            )
        if path.startswith("/activities/500/kudos"):
            return StravaResponse(data=[], rate_info=StravaRateInfo(), status=200)
        if path.startswith("/activities/500"):
            return StravaResponse(data={"id": 500, "name": "Morning Run", "resource_state": 3}, rate_info=StravaRateInfo(), status=200)
        return StravaResponse(data=[], rate_info=StravaRateInfo(), status=200)


def _create_fixture_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            date TEXT, name TEXT, sport_type TEXT,
            distance REAL, moving_time INTEGER, elapsed_time INTEGER,
            total_elevation_gain REAL,
            summary_json TEXT, detail_json TEXT, synced_at TEXT
        );
        CREATE TABLE streams (
            activity_id INTEGER, time_offset INTEGER,
            heartrate INTEGER, velocity REAL, altitude REAL,
            cadence INTEGER, lat REAL, lng REAL, grade REAL,
            gap_speed REAL, gap_distance REAL, is_moving INTEGER, latlng TEXT,
            PRIMARY KEY (activity_id, time_offset)
        );
        CREATE INDEX idx_streams_act ON streams(activity_id);
        CREATE TABLE athlete_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT, zones_json TEXT
        );
        CREATE TABLE sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            activities_seen INTEGER,
            activities_new INTEGER,
            streams_fetched INTEGER,
            details_fetched INTEGER,
            api_calls INTEGER,
            error TEXT,
            kudos_fetched INTEGER
        );
        CREATE TABLE kudos (
            activity_id INTEGER NOT NULL,
            firstname TEXT NOT NULL DEFAULT '',
            lastname TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (activity_id, firstname, lastname)
        );
        PRAGMA user_version=1;
        """
    )
    conn.commit()
    conn.close()
    run_migrations(path)


def _repo(tmp_path: Path) -> SQLiteRepository:
    path = tmp_path / "refresh.db"
    _create_fixture_db(path)
    return SQLiteRepository.from_path(path)


def test_run_once_completes_daily_refresh_per_REFRESH_01_STRAVA_03(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_once

    clock = FakeClock()
    with _repo(tmp_path) as repo:
        result = run_once(repo, FakeStravaTransport(), RefreshPolicy(), clock, FakeSleeper(clock))
        state = repo.get_refresh_state()
        logs = repo.read_sync_log()

    assert result.status == "ok"
    assert state.checkpoint_stage == Stage.COMPLETE.value
    assert state.last_success_at is not None
    assert logs


def test_run_once_same_day_skips_then_force_re_runs_per_D06_D15(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, RefreshSkipped, run_once

    clock = FakeClock()
    transport = FakeStravaTransport()
    with _repo(tmp_path) as repo:
        assert run_once(repo, transport, RefreshPolicy(), clock, FakeSleeper(clock)).status == "ok"
        skipped = run_once(repo, transport, RefreshPolicy(), clock, FakeSleeper(clock))
        assert isinstance(skipped, RefreshSkipped)
        assert skipped.reason == "already_complete"
        calls_before_force = dict(transport.calls_by_path)
        forced = run_once(repo, transport, RefreshPolicy(), clock, FakeSleeper(clock), force=True, mode="quick")

    assert forced.status == "ok"
    assert transport.calls_by_path["/athlete/activities?per_page=100&page=1"] > calls_before_force["/athlete/activities?per_page=100&page=1"]


def test_run_once_force_still_honors_lease_and_backoff_per_D15(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_once

    clock = FakeClock()
    with _repo(tmp_path) as repo:
        assert repo.acquire_refresh_lease("other", "2026-05-21T12:10:00", "2026-05-21T12:00:00")
        skipped = run_once(repo, FakeStravaTransport(), RefreshPolicy(), clock, FakeSleeper(clock), force=True)
        assert skipped.reason == "refresh_in_progress"
        repo.release_refresh_lease("other")
        repo.record_refresh_failure("2026-05-21T12:00:00", "rate_limited", "2026-05-21T13:00:00")
        skipped = run_once(repo, FakeStravaTransport(), RefreshPolicy(), clock, FakeSleeper(clock), force=True)

    assert skipped.reason == "refresh_delayed"


def test_run_once_failure_persists_backoff_and_resumes_per_D09_D13(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_once

    clock = FakeClock()
    with _repo(tmp_path) as repo:
        result = run_once(
            repo,
            FakeStravaTransport({"/streams": StravaUnavailable("rate_limited")}),
            RefreshPolicy(),
            clock,
            FakeSleeper(clock),
        )
        state = repo.get_refresh_state()
        skipped = run_once(repo, FakeStravaTransport(), RefreshPolicy(), clock, FakeSleeper(clock))

    assert result.status == "failed"
    assert result.reason == "rate_limited"
    assert state.last_error_code == "rate_limited"
    assert state.backoff_until is not None
    assert state.lease_owner is None
    assert skipped.reason == "refresh_delayed"


def test_run_backfill_skips_summaries_and_kudos_per_D16(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_backfill

    clock = FakeClock()
    transport = FakeStravaTransport()
    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            activity_id=500,
            date="2026-05-21T06:00:00Z",
            name="Needs Backfill",
            sport_type="Run",
            distance=1000,
            moving_time=600,
            elapsed_time=620,
            total_elevation_gain=10,
            summary_json="{}",
            synced_at="2026-05-21T07:00:00Z",
        )
        result = run_backfill(repo, transport, RefreshPolicy(), clock, FakeSleeper(clock), since="2026-05-20")
        state = repo.get_refresh_state()

    assert result.status == "ok"
    assert state.checkpoint_stage == Stage.COMPLETE_BACKFILL.value
    assert not any(path.startswith("/athlete/activities") for path in transport.calls_by_path)
    assert not any("kudos" in path for path in transport.calls_by_path)
    assert "refresh-backfill"


def test_freshness_evaluate_all_states_per_D05(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, evaluate_freshness

    now = datetime(2026, 5, 21, 12, 0, 0)
    policy = RefreshPolicy(warn_age_hours=12, max_age_hours=24, recent_failure_window_seconds=3600)

    with _repo(tmp_path) as repo:
        repo.record_refresh_success("2026-05-21T11:00:00")
        assert evaluate_freshness(repo.get_refresh_state(), now, policy) == "fresh"
        repo.record_refresh_success("2026-05-20T23:00:00")
        assert evaluate_freshness(repo.get_refresh_state(), now, policy) == "aging"
        repo.record_refresh_success("2026-05-20T11:00:00")
        assert evaluate_freshness(repo.get_refresh_state(), now, policy) == "stale"
        repo.record_refresh_failure("2026-05-21T11:30:00", "network_unstable", None)
        assert evaluate_freshness(repo.get_refresh_state(), now, policy) == "refresh_failed"
        repo.record_refresh_failure("2026-05-21T11:30:00", "rate_limited", "2026-05-21T13:00:00")
        assert evaluate_freshness(repo.get_refresh_state(), now, policy) == "refresh_delayed"
        repo.acquire_refresh_lease("owner", "2026-05-21T12:10:00", "2026-05-21T12:00:00")
        assert evaluate_freshness(repo.get_refresh_state(), now, policy) == "refresh_in_progress"


def test_enqueue_refresh_request_if_stale_is_idempotent_per_D04_REFRESH_02(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, enqueue_refresh_request_if_stale

    now = datetime(2026, 5, 21, 12, 0, 0)
    with _repo(tmp_path) as repo:
        repo.record_refresh_success("2026-05-20T11:00:00")
        assert enqueue_refresh_request_if_stale(repo, now, RefreshPolicy(), reason="first_use_of_day", requested_for_day="2026-05-21")
        assert not enqueue_refresh_request_if_stale(repo, now, RefreshPolicy(), reason="first_use_of_day", requested_for_day="2026-05-21")
        assert not enqueue_refresh_request_if_stale(repo, now, RefreshPolicy(), reason="first_use_of_day", requested_for_day="2026-05-21")
        assert len(repo.pending_refresh_requests()) == 1


def test_refresh_modules_do_not_import_sync_per_D17():
    src_root = Path(__file__).resolve().parents[1] / "src" / "mcp_strava" / "refresh"
    violations: list[str] = []
    for py_file in src_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    if name.name == "mcp_strava.sync":
                        violations.append(f"{py_file}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom) and node.module == "mcp_strava.sync":
                violations.append(f"{py_file}:{node.lineno}")

    assert violations == []
