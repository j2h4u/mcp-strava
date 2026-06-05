"""Athlete zone persistence helpers over the DuckDB repository boundary."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from mcp_strava.adapters.duckdb.repository_utils import Row


class AthleteZoneRepository(Protocol):
    def _next_id(self, table: str) -> int: ...

    def _execute(self, sql: str, params: Iterable[object] | None = None) -> object: ...

    def _fetchone(self, sql: str, params: Iterable[object] | None = None) -> Row | None: ...

    def _commit_if_standalone(self) -> None: ...


def latest_athlete_zones(repo: AthleteZoneRepository) -> str | None:
    row = repo._fetchone("SELECT zones_json FROM athlete_zones ORDER BY fetched_at DESC LIMIT 1")
    return str(row["zones_json"]) if row else None


def insert_athlete_zones(repo: AthleteZoneRepository, fetched_at: str, zones_json: str) -> None:
    repo._execute(
        "INSERT INTO athlete_zones (id, fetched_at, zones_json) VALUES (?, ?, ?)",
        [repo._next_id("athlete_zones"), fetched_at, zones_json],
    )
    repo._commit_if_standalone()
