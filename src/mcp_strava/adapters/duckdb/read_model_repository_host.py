"""Typed host contract for DuckDB read-model repository mixins."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, TypeVar

from mcp_strava.adapters.duckdb.connection import DuckDBConn
from mcp_strava.adapters.duckdb.repository_utils import Row

T = TypeVar("T")


class ReadModelRepositoryHost(Protocol):
    conn: DuckDBConn
    _read_model_enabled_cache: bool | None
    _current_metric_version_cache: int | None

    def _commit_if_standalone(self) -> None: ...

    def _execute(self, sql: str, params: Iterable[object] | None = None) -> object: ...

    def _fetchone(self, sql: str, params: Iterable[object] | None = None) -> Row | None: ...

    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]: ...

    @staticmethod
    def _one(row: Row | None) -> T | None: ...

    @staticmethod
    def _all(rows: list[Row]) -> list[T]: ...

    def _table_columns(self, table: str) -> set[str]: ...

    def _table_exists(self, table: str) -> bool: ...

    def _next_id(self, table: str) -> int: ...

    def _now_iso(self) -> str: ...
