"""Explicit migration gate: preflight -> backup -> migrate -> post-check -> parity."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3
import json
from collections.abc import Callable

from mcp_strava.adapters.sqlite.backup import create_pre_phase_7_backup, create_timestamped_backup
from mcp_strava.adapters.sqlite.schema import (
    PreflightReport,
    integrity_check,
    row_counts,
    read_user_version,
    run_preflight_checks,
    validate_required_inventory,
    set_user_version,
)

LAST_MIGRATION_POSTCHECK: dict[str, int] = {}


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


@dataclass(frozen=True)
class GpsMigrationSnapshot:
    stream_rows: int
    gps_points_from_lat_lng: int
    gps_points_from_latlng: int
    gps_scalar_latlng_conflict_count: int
    gps_malformed_latlng_count: int
    values_json_non_null_count: int


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


def _json_latlng_pair(latlng_raw: object) -> tuple[float, float] | None:
    if latlng_raw is None:
        return None
    try:
        parsed = json.loads(str(latlng_raw))
    except Exception:
        return None
    if not isinstance(parsed, list) or len(parsed) < 2:
        return None
    try:
        lat = float(parsed[0])
        lng = float(parsed[1])
    except (TypeError, ValueError):
        return None
    return lat, lng


def _v4_gps_snapshot(conn: sqlite3.Connection) -> GpsMigrationSnapshot:
    stream_rows = int(conn.execute("SELECT COUNT(*) FROM streams").fetchone()[0])
    gps_points = int(
        conn.execute("SELECT COUNT(*) FROM streams WHERE lat IS NOT NULL AND lng IS NOT NULL").fetchone()[0]
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(streams)").fetchall()}
    if "values_json" in columns:
        values_json_non_null = int(
            conn.execute("SELECT COUNT(*) FROM streams WHERE values_json IS NOT NULL").fetchone()[0]
        )
    else:
        values_json_non_null = 0
    gps_from_latlng = 0
    conflict_count = 0
    malformed_count = 0
    if "latlng" not in columns:
        return GpsMigrationSnapshot(
            stream_rows=stream_rows,
            gps_points_from_lat_lng=gps_points,
            gps_points_from_latlng=0,
            gps_scalar_latlng_conflict_count=0,
            gps_malformed_latlng_count=0,
            values_json_non_null_count=values_json_non_null,
        )
    rows = conn.execute("SELECT lat, lng, latlng FROM streams").fetchall()
    for row in rows:
        latlng_pair = _json_latlng_pair(row[2])
        if row[2] is not None and latlng_pair is None:
            malformed_count += 1
        if latlng_pair is None:
            continue
        gps_from_latlng += 1
        lat, lng = latlng_pair
        scalar_lat = row[0]
        scalar_lng = row[1]
        if scalar_lat is not None and scalar_lng is not None:
            if abs(float(scalar_lat) - lat) > 1e-6 or abs(float(scalar_lng) - lng) > 1e-6:
                conflict_count += 1
    return GpsMigrationSnapshot(
        stream_rows=stream_rows,
        gps_points_from_lat_lng=gps_points,
        gps_points_from_latlng=gps_from_latlng,
        gps_scalar_latlng_conflict_count=conflict_count,
        gps_malformed_latlng_count=malformed_count,
        values_json_non_null_count=values_json_non_null,
    )


def _choose_v4_lat_lng(
    scalar_lat: object,
    scalar_lng: object,
    latlng_raw: object,
    *,
    tolerance: float = 1e-6,
) -> tuple[float | None, float | None, bool, bool]:
    malformed = False
    conflict = False
    json_pair = None
    if latlng_raw is not None:
        json_pair = _json_latlng_pair(latlng_raw)
        malformed = json_pair is None
    scalar_lat_f = float(scalar_lat) if scalar_lat is not None else None
    scalar_lng_f = float(scalar_lng) if scalar_lng is not None else None
    if json_pair is None:
        return scalar_lat_f, scalar_lng_f, conflict, malformed

    json_lat, json_lng = json_pair
    if scalar_lat_f is not None and scalar_lng_f is not None:
        if abs(scalar_lat_f - json_lat) > tolerance or abs(scalar_lng_f - json_lng) > tolerance:
            conflict = True
        return scalar_lat_f, scalar_lng_f, conflict, malformed

    if scalar_lat_f is None and scalar_lng_f is None:
        return json_lat, json_lng, conflict, malformed

    if scalar_lat_f is not None and scalar_lng_f is None:
        if abs(scalar_lat_f - json_lat) <= tolerance:
            return scalar_lat_f, json_lng, conflict, malformed
        conflict = True
        return scalar_lat_f, None, conflict, malformed

    if scalar_lng_f is not None and scalar_lat_f is None:
        if abs(scalar_lng_f - json_lng) <= tolerance:
            return json_lat, scalar_lng_f, conflict, malformed
        conflict = True
        return None, scalar_lng_f, conflict, malformed

    return scalar_lat_f, scalar_lng_f, conflict, malformed


def create_canonical_gps_inventory_v4(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN")
    try:
        conn.execute(
            """
            CREATE TABLE streams_new (
                activity_id INTEGER NOT NULL,
                time_offset INTEGER NOT NULL,
                heartrate INTEGER,
                velocity REAL,
                altitude REAL,
                cadence INTEGER,
                lat REAL,
                lng REAL,
                grade REAL,
                gap_speed REAL,
                gap_distance REAL,
                is_moving INTEGER,
                values_json TEXT,
                PRIMARY KEY (activity_id, time_offset)
            )
            """
        )

        rows = conn.execute(
            """
            SELECT activity_id, time_offset, heartrate, velocity, altitude, cadence,
                   lat, lng, grade, gap_speed, gap_distance, is_moving, latlng, values_json
            FROM streams
            ORDER BY activity_id, time_offset
            """
        ).fetchall()
        converted: list[tuple] = []
        for row in rows:
            lat, lng, _conflict, _malformed = _choose_v4_lat_lng(row[6], row[7], row[12])
            converted.append(
                (
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    lat,
                    lng,
                    row[8],
                    row[9],
                    row[10],
                    row[11],
                    row[13],
                )
            )
        conn.executemany(
            """
            INSERT INTO streams_new (
                activity_id, time_offset, heartrate, velocity, altitude, cadence,
                lat, lng, grade, gap_speed, gap_distance, is_moving, values_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            converted,
        )
        conn.execute("DROP TABLE streams")
        conn.execute("ALTER TABLE streams_new RENAME TO streams")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_streams_act ON streams(activity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stream_channels_activity ON stream_channels(activity_id)")
        set_user_version(conn, 4)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def create_read_model_inventory_v5(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS activity_source_state (
            activity_id INTEGER PRIMARY KEY,
            activity_day TEXT NOT NULL,
            summary_hash TEXT,
            detail_hash TEXT,
            streams_hash TEXT,
            channels_hash TEXT,
            source_hash TEXT NOT NULL,
            source_revision INTEGER NOT NULL DEFAULT 1,
            changed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_activity_source_state_day
            ON activity_source_state(activity_day);

        CREATE TABLE IF NOT EXISTS metric_dirty_activities (
            activity_id INTEGER NOT NULL,
            activity_day TEXT NOT NULL,
            metric_version INTEGER NOT NULL,
            source_revision INTEGER NOT NULL,
            reason TEXT NOT NULL,
            queued_at TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            PRIMARY KEY (activity_id, activity_day, metric_version)
        );
        CREATE INDEX IF NOT EXISTS idx_metric_dirty_lookup
            ON metric_dirty_activities(metric_version, activity_day, activity_id);

        CREATE TABLE IF NOT EXISTS activity_metric_facts (
            activity_id INTEGER NOT NULL,
            activity_day TEXT NOT NULL,
            sport_type TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            source_revision INTEGER NOT NULL,
            metric_version INTEGER NOT NULL,
            computed_at TEXT NOT NULL,
            completeness_status TEXT NOT NULL,
            missing_reasons_json TEXT NOT NULL DEFAULT '[]',
            trimp REAL,
            zone1_seconds INTEGER NOT NULL DEFAULT 0,
            zone2_seconds INTEGER NOT NULL DEFAULT 0,
            zone3_seconds INTEGER NOT NULL DEFAULT 0,
            zone4_seconds INTEGER NOT NULL DEFAULT 0,
            zone5_seconds INTEGER NOT NULL DEFAULT 0,
            hr_recovery_median_rate REAL,
            hr_recovery_best_rate REAL,
            hr_recovery_worst_rate REAL,
            hr_recovery_avg_rate REAL,
            vertical_speed_vmh INTEGER,
            vertical_speed_total_ascent_m REAL,
            vertical_speed_duration_hours REAL,
            cardiac_cost REAL,
            adjusted_cardiac_cost REAL,
            cardiac_drift_pct REAL,
            cardiac_drift_severity TEXT,
            hrr_pct REAL,
            z5_seconds INTEGER NOT NULL DEFAULT 0,
            anomaly_count INTEGER NOT NULL DEFAULT 0,
            distance_m REAL,
            moving_time_s INTEGER,
            elapsed_time_s INTEGER,
            elevation_gain_m REAL,
            heartrate_sample_count INTEGER NOT NULL DEFAULT 0,
            stream_sample_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (activity_id, metric_version)
        );
        CREATE INDEX IF NOT EXISTS idx_activity_metric_day_sport_version
            ON activity_metric_facts(activity_day, sport_type, metric_version);
        CREATE INDEX IF NOT EXISTS idx_activity_metric_activity_version
            ON activity_metric_facts(activity_id, metric_version);

        CREATE TABLE IF NOT EXISTS daily_load_facts (
            day TEXT NOT NULL,
            scope TEXT NOT NULL,
            sport_type TEXT NOT NULL,
            metric_version INTEGER NOT NULL,
            computed_at TEXT NOT NULL,
            completeness_status TEXT NOT NULL,
            missing_reasons_json TEXT NOT NULL DEFAULT '[]',
            activity_count INTEGER NOT NULL DEFAULT 0,
            stream_point_count INTEGER NOT NULL DEFAULT 0,
            heartrate_point_count INTEGER NOT NULL DEFAULT 0,
            observed_trimp REAL,
            effective_trimp REAL NOT NULL DEFAULT 0.0,
            distance_m REAL NOT NULL DEFAULT 0.0,
            moving_time_s INTEGER NOT NULL DEFAULT 0,
            elevation_gain_m REAL NOT NULL DEFAULT 0.0,
            zone4_seconds INTEGER NOT NULL DEFAULT 0,
            zone5_seconds INTEGER NOT NULL DEFAULT 0,
            high_zone_seconds INTEGER NOT NULL DEFAULT 0,
            anomaly_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, scope, sport_type, metric_version)
        );
        CREATE INDEX IF NOT EXISTS idx_daily_load_day_scope_sport_version
            ON daily_load_facts(day, scope, sport_type, metric_version);

        CREATE TABLE IF NOT EXISTS training_model_daily (
            day TEXT NOT NULL,
            scope TEXT NOT NULL,
            sport_type TEXT NOT NULL,
            metric_version INTEGER NOT NULL,
            computed_at TEXT NOT NULL,
            completeness_status TEXT NOT NULL,
            missing_reasons_json TEXT NOT NULL DEFAULT '[]',
            effective_trimp REAL NOT NULL DEFAULT 0.0,
            observed_trimp REAL,
            fitness REAL,
            fatigue REAL,
            form REAL,
            form_zone TEXT,
            atl REAL,
            ctl REAL,
            acwr REAL,
            load_7d REAL,
            load_28d REAL,
            load_42d REAL,
            input_days INTEGER NOT NULL DEFAULT 0,
            missing_days INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, scope, sport_type, metric_version)
        );
        CREATE INDEX IF NOT EXISTS idx_training_model_day_scope_sport_version
            ON training_model_daily(day, scope, sport_type, metric_version);

        CREATE TABLE IF NOT EXISTS rolling_period_facts (
            as_of_day TEXT NOT NULL,
            window_days INTEGER NOT NULL,
            scope TEXT NOT NULL,
            sport_type TEXT NOT NULL,
            metric_version INTEGER NOT NULL,
            computed_at TEXT NOT NULL,
            completeness_status TEXT NOT NULL,
            missing_reasons_json TEXT NOT NULL DEFAULT '[]',
            activity_count INTEGER NOT NULL DEFAULT 0,
            active_days INTEGER NOT NULL DEFAULT 0,
            rest_days INTEGER NOT NULL DEFAULT 0,
            observed_trimp REAL,
            effective_trimp REAL NOT NULL DEFAULT 0.0,
            distance_m REAL NOT NULL DEFAULT 0.0,
            moving_time_s INTEGER NOT NULL DEFAULT 0,
            elevation_gain_m REAL NOT NULL DEFAULT 0.0,
            high_zone_seconds INTEGER NOT NULL DEFAULT 0,
            anomaly_count INTEGER NOT NULL DEFAULT 0,
            fitness REAL,
            fatigue REAL,
            form REAL,
            atl REAL,
            ctl REAL,
            acwr REAL,
            median_cardiac_cost REAL,
            median_adjusted_cardiac_cost REAL,
            median_hr_recovery REAL,
            median_cardiac_drift_pct REAL,
            PRIMARY KEY (as_of_day, window_days, scope, sport_type, metric_version)
        );
        CREATE INDEX IF NOT EXISTS idx_rolling_period_asof_window_scope_sport_version
            ON rolling_period_facts(as_of_day, window_days, scope, sport_type, metric_version);

        CREATE TABLE IF NOT EXISTS read_model_refresh_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            metric_version INTEGER NOT NULL,
            trigger_reason TEXT,
            lease_owner TEXT,
            activities_considered INTEGER NOT NULL DEFAULT 0,
            activities_materialized INTEGER NOT NULL DEFAULT 0,
            daily_facts_materialized INTEGER NOT NULL DEFAULT 0,
            model_facts_materialized INTEGER NOT NULL DEFAULT 0,
            rolling_facts_materialized INTEGER NOT NULL DEFAULT 0,
            dirty_rows_claimed INTEGER NOT NULL DEFAULT 0,
            dirty_rows_cleared INTEGER NOT NULL DEFAULT 0,
            checkpoint_cursor TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_activities_date_id
            ON activities(date, id);
        CREATE INDEX IF NOT EXISTS idx_activities_sport_date_id
            ON activities(sport_type, date, id);
        """
    )
    _seed_initial_read_model_dirty_queue(conn)
    set_user_version(conn, 5)
    conn.execute("PRAGMA optimize")


def _seed_initial_read_model_dirty_queue(conn: sqlite3.Connection) -> int:
    """Queue existing mirror rows once so first v5 refresh materializes facts."""
    from mcp_strava.adapters.sqlite.repository import CURRENT_METRIC_VERSION, SQLiteRepository

    conn.row_factory = sqlite3.Row
    repo = SQLiteRepository.from_connection(conn)
    rows = conn.execute(
        """
        SELECT id
        FROM activities a
        WHERE NOT EXISTS (
            SELECT 1
            FROM activity_source_state s
            WHERE s.activity_id = a.id
        )
        ORDER BY date, id
        """
    ).fetchall()
    queued = 0
    now_iso = datetime.now().isoformat(timespec="seconds")
    for row in rows:
        changed = repo.update_activity_source_state_and_enqueue_dirty(
            int(row["id"]),
            reason="initial_read_model_backfill",
            metric_version=CURRENT_METRIC_VERSION,
            queued_at=now_iso,
        )
        if changed:
            queued += 1
    return queued


MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _baseline_migration_v1,
    2: create_refresh_tables_and_seed_state,
    3: create_lossless_stream_inventory_v3,
    4: create_canonical_gps_inventory_v4,
    5: create_read_model_inventory_v5,
}


def run_migrations(db_path: str | Path) -> PreflightReport:
    path = Path(db_path)
    before = run_preflight(path)
    backup_path = create_timestamped_backup(path)
    pinned_phase_7_backup: Path | None = None
    pre_snapshot: GpsMigrationSnapshot | None = None
    if before.user_version < 4:
        with sqlite3.connect(str(path), check_same_thread=False) as conn:
            pre_snapshot = _v4_gps_snapshot(conn)

    conn = sqlite3.connect(str(path), check_same_thread=False)
    try:
        current = read_user_version(conn)
        for target_version in sorted(MIGRATIONS):
            if current < target_version:
                if target_version == 5 and pinned_phase_7_backup is None:
                    pinned_phase_7_backup = create_pre_phase_7_backup(path)
                    backup_path = pinned_phase_7_backup
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

    if pre_snapshot is not None:
        with sqlite3.connect(str(path), check_same_thread=False) as conn:
            post_snapshot = _v4_gps_snapshot(conn)
            LAST_MIGRATION_POSTCHECK.clear()
            LAST_MIGRATION_POSTCHECK.update({
                "gps_scalar_latlng_conflict_count": pre_snapshot.gps_scalar_latlng_conflict_count,
                "gps_malformed_latlng_count": pre_snapshot.gps_malformed_latlng_count,
                "stream_rows": post_snapshot.stream_rows,
                "gps_points_from_lat_lng": post_snapshot.gps_points_from_lat_lng,
                "gps_points_from_latlng": pre_snapshot.gps_points_from_latlng,
            })
            validate_required_inventory(conn)
            if integrity_check(conn).lower() != "ok":
                raise RuntimeError(f"Post-check failed: integrity (backup: {backup_path})")
            row_count_parity = row_counts(conn).get("streams", 0) == pre_snapshot.stream_rows
            if not row_count_parity:
                raise RuntimeError(f"Post-check failed: stream_rows_parity (backup: {backup_path})")
            if post_snapshot.gps_points_from_lat_lng < pre_snapshot.gps_points_from_lat_lng:
                raise RuntimeError(f"Post-check failed: gps_point_count (backup: {backup_path})")

    return after
