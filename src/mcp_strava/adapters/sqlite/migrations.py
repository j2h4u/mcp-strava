"""Explicit migration gate: preflight -> backup -> migrate -> post-check -> parity."""

from dataclasses import dataclass
from pathlib import Path
import sqlite3

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


def run_migrations(db_path: str | Path) -> PreflightReport:
    path = Path(db_path)
    before = run_preflight(path)
    create_timestamped_backup(path)

    conn = sqlite3.connect(str(path), check_same_thread=False)
    try:
        current = read_user_version(conn)
        if current < 1:
            _baseline_migration_v1(conn)
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
