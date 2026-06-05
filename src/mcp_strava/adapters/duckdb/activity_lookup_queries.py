"""Activity lookup queries shared by application services."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from mcp_strava.adapters.duckdb.repository_utils import Row, as_int


class ActivityLookupRepository(Protocol):
    def _fetchone(self, sql: str, params: Iterable[object] | None = None) -> Row | None: ...


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
