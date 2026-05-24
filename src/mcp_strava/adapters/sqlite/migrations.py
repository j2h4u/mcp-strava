"""Explicit migration gate: preflight -> backup -> migrate -> post-check -> parity."""

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from collections.abc import Callable

from mcp_strava.adapters.sqlite.backup import create_timestamped_backup
from mcp_strava.adapters.sqlite.schema import (
    PreflightReport,
    read_user_version,
    run_preflight_checks,
    set_user_version,
)


@dataclass(frozen=True)
class ParitySnapshot:
    row_counts: dict[str, int]
    observed_trimp: dict[str, float]
    banister_form: float
    banister_series_tail: list[dict[str, float | str]]
    ewma7: float
    ewma28: float
    ewma42: float
    acwr_inputs: dict[str, float]


@dataclass(frozen=True)
class ParityResult:
    ok: bool
    failures: list[str]


def _num_close(a: float, b: float, tolerance: float) -> bool:
    return abs(float(a) - float(b)) <= tolerance


def _compare_banister_series_tail(
    before_tail: list[dict[str, float | str]],
    after_tail: list[dict[str, float | str]],
    tolerance: float,
) -> list[str]:
    failures: list[str] = []
    if len(before_tail) != len(after_tail):
        return [f"banister_series_tail:length:{len(before_tail)}!={len(after_tail)}"]

    for idx, before_point in enumerate(before_tail):
        after_point = after_tail[idx]
        if before_point.get("date") != after_point.get("date"):
            failures.append(f"banister_series_tail:{idx}:date_mismatch")
            break
        for key in ("fitness", "fatigue", "form", "trimp"):
            before_value = before_point.get(key)
            after_value = after_point.get(key)
            if before_value is None or after_value is None:
                failures.append(f"banister_series_tail:{idx}:{key}:missing")
                break
            if not _num_close(float(before_value), float(after_value), tolerance):
                failures.append(f"banister_series_tail:{idx}:{key}:{before_value}!={after_value}")
                break
        if failures:
            break

    return failures


def evaluate_parity(before: ParitySnapshot, after: ParitySnapshot, tolerance: float = 0.1) -> ParityResult:
    failures: list[str] = []

    for table, before_count in before.row_counts.items():
        after_count = after.row_counts.get(table)
        if after_count != before_count:
            failures.append(f"row_count:{table}:{before_count}!={after_count}")

    if set(before.observed_trimp.keys()) != set(after.observed_trimp.keys()):
        failures.append("observed_trimp:date_keys_mismatch")
    else:
        for day, before_value in before.observed_trimp.items():
            after_value = after.observed_trimp[day]
            if not _num_close(before_value, after_value, tolerance):
                failures.append(f"observed_trimp:{day}:{before_value}!={after_value}")
                break

    if not _num_close(before.banister_form, after.banister_form, tolerance):
        failures.append("banister_form_mismatch")

    failures.extend(
        _compare_banister_series_tail(
            before.banister_series_tail,
            after.banister_series_tail,
            tolerance,
        )
    )

    for key in ("ewma7", "ewma28", "ewma42"):
        if not _num_close(getattr(before, key), getattr(after, key), tolerance):
            failures.append(f"{key}_mismatch")

    for key, before_value in before.acwr_inputs.items():
        after_value = after.acwr_inputs.get(key)
        if after_value is None or not _num_close(before_value, after_value, tolerance):
            failures.append(f"acwr_input:{key}:mismatch")

    return ParityResult(ok=not failures, failures=failures)


def run_preflight(db_path: str | Path) -> PreflightReport:
    return run_preflight_checks(db_path)


def _baseline_migration_v1(conn: sqlite3.Connection) -> None:
    set_user_version(conn, 1)


def create_refresh_tables_and_seed_state(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS refresh_state (
            id                  INTEGER PRIMARY KEY,
            last_success_at     TEXT,
            last_attempt_at     TEXT,
            last_status         TEXT,
            last_error_code     TEXT,
            lease_owner         TEXT,
            lease_expires_at    TEXT,
            backoff_until       TEXT,
            checkpoint_stage    TEXT,
            checkpoint_cursor   TEXT
        );
        INSERT OR IGNORE INTO refresh_state (id) VALUES (1);

        CREATE TABLE IF NOT EXISTS refresh_requests (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            reason            TEXT NOT NULL,
            requested_for_day TEXT NOT NULL,
            requested_at      TEXT NOT NULL,
            consumed_at       TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_refresh_requests_dedupe
            ON refresh_requests(reason, requested_for_day)
            WHERE consumed_at IS NULL;
        """
    )
    set_user_version(conn, 2)


def create_lossless_stream_inventory_v3(conn: sqlite3.Connection) -> None:
    stream_columns = {row[1] for row in conn.execute("PRAGMA table_info(streams)").fetchall()}
    if "values_json" not in stream_columns:
        conn.execute("ALTER TABLE streams ADD COLUMN values_json TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stream_channels (
            activity_id INTEGER NOT NULL,
            channel_key TEXT NOT NULL,
            original_size INTEGER,
            resolution TEXT,
            series_type TEXT,
            fetched_at TEXT,
            batch_id TEXT,
            status TEXT NOT NULL,
            error TEXT,
            PRIMARY KEY (activity_id, channel_key)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_stream_channels_activity ON stream_channels(activity_id)"
    )
    set_user_version(conn, 3)


MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _baseline_migration_v1,
    2: create_refresh_tables_and_seed_state,
    3: create_lossless_stream_inventory_v3,
}


def run_migrations(db_path: str | Path) -> PreflightReport:
    path = Path(db_path)
    before = run_preflight(path)
    create_timestamped_backup(path)

    conn = sqlite3.connect(str(path), check_same_thread=False)
    try:
        current = read_user_version(conn)
        for target_version in sorted(MIGRATIONS):
            if current < target_version:
                MIGRATIONS[target_version](conn)
                current = target_version
        conn.commit()
    finally:
        conn.close()

    after = run_preflight(path)

    for table, before_count in before.row_counts.items():
        if after.row_counts.get(table) != before_count:
            raise RuntimeError(
                f"Post-migration row parity failed for {table}: {before_count} != {after.row_counts.get(table)}"
            )

    return after
