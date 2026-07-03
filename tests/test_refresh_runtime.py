import json
import urllib.request
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from mcp_strava.adapters.duckdb.activity_lookup_queries import activity_by_id
from mcp_strava.adapters.duckdb.refresh_state_store import RefreshStateStore
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.duckdb.repository_models import ActivitySourcePayload, ActivitySummaryRecord
from mcp_strava.adapters.duckdb.stream_read_queries import activity_stream_rows
from mcp_strava.adapters.duckdb.sync_log_store import read_sync_log
from mcp_strava.adapters.strava import StravaResponse, StravaUnavailableError
from mcp_strava.adapters.strava.types import StravaRateInfo
from mcp_strava.refresh import RefreshPolicy, _sync_ops, read_model_stage, run_catchup
from mcp_strava.refresh.runtime import RefreshCollaborators
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
        return datetime.fromtimestamp(self.value, tz=UTC).replace(tzinfo=None).isoformat()


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
            return StravaResponse(
                data={"id": 500, "name": "Morning Run", "resource_state": 3}, rate_info=StravaRateInfo(), status=200
            )
        return StravaResponse(data=[], rate_info=StravaRateInfo(), status=200)


def _repo(tmp_path: Path) -> DuckDBRepository:
    path = tmp_path / "refresh.duckdb"
    create_fixture_db(path)
    return DuckDBRepository.from_path(path)


def _refresh_store(repo: DuckDBRepository) -> RefreshStateStore:
    return RefreshStateStore.from_connection(repo.conn)


def test_sync_summaries_skips_rewrite_when_summary_unchanged(tmp_path):
    """Re-syncing an unchanged activity must NOT rewrite the activities row.

    Each rewrite of a PRIMARY-KEY-indexed row churns the DuckDB ART index, which
    (a) bloats the file unbounded — freed index blocks are never reused — and
    (b) re-triggers the upstream ART stale-update-read corruption. The daily
    refresh sees the same ~600 activities every cycle with no content change, so
    unchanged rows must be left untouched. synced_at staying at its first value
    across an unchanged re-sync is the observable proof that no write happened.
    """
    from mcp_strava.refresh.read_model_stage import schema_validate
    from mcp_strava.refresh.source_ingest import sync_summaries

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
        first_before_processing = activity_by_id(repo, 500)
        schema_validate(repo)
        first = activity_by_id(repo, 500)
        repo.clear_dirty_activity_rows(repo.dirty_activity_rows())

        # Same content, later sync timestamp -> must be a no-op (no row rewrite).
        seen2, new2 = sync_summaries(repo, transport, "2026-05-29T01:00:00")
        unchanged = activity_by_id(repo, 500)
        repo.clear_dirty_activity_rows(repo.dirty_activity_rows())

        # Genuinely changed content is captured in bronze, but direct silver
        # rewrite is deferred to the processing stage.
        transport.payload = {**activity, "name": "Renamed Run"}
        sync_summaries(repo, transport, "2026-05-29T02:00:00")
        dirty_before_processing = repo.dirty_activity_rows()
        schema_validate(repo)
        dirty_after_processing = repo.dirty_activity_rows()
        changed = activity_by_id(repo, 500)
        bronze = repo.latest_activity_payload(500, "summary")

    assert (seen1, new1) == (1, 1)
    assert (seen2, new2) == (1, 0)
    assert first_before_processing is None
    assert first is not None
    assert unchanged is not None
    assert changed is not None
    assert first.synced_at == "2026-05-29T00:00:00"
    assert unchanged.synced_at == "2026-05-29T00:00:00"  # untouched by the no-op re-sync
    assert changed.name == "Renamed Run"
    assert changed.synced_at == "2026-05-29T02:00:00"
    assert bronze is not None
    assert '"Renamed Run"' in str(bronze["payload_json"])
    assert dirty_before_processing == []
    assert len(dirty_after_processing) == 1
    assert dirty_after_processing[0]["reason"] == "bronze_payload_changed"


def test_sync_summaries_captures_raw_payloads_in_bronze_without_forcing_silver_rewrite(tmp_path):
    from mcp_strava.refresh.source_ingest import sync_summaries

    activity = {
        "id": 501,
        "name": "Morning Run",
        "sport_type": "Run",
        "start_date_local": "2026-05-21T06:00:00Z",
        "distance": 1000,
        "moving_time": 600,
        "elapsed_time": 620,
        "total_elevation_gain": 10,
    }

    class _SummaryTransport:
        def fetch(self, path: str) -> StravaResponse:
            if path.startswith("/athlete/activities"):
                return StravaResponse(data=[activity], rate_info=StravaRateInfo(), status=200)
            return StravaResponse(data=[], rate_info=StravaRateInfo(), status=200)

    with _repo(tmp_path) as repo:
        sync_summaries(repo, _SummaryTransport(), "2026-05-29T00:00:00")
        first_before_processing = activity_by_id(repo, 501)
        from mcp_strava.refresh.read_model_stage import schema_validate

        schema_validate(repo)
        first = activity_by_id(repo, 501)
        sync_summaries(repo, _SummaryTransport(), "2026-05-29T01:00:00")
        unchanged = activity_by_id(repo, 501)

        bronze_count = repo._scalar_int(
            """
            SELECT COUNT(*)
            FROM bronze.activity_payloads
            WHERE activity_id = 501 AND payload_kind = 'summary'
            """
        )
        latest = repo.latest_activity_payload(501, "summary")

    assert first_before_processing is None
    assert first is not None
    assert unchanged is not None
    assert first.synced_at == "2026-05-29T00:00:00"
    assert unchanged.synced_at == "2026-05-29T00:00:00"
    assert bronze_count == 1
    assert latest is not None
    assert latest["fetched_at"] == "2026-05-29T00:00:00"


def test_sync_summaries_does_not_write_modeled_activity_rows(tmp_path, monkeypatch):
    from mcp_strava.refresh.read_model_stage import schema_validate
    from mcp_strava.refresh.source_ingest import sync_summaries

    activity = {
        "id": 503,
        "name": "Source Only Run",
        "sport_type": "Run",
        "start_date_local": "2026-05-21T06:00:00Z",
        "distance": 1000,
        "moving_time": 600,
        "elapsed_time": 620,
        "total_elevation_gain": 10,
    }

    class _SummaryTransport:
        def fetch(self, path: str) -> StravaResponse:
            if path.startswith("/athlete/activities"):
                return StravaResponse(data=[activity], rate_info=StravaRateInfo(), status=200)
            return StravaResponse(data=[], rate_info=StravaRateInfo(), status=200)

    with _repo(tmp_path) as repo:

        def explode(*_args, **_kwargs):
            raise AssertionError("source ingest must not write modeled activity rows")

        monkeypatch.setattr(repo, "upsert_activity_summary", explode)
        seen, new = sync_summaries(repo, _SummaryTransport(), "2026-05-29T00:00:00")
        before_processing = activity_by_id(repo, 503)
        schema_validate(repo)
        after_processing = activity_by_id(repo, 503)

    assert (seen, new) == (1, 1)
    assert before_processing is None
    assert after_processing is not None
    assert after_processing.name == "Source Only Run"


