"""Stream coverage queries for mirror diagnostics and stream backfill planning."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Protocol, TypedDict

from mcp_strava.adapters.duckdb.repository_utils import Row, as_int


class StreamCoverageRepository(Protocol):
    def _fetchone(self, sql: str, params: Iterable[object] | None = None) -> Row | None: ...

    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]: ...

    def _scalar_int(self, sql: str, params: Iterable[object] | None = None) -> int: ...

    def _table_columns(self, table: str) -> set[str]: ...

    def _table_exists(self, table: str) -> bool: ...


class StreamChannelBackfillCandidate(TypedDict):
    activity_id: int
    missing_channels: list[str]
    metadata_missing: bool


def activities_missing_stream_channels(
    repo: StreamCoverageRepository,
    *,
    since: str | None = None,
    limit: int | None = None,
    requested_channels: Iterable[str],
) -> list[StreamChannelBackfillCandidate]:
    channel_list = list(requested_channels)
    rows = repo._fetchall(
        """
        SELECT a.id, a.date
        FROM activities a
        WHERE EXISTS (SELECT 1 FROM streams s WHERE s.activity_id = a.id)
          AND (? IS NULL OR a.activity_day >= CAST(? AS DATE))
        ORDER BY a.activity_day DESC, a.id DESC
        """,
        [since, since],
    )
    results: list[StreamChannelBackfillCandidate] = []
    for row in rows:
        if limit is not None and len(results) >= limit:
            break
        activity_id = as_int(row["id"])
        missing_channels: list[str] = []
        metadata_missing = False
        for channel in channel_list:
            meta = repo._fetchone(
                """
                SELECT status FROM stream_channels
                WHERE activity_id=? AND channel_key=?
                """,
                [activity_id, channel],
            )
            if meta is None:
                metadata_missing = True
                missing_channels.append(channel)
                continue
            status = meta["status"]
            if status in {"missing", "error"}:
                missing_channels.append(channel)
                continue
            if status == "unavailable":
                continue
            if status != "available":
                missing_channels.append(channel)
                continue
            if channel in {"distance", "watts", "temp"}:
                value_rows = repo._fetchall(
                    """
                    SELECT values_json
                    FROM streams
                    WHERE activity_id=?
                      AND values_json IS NOT NULL
                    """,
                    [activity_id],
                )
                if not any(
                    channel in (json.loads(str(item["values_json"])) if item["values_json"] else {})
                    for item in value_rows
                ):
                    missing_channels.append(channel)
        if missing_channels or metadata_missing:
            results.append(
                {
                    "activity_id": activity_id,
                    "missing_channels": sorted(set(missing_channels)),
                    "metadata_missing": metadata_missing,
                }
            )
    return results


def stream_channel_coverage(repo: StreamCoverageRepository) -> dict[str, int]:
    row = repo._fetchone(
        """
        SELECT
            COUNT(*) AS channels,
            COUNT(DISTINCT activity_id) AS activities_with_channel_metadata,
            SUM(CASE WHEN status='available' THEN 1 ELSE 0 END) AS available_channels,
            SUM(CASE WHEN status='unavailable' THEN 1 ELSE 0 END) AS unavailable_channels,
            SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS error_channels
        FROM stream_channels
        """
    )
    return {
        "channels": as_int(row["channels"]) if row else 0,
        "activities_with_channel_metadata": as_int(row["activities_with_channel_metadata"]) if row else 0,
        "available_channels": as_int(row["available_channels"]) if row else 0,
        "unavailable_channels": as_int(row["unavailable_channels"]) if row else 0,
        "error_channels": as_int(row["error_channels"]) if row else 0,
    }


def stream_table_columns(repo: StreamCoverageRepository) -> set[str]:
    """Column names present on the ``streams`` table."""
    return repo._table_columns("streams")


def mirror_table_exists(repo: StreamCoverageRepository, table: str) -> bool:
    """True when ``table`` exists in the mirror DB."""
    return repo._table_exists(table)


def count_activities(repo: StreamCoverageRepository) -> int:
    return repo._scalar_int("SELECT COUNT(*) FROM activities")


def count_activities_with_streams(repo: StreamCoverageRepository) -> int:
    return repo._scalar_int("SELECT COUNT(DISTINCT activity_id) FROM streams")


def count_stream_points(repo: StreamCoverageRepository) -> int:
    return repo._scalar_int("SELECT COUNT(*) FROM streams")


def count_stream_gps_points(repo: StreamCoverageRepository, *, has_latlng: bool) -> int:
    gps_where = "lat IS NOT NULL AND lng IS NOT NULL"
    if has_latlng:
        gps_where = f"({gps_where}) OR latlng IS NOT NULL"
    return repo._scalar_int(f"SELECT COUNT(*) FROM streams WHERE {gps_where}")


def count_activities_missing_channel_metadata(repo: StreamCoverageRepository) -> int:
    return repo._scalar_int(
        """
        SELECT COUNT(*)
        FROM (
            SELECT s.activity_id
            FROM streams s
            LEFT JOIN stream_channels c ON c.activity_id = s.activity_id
            GROUP BY s.activity_id
            HAVING COUNT(c.channel_key) = 0
        )
        """
    )


def count_streams_missing_extra_values(repo: StreamCoverageRepository, *, has_values_json: bool) -> int:
    if not has_values_json:
        return count_stream_points(repo)
    return repo._scalar_int("SELECT COUNT(*) FROM streams WHERE values_json IS NULL OR values_json = ''")
