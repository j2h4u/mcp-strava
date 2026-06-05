"""Activity lookup queries shared by application services."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from mcp_strava.adapters.duckdb.activity_rows import to_activity_row
from mcp_strava.adapters.duckdb.repository_utils import Row, as_int
from mcp_strava.types import RepositoryActivityRow


class ActivityLookupRepository(Protocol):
    def _fetchone(self, sql: str, params: Iterable[object] | None = None) -> Row | None: ...

    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]: ...


def recent_activities(repo: ActivityLookupRepository, limit: int = 15) -> list[RepositoryActivityRow]:
    rows = repo._fetchall(
        """
        SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
               total_elevation_gain, summary_json, detail_json, synced_at
        FROM activities
        ORDER BY activity_day DESC, id DESC
        LIMIT ?
        """,
        [limit],
    )
    return [to_activity_row(row) for row in rows]


def activity_by_id(repo: ActivityLookupRepository, activity_id: int) -> RepositoryActivityRow | None:
    row = repo._fetchone(
        """
        SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
               total_elevation_gain, summary_json, detail_json, synced_at
        FROM activities
        WHERE id = ?
        """,
        [activity_id],
    )
    return to_activity_row(row) if row else None


def latest_activity_at(repo: ActivityLookupRepository) -> str | None:
    row = repo._fetchone("SELECT MAX(date) AS latest FROM activities")
    return str(row["latest"]) if row and row["latest"] else None


def latest_activity_id(repo: ActivityLookupRepository) -> int | None:
    row = repo._fetchone(
        """
        SELECT id
        FROM activities
        ORDER BY activity_day DESC, id DESC
        LIMIT 1
        """
    )
    return as_int(row["id"]) if row and row["id"] is not None else None