def test_sync_details_captures_raw_payloads_in_bronze_without_silver_mutation(tmp_path):
    from mcp_strava.refresh.read_model_stage import schema_validate
    from mcp_strava.refresh.source_ingest import sync_details, sync_summaries

    activity_id = 502
    summary = {
        "id": activity_id,
        "name": "Morning Run",
        "sport_type": "Run",
        "start_date_local": "2026-05-21T06:00:00Z",
        "distance": 1000,
        "moving_time": 600,
        "elapsed_time": 620,
        "total_elevation_gain": 10,
    }
    detail = {"id": activity_id, "name": "Morning Run", "resource_state": 3, "calories": 321}

    class _DetailTransport:
        def fetch(self, path: str) -> StravaResponse:
            if path.startswith("/athlete/activities"):
                return StravaResponse(data=[summary], rate_info=StravaRateInfo(), status=200)
            if path == f"/activities/{activity_id}":
                return StravaResponse(data=detail, rate_info=StravaRateInfo(), status=200)
            return StravaResponse(data=[], rate_info=StravaRateInfo(), status=200)

    with _repo(tmp_path) as repo:
        transport = _DetailTransport()
        sync_summaries(repo, transport, "2026-05-29T00:00:00")
        repo.clear_dirty_activity_rows(repo.dirty_activity_rows())
        schema_validate(repo)
        fetched = sync_details(repo, transport)
        fetched_again = sync_details(repo, transport)
        dirty_before_processing = repo.dirty_activity_rows()
        schema_validate(repo)
        dirty_after_processing = repo.dirty_activity_rows()

        bronze = repo.latest_activity_payload(activity_id, "detail")
        stored = activity_by_id(repo, activity_id)
        silver = repo._fetchone("SELECT detail_json FROM activities WHERE id = ?", [activity_id])

    assert fetched == 1
    assert fetched_again == 0
    assert bronze is not None
    assert bronze["payload_json"] == '{"id": 502, "name": "Morning Run", "resource_state": 3, "calories": 321}'
    assert stored is not None
    assert stored.detail_json == '{"id": 502, "name": "Morning Run", "resource_state": 3, "calories": 321}'
    assert silver is not None
    assert silver["detail_json"] is None
    assert len(dirty_before_processing) == 1
    assert dirty_before_processing[0]["reason"] == "bronze_payload_changed"
    assert len(dirty_after_processing) == 1
    assert dirty_after_processing[0]["reason"] == "bronze_payload_changed"


def test_run_once_completes_daily_refresh_per_REFRESH_01_STRAVA_03(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_once

    clock = FakeClock()
    with _repo(tmp_path) as repo:
        result = run_once(
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport(),
                policy=RefreshPolicy(),
                clock=clock,
                sleeper=FakeSleeper(clock),
            )
        )
        state = _refresh_store(repo).get_refresh_state()
        logs = read_sync_log(repo)

    assert result.status == "ok"
    assert state.checkpoint_stage == Stage.COMPLETE.value
    assert state.last_success_at is not None
    assert logs


def test_run_once_daily_refresh_does_not_call_legacy_modeled_writes(tmp_path, monkeypatch):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_once

    def explode(*_args, **_kwargs):
        raise AssertionError("daily refresh must not call legacy modeled activity writes")

    clock = FakeClock()
    with _repo(tmp_path) as repo:
        monkeypatch.setattr(repo, "upsert_activity_summary", explode)
        monkeypatch.setattr(repo, "update_activity_detail", explode)

        result = run_once(
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport(),
                policy=RefreshPolicy(),
                clock=clock,
                sleeper=FakeSleeper(clock),
            )
        )
        state = _refresh_store(repo).get_refresh_state()

    assert result.status == "ok"
    assert state.checkpoint_stage == Stage.COMPLETE.value


def test_run_once_skips_until_refresh_interval_then_re_runs_per_D06_D15(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, RefreshSkipped, run_once

    clock = FakeClock()
    policy = RefreshPolicy(regular_refresh_interval_seconds=3600)
    transport = FakeStravaTransport()
    with _repo(tmp_path) as repo:
        assert (
            run_once(
                RefreshCollaborators(
                    repo=repo, transport=transport, policy=policy, clock=clock, sleeper=FakeSleeper(clock)
                )
            ).status
            == "ok"
        )
        skipped = run_once(
            RefreshCollaborators(repo=repo, transport=transport, policy=policy, clock=clock, sleeper=FakeSleeper(clock))
        )
        assert isinstance(skipped, RefreshSkipped)
        assert skipped.reason == "already_complete"
        clock.advance(3599)
        skipped = run_once(
            RefreshCollaborators(repo=repo, transport=transport, policy=policy, clock=clock, sleeper=FakeSleeper(clock))
        )
        assert isinstance(skipped, RefreshSkipped)
        assert skipped.reason == "already_complete"
        calls_before_periodic = dict(transport.calls_by_path)
        clock.advance(1)
        periodic = run_once(
            RefreshCollaborators(
                repo=repo, transport=transport, policy=policy, clock=clock, sleeper=FakeSleeper(clock)
            ),
            mode="periodic",
        )
        calls_before_force = dict(transport.calls_by_path)
        forced = run_once(
            RefreshCollaborators(
                repo=repo, transport=transport, policy=policy, clock=clock, sleeper=FakeSleeper(clock)
            ),
            force=True,
            mode="quick",
        )

    def _activities_calls(calls_dict: dict) -> int:
        return sum(v for k, v in calls_dict.items() if k.startswith("/athlete/activities"))

    assert periodic.status == "ok"
    assert _activities_calls(transport.calls_by_path) > _activities_calls(calls_before_periodic)
    assert forced.status == "ok"
    assert _activities_calls(transport.calls_by_path) > _activities_calls(calls_before_force)


def test_run_once_force_still_honors_lease_and_backoff_per_D15(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_once

    clock = FakeClock()
    with _repo(tmp_path) as repo:
        store = _refresh_store(repo)
        assert store.acquire_refresh_lease("other", "2026-05-21T12:10:00", "2026-05-21T12:00:00")
        skipped = run_once(
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport(),
                policy=RefreshPolicy(),
                clock=clock,
                sleeper=FakeSleeper(clock),
            ),
            force=True,
        )
        assert skipped.reason == "refresh_in_progress"
        store.release_refresh_lease("other")
        store.record_refresh_failure("2026-05-21T12:00:00", "rate_limited", "2026-05-21T13:00:00")
        skipped = run_once(
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport(),
                policy=RefreshPolicy(),
                clock=clock,
                sleeper=FakeSleeper(clock),
            ),
            force=True,
        )

    assert skipped.reason == "refresh_delayed"


