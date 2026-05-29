import json
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.strava import StravaResponse, StravaUnavailable
from mcp_strava.adapters.strava.types import StravaRateInfo
from tests._fixtures_duckdb import create_fixture_db


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


def _repo(tmp_path: Path) -> DuckDBRepository:
    path = tmp_path / "refresh.duckdb"
    create_fixture_db(path)
    return DuckDBRepository.from_path(path)


def test_sync_summaries_skips_rewrite_when_summary_unchanged(tmp_path):
    """Re-syncing an unchanged activity must NOT rewrite the activities row.

    Each rewrite of a PRIMARY-KEY-indexed row churns the DuckDB ART index, which
    (a) bloats the file unbounded — freed index blocks are never reused — and
    (b) re-triggers the upstream ART stale-update-read corruption. The daily
    refresh sees the same ~600 activities every cycle with no content change, so
    unchanged rows must be left untouched. synced_at staying at its first value
    across an unchanged re-sync is the observable proof that no write happened.
    """
    from mcp_strava.refresh._sync_ops import sync_summaries

    activity = {
        "id": 500,
        "name": "Morning Run",
        "sport_type": "Run",
        "start_date_local": "2026-05-21T06:00:00Z",
        "distance": 1000,
        "moving_time": 600,
        "elapsed_time": 620,
        "total_elevation_gain": 10,
    }

    class _SummaryTransport:
        def __init__(self, payload):
            self.payload = payload

        def fetch(self, path: str) -> StravaResponse:
            if path.startswith("/athlete/activities"):
                return StravaResponse(data=[self.payload], rate_info=StravaRateInfo(), status=200)
            return StravaResponse(data=[], rate_info=StravaRateInfo(), status=200)

    transport = _SummaryTransport(activity)
    with _repo(tmp_path) as repo:
        seen1, new1 = sync_summaries(repo, transport, "2026-05-29T00:00:00")
        first = repo.activity_by_id(500)

        # Same content, later sync timestamp -> must be a no-op (no row rewrite).
        seen2, new2 = sync_summaries(repo, transport, "2026-05-29T01:00:00")
        unchanged = repo.activity_by_id(500)

        # Genuinely changed content -> must still write through.
        transport.payload = {**activity, "name": "Renamed Run"}
        sync_summaries(repo, transport, "2026-05-29T02:00:00")
        changed = repo.activity_by_id(500)

    assert (seen1, new1) == (1, 1)
    assert (seen2, new2) == (1, 0)
    assert first.synced_at == "2026-05-29T00:00:00"
    assert unchanged.synced_at == "2026-05-29T00:00:00"  # untouched by the no-op re-sync
    assert changed.name == "Renamed Run"
    assert changed.synced_at == "2026-05-29T02:00:00"  # real change wrote through


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


