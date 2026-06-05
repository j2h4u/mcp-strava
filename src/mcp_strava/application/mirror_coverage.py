"""Aggregate mirror coverage reporting for admin CLI."""

from __future__ import annotations

from contextlib import nullcontext

from mcp_strava.adapters.duckdb.connection import MirrorConn
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.duckdb.stream_coverage_queries import (
    activities_missing_stream_channels,
    count_activities,
    count_activities_missing_channel_metadata,
    count_activities_with_streams,
    count_stream_gps_points,
    count_stream_points,
    count_streams_missing_extra_values,
    mirror_table_exists,
    stream_channel_coverage,
    stream_table_columns,
)

# Cap the per-activity backfill detail so the report stays bounded on large mirrors.
_BACKFILL_SAMPLE_LIMIT = 20


def get_mirror_coverage_service(*, connection=None) -> dict:
    conn_context = nullcontext(connection) if connection is not None else MirrorConn()
    with conn_context as conn:
        repo = DuckDBRepository.from_connection(conn)
        stream_columns = stream_table_columns(repo)
        has_latlng = "latlng" in stream_columns
        has_values_json_col = "values_json" in stream_columns

        activities_total = count_activities(repo)
        activities_with_streams = count_activities_with_streams(repo)
        stream_points = count_stream_points(repo)
        gps_points = count_stream_gps_points(repo, has_latlng=has_latlng)
        channel_stats = stream_channel_coverage(repo)
        has_stream_channels = mirror_table_exists(repo, "stream_channels")

        if has_stream_channels:
            missing_metadata = count_activities_missing_channel_metadata(repo)
        else:
            missing_metadata = activities_with_streams

        missing_extra_values = count_streams_missing_extra_values(repo, has_values_json=has_values_json_col)

        stream_channel_backfill = activities_missing_stream_channels(
            repo,
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
            ),
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
        # Surface *which* activities (and channels) need backfill, not just the count, so an
        # operator can act without a separate DB query. Bounded sample, newest-first.
        "stream_channel_backfill_sample": [
            {"activity_id": item["activity_id"], "missing_channels": item["missing_channels"]}
            for item in stream_channel_backfill[:_BACKFILL_SAMPLE_LIMIT]
        ],
        "backfill_needed": backfill_needed,
    }
