"""SQLite safety and migration adapter APIs."""

from mcp_strava.adapters.sqlite.backup import create_timestamped_backup, enforce_backup_retention
from mcp_strava.adapters.sqlite.connection import create_empty_mirror, open_expected_mirror_db
from mcp_strava.adapters.sqlite.migrations import (
    ParitySnapshot,
    evaluate_parity,
    run_migrations,
    run_preflight,
)

__all__ = [
    "create_empty_mirror",
    "open_expected_mirror_db",
    "create_timestamped_backup",
    "enforce_backup_retention",
    "run_preflight",
    "run_migrations",
    "ParitySnapshot",
    "evaluate_parity",
]
