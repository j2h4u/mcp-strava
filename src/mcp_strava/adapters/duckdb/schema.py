"""DuckDB schema inventory for the primary Strava mirror."""

from __future__ import annotations

from mcp_strava.adapters.duckdb.schema_inventory import DATE_COLUMNS, DUCKDB_TABLES, DUCKDB_VIEWS
from mcp_strava.adapters.duckdb.schema_tables import DUCKDB_SCHEMA_SQL
from mcp_strava.adapters.duckdb.schema_views import DUCKDB_AGGREGATE_VIEW_SQL, create_aggregate_views
from mcp_strava.metric_registry import activity_metric_facts_table_sql

__all__ = [
    "DATE_COLUMNS",
    "DUCKDB_AGGREGATE_VIEW_SQL",
    "DUCKDB_SCHEMA_SQL",
    "DUCKDB_TABLES",
    "DUCKDB_VIEWS",
    "activity_metric_facts_table_sql",
    "create_aggregate_views",
    "create_schema",
]


def create_schema(conn) -> None:
    conn.execute(DUCKDB_SCHEMA_SQL)
    create_aggregate_views(conn)
