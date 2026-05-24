import json
import sqlite3
from pathlib import Path

import pytest

from mcp_strava.adapters.sqlite.migrations import run_migrations
from mcp_strava.adapters.sqlite.repository import SQLiteRepository


def _create_v2_fixture(db_path: Path) -> None:
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
        CREATE TABLE refresh_state (
            id INTEGER PRIMARY KEY,
            last_success_at TEXT,
            last_attempt_at TEXT,
            last_status TEXT,
            last_error_code TEXT,
            lease_owner TEXT,
            lease_expires_at TEXT,
            backoff_until TEXT,
            checkpoint_stage TEXT,
            checkpoint_cursor TEXT
        );
        INSERT OR IGNORE INTO refresh_state (id) VALUES (1);
        CREATE TABLE refresh_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reason TEXT NOT NULL,
            requested_for_day TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            consumed_at TEXT
        );
        CREATE UNIQUE INDEX idx_refresh_requests_dedupe
            ON refresh_requests(reason, requested_for_day)
            WHERE consumed_at IS NULL;
        """
    )
    conn.execute("PRAGMA user_version=2")
    conn.execute(
        """
        INSERT INTO activities (
            id, date, name, sport_type, distance, moving_time, elapsed_time,
            total_elevation_gain, summary_json, detail_json, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            10,
            "2026-05-01T06:00:00Z",
            "Fixture Run",
            "Run",
            10000.0,
            3600,
            3700,
            120.0,
            "{}",
            "{}",
            "2026-05-01T07:00:00Z",
        ),
    )
    conn.execute(
        """
        INSERT INTO streams (
            activity_id, time_offset, heartrate, velocity, altitude, cadence,
            lat, lng, grade, gap_speed, gap_distance, is_moving, latlng
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (10, 0, 150, 3.6, 510.0, 85, 43.2, 76.9, 2.1, 3.5, 25.0, 1, "[43.2,76.9]"),
    )
    conn.commit()
    conn.close()


def test_migration_v3_adds_lossless_stream_inventory(tmp_path: Path) -> None:
    fixture = tmp_path / "v2.db"
    _create_v2_fixture(fixture)

    report = run_migrations(fixture)

    with sqlite3.connect(fixture) as conn:
        assert report.user_version == 3
        stream_cols = {row[1] for row in conn.execute("PRAGMA table_info(streams)").fetchall()}
        assert "values_json" in stream_cols
        assert "latlng" in stream_cols

        channel_cols = {row[1] for row in conn.execute("PRAGMA table_info(stream_channels)").fetchall()}
        assert channel_cols >= {
            "activity_id",
            "channel_key",
            "original_size",
            "resolution",
            "series_type",
            "fetched_at",
            "batch_id",
            "status",
            "error",
        }

        idx_rows = conn.execute("PRAGMA index_list('stream_channels')").fetchall()
        idx_names = {row[1] for row in idx_rows}
        assert "idx_stream_channels_activity" in idx_names


def test_schema_inventory_is_version_aware_for_v3_and_v4_contracts() -> None:
    import mcp_strava.adapters.sqlite.schema as schema

    assert 3 in schema.REQUIRED_COLUMNS_BY_VERSION
    assert "latlng" in schema.REQUIRED_COLUMNS_BY_VERSION[3]["streams"]
    assert "values_json" in schema.REQUIRED_COLUMNS_BY_VERSION[3]["streams"]
    assert "stream_channels" in schema.REQUIRED_TABLES_BY_VERSION[3]
    assert "idx_stream_channels_activity" in schema.REQUIRED_INDEXES_BY_VERSION[3]

    assert 4 in schema.REQUIRED_COLUMNS_BY_VERSION
    assert "latlng" not in schema.REQUIRED_COLUMNS_BY_VERSION[4]["streams"]


def test_insert_stream_rows_chunked_persists_lat_lng_and_values_json(tmp_path: Path) -> None:
    fixture = tmp_path / "v2.db"
    _create_v2_fixture(fixture)
    run_migrations(fixture)

    with SQLiteRepository.from_path(fixture) as repo:
        repo.insert_stream_rows_chunked(
            10,
            [
                {
                    "time_offset": 1,
                    "heartrate": 151,
                    "velocity": 3.7,
                    "altitude": 511.0,
                    "cadence": 86,
                    "lat": 43.2001,
                    "lng": 76.9002,
                    "latlng": "[43.2001,76.9002]",
                    "grade": 2.2,
                    "gap_speed": 3.6,
                    "gap_distance": 26.0,
                    "is_moving": 1,
                    "values_json": json.dumps({"watts": 240, "temp": 21.5}),
                }
            ],
        )

    with sqlite3.connect(fixture) as conn:
        row = conn.execute(
            "SELECT heartrate, lat, lng, values_json FROM streams WHERE activity_id = 10 AND time_offset = 1"
        ).fetchone()
    assert row is not None
    assert row[0] == 151
    assert row[1] == pytest.approx(43.2001)
    assert row[2] == pytest.approx(76.9002)
    assert json.loads(row[3]) == {"watts": 240, "temp": 21.5}


def test_replace_stream_rows_and_channel_metadata_is_atomic(tmp_path: Path) -> None:
    fixture = tmp_path / "v2.db"
    _create_v2_fixture(fixture)
    run_migrations(fixture)

    with SQLiteRepository.from_path(fixture) as repo:
        repo.insert_stream_rows_chunked(
            10,
            [{"time_offset": 4, "heartrate": 155, "velocity": 3.3, "altitude": 505.0, "cadence": 84,
              "lat": 43.2, "lng": 76.9, "latlng": "[43.2,76.9]", "grade": 1.0, "gap_speed": 3.2,
              "gap_distance": 21.0, "is_moving": 1, "values_json": None}],
        )

        class BoomRepo(SQLiteRepository):
            def upsert_stream_channel_metadata(self, *args, **kwargs):
                raise RuntimeError("boom")

        failing_repo = BoomRepo(repo.conn)
        with pytest.raises(RuntimeError):
            failing_repo.replace_stream_rows_and_channel_metadata(
                10,
                rows=[{"time_offset": 9, "heartrate": 160, "velocity": 3.9, "altitude": 520.0, "cadence": 90,
                       "lat": 43.22, "lng": 76.93, "latlng": "[43.22,76.93]", "grade": 1.2, "gap_speed": 3.8,
                       "gap_distance": 30.0, "is_moving": 1, "values_json": None}],
                metadata=[{"channel_key": "heartrate", "original_size": 1, "resolution": "high", "series_type": "distance",
                           "fetched_at": "2026-05-01T08:00:00Z", "batch_id": None, "status": "available", "error": None}],
                chunk_size=100,
            )

    with sqlite3.connect(fixture) as conn:
        points = conn.execute("SELECT COUNT(*) FROM streams WHERE activity_id = 10").fetchone()[0]
        channels = conn.execute("SELECT COUNT(*) FROM stream_channels WHERE activity_id = 10").fetchone()[0]
    assert points >= 1
    assert channels == 0


def test_replace_stream_rows_and_channel_metadata_records_unavailable_channel_status(tmp_path: Path) -> None:
    fixture = tmp_path / "v2.db"
    _create_v2_fixture(fixture)
    run_migrations(fixture)

    with SQLiteRepository.from_path(fixture) as repo:
        repo.replace_stream_rows_and_channel_metadata(
            10,
            rows=[
                {
                    "time_offset": 0,
                    "heartrate": 150,
                    "velocity": 3.6,
                    "altitude": 510.0,
                    "cadence": 85,
                    "lat": 43.2,
                    "lng": 76.9,
                    "latlng": "[43.2,76.9]",
                    "grade": 2.1,
                    "gap_speed": 3.5,
                    "gap_distance": 25.0,
                    "is_moving": 1,
                    "values_json": json.dumps({"distance": 0.0}),
                }
            ],
            metadata=[
                {
                    "channel_key": "distance",
                    "original_size": 1,
                    "resolution": "high",
                    "series_type": "distance",
                    "fetched_at": "2026-05-01T08:00:00Z",
                    "batch_id": None,
                    "status": "available",
                    "error": None,
                },
                {
                    "channel_key": "watts",
                    "original_size": None,
                    "resolution": None,
                    "series_type": None,
                    "fetched_at": "2026-05-01T08:00:00Z",
                    "batch_id": None,
                    "status": "unavailable",
                    "error": None,
                },
            ],
        )

    with sqlite3.connect(fixture) as conn:
        status_row = conn.execute(
            "SELECT status FROM stream_channels WHERE activity_id = 10 AND channel_key = 'watts'"
        ).fetchone()
    assert status_row is not None
    assert status_row[0] == "unavailable"
