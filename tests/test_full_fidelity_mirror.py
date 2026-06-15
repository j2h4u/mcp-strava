import json
from pathlib import Path

import pytest

from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.duckdb.repository_models import ActivitySummaryRecord, StreamChannelRecord
from tests._fixtures_duckdb import create_empty_fixture_db


def _seed_activity(repo: DuckDBRepository, activity_id: int = 10) -> None:
    repo.upsert_activity_summary(
        ActivitySummaryRecord(
            activity_id=activity_id,
            date="2026-05-01T06:00:00Z",
            name="Fixture Run",
            sport_type="Run",
            distance=10000.0,
            moving_time=3600,
            elapsed_time=3700,
            total_elevation_gain=120.0,
            summary_json="{}",
            synced_at="2026-05-01T07:00:00Z",
        )
    )


def test_insert_stream_rows_chunked_persists_lat_lng_and_values_json(tmp_path: Path) -> None:
    fixture = tmp_path / "mirror.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        _seed_activity(repo)
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
                    "grade": 2.2,
                    "gap_speed": 3.6,
                    "gap_distance": 26.0,
                    "is_moving": 1,
                    "values_json": json.dumps({"watts": 240, "temp": 21.5}),
                }
            ],
        )

        row = repo.conn.execute(
            "SELECT heartrate, lat, lng, values_json FROM streams WHERE activity_id = 10 AND time_offset = 1"
        ).fetchone()
    assert row is not None
    assert row[0] == 151
    assert row[1] == pytest.approx(43.2001)
    assert row[2] == pytest.approx(76.9002)
    assert json.loads(row[3]) == {"watts": 240, "temp": 21.5}


def test_replace_stream_rows_and_channel_metadata_is_atomic(tmp_path: Path) -> None:
    fixture = tmp_path / "mirror.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        _seed_activity(repo)
        repo.insert_stream_rows_chunked(
            10,
            [
                {
                    "time_offset": 4,
                    "heartrate": 155,
                    "velocity": 3.3,
                    "altitude": 505.0,
                    "cadence": 84,
                    "lat": 43.2,
                    "lng": 76.9,
                    "grade": 1.0,
                    "gap_speed": 3.2,
                    "gap_distance": 21.0,
                    "is_moving": 1,
                    "values_json": None,
                }
            ],
        )

        class BoomRepo(DuckDBRepository):
            def upsert_stream_channel_metadata(self, record: StreamChannelRecord, *, commit: bool = True):
                raise RuntimeError("boom")

        failing_repo = BoomRepo(repo.conn)
        with pytest.raises(RuntimeError):
            failing_repo.replace_stream_rows_and_channel_metadata(
                10,
                rows=[
                    {
                        "time_offset": 9,
                        "heartrate": 160,
                        "velocity": 3.9,
                        "altitude": 520.0,
                        "cadence": 90,
                        "lat": 43.22,
                        "lng": 76.93,
                        "grade": 1.2,
                        "gap_speed": 3.8,
                        "gap_distance": 30.0,
                        "is_moving": 1,
                        "values_json": None,
                    }
                ],
                metadata=[
                    {
                        "channel_key": "heartrate",
                        "original_size": 1,
                        "resolution": "high",
                        "series_type": "distance",
                        "fetched_at": "2026-05-01T08:00:00Z",
                        "batch_id": None,
                        "status": "available",
                        "error": None,
                    }
                ],
                chunk_size=100,
            )

        points = repo.conn.execute("SELECT COUNT(*) FROM streams WHERE activity_id = 10").fetchone()[0]
        channels = repo.conn.execute("SELECT COUNT(*) FROM stream_channels WHERE activity_id = 10").fetchone()[0]
    assert points >= 1
    assert channels == 0


