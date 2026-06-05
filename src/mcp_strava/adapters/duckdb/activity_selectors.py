"""Activity selection queries used by refresh backfill/sync workflows."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from mcp_strava.adapters.duckdb.activity_rows import to_activity_row
from mcp_strava.adapters.duckdb.repository_utils import Row
from mcp_strava.types import RepositoryActivityRow


class ActivitySelectorRepository(Protocol):
    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]: ...


def activities_missing_streams(
    repo: ActivitySelectorRepository, since: str | None = None
) -> list[RepositoryActivityRow]:
    rows = repo._fetchall(
        """
        SELECT a.id, a.date, a.name, a.sport_type, a.distance, a.moving_time,
               a.elapsed_time, a.total_elevation_gain, a.summary_json,
               a.detail_json, a.synced_at
        FROM activities a
        LEFT JOIN streams s ON s.activity_id = a.id
        WHERE s.activity_id IS NULL
          AND (? IS NULL OR a.activity_day >= CAST(? AS DATE))
        GROUP BY a.id, a.date, a.name, a.sport_type, a.distance, a.moving_time,
                 a.elapsed_time, a.total_elevation_gain, a.summary_json,
                 a.detail_json, a.synced_at, a.activity_day
        ORDER BY a.activity_day DESC, a.id DESC
        """,
        [since, since],
    )
    return [to_activity_row(row) for row in rows]


def activities_missing_details(
    repo: ActivitySelectorRepository, since: str | None = None
) -> list[RepositoryActivityRow]:
    rows = repo._fetchall(
        """
        SELECT id, date, name, sport_type, distance, moving_time,
               elapsed_time, total_elevation_gain, summary_json,
               detail_json, synced_at
        FROM activities
        WHERE detail_json IS NULL
          AND (? IS NULL OR activity_day >= CAST(? AS DATE))
        ORDER BY activity_day DESC, id DESC
        """,
        [since, since],
    )
    return [to_activity_row(row) for row in rows]
