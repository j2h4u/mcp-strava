import ast
import sqlite3
from pathlib import Path

import pytest

from mcp_strava.adapters.sqlite.connection import open_fixture_db
from mcp_strava.adapters.sqlite.schema import set_user_version


def _create_fixture_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            date TEXT, name TEXT, sport_type TEXT,
            distance REAL, moving_time INTEGER, elapsed_time INTEGER,
            total_elevation_gain REAL,
            summary_json TEXT, detail_json TEXT, synced_at TEXT
        );
        CREATE TABLE streams (
            activity_id INTEGER, time_offset INTEGER,
            heartrate INTEGER, velocity REAL, altitude REAL,
            cadence INTEGER, lat REAL, lng REAL, grade REAL,
            gap_speed REAL, gap_distance REAL, is_moving INTEGER, latlng TEXT,
            PRIMARY KEY (activity_id, time_offset)
        );
        CREATE INDEX idx_streams_act ON streams(activity_id);
        CREATE TABLE athlete_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT, zones_json TEXT
        );
        CREATE TABLE sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            activities_seen INTEGER,
            activities_new INTEGER,
            streams_fetched INTEGER,
            details_fetched INTEGER,
            api_calls INTEGER,
            error TEXT,
            kudos_fetched INTEGER
        );
        CREATE TABLE kudos (
            activity_id INTEGER NOT NULL,
            firstname TEXT NOT NULL DEFAULT '',
            lastname TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (activity_id, firstname, lastname)
        );
        """
    )
    set_user_version(conn, 1)
    conn.commit()
    conn.close()


def _guard_direct_sqlite_boundary() -> list[str]:
    repo_root = Path(__file__).resolve().parents[1]
    src_root = repo_root / "src" / "mcp_strava"
    violations: list[str] = []

    for py_file in src_root.rglob("*.py"):
        rel = py_file.relative_to(repo_root).as_posix()
        if rel.startswith("src/mcp_strava/adapters/sqlite/"):
            continue
        if rel == "src/mcp_strava/db.py":
            continue

        mod = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        sqlite_aliases = set()

        for node in ast.walk(mod):
            if isinstance(node, ast.Import):
                for name in node.names:
                    if name.name == "sqlite3":
                        sqlite_aliases.add(name.asname or "sqlite3")
            elif isinstance(node, ast.ImportFrom):
                if node.module == "sqlite3":
                    sqlite_aliases.add(node.module)
            elif isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
                    alias = fn.value.id
                    if alias in sqlite_aliases and fn.attr == "connect":
                        violations.append(f"{rel}:{node.lineno} direct sqlite connect")
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                alias = node.value.id
                if alias in sqlite_aliases and node.attr == "Connection":
                    violations.append(f"{rel}:{node.lineno} sqlite Connection reference")

        if rel == "src/mcp_strava/cli.py":
            tree = mod
            cmd_sql_ok = False
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name == "cmd_sql":
                    cmd_sql_ok = True
            if not cmd_sql_ok:
                violations.append("src/mcp_strava/cli.py missing cmd_sql allowlist target")

    return violations


def test_repository_connection_reports_wal_and_busy_timeout(tmp_path: Path) -> None:
    fixture = tmp_path / "repo.db"
    _create_fixture_db(fixture)

    with open_fixture_db(fixture) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]

    assert mode.lower() == "wal"
    assert int(busy) >= 5000


def test_repository_methods_cover_activity_stream_zone_kudos_and_synclog(tmp_path: Path) -> None:
    fixture = tmp_path / "repo.db"
    _create_fixture_db(fixture)

    from mcp_strava.adapters.sqlite.repository import SQLiteRepository

    with SQLiteRepository.from_path(fixture) as repo:
        repo.upsert_activity_summary(
            activity_id=1,
            date="2026-05-21T06:00:00Z",
            name="Morning Run",
            sport_type="Run",
            distance=10000.0,
            moving_time=3600,
            elapsed_time=3700,
            total_elevation_gain=120.0,
            summary_json="{}",
            synced_at="2026-05-21T07:00:00Z",
        )
        rows = repo.recent_activities(limit=5)
        assert rows and rows[0].id == 1

        repo.insert_stream_rows_chunked(
            1,
            [
                {
                    "time_offset": idx,
                    "heartrate": 145,
                    "velocity": 3.5,
                    "altitude": 100.0,
                    "cadence": 85,
                    "latlng": "[43.2,76.9]",
                    "grade": 1.0,
                    "gap_speed": 3.6,
                    "gap_distance": 10.0,
                    "is_moving": 1,
                }
                for idx in range(6001)
            ],
            chunk_size=5000,
        )

        stream_rows = repo.activity_stream_rows(1)
        assert len(stream_rows) == 6001

        repo.insert_athlete_zones("2026-05-21T07:00:00Z", "[]")
        assert repo.latest_athlete_zones() is not None

        repo.upsert_kudos(1, "A", "B", "2026-05-21T08:00:00Z")
        assert repo.list_kudos(limit=5)

        repo.append_sync_log(
            timestamp="2026-05-21T09:00:00Z",
            status="ok",
            activities_seen=1,
            activities_new=1,
            streams_fetched=1,
            details_fetched=1,
            api_calls=1,
            error=None,
            kudos_fetched=1,
        )
        assert repo.read_sync_log(limit=5)


def test_repository_module_does_not_call_strava_network(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture = tmp_path / "repo.db"
    _create_fixture_db(fixture)

    import mcp_strava.db as legacy_db

    def _boom(*_args, **_kwargs):
        raise AssertionError("network auth/api must not be touched by repository tests")

    monkeypatch.setattr(legacy_db, "api_request", _boom)
    monkeypatch.setattr(legacy_db, "refresh_token", _boom)

    from mcp_strava.adapters.sqlite.repository import SQLiteRepository

    with SQLiteRepository.from_path(fixture) as repo:
        repo.recent_activities(limit=1)


def test_ast_guard_blocks_direct_sqlite_outside_allowlist() -> None:
    violations = _guard_direct_sqlite_boundary()
    assert violations == []
