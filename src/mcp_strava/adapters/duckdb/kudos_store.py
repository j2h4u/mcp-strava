"""Kudos mirror queries over the DuckDB repository connection boundary."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from mcp_strava.adapters.duckdb.repository_utils import Row, as_int


class KudosRepository(Protocol):
    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]: ...

    def _execute(self, sql: str, params: Iterable[object] | None = None) -> object: ...

    def _commit_if_standalone(self) -> None: ...


def list_kudos(repo: KudosRepository, limit: int = 100) -> list[dict[str, Any]]:
    return repo._fetchall(
        """
        SELECT activity_id, firstname, lastname, fetched_at
        FROM kudos
        ORDER BY fetched_at DESC
        LIMIT ?
        """,
        [limit],
    )


def kudos_for_activity(repo: KudosRepository, activity_id: int) -> list[dict[str, Any]]:
    return repo._fetchall(
        """
        SELECT activity_id, firstname, lastname, fetched_at
        FROM kudos
        WHERE activity_id = ?
        ORDER BY firstname, lastname
        """,
        [activity_id],
    )


def activities_missing_kudos(repo: KudosRepository, window_days: int | None = None) -> list[int]:
    """Activity ids that have kudos on Strava but none mirrored locally yet."""
    query = """
        SELECT a.id FROM activities a
        WHERE CAST(json_extract(a.summary_json, '$.kudos_count') AS INTEGER) > 0
          AND NOT EXISTS (SELECT 1 FROM kudos k WHERE k.activity_id = a.id)
    """
    params: list[object] = []
    if window_days is not None:
        query += " AND a.activity_day >= (CURRENT_DATE - (? * INTERVAL '1 day'))"
        params.append(window_days)
    query += " ORDER BY a.activity_day DESC"
    return [as_int(row["id"]) for row in repo._fetchall(query, params)]


def upsert_kudos(repo: KudosRepository, activity_id: int, firstname: str, lastname: str, fetched_at: str) -> None:
    repo._execute(
        """
        INSERT INTO kudos (activity_id, firstname, lastname, fetched_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(activity_id, firstname, lastname) DO UPDATE SET
          fetched_at = excluded.fetched_at
        """,
        [activity_id, firstname, lastname, fetched_at],
    )
    repo._commit_if_standalone()
