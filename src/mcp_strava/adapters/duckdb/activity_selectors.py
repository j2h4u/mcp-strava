"""Activity selection queries used by refresh backfill/sync workflows."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from mcp_strava.adapters.duckdb.activity_rows import to_activity_row
from mcp_strava.adapters.duckdb.hydrated_activity_sql import (
    activity_hydration_joins,
    hydrated_activity_group_by,
    hydrated_activity_select,
)
from mcp_strava.adapters.duckdb.repository_utils import Row
from mcp_strava.types import RepositoryActivityRow


class ActivitySelectorRepository(Protocol):
    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]: ...


def activities_missing_streams(
    repo: ActivitySelectorRepository, since: str | None = None
) -> list[RepositoryActivityRow]:
    rows = repo._fetchall(
        f"""
        SELECT {hydrated_activity_select()}
        FROM activities a
        {activity_hydration_joins()}
        LEFT JOIN streams s ON s.activity_id = a.id
        WHERE s.activity_id IS NULL
          AND (? IS NULL OR a.activity_day >= CAST(? AS DATE))
        GROUP BY {hydrated_activity_group_by()}
        ORDER BY a.activity_day DESC, a.id DESC
        """,
        [since, since],
    )
    return [to_activity_row(row) for row in rows]


def activities_missing_details(
    repo: ActivitySelectorRepository, since: str | None = None
) -> list[RepositoryActivityRow]:
    rows = repo._fetchall(
        f"""
        SELECT {hydrated_activity_select()}
        FROM activities a
        {activity_hydration_joins()}
        WHERE a.detail_json IS NULL
          AND detail_payload.activity_id IS NULL
          AND (? IS NULL OR a.activity_day >= CAST(? AS DATE))
        ORDER BY a.activity_day DESC, a.id DESC
        """,
        [since, since],
    )
    return [to_activity_row(row) for row in rows]
