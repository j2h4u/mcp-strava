"""Stream row and stream-channel write repository methods."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Protocol, TypeVar

from mcp_strava.adapters.duckdb.connection import DuckDBConn
from mcp_strava.adapters.duckdb.repository_utils import Row

# Stream-row insert column order (must match the streams table) and the per-statement
# row cap for batched multi-row INSERTs in _insert_stream_rows. See that method for why.
_STREAM_INSERT_COLUMNS = (
    "activity_id",
    "time_offset",
    "heartrate",
    "velocity",
    "altitude",
    "cadence",
    "lat",
    "lng",
    "grade",
    "gap_speed",
    "gap_distance",
    "is_moving",
    "values_json",
)
_STREAM_INSERT_STMT_ROWS = 250


T = TypeVar("T")


class _StreamWriteRepositoryHost(Protocol):
    conn: DuckDBConn

    def begin(self) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def _execute(self, sql: str, params: Iterable[object] | None = None) -> object: ...

    def _fetchone(self, sql: str, params: Iterable[object] | None = None) -> Row | None: ...

    def _now_iso(self) -> str: ...

    def current_metric_version(self) -> int: ...

    def update_activity_source_state_and_enqueue_dirty(
        self,
        activity_id: int,
        *,
        reason: str = "source_changed",
        metric_version: int,
        queued_at: str | None = None,
    ) -> bool: ...


class StreamWriteRepositoryMixin(_StreamWriteRepositoryHost):
    def insert_stream_rows_chunked(
        self,
        activity_id: int,
        rows: Iterable[dict],
        chunk_size: int = 5000,
    ) -> int:
        payload = list(rows)
        total = len(payload)
        if total == 0:
            return 0
        self.begin()
        try:
            self._insert_stream_rows(activity_id, payload, chunk_size)
            self.update_activity_source_state_and_enqueue_dirty(
                activity_id, metric_version=self.current_metric_version()
            )
        except Exception:
            self.rollback()
            raise
        self.commit()
        return total

    def replace_stream_rows_chunked(
        self,
        activity_id: int,
        rows: Iterable[dict],
        chunk_size: int = 5000,
    ) -> int:
        payload = list(rows)
        if not payload:
            return 0
        self.begin()
        try:
            self._execute("DELETE FROM streams WHERE activity_id = ?", [activity_id])
            self._insert_stream_rows(activity_id, payload, chunk_size)
            self.update_activity_source_state_and_enqueue_dirty(
                activity_id, metric_version=self.current_metric_version()
            )
        except Exception:
            self.rollback()
            raise
        self.commit()
        return len(payload)

    def _insert_stream_rows(self, activity_id: int, rows: list[dict], chunk_size: int) -> None:
        # DuckDB is columnar: a per-row ``executemany`` — and the never-firing
        # ``ON CONFLICT DO UPDATE`` this used to carry — runs ~3.5x slower than batched
        # multi-row INSERTs. Every caller writes a clean slate (replace_* DELETE the
        # activity's rows first; insert_stream_rows_chunked targets a fresh activity), so a
        # plain INSERT is correct and a genuine (activity_id, time_offset) duplicate SHOULD
        # fail loudly rather than silently upsert. The per-statement row count is capped
        # (not the caller's chunk_size) because DuckDB parses the VALUES literal and that
        # cost grows with the placeholder count; 250 rows stays one statement for
        # test-size blocks while keeping long rides off the quadratic-parse tail.
        columns = ", ".join(_STREAM_INSERT_COLUMNS)
        placeholder = "(" + ", ".join(["?"] * len(_STREAM_INSERT_COLUMNS)) + ")"
        step = min(chunk_size, _STREAM_INSERT_STMT_ROWS)
        for start in range(0, len(rows), step):
            chunk = rows[start : start + step]
            params: list[object] = []
            for row in chunk:
                params.extend(
                    (
                        activity_id,
                        row["time_offset"],
                        row.get("heartrate"),
                        row.get("velocity"),
                        row.get("altitude"),
                        row.get("cadence"),
                        row.get("lat"),
                        row.get("lng"),
                        row.get("grade"),
                        row.get("gap_speed"),
                        row.get("gap_distance"),
                        bool(row["is_moving"]) if row.get("is_moving") is not None else None,
                        row.get("values_json"),
                    )
                )
            values_clause = ", ".join([placeholder] * len(chunk))
            self._execute(f"INSERT INTO streams ({columns}) VALUES {values_clause}", params)

    def upsert_stream_channel_metadata(
        self,
        activity_id: int,
        channel_key: str,
        original_size: int | None,
        resolution: str | None,
        series_type: str | None,
        fetched_at: str | None,
        batch_id: str | None,
        status: str,
        error: str | None,
        commit: bool = True,
    ) -> None:
        if commit:
            self.begin()
        try:
            self._execute(
                """
                INSERT INTO stream_channels (
                    activity_id, channel_key, original_size, resolution, series_type,
                    fetched_at, batch_id, status, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(activity_id, channel_key) DO UPDATE SET
                    original_size=excluded.original_size,
                    resolution=excluded.resolution,
                    series_type=excluded.series_type,
                    fetched_at=excluded.fetched_at,
                    batch_id=excluded.batch_id,
                    status=excluded.status,
                    error=excluded.error
                """,
                [
                    activity_id,
                    channel_key,
                    original_size,
                    resolution,
                    series_type,
                    fetched_at or self._now_iso(),
                    batch_id,
                    status,
                    error,
                ],
            )
            if commit:
                self.update_activity_source_state_and_enqueue_dirty(
                    activity_id, metric_version=self.current_metric_version()
                )
        except Exception:
            if commit:
                self.rollback()
            raise
        if commit:
            self.commit()

    def replace_stream_rows_and_channel_metadata(
        self,
        activity_id: int,
        rows: Iterable[dict],
        metadata: Iterable[dict],
        chunk_size: int = 5000,
    ) -> int:
        payload = list(rows)
        self.begin()
        try:
            self._execute("DELETE FROM streams WHERE activity_id = ?", [activity_id])
            self._execute("DELETE FROM stream_channels WHERE activity_id = ?", [activity_id])
            self._insert_stream_rows(activity_id, payload, chunk_size)
            for item in metadata:
                self.upsert_stream_channel_metadata(
                    activity_id=activity_id,
                    channel_key=item["channel_key"],
                    original_size=item.get("original_size"),
                    resolution=item.get("resolution"),
                    series_type=item.get("series_type"),
                    fetched_at=item.get("fetched_at"),
                    batch_id=item.get("batch_id"),
                    status=item.get("status", "available"),
                    error=item.get("error"),
                    commit=False,
                )
            self.update_activity_source_state_and_enqueue_dirty(
                activity_id, metric_version=self.current_metric_version()
            )
        except Exception:
            self.rollback()
            raise
        self.commit()
        return len(payload)

    def merge_stream_channel_values(
        self,
        activity_id: int,
        rows: Iterable[dict],
        metadata: Iterable[dict],
        missing_channel_keys: Iterable[str],
    ) -> int:
        payload = list(rows)
        self.begin()
        try:
            for row in payload:
                if "time_offset" not in row:
                    continue
                existing = self._fetchone(
                    "SELECT values_json FROM streams WHERE activity_id=? AND time_offset=?",
                    [activity_id, row["time_offset"]],
                )
                if existing is None:
                    continue
                existing_map = json.loads(str(existing["values_json"])) if existing.get("values_json") else {}
                values_map = existing_map | (row.get("values") or {})
                self._execute(
                    "UPDATE streams SET values_json=? WHERE activity_id=? AND time_offset=?",
                    [json.dumps(values_map, ensure_ascii=True), activity_id, row["time_offset"]],
                )
            for channel_key in missing_channel_keys:
                self._execute(
                    """
                    INSERT INTO stream_channels (activity_id, channel_key, fetched_at, status)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(activity_id, channel_key) DO UPDATE SET status=excluded.status
                    """,
                    [activity_id, channel_key, self._now_iso(), "unavailable"],
                )
            for item in metadata:
                self.upsert_stream_channel_metadata(
                    activity_id=activity_id,
                    channel_key=item["channel_key"],
                    original_size=item.get("original_size"),
                    resolution=item.get("resolution"),
                    series_type=item.get("series_type"),
                    fetched_at=item.get("fetched_at"),
                    batch_id=item.get("batch_id"),
                    status=item.get("status", "available"),
                    error=item.get("error"),
                    commit=False,
                )
            self.update_activity_source_state_and_enqueue_dirty(
                activity_id, metric_version=self.current_metric_version()
            )
        except Exception:
            self.rollback()
            raise
        self.commit()
        return len(payload)
