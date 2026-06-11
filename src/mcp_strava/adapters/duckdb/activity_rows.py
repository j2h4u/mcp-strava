"""Row mappers for activity records stored in DuckDB."""

from __future__ import annotations

from mcp_strava.adapters.duckdb.repository_utils import Row, as_float, as_int, as_str_opt
from mcp_strava.types import RepositoryActivityRow


def to_activity_row(row: Row) -> RepositoryActivityRow:
    return RepositoryActivityRow(
        id=as_int(row["id"]),
        activity_day=str(row["activity_day"]),
        name=str(row["name"]),
        sport_type=str(row["sport_type"]),
        distance=as_float(row["distance"]),
        moving_time=as_int(row["moving_time"]),
        elapsed_time=as_int(row["elapsed_time"]),
        total_elevation_gain=as_float(row["total_elevation_gain"]),
        summary_json=as_str_opt(row["summary_json"]),
        detail_json=as_str_opt(row["detail_json"]),
        synced_at=as_str_opt(row["synced_at"]),
    )