def test_run_once_failure_persists_backoff_and_resumes_per_D09_D13(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_once

    clock = FakeClock()
    with _repo(tmp_path) as repo:
        result = run_once(
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport({"/streams": StravaUnavailableError("rate_limited")}),
                policy=RefreshPolicy(),
                clock=clock,
                sleeper=FakeSleeper(clock),
            )
        )
        state = _refresh_store(repo).get_refresh_state()
        skipped = run_once(
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport(),
                policy=RefreshPolicy(),
                clock=clock,
                sleeper=FakeSleeper(clock),
            )
        )

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
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport({"/streams": StravaUnavailableError("rate_limited")}),
                policy=policy,
                clock=clock,
                sleeper=FakeSleeper(clock),
            )
        )
        failed_state = _refresh_store(repo).get_refresh_state()
        clock.advance(policy.backoff_seconds_on_rate_limit_default + 1)
        resumed_transport = FakeStravaTransport()
        resumed = run_once(
            RefreshCollaborators(
                repo=repo, transport=resumed_transport, policy=policy, clock=clock, sleeper=FakeSleeper(clock)
            )
        )

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
    from mcp_strava.refresh import RefreshPolicy, _sync_ops, run_once

    clock = FakeClock()
    order: list[str] = []

    from mcp_strava.refresh import source_ingest

    monkeypatch.setattr(source_ingest, "sync_summaries", lambda *_args, **_kwargs: order.append("summaries") or (0, 0))
    monkeypatch.setattr(_sync_ops, "sync_streams", lambda *_args, **_kwargs: order.append("streams") or 0)
    monkeypatch.setattr(source_ingest, "sync_details", lambda *_args, **_kwargs: order.append("details") or 0)
    monkeypatch.setattr(read_model_stage, "schema_validate", lambda *_args, **_kwargs: order.append("schema_validate"))
    monkeypatch.setattr(_sync_ops, "_sync_kudos", lambda *_args, **_kwargs: order.append("kudos") or 0)

    def fake_materialize(repo, now_iso, renew_lease):
        del repo
        assert now_iso == clock.iso()
        assert callable(renew_lease)
        order.append("read_model_materialize")
        return {"status": "ok", "activities_materialized": 0}

    monkeypatch.setattr(read_model_stage, "materialize_read_model_stage", fake_materialize, raising=False)

    with _repo(tmp_path) as repo:
        result = run_once(
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport(),
                policy=RefreshPolicy(),
                clock=clock,
                sleeper=FakeSleeper(clock),
            ),
            force=True,
        )

    assert result.status == "ok"
    assert order == [
        "summaries",
        "schema_validate",
        "streams",
        "details",
        "schema_validate",
        "read_model_materialize",
        "kudos",
    ]


def test_run_once_resumes_from_read_model_materialization_checkpoint(monkeypatch, tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, _sync_ops, run_once

    clock = FakeClock()
    order: list[str] = []

    from mcp_strava.refresh import source_ingest

    monkeypatch.setattr(source_ingest, "sync_summaries", lambda *_args, **_kwargs: order.append("summaries") or (0, 0))
    monkeypatch.setattr(_sync_ops, "sync_streams", lambda *_args, **_kwargs: order.append("streams") or 0)
    monkeypatch.setattr(source_ingest, "sync_details", lambda *_args, **_kwargs: order.append("details") or 0)
    monkeypatch.setattr(read_model_stage, "schema_validate", lambda *_args, **_kwargs: order.append("schema_validate"))
    monkeypatch.setattr(_sync_ops, "_sync_kudos", lambda *_args, **_kwargs: order.append("kudos") or 0)
    monkeypatch.setattr(
        read_model_stage,
        "materialize_read_model_stage",
        lambda *_args, **_kwargs: order.append("read_model_materialize") or {"status": "ok"},
        raising=False,
    )

    with _repo(tmp_path) as repo:
        _refresh_store(repo).set_checkpoint(Stage.READ_MODEL_MATERIALIZE.value, None)
        result = run_once(
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport(),
                policy=RefreshPolicy(),
                clock=clock,
                sleeper=FakeSleeper(clock),
            ),
            force=True,
        )

    assert result.status == "ok"
    assert order == ["read_model_materialize", "kudos"]


