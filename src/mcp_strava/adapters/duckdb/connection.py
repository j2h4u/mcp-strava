"""DuckDB connection policy with fail-closed expected DB open."""

from pathlib import Path

import duckdb


def open_expected_mirror_db(path: str | Path, read_only: bool = False):
    db_path = Path(path)
    if not db_path.exists():
        raise RuntimeError(f"Expected DuckDB mirror does not exist: {db_path}")
    return duckdb.connect(database=str(db_path), read_only=read_only)


def open_fixture_db(path: str | Path):
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(database=str(db_path), read_only=False)
