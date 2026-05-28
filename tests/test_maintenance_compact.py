from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from tests._fixtures_duckdb import ACTIVITY_COUNT, create_fixture_db

from mcp_strava.adapters.duckdb.connection import MirrorDbLocked
from mcp_strava.maintenance.compact import compact_database, humanize_bytes


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


def test_compact_translates_conflicting_lock_to_mirror_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A real running owner holds a cross-process writer lock; DuckDB surfaces
    # that as an IOException "Conflicting lock ... in PID N" (verified in task
    # 11). That condition can't be reproduced in-process, so inject the exact
    # exception shape and assert compact translates it to MirrorDbLocked.
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

    with pytest.raises(MirrorDbLocked, match="locked by another process"):
        compact_database(db)
    # The failed attempt must not leave a half-written scratch file behind.
    assert not list(tmp_path.glob("*.compact-*.duckdb"))


def test_admin_compact_cli_invokes_compact_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import mcp_strava.cli as cli

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

    monkeypatch.setattr(cli, "compact_database", fake_compact, raising=False)
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(database_path=db))
    monkeypatch.setattr(sys, "argv", ["mcp_strava", "admin", "compact", "--no-backup", "--json"])

    cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["reclaimed"] == "624 B"
    assert calls == [{"db_path": db, "backup": False}]
