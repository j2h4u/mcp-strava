"""DuckDB storage adapter boundary."""

from mcp_strava.adapters.duckdb.connection import open_expected_mirror_db, open_fixture_db
from mcp_strava.adapters.duckdb.read_model_materializer import materialize_read_model
from mcp_strava.adapters.duckdb.repository import CURRENT_METRIC_VERSION, DuckDBRepository
from mcp_strava.settings import CANONICAL_DUCKDB_RUNTIME_PATH

__all__ = [
    "CANONICAL_DUCKDB_RUNTIME_PATH",
    "CURRENT_METRIC_VERSION",
    "DuckDBRepository",
    "materialize_read_model",
    "open_expected_mirror_db",
    "open_fixture_db",
]
