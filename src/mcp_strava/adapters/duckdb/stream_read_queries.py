"""Read-only stream row queries for repository boundary checks."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from mcp_strava.adapters.duckdb.repository_utils import Row


class StreamReadRepository(Protocol):
    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]: ...


def activity_stream_rows(repo: StreamReadRepository, activity_id: int) -> list[dict[str, Any]]:
    return repo._fetchall(
        """
        SELECT activity_id, time_offset, heartrate, velocity, altitude,
               cadence, lat, lng, grade, gap_speed, gap_distance, is_moving, values_json
        FROM streams
        WHERE activity_id = ?
        ORDER BY time_offset ASC
        """,
        [activity_id],
    )
