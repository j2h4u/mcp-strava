"""Shared DuckDB fixtures for tests.

DuckDB is the only runtime storage. These helpers seed a DuckDB mirror file
with a deterministic dataset so tests can exercise repository, refresh, load,
and service behavior without the Strava API.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from mcp_strava.adapters.duckdb.connection import open_fixture_db
from mcp_strava.adapters.duckdb.schema import create_schema

ACTIVITY_COUNT = 42
STREAM_POINTS_PER_ACTIVITY = 10
BASE_DAY = datetime(2026, 1, 1)


def create_empty_fixture_db(db_path: str | Path) -> None:
    """Create a DuckDB mirror file with the full schema and no rows."""
    conn = open_fixture_db(db_path)
    try:
        create_schema(conn)
    finally:
        conn.close()


def create_fixture_db(db_path: str | Path) -> None:
    """Create a DuckDB mirror file seeded with deterministic activity data.

    Seeds ``ACTIVITY_COUNT`` daily Run
    activities starting ``BASE_DAY``, each with ``STREAM_POINTS_PER_ACTIVITY``
    stream points carrying heartrate/velocity/altitude/cadence and GPS, plus
    one sync-log row and one kudos row.
    """
    conn = open_fixture_db(db_path)
    try:
        create_schema(conn)

        activities = []
        for idx in range(ACTIVITY_COUNT):
            day = (BASE_DAY + timedelta(days=idx)).strftime("%Y-%m-%d")
            summary = {
                "id": idx + 1,
                "name": f"Run {idx + 1}",
                "sport_type": "Run",
                "start_date_local": f"{day}T06:00:00Z",
                "distance": 10000.0,
                "moving_time": 3600,
                "elapsed_time": 3700,
                "total_elevation_gain": 100.0,
            }
            activities.append(
                [
                    idx + 1,
                    day,
                    f"Run {idx + 1}",
                    "Run",
                    10000.0,
                    3600,
                    3700,
                    100.0,
                    json.dumps(summary),
                    "{}",
                    f"{day}T07:00:00Z",
                ]
            )
        conn.executemany(
            """
            INSERT INTO activities (
                id, activity_day, name, sport_type, distance, moving_time,
                elapsed_time, total_elevation_gain, summary_json, detail_json, synced_at
            ) VALUES (?, CAST(? AS DATE), ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            activities,
        )

        stream_rows = []
        for idx in range(ACTIVITY_COUNT):
            activity_id = idx + 1
            for minute in range(STREAM_POINTS_PER_ACTIVITY):
                values = {
                    "heartrate": 140 + (idx % 5),
                    "velocity_smooth": 3.0 + (minute * 0.05),
                    "altitude": 500.0 + minute,
                    "cadence": 85,
                    "latlng": [43.2, 76.9],
                    "grade_smooth": 1.0,
                }
                stream_rows.append(
                    [
                        activity_id,
                        minute * 60,
                        140 + (idx % 5),
                        3.0 + (minute * 0.05),
                        500.0 + minute,
                        85,
                        43.2,
                        76.9,
                        1.0,
                        3.1,
                        180.0,
                        1,
                        json.dumps(values),
                    ]
                )
        conn.executemany(
            """
            INSERT INTO streams (
                activity_id, time_offset, heartrate, velocity, altitude, cadence,
                lat, lng, grade, gap_speed, gap_distance, is_moving, values_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            stream_rows,
        )

        conn.execute(
            """
            INSERT INTO sync_log (
                id, timestamp, status, activities_seen, activities_new,
                streams_fetched, details_fetched, api_calls, error, kudos_fetched
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                1,
                "2026-02-12T08:00:00Z",
                "ok",
                ACTIVITY_COUNT,
                ACTIVITY_COUNT,
                ACTIVITY_COUNT,
                ACTIVITY_COUNT,
                5,
                None,
                0,
            ],
        )
        conn.execute(
            "INSERT INTO kudos (activity_id, firstname, lastname, fetched_at) VALUES (?, ?, ?, ?)",
            [1, "A", "B", "2026-02-12T08:00:00Z"],
        )
    finally:
        conn.close()
