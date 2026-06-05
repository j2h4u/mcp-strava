from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from mcp_strava.adapters.duckdb.refresh_state_store import RefreshStateStore
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.refresh import RefreshPolicy
from mcp_strava.types import dc_to_dict
from tests._fixtures_duckdb import create_empty_fixture_db


@pytest.fixture
def repo(tmp_path: Path):
    db_path = tmp_path / "application-services.duckdb"
    create_empty_fixture_db(db_path)

    with DuckDBRepository.from_path(db_path) as opened:
        opened.conn.execute(
            """
            INSERT INTO activities (
                id, activity_day, date, name, sport_type, distance, moving_time,
                elapsed_time, total_elevation_gain, summary_json, detail_json, synced_at
            ) VALUES (?, CAST(? AS DATE), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                101,
                "2026-05-18",
                "2026-05-18T07:00:00",
                "Old Run",
                "Run",
                5000.0,
                1800,
                1850,
                25.0,
                "{}",
                None,
                "2026-05-18T08:00:00",
            ],
        )
        # Ensure refresh_state row id=1 exists so _set_refresh_state can update it.
        RefreshStateStore.from_connection(opened.conn).get_refresh_state()
        yield opened


def _set_refresh_state(repo: DuckDBRepository, **values: str | None) -> None:
    assignments = ", ".join(f"{key} = ?" for key in values)
    repo.conn.execute(
        f"UPDATE refresh_state SET {assignments} WHERE id = 1",
        tuple(values.values()),
    )
    repo.conn.commit()


def _refresh_store(repo: DuckDBRepository) -> RefreshStateStore:
    return RefreshStateStore.from_connection(repo.conn)


def test_APP_04_D_08_D_12_freshness_metadata_distinguishes_refresh_and_activity(repo: DuckDBRepository) -> None:
    from mcp_strava.application.freshness import build_freshness_metadata

    _set_refresh_state(
        repo,
        last_success_at="2026-05-21T06:00:00",
        last_attempt_at="2026-05-21T06:00:00",
        last_status="ok",
    )

    metadata = build_freshness_metadata(
        repo,
        datetime.fromisoformat("2026-05-21T09:00:00"),
        RefreshPolicy(),
        signal_first_use=False,
    )

    assert metadata.freshness_state == "fresh"
    assert metadata.last_successful_refresh_at == "2026-05-21T06:00:00"
    assert metadata.refresh_age_seconds == 10_800
    assert metadata.last_activity_at == "2026-05-18T07:00:00"
    assert metadata.last_activity_age_seconds == 266_400
    assert metadata.refresh_requested is False


def test_APP_04_D_04_cross_midnight_first_use_uses_local_day_not_age(repo: DuckDBRepository) -> None:
    from mcp_strava.application.freshness import build_freshness_metadata

    _set_refresh_state(
        repo,
        last_success_at="2026-05-20T23:30:00",
        last_attempt_at="2026-05-20T23:30:00",
        last_status="ok",
    )

    metadata = build_freshness_metadata(
        repo,
        datetime.fromisoformat("2026-05-21T00:15:00"),
        RefreshPolicy(),
        signal_first_use=True,
    )

    assert metadata.freshness_state == "fresh"
    assert metadata.refresh_requested is True
    assert metadata.refresh_request_reason == "first_use_of_day"
    requests = _refresh_store(repo).pending_refresh_requests()
    assert len(requests) == 1
    assert requests[0].reason == "first_use_of_day"
    assert requests[0].requested_for_day == "2026-05-21"


def test_APP_04_D_06_first_use_refresh_request_is_idempotent(repo: DuckDBRepository) -> None:
    from mcp_strava.application.freshness import build_freshness_metadata

    _set_refresh_state(repo, last_success_at="2026-05-20T12:00:00", last_status="ok")
    now = datetime.fromisoformat("2026-05-21T10:00:00")

    first = build_freshness_metadata(repo, now, RefreshPolicy(), signal_first_use=True)
    second = build_freshness_metadata(repo, now, RefreshPolicy(), signal_first_use=True)

    assert first.refresh_requested is True
    assert second.refresh_requested is False
    assert len(_refresh_store(repo).pending_refresh_requests()) == 1


def test_APP_04_refresh_failed_and_delayed_are_factual_metadata(repo: DuckDBRepository) -> None:
    from mcp_strava.application.freshness import build_freshness_metadata

    _set_refresh_state(
        repo,
        last_attempt_at="2026-05-21T09:30:00",
        last_status="failed",
        last_error_code="rate_limited",
        backoff_until="2026-05-21T11:00:00",
    )

    metadata = build_freshness_metadata(
        repo,
        datetime.fromisoformat("2026-05-21T10:00:00"),
        RefreshPolicy(),
        signal_first_use=True,
    )

    assert metadata.freshness_state == "refresh_delayed"
    assert metadata.last_error_code == "rate_limited"
    assert metadata.backoff_until == "2026-05-21T11:00:00"
    assert metadata.refresh_requested is False
    assert _refresh_store(repo).pending_refresh_requests() == []


def test_APP_04_get_freshness_service_returns_shared_envelope(repo: DuckDBRepository) -> None:
    from mcp_strava.application.freshness import get_freshness_service
    from mcp_strava.types import ServiceEnvelope

    _set_refresh_state(repo, last_success_at="2026-05-21T06:00:00", last_status="ok")

    envelope = get_freshness_service(
        now=datetime.fromisoformat("2026-05-21T09:00:00"),
        signal_first_use=False,
        connection=repo.conn,
    )
    payload = dc_to_dict(envelope)

    assert isinstance(envelope, ServiceEnvelope)
    assert set(payload) == {"data", "freshness", "completeness", "warnings", "rationale"}
    assert payload["freshness"]["last_successful_refresh_at"] == "2026-05-21T06:00:00"
    assert payload["data"]["last_successful_refresh_at"] == "2026-05-21T06:00:00"
    assert payload["completeness"]["status"] == "complete"


def test_get_freshness_service_uses_primary_repository_factory_for_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import mcp_strava.application.freshness as freshness
    from mcp_strava.types import RefreshStateRow

    class FakeConnection:
        pass

    connection = FakeConnection()

    class FakeRefreshStore:
        def get_refresh_state(self) -> RefreshStateRow:
            return RefreshStateRow(
                id=1,
                last_success_at="2026-05-21T06:00:00",
                last_attempt_at="2026-05-21T06:00:00",
                last_status="ok",
                last_error_code=None,
                lease_owner=None,
                lease_expires_at=None,
                backoff_until=None,
                checkpoint_stage=None,
                checkpoint_cursor=None,
            )

    class FakeRepository:
        conn = connection

        def latest_activity_at(self) -> str:
            return "2026-05-21T07:00:00"

    seen_connections: list[object] = []

    def fake_repository_from_connection(conn):
        seen_connections.append(conn)
        return FakeRepository()

    monkeypatch.setattr(freshness.DuckDBRepository, "from_connection", staticmethod(fake_repository_from_connection))
    monkeypatch.setattr(
        freshness.RefreshStateStore,
        "from_connection",
        staticmethod(lambda conn: FakeRefreshStore()),
    )

    envelope = freshness.get_freshness_service(
        now=datetime.fromisoformat("2026-05-21T09:00:00"),
        signal_first_use=False,
        connection=connection,
    )
    payload = dc_to_dict(envelope)

    assert seen_connections == [connection]
    assert payload["freshness"]["last_successful_refresh_at"] == "2026-05-21T06:00:00"
    assert payload["freshness"]["last_activity_at"] == "2026-05-21T07:00:00"


def test_WR_02_freshness_now_default_is_utc_not_local(repo: DuckDBRepository, monkeypatch) -> None:
    """WR-02: the defaulted freshness clock must be a UTC instant, not the server's
    LOCAL wall clock.

    last_success_at is stored UTC-naive (refresh writes datetime.now(UTC); _parse_dt
    normalizes Z->+00:00). The age comparison must therefore use a UTC `now`. On a
    non-UTC server (e.g. Asia/Almaty, UTC+6) the old `now or datetime.now()` default
    yielded a LOCAL-naive now that ran +6h ahead of the UTC last_success_at, inflating
    the computed age by the offset and misclassifying a still-fresh mirror as aging.

    Scenario: last_success_at is 10h old in UTC (fresh; < warn_age_hours=12). A local
    clock skewed +6h ahead makes it read as 16h old (aging, between warn=12 and
    max=24). With the UTC fix the state is 'fresh'; with the local bug it is 'aging'.
    """
    import mcp_strava.application.freshness as freshness

    true_utc = datetime.fromisoformat("2026-05-21T10:00:00")  # UTC-naive "now"
    local_skew = datetime.fromisoformat("2026-05-21T16:00:00")  # +6h Almaty wall clock

    class _ClockProxy:
        """Stand-in for the `datetime` symbol the module calls .now() on."""

        @staticmethod
        def now(tz=None):
            if tz is not None:
                # UTC-aware request -> return the true UTC instant, tz-aware.
                return true_utc.replace(tzinfo=tz)
            # Naive request (the buggy local path) -> the +6h-skewed wall clock.
            return local_skew

        @staticmethod
        def fromisoformat(value):
            return datetime.fromisoformat(value)

    # 10h-old-in-UTC success: fresh under a UTC now, aging under the +6h-skewed now.
    _set_refresh_state(
        repo,
        last_success_at="2026-05-21T00:00:00",
        last_attempt_at="2026-05-21T00:00:00",
        last_status="ok",
    )

    monkeypatch.setattr(freshness, "datetime", _ClockProxy)

    # now=None -> exercise the PRODUCTION default freshness-clock path end-to-end.
    envelope = freshness.get_freshness_service(
        now=None,
        signal_first_use=False,
        connection=repo.conn,
    )
    state = dc_to_dict(envelope)["freshness"]["freshness_state"]

    assert state == "fresh", (
        "freshness must classify against a UTC now; a local-skewed default now misreads "
        f"a 10h-old (UTC) success as aging — got {state}"
    )
