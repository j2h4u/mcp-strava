"""Schema inventory and preflight/post-check helpers."""

from dataclasses import dataclass
from pathlib import Path
import sqlite3


REQUIRED_TABLES: tuple[str, ...] = (
    "activities",
    "streams",
    "athlete_zones",
    "sync_log",
    "kudos",
)

REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "activities": (
        "id",
        "date",
        "name",
        "sport_type",
        "distance",
        "moving_time",
        "elapsed_time",
        "total_elevation_gain",
        "summary_json",
        "detail_json",
        "synced_at",
    ),
    "streams": (
        "activity_id",
        "time_offset",
        "heartrate",
        "velocity",
        "altitude",
        "cadence",
        "lat",
        "lng",
        "grade",
        "gap_speed",
        "gap_distance",
        "is_moving",
        "latlng",
    ),
    "athlete_zones": ("id", "fetched_at", "zones_json"),
    "sync_log": (
        "id",
        "timestamp",
        "status",
        "activities_seen",
        "activities_new",
        "streams_fetched",
        "details_fetched",
        "api_calls",
        "error",
        "kudos_fetched",
    ),
    "kudos": ("activity_id", "firstname", "lastname", "fetched_at"),
}

REQUIRED_INDEXES: tuple[str, ...] = ("idx_streams_act",)


@dataclass(frozen=True)
class PreflightReport:
    path: Path
    user_version: int
    row_counts: dict[str, int]
    integrity_result: str


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _columns_for_table(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _indexes(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    return {row[0] for row in rows if row[0]}


def read_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def set_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version={int(version)}")


def integrity_check(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0]) if row else "unknown"


def row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in REQUIRED_TABLES:
        counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return counts


def validate_required_inventory(conn: sqlite3.Connection) -> None:
    for table in REQUIRED_TABLES:
        if not _table_exists(conn, table):
            raise RuntimeError(f"Missing required table: {table}")

    for table, required in REQUIRED_COLUMNS.items():
        actual = _columns_for_table(conn, table)
        missing = [col for col in required if col not in actual]
        if missing:
            raise RuntimeError(f"Missing required columns in {table}: {', '.join(missing)}")

    actual_indexes = _indexes(conn)
    for idx in REQUIRED_INDEXES:
        if idx not in actual_indexes:
            raise RuntimeError(f"Missing required index: {idx}")


def run_preflight_checks(db_path: str | Path) -> PreflightReport:
    path = Path(db_path)
    if not path.exists():
        raise RuntimeError(f"Expected mirror does not exist: {path}")

    conn = sqlite3.connect(str(path), check_same_thread=False)
    try:
        validate_required_inventory(conn)
        integrity = integrity_check(conn)
        if integrity.lower() != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
        return PreflightReport(
            path=path,
            user_version=read_user_version(conn),
            row_counts=row_counts(conn),
            integrity_result=integrity,
        )
    finally:
        conn.close()