def test_replace_stream_rows_and_channel_metadata_preserves_other_activities(tmp_path: Path) -> None:
    fixture = tmp_path / "mirror.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        _seed_activity(repo, 10)
        _seed_activity(repo, 20)
        repo.insert_stream_rows_chunked(
            20,
            [
                {
                    "time_offset": 0,
                    "heartrate": 140,
                    "velocity": 2.8,
                    "altitude": 500.0,
                    "cadence": 80,
                    "lat": 43.1,
                    "lng": 76.8,
                    "grade": 0.5,
                    "gap_speed": 2.9,
                    "gap_distance": 10.0,
                    "is_moving": 1,
                    "values_json": json.dumps({"distance": 10.0, "watts": 180}),
                }
            ],
        )
        repo.upsert_stream_channel_metadata(
            StreamChannelRecord(
                activity_id=20,
                channel_key="watts",
                original_size=1,
                resolution="high",
                series_type="distance",
                fetched_at="2026-05-01T08:00:00Z",
                batch_id="neighbor",
                status="available",
                error=None,
            )
        )
        before_stream = repo.conn.execute(
            "SELECT heartrate, velocity, values_json FROM streams WHERE activity_id = 20 AND time_offset = 0"
        ).fetchone()
        before_channel = repo.conn.execute(
            """
            SELECT original_size, resolution, series_type, fetched_at, batch_id, status, error
            FROM stream_channels
            WHERE activity_id = 20 AND channel_key = 'watts'
            """
        ).fetchone()

        replaced = repo.replace_stream_rows_and_channel_metadata(
            10,
            rows=[
                {
                    "time_offset": 0,
                    "heartrate": 152,
                    "velocity": 3.8,
                    "altitude": 512.0,
                    "cadence": 87,
                    "lat": 43.21,
                    "lng": 76.91,
                    "grade": 1.1,
                    "gap_speed": 3.7,
                    "gap_distance": 25.0,
                    "is_moving": 1,
                    "values_json": json.dumps({"distance": 25.0}),
                }
            ],
            metadata=[
                {
                    "channel_key": "distance",
                    "original_size": 1,
                    "resolution": "high",
                    "series_type": "distance",
                    "fetched_at": "2026-05-01T08:01:00Z",
                    "batch_id": None,
                    "status": "available",
                    "error": None,
                }
            ],
        )

        after_stream = repo.conn.execute(
            "SELECT heartrate, velocity, values_json FROM streams WHERE activity_id = 20 AND time_offset = 0"
        ).fetchone()
        after_channel = repo.conn.execute(
            """
            SELECT original_size, resolution, series_type, fetched_at, batch_id, status, error
            FROM stream_channels
            WHERE activity_id = 20 AND channel_key = 'watts'
            """
        ).fetchone()

    assert replaced == 1
    assert before_stream is not None
    assert after_stream is not None
    assert tuple(after_stream) == tuple(before_stream)
    assert before_channel is not None
    assert after_channel is not None
    assert tuple(after_channel) == tuple(before_channel)


def test_replace_stream_rows_and_channel_metadata_records_unavailable_channel_status(tmp_path: Path) -> None:
    fixture = tmp_path / "mirror.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        _seed_activity(repo)
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

        status_row = repo.conn.execute(
            "SELECT status FROM stream_channels WHERE activity_id = 10 AND channel_key = 'watts'"
        ).fetchone()
    assert status_row is not None
    assert status_row[0] == "unavailable"


def test_merge_stream_channel_values_is_update_only_and_preserves_existing_keys(tmp_path: Path) -> None:
    fixture = tmp_path / "mirror.duckdb"
    create_empty_fixture_db(fixture)

    with DuckDBRepository.from_path(fixture) as repo:
        _seed_activity(repo)
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
                    "grade": 2.2,
                    "gap_speed": 3.6,
                    "gap_distance": 26.0,
                    "is_moving": 1,
                    "values_json": json.dumps({"distance": 11.2, "temp": 20}),
                }
            ],
        )
        repo.upsert_stream_channel_metadata(
            StreamChannelRecord(
                activity_id=10,
                channel_key="distance",
                original_size=2,
                resolution="high",
                series_type="distance",
                fetched_at="2026-05-01T08:00:00Z",
                batch_id=None,
                status="available",
                error=None,
            )
        )
        before = repo.conn.execute(
            "SELECT heartrate, velocity, values_json FROM streams WHERE activity_id = 10 AND time_offset = 1"
        ).fetchone()
        repo.merge_stream_channel_values(
            10,
            rows=[{"time_offset": 1, "values": {"watts": 240}}],
            metadata=[
                {
                    "channel_key": "watts",
                    "original_size": 2,
                    "resolution": "high",
                    "series_type": "distance",
                    "fetched_at": "2026-05-01T08:01:00Z",
                    "batch_id": None,
                    "status": "available",
                    "error": None,
                }
            ],
            missing_channel_keys=[],
        )
        after = repo.conn.execute(
            "SELECT heartrate, velocity, values_json FROM streams WHERE activity_id = 10 AND time_offset = 1"
        ).fetchone()

    assert before[0] == after[0]
    assert before[1] == after[1]
    values = json.loads(after[2])
    assert values["distance"] == pytest.approx(11.2)
    assert values["temp"] == 20
    assert values["watts"] == 240
