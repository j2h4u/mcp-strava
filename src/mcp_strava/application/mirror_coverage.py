"""Aggregate mirror coverage reporting for admin CLI."""

from __future__ import annotations

from contextlib import nullcontext

from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.db import DbConn


def get_mirror_coverage_service(*, connection=None) -> dict:
    conn_context = nullcontext(connection) if connection is not None else DbConn()
    with conn_context as conn:
        repo = SQLiteRepository.from_connection(conn)
        activities_total = int(conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0])
        activities_with_streams = int(
            conn.execute("SELECT COUNT(DISTINCT activity_id) FROM streams").fetchone()[0]
        )
        stream_points = int(conn.execute("SELECT COUNT(*) FROM streams").fetchone()[0])
        gps_points = int(
            conn.execute(
                "SELECT COUNT(*) FROM streams WHERE (lat IS NOT NULL AND lng IS NOT NULL) OR latlng IS NOT NULL"
            ).fetchone()[0]
        )
        channel_stats = repo.stream_channel_coverage()
        has_stream_channels = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='stream_channels'"
        ).fetchone() is not None
        has_values_json = conn.execute("PRAGMA table_info(streams)").fetchall()
        has_values_json_col = any(col[1] == "values_json" for col in has_values_json)

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

    status_counts = {
        "available": channel_stats["available_channels"],
        "unavailable": channel_stats["unavailable_channels"],
        "error": channel_stats["error_channels"],
    }
    backfill_needed = (activities_with_streams > 0) and (
        missing_metadata > 0 or missing_extra_values > 0
    )

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
        "backfill_needed": backfill_needed,
    }
