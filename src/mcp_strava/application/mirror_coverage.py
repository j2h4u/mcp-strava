"""Aggregate mirror coverage reporting for admin CLI."""

from __future__ import annotations

from contextlib import nullcontext

from mcp_strava.adapters.duckdb.connection import MirrorConn
from mcp_strava.adapters.duckdb.repository import DuckDBRepository


def _stream_columns(conn) -> set[str]:
    rows = conn.execute("PRAGMA table_info('streams')").fetchall()
    return {str(row[1]) for row in rows}


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_name = ?
        LIMIT 1
        """,
        [table],
    ).fetchone()
    return row is not None


def get_mirror_coverage_service(*, connection=None) -> dict:
    conn_context = nullcontext(connection) if connection is not None else MirrorConn()
    with conn_context as conn:
        repo = DuckDBRepository.from_connection(conn)
        stream_columns = _stream_columns(conn)
        activities_total = int(conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0])
        activities_with_streams = int(conn.execute("SELECT COUNT(DISTINCT activity_id) FROM streams").fetchone()[0])
        stream_points = int(conn.execute("SELECT COUNT(*) FROM streams").fetchone()[0])
        gps_where = "lat IS NOT NULL AND lng IS NOT NULL"
        if "latlng" in stream_columns:
            gps_where = f"({gps_where}) OR latlng IS NOT NULL"
        gps_points = int(conn.execute(f"SELECT COUNT(*) FROM streams WHERE {gps_where}").fetchone()[0])
        channel_stats = repo.stream_channel_coverage()
        has_stream_channels = _table_exists(conn, "stream_channels")
        has_values_json_col = "values_json" in stream_columns

        if has_stream_channels:
            missing_metadata = int(
                conn.execute(
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
                ).fetchone()[0]
            )
        else:
            missing_metadata = activities_with_streams

        if has_values_json_col:
            missing_extra_values = int(
                conn.execute("SELECT COUNT(*) FROM streams WHERE values_json IS NULL OR values_json = ''").fetchone()[0]
            )
        else:
            missing_extra_values = stream_points
        stream_channel_backfill = repo.activities_missing_stream_channels(
            requested_channels=(
                "time",
                "distance",
                "heartrate",
                "velocity_smooth",
                "altitude",
                "cadence",
                "latlng",
                "grade_smooth",
                "grade_adjusted_speed",
                "grade_adjusted_distance",
                "moving",
                "watts",
                "temp",
            )
        )

    status_counts = {
        "available": channel_stats["available_channels"],
        "unavailable": channel_stats["unavailable_channels"],
        "error": channel_stats["error_channels"],
    }
    backfill_needed = (activities_with_streams > 0) and (missing_metadata > 0 or missing_extra_values > 0)

    return {
        "status": "ok",
        "activities_total": activities_total,
        "activities_with_streams": activities_with_streams,
        "stream_points": stream_points,
        "gps_points": gps_points,
        "channels": channel_stats["channels"],
        "channel_status_counts": status_counts,
        "activities_missing_channel_metadata": missing_metadata,
        "activities_missing_extra_values": missing_extra_values,
        "activities_with_missing_stream_channels": len(stream_channel_backfill),
        "backfill_needed": backfill_needed,
    }
