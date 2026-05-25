"""DuckDB storage adapter boundary."""

from mcp_strava.adapters.duckdb.connection import open_expected_mirror_db, open_fixture_db
from mcp_strava.adapters.duckdb.migrations import (
    CANONICAL_DUCKDB_RUNTIME_PATH,
    DuckDBCutoverReport,
    DuckDBMigrationError,
    run_duckdb_cutover,
)

__all__ = [
    "CANONICAL_DUCKDB_RUNTIME_PATH",
    "DuckDBCutoverReport",
    "DuckDBMigrationError",
    "open_expected_mirror_db",
    "open_fixture_db",
    "run_duckdb_cutover",
]
