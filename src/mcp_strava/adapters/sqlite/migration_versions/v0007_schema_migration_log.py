"""Add applied-migration audit log."""

from __future__ import annotations

import sqlite3

from mcp_strava.adapters.sqlite.schema import set_user_version

VERSION = 7
NAME = "schema_migration_log"


def apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migration_log (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            checksum TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migration_log (version, name, applied_at, checksum)
        VALUES
            (1, 'legacy_inline_v1', datetime('now'), 'legacy-inline'),
            (2, 'legacy_inline_v2', datetime('now'), 'legacy-inline'),
            (3, 'legacy_inline_v3', datetime('now'), 'legacy-inline'),
            (4, 'legacy_inline_v4', datetime('now'), 'legacy-inline'),
            (5, 'legacy_inline_v5', datetime('now'), 'legacy-inline'),
            (6, 'legacy_inline_v6', datetime('now'), 'legacy-inline')
        """
    )
    set_user_version(conn, VERSION)
