"""Sync log persistence helpers over the DuckDB repository connection boundary."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from mcp_strava.adapters.duckdb.repository_models import SyncLogRecord
from mcp_strava.adapters.duckdb.repository_utils import Row, as_int_opt, as_str_opt
from mcp_strava.types import RepositorySyncLogEntry


class SyncLogRepository(Protocol):
    def _next_id(self, table: str) -> int: ...

    def _execute(self, sql: str, params: Iterable[object] | None = None) -> object: ...

    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]: ...

    def _commit_if_standalone(self) -> None: ...


def append_sync_log(repo: SyncLogRepository, record: SyncLogRecord) -> None:
    repo._execute(
        """
        INSERT INTO sync_log (
            id, timestamp, status, activities_seen, activities_new,
            streams_fetched, details_fetched, api_calls, error, kudos_fetched
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            repo._next_id("sync_log"),
            record.timestamp,
            record.status,
            record.activities_seen,
            record.activities_new,
            record.streams_fetched,
            record.details_fetched,
            record.api_calls,
            record.error,
            record.kudos_fetched,
        ],
    )
    repo._commit_if_standalone()


def read_sync_log(repo: SyncLogRepository, limit: int = 20) -> list[RepositorySyncLogEntry]:
    rows = repo._fetchall(
        """
        SELECT timestamp, status, activities_seen, activities_new,
               streams_fetched, details_fetched, api_calls, error, kudos_fetched
        FROM sync_log
        ORDER BY id DESC
        LIMIT ?
        """,
        [limit],
    )
    return [
        RepositorySyncLogEntry(
            timestamp=str(row["timestamp"]),
            status=str(row["status"]),
            activities_seen=as_int_opt(row["activities_seen"]),
            activities_new=as_int_opt(row["activities_new"]),
            streams_fetched=as_int_opt(row["streams_fetched"]),
            details_fetched=as_int_opt(row["details_fetched"]),
            api_calls=as_int_opt(row["api_calls"]),
            error=as_str_opt(row["error"]),
            kudos_fetched=as_int_opt(row["kudos_fetched"]),
        )
        for row in rows
    ]
