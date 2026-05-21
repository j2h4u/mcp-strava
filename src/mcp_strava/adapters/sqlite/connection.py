"""SQLite connection policy with fail-closed expected DB open."""

from pathlib import Path
import sqlite3


def _apply_connection_pragmas(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    conn.execute("PRAGMA busy_timeout=5000")


def open_expected_mirror_db(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    uri = f"file:{db_path}?mode=rw"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    _apply_connection_pragmas(conn)
    return conn


def open_fixture_db(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(Path(path)), check_same_thread=False)
    _apply_connection_pragmas(conn)
    return conn


def create_empty_mirror(path: str | Path) -> None:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.close()
