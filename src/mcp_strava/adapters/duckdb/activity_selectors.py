"""Activity selection queries used by refresh backfill/sync workflows."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from mcp_strava.adapters.duckdb.repository_utils import Row, as_float, as_int, as_str_opt
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


def to_activity_row(row: Row) -> RepositoryActivityRow:
    return RepositoryActivityRow(
        id=as_int(row["id"]),
        date=str(row["date"]),
        name=str(row["name"]),
        sport_type=str(row["sport_type"]),
        distance=as_float(row["distance"]),
        moving_time=as_int(row["moving_time"]),
        elapsed_time=as_int(row["elapsed_time"]),
        total_elevation_gain=as_float(row["total_elevation_gain"]),
        summary_json=as_str_opt(row["summary_json"]),
        detail_json=as_str_opt(row["detail_json"]),
        synced_at=as_str_opt(row["synced_at"]),
    )
