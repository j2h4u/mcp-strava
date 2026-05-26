from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from mcp_strava.adapters.sqlite.migrations import run_migrations
from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.refresh import RefreshPolicy
from mcp_strava.types import dc_to_dict


@pytest.fixture
def repo(tmp_path: Path):
    db_path = tmp_path / "application-services.db"
    conn = sqlite3.connect(db_path)
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
    conn.execute(
        """
        INSERT INTO activities (
            id, date, name, sport_type, distance, moving_time, elapsed_time,
            total_elevation_gain, summary_json, detail_json, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            101,
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
        ),
    )
    conn.commit()
    conn.close()
    run_migrations(db_path)

    with SQLiteRepository.from_path(db_path) as opened:
        yield opened


def _set_refresh_state(repo: SQLiteRepository, **values: str | None) -> None:
    assignments = ", ".join(f"{key} = ?" for key in values)
    repo.conn.execute(
        f"UPDATE refresh_state SET {assignments} WHERE id = 1",
        tuple(values.values()),
    )
    repo.conn.commit()


def test_APP_04_D_08_D_12_freshness_metadata_distinguishes_refresh_and_activity(repo: SQLiteRepository) -> None:
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


def test_APP_04_D_04_cross_midnight_first_use_uses_local_day_not_age(repo: SQLiteRepository) -> None:
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
    requests = repo.pending_refresh_requests()
    assert len(requests) == 1
    assert requests[0].reason == "first_use_of_day"
    assert requests[0].requested_for_day == "2026-05-21"


def test_APP_04_D_06_first_use_refresh_request_is_idempotent(repo: SQLiteRepository) -> None:
    from mcp_strava.application.freshness import build_freshness_metadata

    _set_refresh_state(repo, last_success_at="2026-05-20T12:00:00", last_status="ok")
    now = datetime.fromisoformat("2026-05-21T10:00:00")

    first = build_freshness_metadata(repo, now, RefreshPolicy(), signal_first_use=True)
    second = build_freshness_metadata(repo, now, RefreshPolicy(), signal_first_use=True)

    assert first.refresh_requested is True
    assert second.refresh_requested is False
    assert len(repo.pending_refresh_requests()) == 1


def test_APP_04_refresh_failed_and_delayed_are_factual_metadata(repo: SQLiteRepository) -> None:
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
    assert repo.pending_refresh_requests() == []


def test_APP_04_get_freshness_service_returns_shared_envelope(repo: SQLiteRepository) -> None:
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

    class FakeRepository:
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

        def latest_activity_at(self) -> str:
            return "2026-05-21T07:00:00"

        def enqueue_refresh_request(self, *_args) -> bool:
            raise AssertionError("signal_first_use=False must not enqueue refresh")

    connection = FakeConnection()
    seen_connections: list[object] = []

    def fake_repository_from_connection(conn):
        seen_connections.append(conn)
        return FakeRepository()

    monkeypatch.setattr(freshness, "repository_from_connection", fake_repository_from_connection)

    envelope = freshness.get_freshness_service(
        now=datetime.fromisoformat("2026-05-21T09:00:00"),
        signal_first_use=False,
        connection=connection,
    )
    payload = dc_to_dict(envelope)

    assert seen_connections == [connection]
    assert payload["freshness"]["last_successful_refresh_at"] == "2026-05-21T06:00:00"
    assert payload["freshness"]["last_activity_at"] == "2026-05-21T07:00:00"
