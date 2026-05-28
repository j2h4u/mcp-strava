"""DuckDB connection policy with fail-closed expected DB open."""

from pathlib import Path
from threading import RLock

import duckdb

_DUCKDB_PROCESS_LOCK = RLock()


class MirrorDbLocked(RuntimeError):
    """Raised when the DuckDB mirror file is held by another process (the owner)."""


def duckdb_process_lock() -> RLock:
    return _DUCKDB_PROCESS_LOCK


def _connect_or_translate_lock(path: Path, *, read_only: bool):
    try:
        return duckdb.connect(database=str(path), read_only=read_only)
    except duckdb.IOException as exc:
        if "Conflicting lock" in str(exc):
            raise MirrorDbLocked(
                f"DuckDB mirror is locked by another process: {path}"
            ) from exc
        raise


def open_expected_mirror_db(path: str | Path, read_only: bool = False):
    db_path = Path(path)
    if not db_path.exists():
        raise RuntimeError(f"Expected DuckDB mirror does not exist: {db_path}")
    return _connect_or_translate_lock(db_path, read_only=read_only)


def open_fixture_db(path: str | Path):
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return _connect_or_translate_lock(db_path, read_only=False)
