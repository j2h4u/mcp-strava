import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mcp_strava.db import get_daily_trimp_history
from mcp_strava.settings import reset_settings_cache
from mcp_strava.training import calc_banister, calc_banister_series, ewma


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
    base = datetime(2026, 1, 1)
    activities = []
    for idx in range(42):
        day = (base + timedelta(days=idx)).strftime("%Y-%m-%d")
        activities.append(
            (
                idx + 1,
                f"{day}T06:00:00Z",
                f"Run {idx + 1}",
                "Run",
                10000.0,
                3600,
                3700,
                100.0,
                "{}",
                "{}",
                f"{day}T07:00:00Z",
            )
        )
    conn.executemany(
        """
        INSERT INTO activities (
            id, date, name, sport_type, distance, moving_time, elapsed_time,
            total_elevation_gain, summary_json, detail_json, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        activities,
    )
    stream_rows = []
    for idx in range(42):
        activity_id = idx + 1
        for minute in range(10):
            stream_rows.append(
                (
                    activity_id,
                    minute * 60,
                    140 + (idx % 5),
                    3.0 + (minute * 0.05),
                    500.0 + minute,
                    85,
                    43.2,
                    76.9,
                    1.0,
                    3.1,
                    180.0,
                    1,
                    "[43.2,76.9]",
                )
            )
    conn.executemany(
        """
        INSERT INTO streams (
            activity_id, time_offset, heartrate, velocity, altitude, cadence,
            lat, lng, grade, gap_speed, gap_distance, is_moving, latlng
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        stream_rows,
    )
    conn.execute(
        "INSERT INTO athlete_zones (fetched_at, zones_json) VALUES (?, ?)",
        ("2026-02-12T07:00:00Z", "[]"),
    )
    conn.execute(
        """
        INSERT INTO sync_log (
            timestamp, status, activities_seen, activities_new,
            streams_fetched, details_fetched, api_calls, error, kudos_fetched
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-02-12T08:00:00Z", "ok", 42, 42, 42, 42, 5, None, 0),
    )
    conn.execute(
        "INSERT INTO kudos (activity_id, firstname, lastname, fetched_at) VALUES (?, ?, ?, ?)",
        (1, "A", "B", "2026-02-12T08:00:00Z"),
    )
    conn.execute("PRAGMA user_version=0")
    conn.commit()
    conn.close()


def _real_db_stat() -> tuple[int, int, float] | None:
    real_db = Path("data") / "strava.db"
    if not real_db.exists():
        return None
    stat = real_db.stat()
    return stat.st_ino, stat.st_size, stat.st_mtime


def test_safe04_fail_closed_open_missing_expected_db_d05(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_strava.adapters.sqlite.connection import open_expected_mirror_db

    missing = tmp_path / "missing.db"
    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(missing))
    reset_settings_cache()
    try:
        with pytest.raises(sqlite3.OperationalError):
            open_expected_mirror_db(missing)
    finally:
        reset_settings_cache()
    assert not missing.exists()


def test_safe01_preflight_fails_invalid_db_before_ddl_d03_d17(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_preflight

    bad_db = tmp_path / "bad.db"
    bad_db.write_bytes(b"not-sqlite")
    with pytest.raises(Exception):
        run_preflight(bad_db)


def test_safe01_preflight_reports_required_row_counts_and_user_version_d03(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_preflight

    db_path = tmp_path / "fixture.db"
    _create_fixture_db(db_path)
    report = run_preflight(db_path)
    assert report.row_counts["activities"] == 42
    assert report.row_counts["streams"] == 420
    assert report.row_counts["athlete_zones"] == 1
    assert report.row_counts["sync_log"] == 1
    assert report.row_counts["kudos"] == 1
    assert report.user_version == 0


def test_safe02_backup_is_timestamped_openable_and_permissions_d04(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_strava.adapters.sqlite.backup import create_timestamped_backup

    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)
    backups_dir = tmp_path / "backups"
    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(fixture))
    reset_settings_cache()
    try:
        backup_path = create_timestamped_backup(fixture, backups_dir=backups_dir)
    finally:
        reset_settings_cache()
    assert backup_path.parent == backups_dir
    assert backup_path.name.startswith("strava-")
    assert backup_path.suffix == ".db"
    assert backup_path.stat().st_size > 0
    with sqlite3.connect(backup_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM activities").fetchone()
    assert row is not None and row[0] == 42
    if hasattr(Path, "chmod"):
        mode = backup_path.stat().st_mode & 0o777
        assert mode == 0o600


def test_safe02_backup_integrity_check_failure_blocks_success_d04(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import mcp_strava.adapters.sqlite.backup as backup_module

    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)
    backups_dir = tmp_path / "backups"
    real_connect = backup_module.sqlite3.connect
    calls: list[str] = []

    class BadIntegrityConnection:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc_val, _exc_tb) -> None:
            return None

        def execute(self, _sql: str):
            return self

        def fetchone(self) -> tuple[str]:
            return ("not ok",)

    def fake_connect(*args, **kwargs):
        calls.append(str(args[0]))
        if len(calls) == 3:
            return BadIntegrityConnection()
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(backup_module.sqlite3, "connect", fake_connect)

    with pytest.raises(RuntimeError, match="Backup integrity check failed"):
        backup_module.create_timestamped_backup(fixture, backups_dir=backups_dir)


def test_safe03_baseline_migration_sets_user_version_to_7_idempotently_d02(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations

    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)
    run_migrations(fixture)
    run_migrations(fixture)
    with sqlite3.connect(fixture) as conn:
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        count = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        refresh_state_count = conn.execute("SELECT COUNT(*) FROM refresh_state").fetchone()[0]
        refresh_requests_count = conn.execute("SELECT COUNT(*) FROM refresh_requests").fetchone()[0]
    assert user_version == 7
    assert count == 42
    assert refresh_state_count == 1
    assert refresh_requests_count == 0


def test_migration_runner_records_applied_schema_migrations(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import MIGRATIONS, latest_migration_version, migration_specs, run_migrations

    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)

    run_migrations(fixture)
    run_migrations(fixture)

    with sqlite3.connect(fixture) as conn:
        rows = conn.execute(
            "SELECT version, name, checksum FROM schema_migration_log ORDER BY version"
        ).fetchall()

    assert latest_migration_version() == 7
    assert 7 not in MIGRATIONS
    assert [spec.version for spec in migration_specs()] == list(range(1, 8))
    assert [row[0] for row in rows] == list(range(1, 8))
    assert len(rows) == 7
    assert all(row[2] for row in rows)
    assert rows[-1][1] == "schema_migration_log"
    assert rows[-1][2] != "legacy-inline"


def test_migration_v1_to_v3_creates_refresh_tables_and_preserves_parity(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations

    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)

    preserved_tables = ("activities", "streams", "athlete_zones", "sync_log", "kudos")
    with sqlite3.connect(fixture) as conn:
        before_counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in preserved_tables
        }

    run_migrations(fixture)

    with sqlite3.connect(fixture) as conn:
        after_counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in preserved_tables
        }
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        refresh_state_count = conn.execute("SELECT COUNT(*) FROM refresh_state").fetchone()[0]
        refresh_requests_count = conn.execute("SELECT COUNT(*) FROM refresh_requests").fetchone()[0]

    assert user_version == 7
    assert refresh_state_count == 1
    assert refresh_requests_count == 0
    assert after_counts == before_counts


def test_preflight_v3_includes_refresh_tables(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations, run_preflight

    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)
    run_migrations(fixture)

    report = run_preflight(fixture)

    assert report.user_version == 7
    assert report.row_counts["refresh_state"] == 1
    assert report.row_counts["refresh_requests"] == 0


def test_refresh_requests_partial_unique_index_exists(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import run_migrations

    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)
    run_migrations(fixture)

    with sqlite3.connect(fixture) as conn:
        indexes = conn.execute("PRAGMA index_list('refresh_requests')").fetchall()
        match = [row for row in indexes if row[1] == "idx_refresh_requests_dedupe"]
        columns = conn.execute("PRAGMA index_info('idx_refresh_requests_dedupe')").fetchall()

    assert match
    assert match[0][2] == 1
    assert match[0][4] == 1
    assert [row[2] for row in columns] == ["reason", "requested_for_day"]


def test_full_fidelity_migration_tests_use_temp_paths_only(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)
    resolved = fixture.resolve()
    assert "/data/strava.db" not in str(resolved)
    assert "/opt/docker/mcp-strava" not in str(resolved)


def test_safe03_synthetic_schema_change_detects_row_or_load_parity_d06_d07(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.migrations import ParitySnapshot, evaluate_parity

    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)
    as_of = "2026-02-11"

    with sqlite3.connect(fixture) as conn:
        conn.row_factory = sqlite3.Row
        history = get_daily_trimp_history(conn, days=42, sport_filter="training")
        ban = calc_banister(history, today_str=as_of)
        series = calc_banister_series(history, end_date=as_of)
        load7 = ewma(history, tau=7, end_date=as_of).get(as_of, 0.0)
        load28 = ewma(history, tau=28, end_date=as_of).get(as_of, 0.0)
        load42 = ewma(history, tau=42, end_date=as_of).get(as_of, 0.0)
        before = ParitySnapshot(
            row_counts={"activities": 42, "streams": 420},
            observed_trimp=history,
            banister_form=ban.form if ban else 0.0,
            banister_series_tail=series[-7:],
            ewma7=load7,
            ewma28=load28,
            ewma42=load42,
            acwr_inputs={"fatigue": ban.fatigue if ban else 0.0, "fitness": load28},
        )

        conn.execute("ALTER TABLE activities ADD COLUMN synthetic_nullable TEXT")
        conn.execute("DELETE FROM streams WHERE activity_id = 1")
        conn.commit()

        history_after = get_daily_trimp_history(conn, days=42, sport_filter="training")
        ban_after = calc_banister(history_after, today_str=as_of)
        series_after = calc_banister_series(history_after, end_date=as_of)
        after = ParitySnapshot(
            row_counts={
                "activities": conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0],
                "streams": conn.execute("SELECT COUNT(*) FROM streams").fetchone()[0],
            },
            observed_trimp=history_after,
            banister_form=ban_after.form if ban_after else 0.0,
            banister_series_tail=series_after[-7:],
            ewma7=ewma(history_after, tau=7, end_date=as_of).get(as_of, 0.0),
            ewma28=ewma(history_after, tau=28, end_date=as_of).get(as_of, 0.0),
            ewma42=ewma(history_after, tau=42, end_date=as_of).get(as_of, 0.0),
            acwr_inputs={
                "fatigue": ban_after.fatigue if ban_after else 0.0,
                "fitness": ewma(history_after, tau=28, end_date=as_of).get(as_of, 0.0),
            },
        )

    result = evaluate_parity(before, after, tolerance=0.1)
    assert not result.ok


def test_safe03_banister_series_tail_parity_is_enforced_d07() -> None:
    from mcp_strava.adapters.sqlite.migrations import ParitySnapshot, evaluate_parity

    before = ParitySnapshot(
        row_counts={"activities": 1},
        observed_trimp={"2026-01-01": 100.0},
        banister_form=1.0,
        banister_series_tail=[
            {"date": "2026-01-01", "fitness": 10.0, "fatigue": 9.0, "form": 1.0, "trimp": 100.0},
        ],
        ewma7=10.0,
        ewma28=10.0,
        ewma42=10.0,
        acwr_inputs={"fatigue": 9.0, "fitness": 10.0},
    )
    after = ParitySnapshot(
        row_counts={"activities": 1},
        observed_trimp={"2026-01-01": 100.0},
        banister_form=1.0,
        banister_series_tail=[
            {"date": "2026-01-01", "fitness": 10.0, "fatigue": 7.0, "form": 3.0, "trimp": 100.0},
        ],
        ewma7=10.0,
        ewma28=10.0,
        ewma42=10.0,
        acwr_inputs={"fatigue": 9.0, "fitness": 10.0},
    )

    result = evaluate_parity(before, after, tolerance=0.1)

    assert not result.ok
    assert any("banister_series_tail" in failure for failure in result.failures)


def test_safe02_backup_retention_keeps_five_newest_d04(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.backup import enforce_backup_retention

    backups_dir = tmp_path / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(8):
        p = backups_dir / f"strava-20260101T00000{idx}Z.db"
        p.write_bytes(b"x")
    kept = enforce_backup_retention(backups_dir, keep=5)
    assert len(kept) == 5
    assert sorted(path.name for path in backups_dir.glob("strava-*.db")) == sorted(path.name for path in kept)


def test_safe02_backup_retention_preserves_pinned_pre_phase_7_backup(tmp_path: Path) -> None:
    from mcp_strava.adapters.sqlite.backup import create_pre_phase_7_backup, enforce_backup_retention

    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)
    backups_dir = tmp_path / "backups"
    pinned = create_pre_phase_7_backup(fixture, backups_dir=backups_dir)

    for idx in range(8):
        p = backups_dir / f"strava-20260101T00000{idx}Z.db"
        p.write_bytes(b"x")

    kept = enforce_backup_retention(backups_dir, keep=5)

    assert pinned.exists()
    assert pinned in kept
    regular = [path for path in kept if "pre-phase-7" not in path.name]
    assert len(regular) == 5


def test_safe16_default_tests_do_not_mutate_real_db_metadata_d16_d17(tmp_path: Path) -> None:
    before = _real_db_stat()
    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)

    # Read-only smoke over temp fixture to ensure no incidental use of real DB path.
    with sqlite3.connect(fixture) as conn:
        conn.execute("SELECT COUNT(*) FROM activities").fetchone()

    after = _real_db_stat()
    assert before == after