def test_run_once_skips_until_refresh_interval_then_re_runs_per_D06_D15(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, RefreshSkipped, run_once

    clock = FakeClock()
    policy = RefreshPolicy(regular_refresh_interval_seconds=3600)
    transport = FakeStravaTransport()
    with _repo(tmp_path) as repo:
        assert run_once(repo, transport, policy, clock, FakeSleeper(clock)).status == "ok"
        skipped = run_once(repo, transport, policy, clock, FakeSleeper(clock))
        assert isinstance(skipped, RefreshSkipped)
        assert skipped.reason == "already_complete"
        clock.advance(3599)
        skipped = run_once(repo, transport, policy, clock, FakeSleeper(clock))
        assert isinstance(skipped, RefreshSkipped)
        assert skipped.reason == "already_complete"
        calls_before_periodic = dict(transport.calls_by_path)
        clock.advance(1)
        periodic = run_once(repo, transport, policy, clock, FakeSleeper(clock), mode="periodic")
        calls_before_force = dict(transport.calls_by_path)
        forced = run_once(repo, transport, policy, clock, FakeSleeper(clock), force=True, mode="quick")

    assert periodic.status == "ok"
    assert transport.calls_by_path["/athlete/activities?per_page=100&page=1"] > calls_before_periodic["/athlete/activities?per_page=100&page=1"]
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


def test_run_once_after_stream_failure_resumes_without_summary_page_walk_per_D09(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_once

    clock = FakeClock()
    policy = RefreshPolicy()
    with _repo(tmp_path) as repo:
        failed = run_once(
            repo,
            FakeStravaTransport({"/streams": StravaUnavailable("rate_limited")}),
            policy,
            clock,
            FakeSleeper(clock),
        )
        failed_state = repo.get_refresh_state()
        clock.advance(policy.backoff_seconds_on_rate_limit_default + 1)
        resumed_transport = FakeStravaTransport()
        resumed = run_once(repo, resumed_transport, policy, clock, FakeSleeper(clock))

    assert failed.status == "failed"
    assert failed_state.checkpoint_stage == Stage.STREAMS.value
    assert resumed.status == "ok"
    assert resumed_transport.calls_by_path["/athlete/activities?per_page=100&page=1"] == 0
    stream_call = next(path for path in resumed_transport.calls_by_path if path.startswith("/activities/500/streams"))
    assert "distance" in stream_call and "watts" in stream_call and "temp" in stream_call
    assert resumed_transport.calls_by_path[stream_call] == 1


def test_read_model_materialization_checkpoint_stage_participates_in_routing() -> None:
    from mcp_strava.refresh.checkpoints import NEXT_STAGE_BACKFILL, NEXT_STAGE_DAILY, Stage, is_active_backfill_stage

    assert Stage.READ_MODEL_MATERIALIZE.value == "read_model_materialize"
    assert NEXT_STAGE_DAILY[Stage.SCHEMA_VALIDATE] == Stage.READ_MODEL_MATERIALIZE
    assert NEXT_STAGE_DAILY[Stage.READ_MODEL_MATERIALIZE] == Stage.KUDOS
    assert NEXT_STAGE_BACKFILL[Stage.DETAILS_BACKFILL] == Stage.READ_MODEL_MATERIALIZE_BACKFILL
    assert NEXT_STAGE_BACKFILL[Stage.READ_MODEL_MATERIALIZE_BACKFILL] == Stage.COMPLETE_BACKFILL
    assert not is_active_backfill_stage(Stage.READ_MODEL_MATERIALIZE)
    assert is_active_backfill_stage(Stage.READ_MODEL_MATERIALIZE_BACKFILL)


def test_run_once_materializes_after_schema_validation_before_kudos(monkeypatch, tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_once
    from mcp_strava.refresh import _sync_ops

    clock = FakeClock()
    order: list[str] = []

    monkeypatch.setattr(_sync_ops, "sync_summaries", lambda *_args, **_kwargs: order.append("summaries") or (0, 0))
    monkeypatch.setattr(_sync_ops, "sync_streams", lambda *_args, **_kwargs: order.append("streams") or 0)
    monkeypatch.setattr(_sync_ops, "sync_details", lambda *_args, **_kwargs: order.append("details") or 0)
    monkeypatch.setattr(_sync_ops, "schema_validate", lambda *_args, **_kwargs: order.append("schema_validate"))
    monkeypatch.setattr(_sync_ops, "_sync_kudos", lambda *_args, **_kwargs: order.append("kudos") or 0)

    def fake_materialize(repo, metric_version, now_iso, renew_lease):
        del repo
        assert metric_version == 1
        assert now_iso == clock.iso()
        assert callable(renew_lease)
        order.append("read_model_materialize")
        return {"status": "ok", "activities_materialized": 0}

    monkeypatch.setattr(_sync_ops, "materialize_read_model_stage", fake_materialize, raising=False)

    with _repo(tmp_path) as repo:
        result = run_once(repo, FakeStravaTransport(), RefreshPolicy(), clock, FakeSleeper(clock), force=True)

    assert result.status == "ok"
    assert order == ["summaries", "streams", "details", "schema_validate", "read_model_materialize", "kudos"]


def test_run_once_resumes_from_read_model_materialization_checkpoint(monkeypatch, tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_once
    from mcp_strava.refresh import _sync_ops

    clock = FakeClock()
    order: list[str] = []

    monkeypatch.setattr(_sync_ops, "sync_summaries", lambda *_args, **_kwargs: order.append("summaries") or (0, 0))
    monkeypatch.setattr(_sync_ops, "sync_streams", lambda *_args, **_kwargs: order.append("streams") or 0)
    monkeypatch.setattr(_sync_ops, "sync_details", lambda *_args, **_kwargs: order.append("details") or 0)
    monkeypatch.setattr(_sync_ops, "schema_validate", lambda *_args, **_kwargs: order.append("schema_validate"))
    monkeypatch.setattr(_sync_ops, "_sync_kudos", lambda *_args, **_kwargs: order.append("kudos") or 0)
    monkeypatch.setattr(
        _sync_ops,
        "materialize_read_model_stage",
        lambda *_args, **_kwargs: order.append("read_model_materialize") or {"status": "ok"},
        raising=False,
    )

    with _repo(tmp_path) as repo:
        repo.set_checkpoint(Stage.READ_MODEL_MATERIALIZE.value, None)
        result = run_once(repo, FakeStravaTransport(), RefreshPolicy(), clock, FakeSleeper(clock), force=True)

    assert result.status == "ok"
    assert order == ["read_model_materialize", "kudos"]


def test_materialization_lost_lease_fails_closed(monkeypatch, tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_once
    from mcp_strava.refresh import _sync_ops

    monkeypatch.setattr(_sync_ops, "sync_summaries", lambda *_args, **_kwargs: (0, 0))
    monkeypatch.setattr(_sync_ops, "sync_streams", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(_sync_ops, "sync_details", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(_sync_ops, "schema_validate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(_sync_ops, "_sync_kudos", lambda *_args, **_kwargs: 0)

    def fake_materialize(repo, metric_version, now_iso, renew_lease):
        del repo, metric_version, now_iso
        renew_lease()

    monkeypatch.setattr(_sync_ops, "materialize_read_model_stage", fake_materialize, raising=False)

    with _repo(tmp_path) as repo:
        repo.renew_refresh_lease = lambda *_args, **_kwargs: False  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="refresh lease lost during read-model materialization"):
            run_once(repo, FakeStravaTransport(), RefreshPolicy(), FakeClock(), FakeSleeper(), force=True)


def test_run_backfill_skips_summaries_and_kudos_per_D16(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_catchup

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
        result = run_catchup(repo, transport, RefreshPolicy(), clock, FakeSleeper(clock), since="2026-05-20")
        state = repo.get_refresh_state()

    assert result.status == "ok"
    assert state.checkpoint_stage == Stage.COMPLETE_BACKFILL.value
    assert not any(path.startswith("/athlete/activities") for path in transport.calls_by_path)
    assert not any("kudos" in path for path in transport.calls_by_path)
    assert "refresh-backfill"


def test_run_backfill_materializes_after_source_changing_work(monkeypatch, tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_catchup
    from mcp_strava.refresh import _sync_ops

    order: list[str] = []
    monkeypatch.setattr(_sync_ops, "sync_streams", lambda *_args, **_kwargs: order.append("streams_backfill") or 1)
    monkeypatch.setattr(_sync_ops, "sync_details", lambda *_args, **_kwargs: order.append("details_backfill") or 1)
    monkeypatch.setattr(
        _sync_ops,
        "materialize_read_model_stage",
        lambda *_args, **_kwargs: order.append("read_model_materialize") or {"status": "ok"},
        raising=False,
    )

    with _repo(tmp_path) as repo:
        result = run_catchup(repo, FakeStravaTransport(), RefreshPolicy(), FakeClock(), FakeSleeper(), since="2026-05-20")

    assert result.status == "ok"
    assert order == ["streams_backfill", "details_backfill", "read_model_materialize"]


def test_run_backfill_failure_preserves_backfill_checkpoint_per_D16(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_catchup

    clock = FakeClock()
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
        result = run_catchup(
            repo,
            FakeStravaTransport({"/streams": StravaUnavailable("rate_limited")}),
            RefreshPolicy(),
            clock,
            FakeSleeper(clock),
            since="2026-05-20",
        )
        state = repo.get_refresh_state()

    assert result.status == "failed"
    assert state.checkpoint_stage == Stage.STREAMS_BACKFILL.value


def test_stream_channel_backfill_materializes_after_source_changing_work(monkeypatch, tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_stream_channel_catchup
    from mcp_strava.refresh import _sync_ops

    order: list[str] = []
    monkeypatch.setattr(
        _sync_ops,
        "estimate_stream_channel_backfill",
        lambda *_args, **_kwargs: {
            "activities_considered": 1,
            "activities_to_backfill": 1,
            "missing_channels": {"watts": 1},
            "metadata_missing": 1,
            "estimated_api_calls": 1,
            "candidates": [{"activity_id": 500, "missing_channels": ["watts"], "metadata_missing": True}],
        },
    )
    monkeypatch.setattr(
        _sync_ops,
        "sync_stream_channels_backfill",
        lambda *_args, **_kwargs: order.append("stream_channels_backfill")
        or {
            "activities_considered": 1,
            "activities_to_backfill": 1,
            "missing_channels": {"watts": 1},
            "metadata_missing": 1,
            "estimated_api_calls": 1,
            "completed": 1,
        },
    )
    monkeypatch.setattr(
        _sync_ops,
        "materialize_read_model_stage",
        lambda *_args, **_kwargs: order.append("read_model_materialize") or {"status": "ok"},
        raising=False,
    )

    with _repo(tmp_path) as repo:
        result = run_stream_channel_catchup(
            repo,
            FakeStravaTransport(),
            RefreshPolicy(),
            FakeClock(),
            FakeSleeper(),
        )

    assert result["status"] == "ok"
    assert order == ["stream_channels_backfill", "read_model_materialize"]


def test_run_once_after_complete_backfill_starts_daily_refresh_per_D16(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_catchup, run_once

    clock = FakeClock()
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
        assert run_catchup(repo, FakeStravaTransport(), RefreshPolicy(), clock, FakeSleeper(clock)).status == "ok"
        daily_transport = FakeStravaTransport()
        result = run_once(repo, daily_transport, RefreshPolicy(), clock, FakeSleeper(clock))

    assert result.status == "ok"
    assert daily_transport.calls_by_path["/athlete/activities?per_page=100&page=1"] == 1


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


def test_worker_materializes_read_model_in_bounded_batch(monkeypatch):
    from mcp_strava.refresh import worker

    calls = []
    events = []

    class FakeDbConn:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def read_model_status(self, metric_version=None):
            del metric_version
            return {"dirty_count": 12}

    def fake_repository_from_connection(conn):
        calls.append(("repo_factory", conn))
        return FakeRepo()

    def fake_materialize_stage(repo, metric_version, now_iso, renew_lease, limit=None):
        del repo, metric_version, now_iso, renew_lease
        calls.append(("materialize_stage", limit))
        return {"dirty_rows_cleared": limit}

    monkeypatch.setattr(worker, "DbConn", FakeDbConn)
    monkeypatch.setattr(worker, "repository_from_connection", fake_repository_from_connection)
    monkeypatch.setattr(worker._sync_ops, "materialize_read_model_stage", fake_materialize_stage)
    monkeypatch.setattr(worker, "_emit", lambda event, **fields: events.append((event, fields)))

    assert worker._materialize_dirty_read_model(batch_size=5) == 5
    assert [call[0] for call in calls] == ["repo_factory", "materialize_stage"]
    assert calls[-1] == ("materialize_stage", 5)
    assert events == [
        ("read_model_materialize_started", {"dirty_count": 12, "batch_size": 5}),
        ("read_model_materialize_ok", {"dirty_rows_cleared": 5, "dirty_count_remaining": 7}),
    ]


def test_worker_materialization_uses_repository_factory_and_runtime_stage(monkeypatch):
    from mcp_strava.refresh import worker

    calls: list[tuple[str, object]] = []

    class FakeDbConn:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def read_model_status(self, metric_version=None):
            del metric_version
            return {"dirty_count": 8}

    def fake_repository_from_connection(conn):
        calls.append(("repo_factory", conn))
        return FakeRepo()

    def fake_materialize_stage(repo, metric_version, now_iso, renew_lease, limit=None):
        del repo, metric_version, now_iso, renew_lease
        calls.append(("materialize_stage", 3))
        return {"dirty_rows_cleared": 3}

    monkeypatch.setattr(worker, "DbConn", FakeDbConn)
    monkeypatch.setattr(worker, "repository_from_connection", fake_repository_from_connection)
    monkeypatch.setattr(worker._sync_ops, "materialize_read_model_stage", fake_materialize_stage)
    monkeypatch.setattr(worker, "_emit", lambda *_args, **_kwargs: None)

    assert worker._materialize_dirty_read_model(batch_size=3) == 3
    assert [name for name, _value in calls] == ["repo_factory", "materialize_stage"]


def test_worker_logs_exception_message_and_traceback(monkeypatch, capsys):
    from mcp_strava.refresh import worker

    events = []

    class StopAfterFirstWait:
        def is_set(self) -> bool:
            return False

        def wait(self, timeout: int) -> bool:
            assert timeout == 5
            return True

    def fake_run_pending_once(*, emit_idle: bool = True) -> int:
        assert emit_idle is False
        raise RuntimeError("duckdb fatal detail")

    monkeypatch.setattr(worker, "run_pending_once", fake_run_pending_once)
    monkeypatch.setattr(worker, "_emit", lambda event, **fields: events.append((event, fields)))

    worker.run_forever(poll_seconds=5, stop_event=StopAfterFirstWait(), emit_start=False)

    captured = capsys.readouterr()
    assert events == [
        ("refresh_worker_error", {"error_type": "RuntimeError", "error": "duckdb fatal detail"}),
    ]
    assert "Traceback" in captured.err
    assert "RuntimeError: duckdb fatal detail" in captured.err


def test_worker_runs_periodic_refresh_without_pending_requests(monkeypatch, tmp_path):
    from mcp_strava.refresh import Stage
    from mcp_strava.refresh import worker

    calls = []
    backfill_calls = []
    settings = SimpleNamespace(
        database_path=tmp_path / "refresh.db",
        freshness=SimpleNamespace(warn_age_hours=12, max_age_hours=24),
        refresh=SimpleNamespace(interval_seconds=3600, stream_backfill_batch_size=50, read_model_batch_size=25),
    )
    state = SimpleNamespace(
        lease_owner=None,
        lease_expires_at=None,
        backoff_until=None,
        checkpoint_stage=Stage.COMPLETE.value,
        last_success_at="2026-05-20T12:00:00",
    )

    class FakeDbConn:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def read_model_status(self, metric_version=None):
            del metric_version
            return {"dirty_count": 0}

        def get_refresh_state(self):
            return state

        def pending_refresh_requests(self):
            return []

        def mark_refresh_requests_consumed(self, consumed_at):
            return 0

    def fake_run_once(repo, transport, refresh_policy, clock, sleeper, *, owner, force, mode):
        calls.append((owner, force, mode))
        return SimpleNamespace(
            status="ok",
            checkpoint_stage=Stage.COMPLETE.value,
            activities_seen=3,
            activities_new=1,
            streams_fetched=0,
            details_fetched=0,
            kudos_fetched=0,
        )

    def fake_stream_backfill(repo, transport, refresh_policy, clock, sleeper):
        backfill_calls.append(refresh_policy.stream_backfill_batch_size)
        return {
            "status": "ok",
            "checkpoint_stage": Stage.COMPLETE.value,
            "activities_to_backfill": 0,
            "completed": 0,
        }

    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "_now_iso", lambda: "2026-05-21T12:00:00")
    monkeypatch.setattr(worker, "ensure_runtime_refresh_schema", lambda _settings: None)
    monkeypatch.setattr(worker, "DbConn", FakeDbConn)
    monkeypatch.setattr(worker, "repository_from_connection", lambda _conn: FakeRepo())
    monkeypatch.setattr(
        worker,
        "build_refresh_collaborators",
        lambda _settings: (_settings, object(), object(), object(), worker.RefreshPolicy.from_settings(settings)),
    )
    monkeypatch.setattr(worker.refresh_runtime, "run_once", fake_run_once)
    monkeypatch.setattr(worker, "_run_stream_channel_backfill", fake_stream_backfill)

    assert worker.run_pending_once(emit_idle=False) == 0
    assert calls == [("refresh-worker", False, "periodic")]
    assert backfill_calls == [50]


def test_worker_resumes_stream_channel_backfill_without_regular_refresh(monkeypatch, tmp_path):
    from mcp_strava.refresh import Stage
    from mcp_strava.refresh import worker

    backfill_calls = []
    settings = SimpleNamespace(
        database_path=tmp_path / "refresh.db",
        freshness=SimpleNamespace(warn_age_hours=12, max_age_hours=24),
        refresh=SimpleNamespace(interval_seconds=3600, stream_backfill_batch_size=25, read_model_batch_size=25),
    )
    state = SimpleNamespace(
        lease_owner=None,
        lease_expires_at=None,
        backoff_until=None,
        checkpoint_stage=Stage.STREAM_CHANNELS_BACKFILL.value,
        last_success_at="2026-05-21T11:30:00",
    )

    class FakeDbConn:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def read_model_status(self, metric_version=None):
            del metric_version
            return {"dirty_count": 0}

        def get_refresh_state(self):
            return state

        def pending_refresh_requests(self):
            return []

    def fake_stream_backfill(repo, transport, refresh_policy, clock, sleeper):
        backfill_calls.append(refresh_policy.stream_backfill_batch_size)
        return {
            "status": "ok",
            "checkpoint_stage": Stage.COMPLETE_STREAM_CHANNELS_BACKFILL.value,
            "activities_to_backfill": 25,
            "completed": 25,
        }

    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "_now_iso", lambda: "2026-05-21T12:00:00")
    monkeypatch.setattr(worker, "ensure_runtime_refresh_schema", lambda _settings: None)
    monkeypatch.setattr(worker, "DbConn", FakeDbConn)
    monkeypatch.setattr(worker, "repository_from_connection", lambda _conn: FakeRepo())
    monkeypatch.setattr(
        worker,
        "build_refresh_collaborators",
        lambda _settings: (_settings, object(), object(), object(), worker.RefreshPolicy.from_settings(settings)),
    )
    monkeypatch.setattr(worker.refresh_runtime, "run_once", lambda *_args, **_kwargs: pytest.fail("regular refresh must not run"))
    monkeypatch.setattr(worker, "_run_stream_channel_backfill", fake_stream_backfill)

    assert worker.run_pending_once(emit_idle=False) == 0
    assert backfill_calls == [25]


def test_worker_skips_periodic_refresh_before_interval(monkeypatch, tmp_path):
    from mcp_strava.refresh import Stage
    from mcp_strava.refresh import worker

    settings = SimpleNamespace(
        database_path=tmp_path / "refresh.db",
        freshness=SimpleNamespace(warn_age_hours=12, max_age_hours=24),
        refresh=SimpleNamespace(interval_seconds=3600, stream_backfill_batch_size=50, read_model_batch_size=25),
    )
    state = SimpleNamespace(
        lease_owner=None,
        lease_expires_at=None,
        backoff_until=None,
        checkpoint_stage=Stage.COMPLETE.value,
        last_success_at="2026-05-21T11:30:00",
    )

    class FakeDbConn:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def read_model_status(self, metric_version=None):
            del metric_version
            return {"dirty_count": 0}

        def get_refresh_state(self):
            return state

        def pending_refresh_requests(self):
            return []

    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "_now_iso", lambda: "2026-05-21T12:00:00")
    monkeypatch.setattr(worker, "ensure_runtime_refresh_schema", lambda _settings: None)
    monkeypatch.setattr(worker, "DbConn", FakeDbConn)
    monkeypatch.setattr(worker, "repository_from_connection", lambda _conn: FakeRepo())
    monkeypatch.setattr(
        worker,
        "build_refresh_collaborators",
        lambda _settings: pytest.fail("refresh collaborators should not be built before interval elapses"),
    )

    assert worker.run_pending_once(emit_idle=False) == 0


def test_emit_mirror_storage_reports_free_block_delta(tmp_path, monkeypatch):
    from mcp_strava.refresh import worker
    from tests._fixtures_duckdb import create_fixture_db

    db = tmp_path / "mirror.duckdb"
    create_fixture_db(db)
    events: list[tuple[str, dict]] = []

    class FakeDbConn:
        def __enter__(self):
            self._conn = duckdb.connect(str(db), read_only=True)
            return self._conn

        def __exit__(self, *_a):
            self._conn.close()
            return False

    monkeypatch.setattr(worker, "DbConn", FakeDbConn)
    monkeypatch.setattr(worker, "_emit", lambda event, **fields: events.append((event, fields)))
    monkeypatch.setattr(worker, "_prev_free_blocks", None)

    worker._emit_mirror_storage()
    worker._emit_mirror_storage()

    assert [name for name, _ in events] == ["mirror_storage", "mirror_storage"]
    # First reading has no prior; second compares against it (no change between reads).
    assert events[0][1]["free_blocks_delta"] is None
    assert events[1][1]["free_blocks_delta"] == 0
    assert "reclaimable_pct" in events[0][1] and "message" in events[0][1]


def test_sync_streams_requests_all_configured_channels_and_writes_projection_metadata(tmp_path):
    from mcp_strava.refresh._sync_ops import sync_streams

    class RichStreamsTransport(FakeStravaTransport):
        def fetch(self, path: str) -> StravaResponse:
            self.calls_by_path[path] += 1
            if path.startswith("/activities/500/streams"):
                return StravaResponse(
                    data={
                        "time": {"data": [0, 1], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "distance": {"data": [0.0, 11.2], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "heartrate": {"data": [140, 141], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "velocity_smooth": {"data": [3.0, 3.1], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "altitude": {"data": [501.0, 502.0], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "cadence": {"data": [84, 85], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "latlng": {"data": [[43.21, 76.91], [43.22, 76.92]], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "grade_smooth": {"data": [1.1, 1.2], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "grade_adjusted_speed": {"data": [3.05, 3.15], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "grade_adjusted_distance": {"data": [0.0, 10.9], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "moving": {"data": [1, 1], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "watts": {"data": [220, 230], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "temp": {"data": [20, 21], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "unknown_future_key": {"data": ["a", "b"], "original_size": 2, "resolution": "high", "series_type": "distance"},
                    },
                    rate_info=StravaRateInfo(),
                    status=200,
                )
            return super().fetch(path)

    transport = RichStreamsTransport()
    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            activity_id=500,
            date="2026-05-21T06:00:00Z",
            name="Morning Run",
            sport_type="Run",
            distance=1000,
            moving_time=600,
            elapsed_time=620,
            total_elevation_gain=10,
            summary_json="{}",
            synced_at="2026-05-21T07:00:00Z",
        )
        fetched = sync_streams(repo, transport, since="2026-05-20")
        stream_rows = repo.activity_stream_rows(500)
        channel_rows = repo._fetchall(
            "SELECT channel_key, original_size, resolution, series_type, status, error FROM stream_channels WHERE activity_id = 500 ORDER BY channel_key"
        )

    assert fetched == 1
    stream_call = next(path for path in transport.calls_by_path if path.startswith("/activities/500/streams"))
    assert "watts" in stream_call and "temp" in stream_call
    assert len(stream_rows) == 2
    first = stream_rows[0]
    assert first["heartrate"] == 140
    assert first["velocity"] == pytest.approx(3.0)
    assert first["altitude"] == pytest.approx(501.0)
    assert first["cadence"] == 84
    assert first["grade"] == pytest.approx(1.1)
    assert first["gap_speed"] == pytest.approx(3.05)
    assert first["gap_distance"] == pytest.approx(0.0)
    assert first["is_moving"] == 1
    assert first["lat"] == pytest.approx(43.21)
    assert first["lng"] == pytest.approx(76.91)
    values = json.loads(first["values_json"])
    assert values["distance"] == pytest.approx(0.0)
    assert values["watts"] == 220
    assert values["temp"] == 20
    assert values["unknown_future_key"] == "a"
    assert "latlng" not in values

    assert channel_rows
    for row in channel_rows:
        assert row["original_size"] == 2
        assert row["resolution"] == "high"
        assert row["series_type"] == "distance"
        assert row["status"] == "available"
        assert row["error"] is None


def test_sync_streams_records_missing_requested_channels_without_failure(tmp_path):
    from mcp_strava.refresh._sync_ops import sync_streams

    class PartialStreamsTransport(FakeStravaTransport):
        def fetch(self, path: str) -> StravaResponse:
            self.calls_by_path[path] += 1
            if path.startswith("/activities/500/streams"):
                return StravaResponse(
                    data={
                        "time": {"data": [0], "original_size": 1, "resolution": "high", "series_type": "distance"},
                        "heartrate": {"data": [142], "original_size": 1, "resolution": "high", "series_type": "distance"},
                    },
                    rate_info=StravaRateInfo(),
                    status=200,
                )
            return super().fetch(path)

    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            activity_id=500,
            date="2026-05-21T06:00:00Z",
            name="Missing Channels",
            sport_type="Run",
            distance=1000,
            moving_time=600,
            elapsed_time=620,
            total_elevation_gain=10,
            summary_json="{}",
            synced_at="2026-05-21T07:00:00Z",
        )
        fetched = sync_streams(repo, PartialStreamsTransport(), since="2026-05-20")
        missing = repo.conn.execute(
            "SELECT COUNT(*) FROM stream_channels WHERE activity_id = 500 AND status = 'unavailable'"
        ).fetchone()[0]

    assert fetched == 1
    assert missing > 0


def test_unavailable_stream_channels_do_not_create_repeat_backfill_work(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_stream_channel_catchup
    from mcp_strava.refresh._sync_ops import sync_streams

    class PartialStreamsTransport(FakeStravaTransport):
        def fetch(self, path: str) -> StravaResponse:
            self.calls_by_path[path] += 1
            if path.startswith("/activities/500/streams"):
                return StravaResponse(
                    data={
                        "time": {"data": [0], "original_size": 1, "resolution": "high", "series_type": "distance"},
                        "heartrate": {"data": [142], "original_size": 1, "resolution": "high", "series_type": "distance"},
                    },
                    rate_info=StravaRateInfo(),
                    status=200,
                )
            return super().fetch(path)

    with _repo(tmp_path) as repo:
        repo._execute("DELETE FROM streams")
        repo._execute("DELETE FROM stream_channels")
        repo._execute("DELETE FROM activities")
        repo.upsert_activity_summary(
            activity_id=500,
            date="2026-05-21T06:00:00Z",
            name="Unavailable Channels",
            sport_type="Run",
            distance=1000,
            moving_time=600,
            elapsed_time=620,
            total_elevation_gain=10,
            summary_json="{}",
            synced_at="2026-05-21T07:00:00Z",
        )
        assert sync_streams(repo, PartialStreamsTransport(), since="2026-05-20") == 1
        result = run_stream_channel_catchup(
            repo,
            FakeStravaTransport(),
            RefreshPolicy(),
            FakeClock(),
            FakeSleeper(),
            dry_run=True,
        )

    assert result["activities_to_backfill"] == 0
    assert result["estimated_api_calls"] == 0


def test_stream_channel_backfill_dry_run_reports_remaining_work_without_transport_calls(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_stream_channel_catchup

    transport = FakeStravaTransport()
    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            activity_id=500,
            date="2026-05-21T06:00:00Z",
            name="Channel Gap Run",
            sport_type="Run",
            distance=1000,
            moving_time=600,
            elapsed_time=620,
            total_elevation_gain=10,
            summary_json="{}",
            synced_at="2026-05-21T07:00:00Z",
        )
        repo.insert_stream_rows_chunked(
            500,
            [
                {
                    "time_offset": 0,
                    "heartrate": 140,
                    "velocity": 3.0,
                    "altitude": 501.0,
                    "cadence": 84,
                    "lat": 43.21,
                    "lng": 76.91,
                    "grade": 1.1,
                    "gap_speed": 3.05,
                    "gap_distance": 0.0,
                    "is_moving": 1,
                    "values_json": json.dumps({"distance": 0.0}),
                }
            ],
        )
        result = run_stream_channel_catchup(
            repo,
            transport,
            RefreshPolicy(),
            FakeClock(),
            FakeSleeper(),
            dry_run=True,
        )

    assert result["status"] == "ok"
    assert result["mode"] == "backfill_stream_channels"
    assert result["activities_considered"] >= 1
    assert result["activities_to_backfill"] >= 1
    assert "missing_channels" in result
    assert "metadata_missing" in result
    assert result["estimated_api_calls"] == result["activities_to_backfill"]
    assert "checkpoint_stage" in result
    assert transport.calls_by_path == {}


def test_run_once_rejects_active_stream_channel_backfill_checkpoint(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_once

    with _repo(tmp_path) as repo:
        repo.set_checkpoint(Stage.STREAM_CHANNELS_BACKFILL.value, "500")
        with pytest.raises(RuntimeError, match="admin catchup"):
            run_once(repo, FakeStravaTransport(), RefreshPolicy(), FakeClock(), FakeSleeper())


def test_run_catchup_rejects_stream_channel_backfill_checkpoint(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_catchup

    with _repo(tmp_path) as repo:
        repo.set_checkpoint(Stage.STREAM_CHANNELS_BACKFILL.value, "500")
        with pytest.raises(RuntimeError, match="admin catchup"):
            run_catchup(repo, FakeStravaTransport(), RefreshPolicy(), FakeClock(), FakeSleeper())


def test_stream_channel_backfill_uses_only_streams_endpoint(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_stream_channel_catchup

    class StreamsOnlyTransport(FakeStravaTransport):
        def fetch(self, path: str) -> StravaResponse:
            self.calls_by_path[path] += 1
            if path.startswith("/athlete/activities"):
                raise AssertionError("must not call summaries endpoint")
            if path.startswith("/activities/500/kudos"):
                raise AssertionError("must not call kudos endpoint")
            if path.startswith("/activities/500/streams"):
                return StravaResponse(
                    data={
                        "time": {"data": [0]},
                        "distance": {"data": [0.0]},
                        "watts": {"data": [220]},
                    },
                    rate_info=StravaRateInfo(),
                    status=200,
                )
            if path.startswith("/activities/500"):
                raise AssertionError("must not call details endpoint")
            return StravaResponse(data=[], rate_info=StravaRateInfo(), status=200)

    transport = StreamsOnlyTransport()
    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            activity_id=500,
            date="2026-05-21T06:00:00Z",
            name="Streams Only",
            sport_type="Run",
            distance=1000,
            moving_time=600,
            elapsed_time=620,
            total_elevation_gain=10,
            summary_json="{}",
            synced_at="2026-05-21T07:00:00Z",
        )
        repo.insert_stream_rows_chunked(
            500,
            [
                {
                    "time_offset": 0,
                    "heartrate": 140,
                    "velocity": 3.0,
                    "altitude": 501.0,
                    "cadence": 84,
                    "lat": 43.21,
                    "lng": 76.91,
                    "grade": 1.1,
                    "gap_speed": 3.05,
                    "gap_distance": 0.0,
                    "is_moving": 1,
                    "values_json": json.dumps({"distance": 0.0}),
                }
            ],
        )
        result = run_stream_channel_catchup(repo, transport, RefreshPolicy(), FakeClock(), FakeSleeper())

    assert result["status"] in {"ok", "delayed"}
    assert any(path.startswith("/activities/500/streams") for path in transport.calls_by_path)
    assert not any(path.startswith("/athlete/activities") for path in transport.calls_by_path)
    assert not any(path.endswith("/kudos?per_page=100") for path in transport.calls_by_path)


def test_stream_channel_backfill_renews_long_lease_during_progress(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_stream_channel_catchup

    clock = FakeClock()

    class WaitingStreamsTransport(FakeStravaTransport):
        def fetch(self, path: str) -> StravaResponse:
            self.calls_by_path[path] += 1
            clock.advance(901)
            return StravaResponse(
                data={
                    "time": {"data": [0]},
                    "distance": {"data": [0.0]},
                    "watts": {"data": [220]},
                },
                rate_info=StravaRateInfo(),
                status=200,
            )

    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            activity_id=500,
            date="2026-05-21T06:00:00Z",
            name="Lease Renewal",
            sport_type="Run",
            distance=1000,
            moving_time=600,
            elapsed_time=620,
            total_elevation_gain=10,
            summary_json="{}",
            synced_at="2026-05-21T07:00:00Z",
        )
        repo.insert_stream_rows_chunked(
            500,
            [
                {
                    "time_offset": 0,
                    "heartrate": 140,
                    "velocity": 3.0,
                    "altitude": 501.0,
                    "cadence": 84,
                    "lat": 43.21,
                    "lng": 76.91,
                    "grade": 1.1,
                    "gap_speed": 3.05,
                    "gap_distance": 0.0,
                    "is_moving": 1,
                    "values_json": json.dumps({"distance": 0.0}),
                }
            ],
        )
        renewals: list[str] = []
        original_renew = repo.renew_refresh_lease

        def record_renewal(owner: str, expires_at: str) -> bool:
            renewals.append(expires_at)
            return original_renew(owner, expires_at)

        repo.renew_refresh_lease = record_renewal  # type: ignore[method-assign]
        result = run_stream_channel_catchup(
            repo,
            WaitingStreamsTransport(),
            RefreshPolicy(lease_duration_seconds=10),
            clock,
            FakeSleeper(clock),
        )

    assert result["status"] == "ok"
    assert len(renewals) >= 2
    first = datetime.fromisoformat(renewals[0])
    last = datetime.fromisoformat(renewals[-1])
    assert (first - datetime.fromtimestamp(1_716_206_400.0, tz=timezone.utc).replace(tzinfo=None)).total_seconds() == 1800
    assert (last - first).total_seconds() >= 901


def test_stream_channel_backfill_rate_limit_keeps_checkpoint_and_rows(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_stream_channel_catchup

    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            activity_id=500,
            date="2026-05-21T06:00:00Z",
            name="Rate Limited Backfill",
            sport_type="Run",
            distance=1000,
            moving_time=600,
            elapsed_time=620,
            total_elevation_gain=10,
            summary_json="{}",
            synced_at="2026-05-21T07:00:00Z",
        )
        repo.insert_stream_rows_chunked(
            500,
            [
                {
                    "time_offset": 0,
                    "heartrate": 140,
                    "velocity": 3.0,
                    "altitude": 501.0,
                    "cadence": 84,
                    "lat": 43.21,
                    "lng": 76.91,
                    "grade": 1.1,
                    "gap_speed": 3.05,
                    "gap_distance": 0.0,
                    "is_moving": 1,
                    "values_json": json.dumps({"distance": 0.0}),
                }
            ],
        )
        result = run_stream_channel_catchup(
            repo,
            FakeStravaTransport({"/streams": StravaUnavailable("rate_limited")}),
            RefreshPolicy(),
            FakeClock(),
            FakeSleeper(),
        )
        state = repo.get_refresh_state()
        rows = repo.activity_stream_rows(500)

    assert result["status"] in {"failed", "delayed"}
    assert state.checkpoint_stage == Stage.STREAM_CHANNELS_BACKFILL.value
    assert len(rows) == 1