def test_materialization_lost_lease_fails_closed(monkeypatch, tmp_path):
    from mcp_strava.refresh import RefreshPolicy, _sync_ops, run_once, source_ingest

    monkeypatch.setattr(source_ingest, "sync_summaries", lambda *_args, **_kwargs: (0, 0))
    monkeypatch.setattr(_sync_ops, "sync_streams", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(source_ingest, "sync_details", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(read_model_stage, "schema_validate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(_sync_ops, "_sync_kudos", lambda *_args, **_kwargs: 0)

    def fake_materialize(repo, now_iso, renew_lease):
        del repo, now_iso
        renew_lease()

    monkeypatch.setattr(read_model_stage, "materialize_read_model_stage", fake_materialize, raising=False)

    with _repo(tmp_path) as repo:
        monkeypatch.setattr(RefreshStateStore, "renew_refresh_lease", lambda *_args, **_kwargs: False)
        with pytest.raises(RuntimeError, match="refresh lease lost during read-model materialization"):
            run_once(
                RefreshCollaborators(
                    repo=repo,
                    transport=FakeStravaTransport(),
                    policy=RefreshPolicy(),
                    clock=FakeClock(),
                    sleeper=FakeSleeper(),
                ),
                force=True,
            )


def test_run_backfill_skips_summaries_and_kudos_per_D16(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_catchup

    clock = FakeClock()
    transport = FakeStravaTransport()
    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            ActivitySummaryRecord(
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
        )
        result = run_catchup(
            RefreshCollaborators(
                repo=repo, transport=transport, policy=RefreshPolicy(), clock=clock, sleeper=FakeSleeper(clock)
            ),
            since="2026-05-20",
        )
        state = _refresh_store(repo).get_refresh_state()

    assert result.status == "ok"
    assert state.checkpoint_stage == Stage.COMPLETE_BACKFILL.value
    assert not any(path.startswith("/athlete/activities") for path in transport.calls_by_path)
    assert not any("kudos" in path for path in transport.calls_by_path)
    assert "refresh-backfill"


def test_run_backfill_materializes_after_source_changing_work(monkeypatch, tmp_path):
    from mcp_strava.refresh import RefreshPolicy, _sync_ops, run_catchup

    order: list[str] = []
    monkeypatch.setattr(_sync_ops, "sync_streams", lambda *_args, **_kwargs: order.append("streams_backfill") or 1)
    from mcp_strava.refresh import source_ingest

    monkeypatch.setattr(source_ingest, "sync_details", lambda *_args, **_kwargs: order.append("details_backfill") or 1)
    monkeypatch.setattr(read_model_stage, "schema_validate", lambda *_args, **_kwargs: order.append("schema_validate"))
    monkeypatch.setattr(
        read_model_stage,
        "materialize_read_model_stage",
        lambda *_args, **_kwargs: order.append("read_model_materialize") or {"status": "ok"},
        raising=False,
    )

    with _repo(tmp_path) as repo:
        result = run_catchup(
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport(),
                policy=RefreshPolicy(),
                clock=FakeClock(),
                sleeper=FakeSleeper(),
            ),
            since="2026-05-20",
        )

    assert result.status == "ok"
    assert order == ["streams_backfill", "details_backfill", "schema_validate", "read_model_materialize"]


def test_run_backfill_detail_only_ingest_invalidates_and_rematerializes(tmp_path):
    activity_id = 500
    transport = FakeStravaTransport()
    order: list[str] = []

    from mcp_strava.refresh import read_model_stage

    real_schema_validate = read_model_stage.schema_validate
    real_materialize = read_model_stage.materialize_read_model_stage

    def wrapped_schema_validate(repo):
        order.append("schema_validate")
        return real_schema_validate(repo)

    def wrapped_materialize(repo, now_iso, renew_lease):
        order.append("materialize")
        return real_materialize(repo, now_iso, renew_lease)

    try:
        with _repo(tmp_path) as repo:
            from mcp_strava.refresh.source_ingest import sync_summaries

            sync_summaries(repo, transport, "2026-05-29T00:00:00")
            read_model_stage.schema_validate(repo)
            _sync_ops.sync_streams(repo, transport, since="2026-05-20")
            read_model_stage.materialize_read_model_stage(repo, "2026-05-29T00:05:00", None)
            order.clear()
            monkeypatch = pytest.MonkeyPatch()
            monkeypatch.setattr(read_model_stage, "schema_validate", wrapped_schema_validate)
            monkeypatch.setattr(read_model_stage, "materialize_read_model_stage", wrapped_materialize)

            before_source = repo.source_state_for_activity(activity_id)
            before_dirty = repo.dirty_activity_rows()
            before_fact = repo._fetchone(
                "SELECT calories_kcal FROM activity_metric_facts WHERE activity_id = ? AND metric_version = ?",
                [activity_id, repo.current_metric_version()],
            )

            result = run_catchup(
                RefreshCollaborators(
                    repo=repo,
                    transport=transport,
                    policy=RefreshPolicy(),
                    clock=FakeClock(),
                    sleeper=FakeSleeper(),
                ),
                since="2026-05-20",
            )

            after_source = repo.source_state_for_activity(activity_id)
            after_dirty = repo.dirty_activity_rows()
            detail_bronze = repo.latest_activity_payload(activity_id, "detail")
            after_fact = repo._fetchone(
                "SELECT calories_kcal FROM activity_metric_facts WHERE activity_id = ? AND metric_version = ?",
                [activity_id, repo.current_metric_version()],
            )
    finally:
        monkeypatch.undo()

    assert before_source is not None
    assert before_dirty == []
    assert before_fact is not None
    assert before_fact["calories_kcal"] is None
    assert result.status == "ok"
    assert result.streams_fetched == 0
    assert result.details_fetched == 1
    assert after_source is not None
    assert int(after_source["source_revision"]) == int(before_source["source_revision"]) + 1
    assert after_source["detail_hash"] != before_source["detail_hash"]
    assert after_dirty == []
    assert detail_bronze is not None
    assert detail_bronze["payload_json"] == '{"id": 500, "name": "Morning Run", "resource_state": 3}'
    assert after_fact is not None
    assert after_fact["calories_kcal"] is None
    assert order == ["schema_validate", "materialize"]


def test_run_backfill_failure_preserves_backfill_checkpoint_per_D16(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_catchup

    clock = FakeClock()
    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            ActivitySummaryRecord(
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
        )
        result = run_catchup(
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport({"/streams": StravaUnavailableError("rate_limited")}),
                policy=RefreshPolicy(),
                clock=clock,
                sleeper=FakeSleeper(clock),
            ),
            since="2026-05-20",
        )
        state = _refresh_store(repo).get_refresh_state()

    assert result.status == "failed"
    assert state.checkpoint_stage == Stage.STREAMS_BACKFILL.value


def test_stream_channel_backfill_materializes_after_source_changing_work(monkeypatch, tmp_path):
    from mcp_strava.refresh import RefreshPolicy, _sync_ops, run_stream_channel_catchup

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
        lambda *_args, **_kwargs: (
            order.append("stream_channels_backfill")
            or {
                "activities_considered": 1,
                "activities_to_backfill": 1,
                "missing_channels": {"watts": 1},
                "metadata_missing": 1,
                "estimated_api_calls": 1,
                "completed": 1,
            }
        ),
    )
    monkeypatch.setattr(
        read_model_stage,
        "materialize_read_model_stage",
        lambda *_args, **_kwargs: order.append("read_model_materialize") or {"status": "ok"},
        raising=False,
    )

    with _repo(tmp_path) as repo:
        result = run_stream_channel_catchup(
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport(),
                policy=RefreshPolicy(),
                clock=FakeClock(),
                sleeper=FakeSleeper(),
            )
        )

    assert result["status"] == "ok"
    assert order == ["stream_channels_backfill", "read_model_materialize"]


def test_run_once_after_complete_backfill_starts_daily_refresh_per_D16(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_catchup, run_once

    clock = FakeClock()
    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            ActivitySummaryRecord(
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
        )
        assert (
            run_catchup(
                RefreshCollaborators(
                    repo=repo,
                    transport=FakeStravaTransport(),
                    policy=RefreshPolicy(),
                    clock=clock,
                    sleeper=FakeSleeper(clock),
                )
            ).status
            == "ok"
        )
        daily_transport = FakeStravaTransport()
        result = run_once(
            RefreshCollaborators(
                repo=repo, transport=daily_transport, policy=RefreshPolicy(), clock=clock, sleeper=FakeSleeper(clock)
            )
        )

    assert result.status == "ok"
    assert daily_transport.calls_by_path["/athlete/activities?per_page=100&page=1"] == 1


def test_freshness_evaluate_all_states_per_D05(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, evaluate_freshness

    now = datetime(2026, 5, 21, 12, 0, 0)
    policy = RefreshPolicy(warn_age_hours=12, max_age_hours=24, recent_failure_window_seconds=3600)

    with _repo(tmp_path) as repo:
        store = _refresh_store(repo)
        store.record_refresh_success("2026-05-21T11:00:00")
        assert evaluate_freshness(store.get_refresh_state(), now, policy) == "fresh"
        store.record_refresh_success("2026-05-20T23:00:00")
        assert evaluate_freshness(store.get_refresh_state(), now, policy) == "aging"
        store.record_refresh_success("2026-05-20T11:00:00")
        assert evaluate_freshness(store.get_refresh_state(), now, policy) == "stale"
        store.record_refresh_failure("2026-05-21T11:30:00", "network_unstable", None)
        assert evaluate_freshness(store.get_refresh_state(), now, policy) == "refresh_failed"
        store.record_refresh_failure("2026-05-21T11:30:00", "rate_limited", "2026-05-21T13:00:00")
        assert evaluate_freshness(store.get_refresh_state(), now, policy) == "refresh_delayed"
        store.acquire_refresh_lease("owner", "2026-05-21T12:10:00", "2026-05-21T12:00:00")
        assert evaluate_freshness(store.get_refresh_state(), now, policy) == "refresh_in_progress"


def test_enqueue_refresh_request_if_stale_is_idempotent_per_D04_REFRESH_02(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, enqueue_refresh_request_if_stale

    now = datetime(2026, 5, 21, 12, 0, 0)
    with _repo(tmp_path) as repo:
        store = _refresh_store(repo)
        store.record_refresh_success("2026-05-20T11:00:00")
        assert enqueue_refresh_request_if_stale(
            store, now, RefreshPolicy(), reason="first_use_of_day", requested_for_day=date(2026, 5, 21)
        )
        assert not enqueue_refresh_request_if_stale(
            store, now, RefreshPolicy(), reason="first_use_of_day", requested_for_day=date(2026, 5, 21)
        )
        assert not enqueue_refresh_request_if_stale(
            store, now, RefreshPolicy(), reason="first_use_of_day", requested_for_day=date(2026, 5, 21)
        )
        assert len(store.pending_refresh_requests()) == 1


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
        def current_metric_version(self):
            return 1

        def read_model_status(self, metric_version=None):
            del metric_version
            return {"dirty_count": 12}

    def fake_repository_from_connection(conn):
        calls.append(("repo_factory", conn))
        return FakeRepo()

    def fake_materialize_stage(repo, now_iso, renew_lease, limit=None):
        del repo, now_iso, renew_lease
        calls.append(("materialize_stage", limit))
        return {"dirty_rows_cleared": limit}

    monkeypatch.setattr(worker, "MirrorConn", FakeDbConn)
    monkeypatch.setattr(worker.DuckDBRepository, "from_connection", staticmethod(fake_repository_from_connection))
    monkeypatch.setattr(worker.read_model_stage, "materialize_read_model_stage", fake_materialize_stage)
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
        def current_metric_version(self):
            return 1

        def read_model_status(self, metric_version=None):
            del metric_version
            return {"dirty_count": 8}

    def fake_repository_from_connection(conn):
        calls.append(("repo_factory", conn))
        return FakeRepo()

    def fake_materialize_stage(repo, now_iso, renew_lease, limit=None):
        del repo, now_iso, renew_lease
        calls.append(("materialize_stage", 3))
        return {"dirty_rows_cleared": 3}

    monkeypatch.setattr(worker, "MirrorConn", FakeDbConn)
    monkeypatch.setattr(worker.DuckDBRepository, "from_connection", staticmethod(fake_repository_from_connection))
    monkeypatch.setattr(worker.read_model_stage, "materialize_read_model_stage", fake_materialize_stage)
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

    def fake_run_pending_once_result(*, emit_idle: bool = True):
        assert emit_idle is False
        raise RuntimeError("duckdb fatal detail")

    monkeypatch.setattr(worker, "_run_pending_once_result", fake_run_pending_once_result)
    monkeypatch.setattr(worker, "_emit", lambda event, **fields: events.append((event, fields)))

    worker.run_forever(poll_seconds=5, stop_event=StopAfterFirstWait(), emit_start=False)

    captured = capsys.readouterr()
    assert events == [
        ("refresh_worker_error", {"error_type": "RuntimeError", "error": "duckdb fatal detail"}),
    ]
    assert "Traceback" in captured.err
    assert "RuntimeError: duckdb fatal detail" in captured.err


def test_worker_health_records_refresh_failure_reason(monkeypatch, tmp_path):
    from mcp_strava.refresh import worker

    health_path = tmp_path / "refresh-health.json"
    monkeypatch.setenv("MCP_STRAVA_REFRESH_HEALTH_PATH", str(health_path))

    class StopAfterFirstWait:
        def is_set(self) -> bool:
            return False

        def wait(self, timeout: int) -> bool:
            assert timeout == 5
            return True

    monkeypatch.setattr(
        worker,
        "_run_pending_once_result",
        lambda *, emit_idle=False: worker._CycleResult(
            exit_code=1,
            failure_reason="strava_application_inactive",
        ),
    )
    monkeypatch.setattr(worker, "_emit", lambda *_args, **_kwargs: None)

    worker.run_forever(poll_seconds=5, stop_event=StopAfterFirstWait(), emit_start=False)

    data = json.loads(health_path.read_text())
    assert data["last_outcome"] == "error"
    assert data["consecutive_failures"] == 1
    assert data["last_error_type"] == "RefreshFailed"
    assert data["last_error"] == "strava_application_inactive"


def test_worker_runs_periodic_refresh_without_pending_requests(monkeypatch, tmp_path):
    from mcp_strava.refresh import Stage, worker

    calls = []
    backfill_calls = []
    settings = SimpleNamespace(
        database_path=tmp_path / "refresh.db",
        freshness=SimpleNamespace(warn_age_hours=12, max_age_hours=24),
        refresh=SimpleNamespace(
            interval_seconds=3600,
            stream_backfill_batch_size=50,
            read_model_batch_size=25,
            full_resync_interval_seconds=604800,
        ),
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
        def current_metric_version(self):
            return 1

        def read_model_status(self, metric_version=None):
            del metric_version
            return {"dirty_count": 0}

    class FakeRefreshStore:
        def get_refresh_state(self):
            return state

        def pending_refresh_requests(self):
            return []

        def mark_refresh_requests_consumed(self, consumed_at):
            return 0

    def fake_run_once(collaborators, *, owner, force, mode):
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
    monkeypatch.setattr(worker, "MirrorConn", FakeDbConn)
    # Empty dirty queue still calls the chokepoint (fingerprint check); these tests
    # exercise the periodic-refresh cycle, not materialization, so stub it out.
    monkeypatch.setattr(
        worker.read_model_stage, "materialize_read_model_stage", lambda *_a, **_k: {"dirty_rows_cleared": 0}
    )
    monkeypatch.setattr(worker.DuckDBRepository, "from_connection", staticmethod(lambda _conn: FakeRepo()))
    monkeypatch.setattr(worker.RefreshStateStore, "from_connection", staticmethod(lambda _conn: FakeRefreshStore()))
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
    from mcp_strava.refresh import Stage, worker

    backfill_calls = []
    settings = SimpleNamespace(
        database_path=tmp_path / "refresh.db",
        freshness=SimpleNamespace(warn_age_hours=12, max_age_hours=24),
        refresh=SimpleNamespace(
            interval_seconds=3600,
            stream_backfill_batch_size=25,
            read_model_batch_size=25,
            full_resync_interval_seconds=604800,
        ),
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
        def current_metric_version(self):
            return 1

        def read_model_status(self, metric_version=None):
            del metric_version
            return {"dirty_count": 0}

    class FakeRefreshStore:
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
    monkeypatch.setattr(worker, "MirrorConn", FakeDbConn)
    # Empty dirty queue still calls the chokepoint (fingerprint check); these tests
    # exercise the periodic-refresh cycle, not materialization, so stub it out.
    monkeypatch.setattr(
        worker.read_model_stage, "materialize_read_model_stage", lambda *_a, **_k: {"dirty_rows_cleared": 0}
    )
    monkeypatch.setattr(worker.DuckDBRepository, "from_connection", staticmethod(lambda _conn: FakeRepo()))
    monkeypatch.setattr(worker.RefreshStateStore, "from_connection", staticmethod(lambda _conn: FakeRefreshStore()))
    monkeypatch.setattr(
        worker,
        "build_refresh_collaborators",
        lambda _settings: (_settings, object(), object(), object(), worker.RefreshPolicy.from_settings(settings)),
    )
    monkeypatch.setattr(
        worker.refresh_runtime, "run_once", lambda *_args, **_kwargs: pytest.fail("regular refresh must not run")
    )
    monkeypatch.setattr(worker, "_run_stream_channel_backfill", fake_stream_backfill)

    assert worker.run_pending_once(emit_idle=False) == 0
    assert backfill_calls == [25]


def test_worker_skips_periodic_refresh_before_interval(monkeypatch, tmp_path):
    from mcp_strava.refresh import Stage, worker

    settings = SimpleNamespace(
        database_path=tmp_path / "refresh.db",
        freshness=SimpleNamespace(warn_age_hours=12, max_age_hours=24),
        refresh=SimpleNamespace(
            interval_seconds=3600,
            stream_backfill_batch_size=50,
            read_model_batch_size=25,
            full_resync_interval_seconds=604800,
        ),
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
        def current_metric_version(self):
            return 1

        def read_model_status(self, metric_version=None):
            del metric_version
            return {"dirty_count": 0}

    class FakeRefreshStore:
        def get_refresh_state(self):
            return state

        def pending_refresh_requests(self):
            return []

    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "_now_iso", lambda: "2026-05-21T12:00:00")
    monkeypatch.setattr(worker, "ensure_runtime_refresh_schema", lambda _settings: None)
    monkeypatch.setattr(worker, "MirrorConn", FakeDbConn)
    # Empty dirty queue still calls the chokepoint (fingerprint check); these tests
    # exercise the periodic-refresh cycle, not materialization, so stub it out.
    monkeypatch.setattr(
        worker.read_model_stage, "materialize_read_model_stage", lambda *_a, **_k: {"dirty_rows_cleared": 0}
    )
    monkeypatch.setattr(worker.DuckDBRepository, "from_connection", staticmethod(lambda _conn: FakeRepo()))
    monkeypatch.setattr(worker.RefreshStateStore, "from_connection", staticmethod(lambda _conn: FakeRefreshStore()))
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

    monkeypatch.setattr(worker, "MirrorConn", FakeDbConn)
    monkeypatch.setattr(worker, "_emit", lambda event, **fields: events.append((event, fields)))
    monkeypatch.setattr(worker, "_prev_free_blocks", None)

    worker._emit_mirror_storage()
    worker._emit_mirror_storage()

    assert [name for name, _ in events] == ["mirror_storage", "mirror_storage"]
    # First reading has no prior; second compares against it (no change between reads).
    assert events[0][1]["free_blocks_delta"] is None
    assert events[1][1]["free_blocks_delta"] == 0
    assert "reclaimable_pct" in events[0][1] and "message" in events[0][1]


def test_stream_payload_deduplicates_duplicate_time_offsets_from_strava_response(capsys):
    from mcp_strava.refresh._sync_ops import _stream_payload

    rows, metadata = _stream_payload(
        {
            "time": {"data": [0, 0, 1], "original_size": 3, "resolution": "high", "series_type": "time"},
            "heartrate": {"data": [140, 999, 141], "original_size": 3, "resolution": "high", "series_type": "time"},
            "velocity_smooth": {
                "data": [3.0, 9.9, 3.1],
                "original_size": 3,
                "resolution": "high",
                "series_type": "time",
            },
        },
        fetched_at="2026-06-06T08:00:00",
        activity_id=18801251418,
    )

    assert [row["time_offset"] for row in rows] == [0, 1]
    assert rows[0]["heartrate"] == 140
    assert rows[0]["velocity"] == 3.0
    assert {item["channel_key"] for item in metadata} >= {"time", "heartrate", "velocity_smooth"}
    event = json.loads(capsys.readouterr().out)
    assert event == {
        "event": "strava_stream_duplicate_time_offset",
        "activity_id": 18801251418,
        "time_offset": 0,
        "kept_index": 0,
        "dropped_index": 1,
    }


def test_sync_streams_requests_all_configured_channels_and_writes_projection_metadata(tmp_path):
    from mcp_strava.refresh._sync_ops import sync_streams

    class RichStreamsTransport(FakeStravaTransport):
        def fetch(self, path: str) -> StravaResponse:
            self.calls_by_path[path] += 1
            if path.startswith("/activities/500/streams"):
                return StravaResponse(
                    data={
                        "time": {"data": [0, 1], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "distance": {
                            "data": [0.0, 11.2],
                            "original_size": 2,
                            "resolution": "high",
                            "series_type": "distance",
                        },
                        "heartrate": {
                            "data": [140, 141],
                            "original_size": 2,
                            "resolution": "high",
                            "series_type": "distance",
                        },
                        "velocity_smooth": {
                            "data": [3.0, 3.1],
                            "original_size": 2,
                            "resolution": "high",
                            "series_type": "distance",
                        },
                        "altitude": {
                            "data": [501.0, 502.0],
                            "original_size": 2,
                            "resolution": "high",
                            "series_type": "distance",
                        },
                        "cadence": {
                            "data": [84, 85],
                            "original_size": 2,
                            "resolution": "high",
                            "series_type": "distance",
                        },
                        "latlng": {
                            "data": [[43.21, 76.91], [43.22, 76.92]],
                            "original_size": 2,
                            "resolution": "high",
                            "series_type": "distance",
                        },
                        "grade_smooth": {
                            "data": [1.1, 1.2],
                            "original_size": 2,
                            "resolution": "high",
                            "series_type": "distance",
                        },
                        "grade_adjusted_speed": {
                            "data": [3.05, 3.15],
                            "original_size": 2,
                            "resolution": "high",
                            "series_type": "distance",
                        },
                        "grade_adjusted_distance": {
                            "data": [0.0, 10.9],
                            "original_size": 2,
                            "resolution": "high",
                            "series_type": "distance",
                        },
                        "moving": {"data": [1, 1], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "watts": {
                            "data": [220, 230],
                            "original_size": 2,
                            "resolution": "high",
                            "series_type": "distance",
                        },
                        "temp": {"data": [20, 21], "original_size": 2, "resolution": "high", "series_type": "distance"},
                        "unknown_future_key": {
                            "data": ["a", "b"],
                            "original_size": 2,
                            "resolution": "high",
                            "series_type": "distance",
                        },
                    },
                    rate_info=StravaRateInfo(),
                    status=200,
                )
            return super().fetch(path)

    transport = RichStreamsTransport()
    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            ActivitySummaryRecord(
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
        )
        fetched = sync_streams(repo, transport, since="2026-05-20")
        stream_rows = activity_stream_rows(repo, 500)
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
                        "heartrate": {
                            "data": [142],
                            "original_size": 1,
                            "resolution": "high",
                            "series_type": "distance",
                        },
                    },
                    rate_info=StravaRateInfo(),
                    status=200,
                )
            return super().fetch(path)

    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            ActivitySummaryRecord(
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
        )
        fetched = sync_streams(repo, PartialStreamsTransport(), since="2026-05-20")
        missing = repo.conn.execute(
            "SELECT COUNT(*) FROM stream_channels WHERE activity_id = 500 AND status = 'unavailable'"
        ).fetchone()[0]

    assert fetched == 1
    assert missing > 0


def test_sync_streams_does_not_mutate_refresh_checkpoint_without_runtime_callback(tmp_path):
    from mcp_strava.refresh._sync_ops import sync_streams

    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            ActivitySummaryRecord(
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
        )

        assert _refresh_store(repo).get_refresh_state().checkpoint_stage is None
        assert sync_streams(repo, FakeStravaTransport(), since="2026-05-20") == 1

        state = _refresh_store(repo).get_refresh_state()

    assert state.checkpoint_stage is None
    assert state.checkpoint_cursor is None


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
                        "heartrate": {
                            "data": [142],
                            "original_size": 1,
                            "resolution": "high",
                            "series_type": "distance",
                        },
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
            ActivitySummaryRecord(
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
        )
        assert sync_streams(repo, PartialStreamsTransport(), since="2026-05-20") == 1
        result = run_stream_channel_catchup(
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport(),
                policy=RefreshPolicy(),
                clock=FakeClock(),
                sleeper=FakeSleeper(),
            ),
            dry_run=True,
        )

    assert result["activities_to_backfill"] == 0
    assert result["estimated_api_calls"] == 0


def test_stream_channel_backfill_dry_run_reports_remaining_work_without_transport_calls(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, run_stream_channel_catchup

    transport = FakeStravaTransport()
    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            ActivitySummaryRecord(
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
            RefreshCollaborators(
                repo=repo,
                transport=transport,
                policy=RefreshPolicy(),
                clock=FakeClock(),
                sleeper=FakeSleeper(),
            ),
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
        _refresh_store(repo).set_checkpoint(Stage.STREAM_CHANNELS_BACKFILL.value, "500")
        with pytest.raises(RuntimeError, match="admin catchup"):
            run_once(
                RefreshCollaborators(
                    repo=repo,
                    transport=FakeStravaTransport(),
                    policy=RefreshPolicy(),
                    clock=FakeClock(),
                    sleeper=FakeSleeper(),
                )
            )


def test_run_catchup_rejects_stream_channel_backfill_checkpoint(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_catchup

    with _repo(tmp_path) as repo:
        _refresh_store(repo).set_checkpoint(Stage.STREAM_CHANNELS_BACKFILL.value, "500")
        with pytest.raises(RuntimeError, match="admin catchup"):
            run_catchup(
                RefreshCollaborators(
                    repo=repo,
                    transport=FakeStravaTransport(),
                    policy=RefreshPolicy(),
                    clock=FakeClock(),
                    sleeper=FakeSleeper(),
                )
            )


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
            ActivitySummaryRecord(
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
            RefreshCollaborators(
                repo=repo, transport=transport, policy=RefreshPolicy(), clock=FakeClock(), sleeper=FakeSleeper()
            )
        )

    assert result["status"] in {"ok", "delayed"}
    assert any(path.startswith("/activities/500/streams") for path in transport.calls_by_path)
    assert not any(path.startswith("/athlete/activities") for path in transport.calls_by_path)
    assert not any(path.endswith("/kudos?per_page=100") for path in transport.calls_by_path)


def test_stream_channel_backfill_renews_long_lease_during_progress(monkeypatch, tmp_path):
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
            ActivitySummaryRecord(
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
        original_renew = RefreshStateStore.renew_refresh_lease

        def record_renewal(store: RefreshStateStore, owner: str, expires_at: str) -> bool:
            renewals.append(expires_at)
            return original_renew(store, owner, expires_at)

        monkeypatch.setattr(RefreshStateStore, "renew_refresh_lease", record_renewal)
        result = run_stream_channel_catchup(
            RefreshCollaborators(
                repo=repo,
                transport=WaitingStreamsTransport(),
                policy=RefreshPolicy(lease_duration_seconds=10),
                clock=clock,
                sleeper=FakeSleeper(clock),
            )
        )

    assert result["status"] == "ok"
    assert len(renewals) >= 2
    first = datetime.fromisoformat(renewals[0])
    last = datetime.fromisoformat(renewals[-1])
    assert (first - datetime.fromtimestamp(1_716_206_400.0, tz=UTC).replace(tzinfo=None)).total_seconds() == 1800
    assert (last - first).total_seconds() >= 901


def test_stream_channel_backfill_rate_limit_keeps_checkpoint_and_rows(tmp_path):
    from mcp_strava.refresh import RefreshPolicy, Stage, run_stream_channel_catchup

    with _repo(tmp_path) as repo:
        repo.upsert_activity_summary(
            ActivitySummaryRecord(
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
            RefreshCollaborators(
                repo=repo,
                transport=FakeStravaTransport({"/streams": StravaUnavailableError("rate_limited")}),
                policy=RefreshPolicy(),
                clock=FakeClock(),
                sleeper=FakeSleeper(),
            )
        )
        state = _refresh_store(repo).get_refresh_state()
        rows = activity_stream_rows(repo, 500)

    assert result["status"] in {"failed", "delayed"}
    assert state.checkpoint_stage == Stage.STREAM_CHANNELS_BACKFILL.value
    assert len(rows) == 1


def _seed_one_dirty_activity(repo, *, activity_id: int = 920, day: str = "2026-05-21") -> None:
    """Seed one HR-bearing activity so the dirty queue + activity_source_state
    have a row to materialize/enqueue. Mirrors the materializer test fixture."""
    repo.upsert_activity_summary(
        ActivitySummaryRecord(
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
                '"average_heartrate":145,"max_heartrate":172,"has_heartrate":true}}'
            ),
            synced_at=f"{day}T07:00:00Z",
        )
    )
    repo.update_activity_detail(activity_id, f'{{"id": {activity_id}, "resource_state": 3}}')
    rows = [
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
                "batch_id": "fingerprint-test",
                "status": "available",
                "error": None,
            }
        ],
    )


def _last_ok_run_version(repo) -> int:
    return int(
        repo.conn.execute(
            """
            SELECT metric_version FROM read_model_refresh_runs
            WHERE status = 'ok' ORDER BY id DESC LIMIT 1
            """
        ).fetchone()[0]
    )


def test_chokepoint_materializes_at_bumped_version_on_fingerprint_mismatch(tmp_path):
    """Stale-version HIGH guard: when stored != live, the stage must bump to N+1,
    enqueue every activity at N+1, AND materialize at the SAME N+1 it just bumped
    to — never at the pre-bump N. The version is re-resolved internally post-bump,
    so the enqueue version and the materialize version cannot disagree."""
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository
    from mcp_strava.refresh.read_model_stage import materialize_read_model_stage
    from tests._fixtures_duckdb import create_empty_fixture_db

    fixture = tmp_path / "fingerprint.duckdb"
    create_empty_fixture_db(fixture)
    with DuckDBRepository.from_path(fixture) as repo:
        _seed_one_dirty_activity(repo)
        # First cycle: stored == live (seed adopted current) -> normal materialize at N=1.
        materialize_read_model_stage(repo, "2026-05-24T12:00:00", None)
        assert _last_ok_run_version(repo) == 1

        # Force a logic-edit signal: overwrite the stored fingerprint with a wrong
        # value (the live side is the real cached fingerprint). This is exactly how
        # a real source edit looks: stored is stale, live moved on.
        repo.bump_logic_version(1, "STALE_WRONG_FINGERPRINT", "2026-05-24T12:30:00")
        # Re-dirty the activity so there is something to recompute at N+1.
        repo.update_activity_detail(920, '{"id": 920, "resource_state": 3, "calories": 410}')

        materialize_read_model_stage(repo, "2026-05-24T13:00:00", None)

        bumped = repo.current_metric_version()
        materialized_version = _last_ok_run_version(repo)
        fact_at_2 = repo.fetch_activity_metric_fact(920, metric_version=2)

    assert bumped == 2, "fingerprint mismatch must bump metric_version to N+1"
    assert materialized_version == 2, "materialize must run at the bumped N+1, not the stale N"
    assert fact_at_2 is not None, "the recompute must write facts at the bumped version"


def test_chokepoint_bump_and_enqueue_are_atomic_on_enqueue_failure(tmp_path):
    """WR-01 atomicity: on a fingerprint mismatch the stage bumps the logic version
    AND mass-enqueues the recompute. If the enqueue fails AFTER the bump (process
    crash, lease loss, OOM mid-step), the bump must NOT durably land on its own —
    otherwise the stored fingerprint advances to live while the dirty queue is never
    populated, so the next cycle sees stored == live and silently never recomputes
    (the exact under-invalidation this phase exists to prevent).

    We inject a failure inside enqueue_metric_version_recompute (it runs AFTER the
    bump in the chokepoint) and assert, by reopening the DB in a fresh repository,
    that the durably-stored logic version is still the PRE-bump one — so the next
    cycle still detects the mismatch and recomputes.
    """
    from mcp_strava.adapters.duckdb.repository import DuckDBRepository
    from mcp_strava.metric_registry import cached_logic_fingerprint
    from mcp_strava.refresh.read_model_stage import materialize_read_model_stage
    from tests._fixtures_duckdb import create_empty_fixture_db

    class EnqueueExplodesRepo(DuckDBRepository):
        def enqueue_metric_version_recompute(self, *args, **kwargs):
            # Simulate a crash/abort AFTER bump_logic_version has run but while the
            # mass-enqueue is in flight.
            raise RuntimeError("enqueue crashed mid-recompute")

    fixture = tmp_path / "atomic.duckdb"
    create_empty_fixture_db(fixture)

    # Seed + adopt-current with a normal repo so stored == live at version 1.
    with DuckDBRepository.from_path(fixture) as repo:
        _seed_one_dirty_activity(repo)
        materialize_read_model_stage(repo, "2026-05-24T12:00:00", None)
        version_before = repo.current_metric_version()
        stored_fp_before = repo.current_logic_version()["logic_fingerprint"]
    assert version_before == 1
    assert stored_fp_before == cached_logic_fingerprint(), "precondition: stored == live before the edit"

    # Now drive a mismatch: stale the stored fingerprint, then run the chokepoint
    # through a repo whose enqueue explodes after the bump.
    with EnqueueExplodesRepo.from_path(fixture) as repo:
        repo.bump_logic_version(1, "STALE_WRONG_FINGERPRINT", "2026-05-24T12:30:00")
        repo._current_metric_version_cache = None
        with pytest.raises(RuntimeError, match="enqueue crashed mid-recompute"):
            materialize_read_model_stage(repo, "2026-05-24T13:00:00", None)

    # Reopen fresh: the bump+enqueue must have been atomic. The durably-stored
    # version must still be the stale-but-pre-bump version (1) with the STALE
    # fingerprint — NOT advanced to 2 with the live fingerprint. So the next cycle
    # still sees stored (STALE) != live and will recompute.
    with DuckDBRepository.from_path(fixture) as repo:
        stored = repo.current_logic_version()
        durable_version = repo.current_metric_version()

    assert durable_version == 1, (
        f"bump+enqueue must be atomic: a failed enqueue must NOT durably advance the version, got {durable_version}"
    )
    assert stored["logic_fingerprint"] == "STALE_WRONG_FINGERPRINT", (
        "the stored fingerprint must NOT have advanced to live on a failed enqueue, "
        "or the next cycle would see stored == live and never recompute"
    )
    assert stored["logic_fingerprint"] != cached_logic_fingerprint()


def test_sync_kudos_indexes_raw_rows_positionally(tmp_path):
    """Regression: _sync_kudos read raw DB-API rows with row['id'].

    repo.conn.execute(...).fetchall() yields positional tuples, so the string
    key raised `TypeError: tuple indices must be integers or slices, not str`
    on every refresh cycle for any activity with kudos_count > 0 — silently
    wedging the worker (healthcheck red) while the MCP read surface stayed ok.
    The body was never exercised because other tests monkeypatch _sync_kudos.
    """
    from mcp_strava.refresh._sync_ops import _sync_kudos
    from mcp_strava.refresh.read_model_stage import schema_validate
    from mcp_strava.refresh.source_ingest import sync_summaries

    repo = _repo(tmp_path)
    # Seed activity 500 through the real summary path, then mark it as having
    # kudos through the bronze source payload so the _sync_kudos SELECT picks it up.
    sync_summaries(repo, FakeStravaTransport(), "2026-05-29T00:00:00")
    schema_validate(repo)
    repo.write_activity_payload(
        ActivitySourcePayload(
            activity_id=500,
            activity_day="2026-05-21",
            payload_kind="summary",
            endpoint="/athlete/activities",
            fetched_at="2026-05-29T00:10:00",
            payload_json='{"id":500,"kudos_count":2}',
            raw_hash="raw-kudos-500",
            modeled_projection_hash="semantic-kudos-500",
            schema_status="clean",
        )
    )

    class _KudosTransport:
        def __init__(self):
            self.calls: list[str] = []

        def fetch(self, path: str) -> StravaResponse:
            self.calls.append(path)
            return StravaResponse(
                data=[{"firstname": "Ada", "lastname": "Lovelace"}],
                rate_info=StravaRateInfo(),
                status=200,
            )

    transport = _KudosTransport()
    fetched = _sync_kudos(repo, transport, "2026-05-29T00:00:00")

    assert fetched == 1
    assert transport.calls == ["/activities/500/kudos?per_page=100"]
