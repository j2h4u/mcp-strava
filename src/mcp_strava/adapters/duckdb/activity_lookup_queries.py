"""Activity lookup queries shared by application services."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from mcp_strava.adapters.duckdb.activity_rows import to_activity_row
from mcp_strava.adapters.duckdb.hydrated_activity_sql import (
    activity_hydration_joins,
    hydrated_activity_select,
)
from mcp_strava.adapters.duckdb.repository_models import ActivityMaterializationSource
from mcp_strava.adapters.duckdb.repository_utils import Row, as_int
from mcp_strava.adapters.duckdb.repository_utils import placeholders as make_placeholders
from mcp_strava.types import RepositoryActivityRow


class ActivityLookupRepository(Protocol):
    def _fetchone(self, sql: str, params: Iterable[object] | None = None) -> Row | None: ...

    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]: ...


def recent_activities(repo: ActivityLookupRepository, limit: int = 15) -> list[RepositoryActivityRow]:
    rows = repo._fetchall(
        f"""
        SELECT {hydrated_activity_select()}
        FROM activities a
        {activity_hydration_joins()}
        ORDER BY a.activity_day DESC, a.id DESC
        LIMIT ?
        """,
        [limit],
    )
    return [to_activity_row(row) for row in rows]


def activity_by_id(repo: ActivityLookupRepository, activity_id: int) -> RepositoryActivityRow | None:
    row = repo._fetchone(
        f"""
        SELECT {hydrated_activity_select()}
        FROM activities a
        {activity_hydration_joins()}
        WHERE a.id = ?
        """,
        [activity_id],
    )
    return to_activity_row(row) if row else None


def activity_materialization_sources(
    repo: ActivityLookupRepository, activity_ids: Iterable[int]
) -> dict[int, ActivityMaterializationSource]:
    ids = sorted({int(activity_id) for activity_id in activity_ids})
    if not ids:
        return {}
    placeholders = make_placeholders(len(ids))
    rows = repo._fetchall(
        f"""
        SELECT {hydrated_activity_select()},
               s.source_hash, s.source_revision
        FROM activities a
        {activity_hydration_joins()}
        JOIN activity_source_state s ON s.activity_id = a.id
        WHERE a.id IN ({placeholders})
        """,
        ids,
    )
    sources: dict[int, ActivityMaterializationSource] = {}
    for row in rows:
        activity = to_activity_row(row)
        sources[activity.id] = ActivityMaterializationSource(
            activity=activity,
            source_hash=str(row["source_hash"]),
            source_revision=as_int(row["source_revision"]),
        )
    return sources


def latest_activity_at(repo: ActivityLookupRepository) -> str | None:
    row = repo._fetchone("SELECT MAX(activity_day) AS latest FROM activities")
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
