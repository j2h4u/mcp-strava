"""DuckDB connection policy with fail-closed expected DB open."""

import sys
import threading
from pathlib import Path
from threading import RLock

import duckdb

from mcp_strava.settings import get_settings

# The concrete DuckDB connection type. Carrying it through every helper (instead
# of a bare ``Any``) is what lets the row-fetch chain — ``conn.execute(...)
# .fetchall()`` / ``.description`` — type as ``list[tuple[Any, ...]]`` and the
# fully-typed description tuples, narrowing the unavoidable ``Any`` down to just
# the individual cell values rather than the whole connection surface.
DuckDBConn = duckdb.DuckDBPyConnection

_DUCKDB_PROCESS_LOCK = RLock()


class MirrorDbLocked(RuntimeError):
    """Raised when the DuckDB mirror file is held by another process (the owner)."""


def duckdb_process_lock() -> RLock:
    return _DUCKDB_PROCESS_LOCK


def _connect_or_translate_lock(path: Path, *, read_only: bool) -> DuckDBConn:
    try:
        return duckdb.connect(database=str(path), read_only=read_only)
    except duckdb.IOException as exc:
        if "Conflicting lock" in str(exc):
            raise MirrorDbLocked(f"DuckDB mirror is locked by another process: {path}") from exc
        raise


def open_expected_mirror_db(path: str | Path, read_only: bool = False) -> DuckDBConn:
    db_path = Path(path)
    if not db_path.exists():
        raise RuntimeError(f"Expected DuckDB mirror does not exist: {db_path}")
    return _connect_or_translate_lock(db_path, read_only=read_only)


def open_fixture_db(path: str | Path) -> DuckDBConn:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return _connect_or_translate_lock(db_path, read_only=False)


# ---------------------------------------------------------------------------
# Connection-lifetime helpers (migrated from db.py — D-01/D-02/D-03)
# ---------------------------------------------------------------------------


def _db_path() -> str:
    return str(get_settings().database_path)


class MirrorConn:
    """Context manager for primary storage connections — auto-closes on exit.

    Renamed from DbConn (D-03). Opens via open_expected_mirror_db so the
    fail-closed expected-mirror check is always applied.
    """

    def __enter__(self) -> DuckDBConn:
        self.conn = open_expected_mirror_db(_db_path())
        return self.conn

    def __exit__(self, _exc_type: object, _exc_val: object, _exc_tb: object) -> None:
        self.conn.close()


# --- Thread-local read connection reuse ---
#
# Opening a fresh DuckDB connection per request costs ~25 ms (catalog attach),
# which dominated warm read latency. Read services reuse one connection per
# (thread, db path) instead. DuckDB caches the database instance by path within
# a process, so a persistent reader coexists with the refresh writer exactly as
# the previous open-per-call readers did — only the connection lifetime changes,
# not the in-process RLock or MVCC behaviour. Each FastMCP worker thread keeps
# its own connection, matching the single-owner / per-thread-connection model.

_thread_state = threading.local()


def _thread_read_connections() -> dict[str, DuckDBConn]:
    connections: dict[str, DuckDBConn] | None = getattr(_thread_state, "read_connections", None)
    if connections is None:
        connections = {}
        _thread_state.read_connections = connections
    return connections


def _close_safely(conn: DuckDBConn, *, context: str) -> None:
    try:
        conn.close()
    except Exception as exc:  # noqa: BLE001 - connection cleanup must not mask caller shutdown paths.
        print(
            f"duckdb connection close failed during {context}: {type(exc).__name__}: {str(exc)[:200]}",
            file=sys.stderr,
            flush=True,
        )


class ReadConn:
    """Thread-local reused read connection — opened once per (thread, db path).

    Not closed on normal exit, so repeated reads avoid connect/close overhead.
    On an error inside the ``with`` block the connection is evicted and closed
    so the next call reopens a clean one (a poisoned cached connection is a
    worse failure mode than the churn this removes). Use
    ``reset_thread_connections()`` for shutdown and per-test isolation.
    """

    def __enter__(self) -> DuckDBConn:
        self._path = _db_path()
        connections = _thread_read_connections()
        conn = connections.get(self._path)
        if conn is None:
            conn = open_expected_mirror_db(self._path)
            connections[self._path] = conn
        return conn

    def __exit__(self, exc_type: object, _exc_val: object, _exc_tb: object) -> bool:
        if exc_type is not None:
            conn = _thread_read_connections().pop(self._path, None)
            if conn is not None:
                _close_safely(conn, context="read connection eviction")
        return False


def reset_thread_connections() -> None:
    """Close and clear this thread's cached read connections (tests, shutdown)."""
    connections: dict[str, DuckDBConn] | None = getattr(_thread_state, "read_connections", None)
    if not connections:
        return
    for conn in list(connections.values()):
        _close_safely(conn, context="thread connection reset")
    connections.clear()
