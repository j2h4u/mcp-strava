from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from mcp_strava.adapters.duckdb.connection import MirrorDbLockedError
from mcp_strava.maintenance.compact import compact_database, humanize_bytes, storage_stats
from tests._fixtures_duckdb import ACTIVITY_COUNT, create_fixture_db

_DB_SIZE_COLUMNS = (
    "database_name",
    "database_size",
    "block_size",
    "total_blocks",
    "used_blocks",
    "free_blocks",
    "wal_size",
    "memory_usage",
    "memory_limit",
)


class _FakeDbSizeConn:
    """Stands in for a DuckDB connection answering `PRAGMA database_size`."""

    def __init__(self, *, block_size: int, total_blocks: int, free_blocks: int) -> None:
        self._row = (
            "mirror",
            "n/a",
            block_size,
            total_blocks,
            total_blocks - free_blocks,
            free_blocks,
            "0 bytes",
            "0 bytes",
            "0 bytes",
        )
        self.description = [(name,) for name in _DB_SIZE_COLUMNS]

    def execute(self, _sql: str):
        return self

    def fetchone(self):
        return self._row


@pytest.mark.parametrize(
    ("num", "expected"),
    [
        (0, "0 B"),
        (512, "512 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (102_400, "100.0 KB"),
        (1024 * 1024, "1.0 MB"),
        (765_000_000, "729.6 MB"),
        (5 * 1024**3, "5.0 GB"),
        (3 * 1024**4, "3.0 TB"),
        (-1024, "-1.0 KB"),
    ],
)
def test_humanize_bytes_scales_unit_to_magnitude(num: int, expected: str) -> None:
    assert humanize_bytes(num) == expected


def _activity_count(db_path: Path) -> int:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        return conn.execute("SELECT count(*) FROM activities").fetchone()[0]
    finally:
        conn.close()


def test_compact_preserves_data_and_keeps_backup(tmp_path: Path) -> None:
    db = tmp_path / "strava.duckdb"
    create_fixture_db(db)
    assert _activity_count(db) == ACTIVITY_COUNT

    result = compact_database(db, backup=True)

    assert result["status"] == "ok"
    assert result["db_path"] == str(db)
    for key in ("size_before", "size_after", "reclaimed", "backup_path"):
        assert key in result
    # Data survives the rewrite-and-swap.
    assert _activity_count(db) == ACTIVITY_COUNT
    # Backup is a real, separate file alongside the mirror.
    backup = Path(result["backup_path"])
    assert backup.exists() and backup != db
    assert _activity_count(backup) == ACTIVITY_COUNT


def test_compact_carries_catalog_views(tmp_path: Path) -> None:
    db = tmp_path / "strava.duckdb"
    create_fixture_db(db)

    compact_database(db, backup=False)

    conn = duckdb.connect(str(db), read_only=True)
    try:
        # View from the schema must come across with the catalog and stay queryable.
        conn.execute("SELECT count(*) FROM v_activity_aggregate_facts").fetchone()
    finally:
        conn.close()


def test_compact_without_backup_leaves_no_backup_file(tmp_path: Path) -> None:
    db = tmp_path / "strava.duckdb"
    create_fixture_db(db)

    result = compact_database(db, backup=False)

    assert result["backup_path"] is None
    assert not list(tmp_path.glob("*.pre-compact-*.duckdb"))
    # No leftover compaction scratch file either.
    assert not list(tmp_path.glob("*.compact-*.duckdb"))


def test_compact_missing_mirror_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="does not exist"):
        compact_database(tmp_path / "absent.duckdb")


def test_compact_translates_conflicting_lock_to_mirror_locked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A real running owner holds a cross-process writer lock; DuckDB surfaces
    # that as an IOException "Conflicting lock ... in PID N" (verified in task
    # 11). That condition can't be reproduced in-process, so inject the exact
    # exception shape and assert compact translates it to MirrorDbLockedError.
    db = tmp_path / "strava.duckdb"
    create_fixture_db(db)

    import mcp_strava.maintenance.compact as compact_mod

    class _LockedConn:
        def execute(self, sql: str):
            if "ATTACH" in sql and "READ_ONLY" in sql:
                raise duckdb.IOException("Conflicting lock is held in PID 1")
            return self

        def close(self) -> None:
            return None

    monkeypatch.setattr(compact_mod.duckdb, "connect", lambda *_a, **_k: _LockedConn())

    with pytest.raises(MirrorDbLockedError, match="locked by another process"):
        compact_database(db)
    # The failed attempt must not leave a half-written scratch file behind.
    assert not list(tmp_path.glob("*.compact-*.duckdb"))


def test_admin_compact_cli_invokes_compact_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import mcp_strava.cli as cli
    import mcp_strava.cli_admin as cli_admin

    db = tmp_path / "strava.duckdb"
    calls: list[dict] = []

    def fake_compact(db_path, *, backup):
        calls.append({"db_path": db_path, "backup": backup})
        return {
            "status": "ok",
            "db_path": str(db_path),
            "size_before": "1.0 KB",
            "size_after": "400 B",
            "reclaimed": "624 B",
            "backup_path": None,
        }

    monkeypatch.setattr(cli_admin, "compact_database", fake_compact)
    monkeypatch.setattr(cli_admin, "get_settings", lambda: SimpleNamespace(database_path=db))
    monkeypatch.setattr(sys, "argv", ["mcp_strava", "admin", "compact", "--no-backup", "--json"])

    cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["reclaimed"] == "624 B"
    assert calls == [{"db_path": db, "backup": False}]


def test_storage_stats_clean_fixture_reports_no_reclaimable(tmp_path: Path) -> None:
    db = tmp_path / "strava.duckdb"
    create_fixture_db(db)

    conn = duckdb.connect(str(db), read_only=True)
    try:
        stats = storage_stats(conn)
    finally:
        conn.close()

    # A freshly written file has no freed blocks.
    assert stats["reclaimable_pct"] == 0.0
    assert stats["compaction_recommended"] is False
    assert "compaction not needed" in stats["message"]
    assert stats["file_size"].endswith(("KB", "MB"))
    # Raw block counts for diagnosis/delta.
    assert stats["free_blocks"] == 0
    assert stats["total_blocks"] > 0


def test_storage_stats_recommends_compaction_above_threshold() -> None:
    # 40 of 100 blocks free => 40% reclaimable, over the 25% threshold.
    conn = _FakeDbSizeConn(block_size=262_144, total_blocks=100, free_blocks=40)

    stats = storage_stats(conn)

    assert stats["reclaimable_pct"] == 40.0
    assert stats["compaction_recommended"] is True
    assert "just admin compact" in stats["message"]


def test_storage_stats_below_threshold_does_not_recommend() -> None:
    # 10 of 100 blocks free => 10%, under the threshold.
    conn = _FakeDbSizeConn(block_size=262_144, total_blocks=100, free_blocks=10)

    stats = storage_stats(conn)

    assert stats["reclaimable_pct"] == 10.0
    assert stats["compaction_recommended"] is False
    assert "compaction not needed" in stats["message"]
