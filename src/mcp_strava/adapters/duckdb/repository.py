"""DuckDB repository boundary for primary Strava mirror storage."""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Iterable

from mcp_strava.adapters.duckdb.connection import duckdb_process_lock, open_expected_mirror_db, open_fixture_db
from mcp_strava.adapters.duckdb.schema import ensure_provenance_columns
from mcp_strava.constants import Config, TRAINING_SPORTS
from mcp_strava.types import (
    ALLOWED_REASON_CODES,
    DailyLoadPoint,
    ReadModelMetadata,
    RefreshRequestRow,
    RefreshStateRow,
    RepositoryActivityRow,
    RepositoryDailyLoadStatus,
    RepositorySyncLogEntry,
)

CURRENT_METRIC_VERSION = 1


def build_trimp_sql(bounds: list[int], alias: str = "") -> str:
    """Build the TRIMP SQL fragment from precomputed integer zone bounds.

    Mirrors the structure of the old _build_trimp_cases() in constants.py so
    that TRIMP values are byte-identical for the same bounds. Uses
    Config.Zones.COEFF for zone weights (unchanged).

    Args:
        bounds: Ordered zone upper bounds list, e.g. [122, 136, 150, 163, 177, 300].
                Must have at least 2 elements; last element is the cap.
        alias:  Optional column alias prefix, e.g. "s." to produce "s.heartrate".

    Returns:
        SQL string ending with "/ 60.0 as trimp".
    """
    c = Config.Zones.COEFF
    h = alias
    parts = [f"SUM(CASE WHEN {h}heartrate < {bounds[0]} THEN 1 ELSE 0 END) * {c[0]}"]
    for i in range(1, len(bounds) - 1):
        parts.append(
            f"SUM(CASE WHEN {h}heartrate >= {bounds[i-1]} AND {h}heartrate < {bounds[i]} THEN 1 ELSE 0 END) * {c[i]}"
        )
    parts.append(f"SUM(CASE WHEN {h}heartrate >= {bounds[-2]} THEN 1 ELSE 0 END) * {c[-1]}")
    return "(" + " +\n                ".join(parts) + ") / 60.0 as trimp"


def build_zones_sql(bounds: list[int], alias: str = "") -> str:
    """Build the zone-seconds SQL fragment from precomputed integer zone bounds.

    Returns a SQL string with z1..z{n} SUM CASE expressions separated by commas,
    matching the structure of the old _build_trimp_cases() zones portion.

    Args:
        bounds: Ordered zone upper bounds list including cap.
        alias:  Optional column alias prefix, e.g. "s.".

    Returns:
        SQL string of comma-separated zone SUM expressions.
    """
    h = alias
    zones = [f"SUM(CASE WHEN {h}heartrate < {bounds[0]} THEN 1 ELSE 0 END) as z1"]
    for i in range(1, len(bounds) - 1):
        zones.append(
            f"SUM(CASE WHEN {h}heartrate >= {bounds[i-1]} AND {h}heartrate < {bounds[i]} THEN 1 ELSE 0 END) as z{i+1}"
        )
    zones.append(f"SUM(CASE WHEN {h}heartrate >= {bounds[-2]} THEN 1 ELSE 0 END) as z{len(bounds)}")
    return ",\n                ".join(zones)


NON_SEMANTIC_SOURCE_KEYS = frozenset(
    {
        "synced_at",
        "fetched_at",
        "timestamp",
        "updated_at",
        "modified_at",
        "batch_id",
    }
)


def _loads_json_if_possible(value: object) -> object:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _canonical_semantic_value(value: object) -> object:
    value = _loads_json_if_possible(value)
    if isinstance(value, dict):
        return {
            str(key): _canonical_semantic_value(item)
            for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))
            if str(key).lower() not in NON_SEMANTIC_SOURCE_KEYS
        }
    if isinstance(value, list):
        return [_canonical_semantic_value(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


def _semantic_json_hash(value: object) -> str:
    payload = json.dumps(
        _canonical_semantic_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summary_payload_changed(stored_summary_json: object, new_summary_json: object) -> bool:
    """True when two Strava summary payloads differ in semantic content.

    Compares canonicalized content (sorted keys, non-semantic keys like
    synced_at/fetched_at dropped) so that re-syncing an unchanged activity is
    not treated as a change. The daily refresh re-sees the same ~600 activities
    every cycle; rewriting an unchanged PRIMARY-KEY-indexed row churns the
    DuckDB ART index, which bloats the file (freed index blocks are never
    reused) and re-triggers the upstream ART stale-update-read corruption.

    A plain string-equality fast path covers the common case (Strava returns
    byte-identical JSON for an unchanged activity); the semantic hash is the
    fallback that tolerates key reordering or whitespace differences.
    """
    if stored_summary_json is None:
        return True
    if stored_summary_json == new_summary_json:
        return False
    return _semantic_json_hash(stored_summary_json) != _semantic_json_hash(new_summary_json)


def _normalize_cell(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    return value


@dataclass
class DuckDBRepository:
    """Focused DuckDB repository with explicit unit-of-work lifetime."""

    conn: object
    _transaction_depth: int = field(default=0, init=False, repr=False)
    _transaction_lock_held: bool = field(default=False, init=False, repr=False)
    _read_model_enabled_cache: bool | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_path(cls, db_path: str | Path, expected_mirror: bool = False) -> "DuckDBRepository":
        path = Path(db_path)
        conn = open_expected_mirror_db(path) if expected_mirror else open_fixture_db(path)
        repo = cls(conn=conn)
        repo._ensure_schema_extensions()
        return repo

    @classmethod
    def from_connection(cls, conn: object) -> "DuckDBRepository":
        repo = cls(conn=conn)
        repo._ensure_schema_extensions()
        return repo

    def _ensure_schema_extensions(self) -> None:
        """Additive migration: ensure provenance columns exist on live DB."""
        try:
            ensure_provenance_columns(self.conn)
        except Exception:
            # Table may not exist yet (fresh DB before create_schema); that is fine.
            pass

    def __enter__(self) -> "DuckDBRepository":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.conn.close()

    def close(self) -> None:
        self.conn.close()

    def begin(self) -> None:
        acquired = False
        if self._transaction_depth == 0:
            duckdb_process_lock().acquire()
            self._transaction_lock_held = True
            acquired = True
        try:
            self.conn.execute("BEGIN")
            self._transaction_depth += 1
        except Exception:
            if acquired:
                self._transaction_lock_held = False
                duckdb_process_lock().release()
            raise

    def commit(self) -> None:
        should_release = self._transaction_depth <= 1 and self._transaction_lock_held
        try:
            self.conn.commit()
        finally:
            if self._transaction_depth > 0:
                self._transaction_depth -= 1
            if should_release:
                self._transaction_lock_held = False
                duckdb_process_lock().release()

    def rollback(self) -> None:
        should_release = self._transaction_lock_held
        try:
            self.conn.rollback()
        finally:
            self._transaction_depth = 0
            if should_release:
                self._transaction_lock_held = False
                duckdb_process_lock().release()

    def _commit_if_standalone(self) -> None:
        if self._transaction_depth == 0:
            with duckdb_process_lock():
                self.conn.commit()

    def _execute(self, sql: str, params: Iterable[object] | None = None):
        if self._transaction_depth > 0:
            return self.conn.execute(sql, list(params or []))
        with duckdb_process_lock():
            return self.conn.execute(sql, list(params or []))

    def _executemany(self, sql: str, params: Iterable[Iterable[object]]):
        if self._transaction_depth > 0:
            return self.conn.executemany(sql, params)
        with duckdb_process_lock():
            return self.conn.executemany(sql, params)

    def _fetchone(self, sql: str, params: Iterable[object] | None = None) -> dict[str, object] | None:
        if self._transaction_depth > 0:
            result = self.conn.execute(sql, list(params or []))
            row = result.fetchone()
        else:
            with duckdb_process_lock():
                result = self.conn.execute(sql, list(params or []))
                row = result.fetchone()
        if row is None:
            return None
        columns = [item[0] for item in result.description]
        return {column: _normalize_cell(value) for column, value in zip(columns, row, strict=False)}

    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[dict[str, object]]:
        if self._transaction_depth > 0:
            result = self.conn.execute(sql, list(params or []))
            rows = result.fetchall()
        else:
            with duckdb_process_lock():
                result = self.conn.execute(sql, list(params or []))
                rows = result.fetchall()
        columns = [item[0] for item in result.description]
        return [{column: _normalize_cell(value) for column, value in zip(columns, row, strict=False)} for row in rows]

    def _scalar(self, sql: str, params: Iterable[object] | None = None) -> object | None:
        if self._transaction_depth > 0:
            row = self.conn.execute(sql, list(params or [])).fetchone()
        else:
            with duckdb_process_lock():
                row = self.conn.execute(sql, list(params or [])).fetchone()
        return row[0] if row is not None else None

    def _table_columns(self, table: str) -> set[str]:
        with duckdb_process_lock():
            rows = self.conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        return {str(row[1]) for row in rows}

    def _table_exists(self, table: str) -> bool:
        with duckdb_process_lock():
            row = self.conn.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = ?
                LIMIT 1
                """,
                [table],
            ).fetchone()
        return row is not None

    def _next_id(self, table: str) -> int:
        value = self._scalar(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table}")
        return int(value or 1)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # Read-model invalidation
    def _read_model_enabled(self) -> bool:
        # Memoized per repository instance (one per read call): the read-model
        # schema is immutable within a repo's lifetime — migrations own DDL and
        # read paths never create/drop tables — so the information_schema lookup
        # is derived once instead of repeatedly (read_model_status alone asks
        # twice). Read repos are short-lived, so there is no staleness window.
        if self._read_model_enabled_cache is None:
            self._read_model_enabled_cache = self._table_exists("activity_source_state")
        return self._read_model_enabled_cache

    def _read_activity_source_components(self, activity_id: int) -> dict[str, object] | None:
        activity = self._fetchone(
            """
            SELECT id, activity_day, date, name, sport_type, distance, moving_time,
                   elapsed_time, total_elevation_gain, summary_json, detail_json
            FROM activities
            WHERE id = ?
            """,
            [activity_id],
        )
        if activity is None:
            return None

        summary_hash = _semantic_json_hash(activity.get("summary_json"))
        detail_hash = _semantic_json_hash(activity.get("detail_json"))

        stream_columns = sorted(self._table_columns("streams"))
        streams: list[dict[str, object]] = []
        if stream_columns:
            quoted_cols = ", ".join(stream_columns)
            rows = self._fetchall(
                f"SELECT {quoted_cols} FROM streams WHERE activity_id = ? ORDER BY time_offset",
                [activity_id],
            )
            for row in rows:
                if "values_json" in row:
                    row["values_json"] = _canonical_semantic_value(row["values_json"])
                streams.append(row)
        streams_hash = _semantic_json_hash(streams)

        channels = self._fetchall(
            """
            SELECT channel_key, original_size, resolution, series_type, status, error
            FROM stream_channels
            WHERE activity_id = ?
            ORDER BY channel_key
            """,
            [activity_id],
        )
        channels_hash = _semantic_json_hash(channels)

        source_payload = {
            "activity": {
                key: _canonical_semantic_value(value)
                for key, value in activity.items()
                if key not in {"summary_json", "detail_json"}
            },
            "summary_hash": summary_hash,
            "detail_hash": detail_hash,
            "streams_hash": streams_hash,
            "channels_hash": channels_hash,
        }
        return {
            "activity_day": str(activity["activity_day"]),
            "summary_hash": summary_hash,
            "detail_hash": detail_hash,
            "streams_hash": streams_hash,
            "channels_hash": channels_hash,
            "source_hash": _semantic_json_hash(source_payload),
        }

    def update_activity_source_state_and_enqueue_dirty(
        self,
        activity_id: int,
        *,
        reason: str = "source_changed",
        metric_version: int = CURRENT_METRIC_VERSION,
        queued_at: str | None = None,
    ) -> bool:
        if not self._read_model_enabled():
            return False
        components = self._read_activity_source_components(activity_id)
        if components is None:
            return False

        existing = self._fetchone(
            """
            SELECT source_hash, source_revision
            FROM activity_source_state
            WHERE activity_id = ?
            """,
            [activity_id],
        )
        if existing is not None and existing["source_hash"] == components["source_hash"]:
            return False

        source_revision = 1 if existing is None else int(existing["source_revision"]) + 1
        changed_at = queued_at or self._now_iso()
        self._execute(
            """
            INSERT INTO activity_source_state (
                activity_id, activity_day, summary_hash, detail_hash, streams_hash,
                channels_hash, source_hash, source_revision, changed_at
            ) VALUES (?, CAST(? AS DATE), ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id) DO UPDATE SET
                activity_day=excluded.activity_day,
                summary_hash=excluded.summary_hash,
                detail_hash=excluded.detail_hash,
                streams_hash=excluded.streams_hash,
                channels_hash=excluded.channels_hash,
                source_hash=excluded.source_hash,
                source_revision=excluded.source_revision,
                changed_at=excluded.changed_at
            """,
            [
                activity_id,
                components["activity_day"],
                components["summary_hash"],
                components["detail_hash"],
                components["streams_hash"],
                components["channels_hash"],
                components["source_hash"],
                source_revision,
                changed_at,
            ],
        )
        self.enqueue_metric_dirty_activity(
            activity_id=activity_id,
            activity_day=str(components["activity_day"]),
            metric_version=metric_version,
            source_revision=source_revision,
            reason=reason,
            queued_at=changed_at,
        )
        return True

    def enqueue_metric_dirty_activity(
        self,
        *,
        activity_id: int,
        activity_day: str,
        metric_version: int,
        source_revision: int,
        reason: str,
        queued_at: str,
    ) -> None:
        self._execute(
            """
            INSERT INTO metric_dirty_activities (
                activity_id, activity_day, metric_version, source_revision,
                reason, queued_at, attempt_count, last_error
            ) VALUES (?, CAST(? AS DATE), ?, ?, ?, ?, 0, NULL)
            ON CONFLICT(activity_id, metric_version) DO UPDATE SET
                activity_day=excluded.activity_day,
                source_revision=excluded.source_revision,
                reason=excluded.reason,
                queued_at=excluded.queued_at,
                attempt_count=0,
                last_error=NULL
            """,
            [activity_id, activity_day, metric_version, source_revision, reason, queued_at],
        )

    def dirty_activity_rows(self, metric_version: int | None = None, activity_id: int | None = None) -> list[dict[str, object]]:
        where: list[str] = []
        params: list[object] = []
        if metric_version is not None:
            where.append("metric_version = ?")
            params.append(metric_version)
        if activity_id is not None:
            where.append("activity_id = ?")
            params.append(activity_id)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        return self._fetchall(
            f"""
            SELECT *
            FROM metric_dirty_activities
            {where_sql}
            ORDER BY activity_day, activity_id, metric_version
            """,
            params,
        )

    def mark_dirty_activity_attempt_failed(
        self,
        activity_id: int,
        activity_day: str,
        metric_version: int,
        last_error: str,
    ) -> None:
        self._execute(
            """
            UPDATE metric_dirty_activities
            SET attempt_count = attempt_count + 1, last_error = ?
            WHERE activity_id = ? AND activity_day = CAST(? AS DATE) AND metric_version = ?
            """,
            [last_error, activity_id, activity_day, metric_version],
        )
        self._commit_if_standalone()

    def enqueue_metric_version_recompute(self, metric_version: int, reason: str, queued_at: str) -> int:
        if not self._read_model_enabled():
            return 0
        rows = self._fetchall(
            """
            SELECT activity_id, activity_day, source_revision
            FROM activity_source_state
            ORDER BY activity_day, activity_id
            """
        )
        for row in rows:
            self.enqueue_metric_dirty_activity(
                activity_id=int(row["activity_id"]),
                activity_day=str(row["activity_day"]),
                metric_version=metric_version,
                source_revision=int(row["source_revision"]),
                reason=reason,
                queued_at=queued_at,
            )
        self._commit_if_standalone()
        return len(rows)

    def dirty_activity_rows_for_materialization(
        self,
        metric_version: int,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        params: list[object] = [metric_version]
        sql = """
            SELECT d.*, s.source_hash
            FROM metric_dirty_activities d
            JOIN activity_source_state s ON s.activity_id = d.activity_id
            WHERE d.metric_version = ?
            ORDER BY d.activity_day, d.activity_id
        """
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return self._fetchall(sql, params)

    def clear_dirty_activity_rows(self, rows: Iterable[object]) -> int:
        count = 0
        for row in rows:
            activity_id = int(row["activity_id"])
            activity_day = str(row["activity_day"])
            metric_version = int(row["metric_version"])
            existing = self._fetchone(
                """
                SELECT 1
                FROM metric_dirty_activities
                WHERE activity_id = ? AND activity_day = CAST(? AS DATE) AND metric_version = ?
                """,
                [activity_id, activity_day, metric_version],
            )
            self._execute(
                """
                DELETE FROM metric_dirty_activities
                WHERE activity_id = ? AND activity_day = CAST(? AS DATE) AND metric_version = ?
                """,
                [activity_id, activity_day, metric_version],
            )
            if existing is not None:
                count += 1
        return count

    def source_state_for_activity(self, activity_id: int) -> dict[str, object] | None:
        return self._fetchone(
            "SELECT * FROM activity_source_state WHERE activity_id = ?",
            [activity_id],
        )

    def _upsert_fact(self, table: str, values: dict[str, object], conflict_columns: tuple[str, ...]) -> None:
        columns = tuple(values.keys())
        placeholders = ", ".join("?" for _ in columns)
        update_columns = [col for col in columns if col not in conflict_columns]
        assignments = ", ".join(f"{col}=excluded.{col}" for col in update_columns)
        conflict = ", ".join(conflict_columns)
        sql = f"""
            INSERT INTO {table} ({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT({conflict}) DO UPDATE SET {assignments}
        """
        self._execute(sql, [values[col] for col in columns])

    def upsert_activity_metric_fact(self, values: dict[str, object]) -> None:
        self._upsert_fact("activity_metric_facts", values, ("activity_id", "metric_version"))

    def upsert_daily_load_fact(self, values: dict[str, object]) -> None:
        self._upsert_fact("daily_load_facts", values, ("day", "scope", "sport_type", "metric_version"))

    def upsert_training_model_daily_fact(self, values: dict[str, object]) -> None:
        self._upsert_fact("training_model_daily", values, ("day", "scope", "sport_type", "metric_version"))

    def upsert_rolling_period_fact(self, values: dict[str, object]) -> None:
        self._upsert_fact(
            "rolling_period_facts",
            values,
            ("as_of_day", "window_days", "scope", "sport_type", "metric_version"),
        )

    def record_read_model_refresh_run(self, values: dict[str, object]) -> int:
        payload = dict(values)
        payload.setdefault("id", self._next_id("read_model_refresh_runs"))
        columns = tuple(payload.keys())
        placeholders = ", ".join("?" for _ in columns)
        self._execute(
            f"INSERT INTO read_model_refresh_runs ({', '.join(columns)}) VALUES ({placeholders})",
            [payload[col] for col in columns],
        )
        return int(payload["id"])

    # Read-model fact queries
    def read_model_status(self, metric_version: int | None = None) -> dict[str, object]:
        if not self._read_model_enabled():
            return {
                "status": "unavailable",
                "last_materialized_at": None,
                "dirty_count": 0,
                "oldest_dirty_day": None,
                "metric_versions_present": [],
                "stale_reason": "read_model_schema_missing",
            }

        params: list[object] = []
        metric_sql = ""
        if metric_version is not None:
            metric_sql = " AND metric_version = ?"
            params.append(metric_version)

        dirty = self._fetchone(
            """
            SELECT COUNT(*) AS dirty_count, MIN(activity_day) AS oldest_dirty_day
            FROM metric_dirty_activities
            WHERE 1=1
            """
            + metric_sql,
            params,
        )
        run = self._fetchone(
            """
            SELECT MAX(finished_at) AS last_materialized_at
            FROM read_model_refresh_runs
            WHERE status = 'ok'
            """
            + metric_sql,
            params,
        )
        # Single pass over the four fact tables: MAX(computed_at) and the set
        # of distinct metric_versions present, in one round-trip. The previous
        # implementation scanned the same union twice (one MAX query plus four
        # separate DISTINCT scans inside a helper), which dominated
        # weekly_digest latency.
        facts_summary = self._fetchone(
            """
            SELECT
                MAX(computed_at) AS last_materialized_at,
                LIST(DISTINCT metric_version ORDER BY metric_version)
                    FILTER (WHERE metric_version IS NOT NULL) AS metric_versions_present
            FROM (
                SELECT computed_at, metric_version FROM activity_metric_facts
                UNION ALL
                SELECT computed_at, metric_version FROM daily_load_facts
                UNION ALL
                SELECT computed_at, metric_version FROM training_model_daily
                UNION ALL
                SELECT computed_at, metric_version FROM rolling_period_facts
            ) all_facts
            WHERE 1=1
            """
            + metric_sql,
            params,
        )

        dirty_count = int(dirty["dirty_count"] or 0) if dirty else 0
        last_materialized_at = None
        if run and run["last_materialized_at"]:
            last_materialized_at = str(run["last_materialized_at"])
        elif facts_summary and facts_summary["last_materialized_at"]:
            last_materialized_at = str(facts_summary["last_materialized_at"])
        raw_versions = facts_summary["metric_versions_present"] if facts_summary else None
        versions: list[int] = (
            sorted(int(v) for v in raw_versions) if raw_versions else []
        )

        status = "current"
        stale_reason = None
        if dirty_count > 0:
            status = "stale"
            stale_reason = "dirty_queue_not_empty"
        elif not versions and last_materialized_at is None:
            status = "unavailable"
            stale_reason = "no_materialized_facts"

        metadata = ReadModelMetadata(
            status=status,
            last_materialized_at=last_materialized_at,
            dirty_count=dirty_count,
            oldest_dirty_day=str(dirty["oldest_dirty_day"]) if dirty and dirty["oldest_dirty_day"] else None,
            metric_versions_present=versions,
            stale_reason=stale_reason,
        )
        return {
            "status": metadata.status,
            "last_materialized_at": metadata.last_materialized_at,
            "dirty_count": metadata.dirty_count,
            "oldest_dirty_day": metadata.oldest_dirty_day,
            "metric_versions_present": metadata.metric_versions_present,
            "stale_reason": metadata.stale_reason,
        }

    def fetch_latest_training_model_day(
        self,
        metric_version: int,
        *,
        as_of_day: str | None = None,
        scope: str = "all",
        sport: str | None = None,
    ) -> dict[str, object] | None:
        if not self._read_model_enabled():
            return None
        where = ["metric_version = ?", "scope = ?", "sport_type = ?"]
        params: list[object] = [metric_version, scope, sport or "all"]
        if as_of_day is not None:
            where.append("day <= CAST(? AS DATE)")
            params.append(as_of_day)
        return self._fetchone(
            f"""
            SELECT *
            FROM training_model_daily
            WHERE {" AND ".join(where)}
            ORDER BY day DESC
            LIMIT 1
            """,
            params,
        )

    def fetch_activity_metric_facts(
        self,
        start_day: str,
        end_day: str,
        *,
        sport: str | None = None,
        metric_version: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> list[dict[str, object]]:
        if not self._read_model_enabled():
            return []
        where = ["f.activity_day >= CAST(? AS DATE)", "f.activity_day < CAST(? AS DATE)"]
        params: list[object] = [start_day, end_day]
        if sport is not None:
            where.append("f.sport_type = ?")
            params.append(sport)
        if metric_version is not None:
            where.append("f.metric_version = ?")
            params.append(metric_version)
        if cursor is not None:
            where.append("(f.activity_day < CAST(? AS DATE) OR (f.activity_day = CAST(? AS DATE) AND f.activity_id < ?))")
            params.extend([cursor, cursor, cursor])
        sql = f"""
            SELECT f.*, a.name AS activity_name, a.date AS activity_date, a.summary_json, a.detail_json
            FROM activity_metric_facts f
            LEFT JOIN activities a ON a.id = f.activity_id
            WHERE {" AND ".join(where)}
            ORDER BY f.activity_day DESC, f.activity_id DESC
        """
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return self._fetchall(sql, params)

    def fetch_activity_metric_fact(self, activity_id: int, metric_version: int | None = None) -> dict[str, object] | None:
        if not self._read_model_enabled():
            return None
        where = ["f.activity_id = ?"]
        params: list[object] = [activity_id]
        if metric_version is not None:
            where.append("f.metric_version = ?")
            params.append(metric_version)
        return self._fetchone(
            f"""
            SELECT f.*, a.name AS activity_name, a.date AS activity_date, a.summary_json, a.detail_json
            FROM activity_metric_facts f
            LEFT JOIN activities a ON a.id = f.activity_id
            WHERE {" AND ".join(where)}
            ORDER BY f.metric_version DESC
            LIMIT 1
            """,
            params,
        )

    def fetch_daily_load_facts(
        self,
        start_day: str,
        end_day: str,
        *,
        scope: str,
        sport: str | None = None,
        metric_version: int | None = None,
    ) -> list[dict[str, object]]:
        if not self._read_model_enabled():
            return []
        where = ["day >= CAST(? AS DATE)", "day < CAST(? AS DATE)", "scope = ?", "sport_type = ?"]
        params: list[object] = [start_day, end_day, scope, sport or "all"]
        if metric_version is not None:
            where.append("metric_version = ?")
            params.append(metric_version)
        return self._fetchall(
            f"""
            SELECT *
            FROM daily_load_facts
            WHERE {" AND ".join(where)}
            ORDER BY day ASC
            """,
            params,
        )

    def fetch_rolling_period_facts(
        self,
        as_of_day: str,
        window_days: int,
        *,
        scope: str,
        sport: str | None = None,
        metric_version: int | None = None,
    ) -> dict[str, object] | None:
        if not self._read_model_enabled():
            return None
        where = ["as_of_day = CAST(? AS DATE)", "window_days = ?", "scope = ?", "sport_type = ?"]
        params: list[object] = [as_of_day, window_days, scope, sport or "all"]
        if metric_version is not None:
            where.append("metric_version = ?")
            params.append(metric_version)
        return self._fetchone(
            f"""
            SELECT *
            FROM rolling_period_facts
            WHERE {" AND ".join(where)}
            ORDER BY metric_version DESC
            LIMIT 1
            """,
            params,
        )

    def fetch_rolling_period_facts_by_windows(
        self,
        as_of_day: str,
        window_days: tuple[int, ...],
        *,
        scope: str,
        sport: str | None = None,
        metric_version: int | None = None,
    ) -> dict[int, dict[str, object]]:
        if not self._read_model_enabled() or not window_days:
            return {}
        window_placeholders = ", ".join("?" for _ in window_days)
        where = [
            "as_of_day = CAST(? AS DATE)",
            f"window_days IN ({window_placeholders})",
            "scope = ?",
            "sport_type = ?",
        ]
        params: list[object] = [as_of_day, *window_days, scope, sport or "all"]
        if metric_version is not None:
            where.append("metric_version = ?")
            params.append(metric_version)
        rows = self._fetchall(
            f"""
            SELECT *
            FROM rolling_period_facts
            WHERE {" AND ".join(where)}
            ORDER BY window_days ASC, metric_version DESC
            """,
            params,
        )
        by_window: dict[int, dict[str, object]] = {}
        for row in rows:
            window = int(row["window_days"])
            by_window.setdefault(window, row)
        return by_window

    # Activities
    def recent_activities(self, limit: int = 15) -> list[RepositoryActivityRow]:
        rows = self._fetchall(
            """
            SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
                   total_elevation_gain, summary_json, detail_json, synced_at
            FROM activities
            ORDER BY activity_day DESC, id DESC
            LIMIT ?
            """,
            [limit],
        )
        return [self._to_activity_row(row) for row in rows]

    def list_activities(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        sport: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> list[RepositoryActivityRow]:
        where: list[str] = []
        params: list[object] = []
        if start_date is not None:
            where.append("activity_day >= CAST(? AS DATE)")
            params.append(start_date)
        if end_date is not None:
            where.append("activity_day <= CAST(? AS DATE)")
            params.append(end_date)
        if sport is not None:
            where.append("sport_type = ?")
            params.append(sport)
        if cursor is not None:
            where.append("date < ?")
            params.append(cursor)
        where_sql = " WHERE " + " AND ".join(where) if where else ""
        rows = self._fetchall(
            """
            SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
                   total_elevation_gain, summary_json, detail_json, synced_at
            FROM activities
            """
            + where_sql
            + """
            ORDER BY activity_day DESC, id DESC
            LIMIT ?
            """,
            [*params, limit],
        )
        return [self._to_activity_row(row) for row in rows]

    def activity_by_id(self, activity_id: int) -> RepositoryActivityRow | None:
        row = self._fetchone(
            """
            SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
                   total_elevation_gain, summary_json, detail_json, synced_at
            FROM activities
            WHERE id = ?
            """,
            [activity_id],
        )
        return self._to_activity_row(row) if row else None

    def activity_rows_between(self, start_day: str, end_day: str) -> list[RepositoryActivityRow]:
        rows = self._fetchall(
            """
            SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
                   total_elevation_gain, summary_json, detail_json, synced_at
            FROM activities
            WHERE activity_day BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
            ORDER BY activity_day ASC, id ASC
            """,
            [start_day, end_day],
        )
        return [self._to_activity_row(row) for row in rows]

    def daily_activity_presence(self, day: str) -> bool:
        return self._fetchone(
            "SELECT 1 FROM activities WHERE activity_day = CAST(? AS DATE) LIMIT 1",
            [day],
        ) is not None

    def first_activity_day(self, sport_filter: str | None = None) -> str | None:
        sport_sql, sport_params = self._sport_where_clause(sport_filter)
        row = self._fetchone(
            """
            SELECT MIN(activity_day) AS day
            FROM activities a
            WHERE 1=1
            """
            + sport_sql,
            sport_params,
        )
        return str(row["day"]) if row and row["day"] else None

    def latest_activity_at(self) -> str | None:
        row = self._fetchone("SELECT MAX(date) AS latest FROM activities")
        return str(row["latest"]) if row and row["latest"] else None

    def latest_activity_id(self) -> int | None:
        row = self._fetchone(
            """
            SELECT id
            FROM activities
            ORDER BY activity_day DESC, id DESC
            LIMIT 1
            """
        )
        return int(row["id"]) if row and row["id"] is not None else None

    def upsert_activity_summary(
        self,
        *,
        activity_id: int,
        date: str,
        name: str,
        sport_type: str,
        distance: float,
        moving_time: int,
        elapsed_time: int,
        total_elevation_gain: float,
        summary_json: str,
        synced_at: str,
    ) -> None:
        self.begin()
        try:
            self._execute(
                """
                INSERT INTO activities (
                    id, activity_day, date, name, sport_type, distance, moving_time,
                    elapsed_time, total_elevation_gain, summary_json, synced_at
                ) VALUES (?, CAST(? AS DATE), ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    activity_day=excluded.activity_day,
                    date=excluded.date,
                    name=excluded.name,
                    sport_type=excluded.sport_type,
                    distance=excluded.distance,
                    moving_time=excluded.moving_time,
                    elapsed_time=excluded.elapsed_time,
                    total_elevation_gain=excluded.total_elevation_gain,
                    summary_json=excluded.summary_json,
                    synced_at=excluded.synced_at
                """,
                [
                    activity_id,
                    date[:10],
                    date,
                    name,
                    sport_type,
                    distance,
                    moving_time,
                    elapsed_time,
                    total_elevation_gain,
                    summary_json,
                    synced_at,
                ],
            )
            self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            self.rollback()
            raise
        self.commit()

    def update_activity_detail(self, activity_id: int, detail_json: str) -> None:
        self.begin()
        try:
            self._execute("UPDATE activities SET detail_json = ? WHERE id = ?", [detail_json, activity_id])
            self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            self.rollback()
            raise
        self.commit()

    # Streams and load
    def activity_stream_rows(self, activity_id: int) -> list[dict[str, object]]:
        return self._fetchall(
            """
            SELECT activity_id, time_offset, heartrate, velocity, altitude,
                   cadence, lat, lng, grade, gap_speed, gap_distance, is_moving, values_json
            FROM streams
            WHERE activity_id = ?
            ORDER BY time_offset ASC
            """,
            [activity_id],
        )

    def _sport_where_clause(self, sport_filter: str | None) -> tuple[str, list[object]]:
        params: list[object] = []
        if sport_filter == "training":
            placeholders = ",".join("?" * len(TRAINING_SPORTS))
            params.extend(TRAINING_SPORTS)
            return f" AND a.sport_type IN ({placeholders})", params
        return "", params

    def observed_trimp_history(
        self,
        *,
        bounds: list[int],
        since_day: str | None = None,
        until_day: str | None = None,
        sport_filter: str | None = None,
    ) -> dict[str, float]:
        """Return daily TRIMP history keyed by ISO date string.

        Args:
            bounds: Precomputed integer zone upper bounds from zone_bounds().
                    Caller must compute from (running hr_max, hr_rest from settings).
                    No default — callers must supply bounds explicitly.
        """
        where = ["s.heartrate IS NOT NULL"]
        params: list[object] = []
        if since_day is not None:
            where.append("a.activity_day >= CAST(? AS DATE)")
            params.append(since_day)
        if until_day is not None:
            where.append("a.activity_day <= CAST(? AS DATE)")
            params.append(until_day)
        sport_sql, sport_params = self._sport_where_clause(sport_filter)
        params.extend(sport_params)
        rows = self._fetchall(
            """
            SELECT a.activity_day AS day,
                   """
            + build_trimp_sql(bounds, alias="s.")
            + """
            FROM activities a
            JOIN streams s ON a.id = s.activity_id
            WHERE """
            + " AND ".join(where)
            + sport_sql
            + """
            GROUP BY day
            """,
            params,
        )
        return {str(row["day"]): round(float(row["trimp"]), 1) for row in rows}

    def daily_load_status(self, day: str) -> RepositoryDailyLoadStatus:
        activity_count = int(self._scalar("SELECT COUNT(*) FROM activities WHERE activity_day = CAST(? AS DATE)", [day]) or 0)
        stream_count = int(
            self._scalar(
                """
                SELECT COUNT(*)
                FROM streams s
                JOIN activities a ON a.id = s.activity_id
                WHERE a.activity_day = CAST(? AS DATE)
                """,
                [day],
            )
            or 0
        )
        hr_count = int(
            self._scalar(
                """
                SELECT COUNT(*)
                FROM streams s
                JOIN activities a ON a.id = s.activity_id
                WHERE a.activity_day = CAST(? AS DATE)
                  AND s.heartrate IS NOT NULL
                """,
                [day],
            )
            or 0
        )
        if activity_count == 0:
            status = "REST"
        elif stream_count == 0:
            status = "UNKNOWN"
        elif hr_count == 0:
            status = "PARTIAL"
        else:
            status = "OBSERVED"
        return RepositoryDailyLoadStatus(
            day=day,
            status=status,
            observed_trimp=0.0,
            effective_trimp=0.0,
            activity_count=activity_count,
            stream_points=stream_count,
            heartrate_points=hr_count,
        )

    def daily_load_points_between(
        self,
        start_day: str,
        end_day: str,
        *,
        bounds: list[int],
        sport_filter: str | None = None,
    ) -> list[DailyLoadPoint]:
        daily_activity_counts: dict[str, int] = {}
        daily_stream_counts: dict[str, int] = {}
        daily_hr_counts: dict[str, int] = {}
        sport_sql, sport_params = self._sport_where_clause(sport_filter)

        act_rows = self._fetchall(
            """
            SELECT activity_day AS day, COUNT(*) AS c
            FROM activities a
            WHERE activity_day BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
            """
            + sport_sql
            + """
            GROUP BY day
            """,
            [start_day, end_day, *sport_params],
        )
        for row in act_rows:
            daily_activity_counts[str(row["day"])] = int(row["c"])

        stream_rows = self._fetchall(
            """
            SELECT a.activity_day AS day, COUNT(*) AS c
            FROM activities a
            JOIN streams s ON s.activity_id = a.id
            WHERE a.activity_day BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
            """
            + sport_sql
            + """
            GROUP BY day
            """,
            [start_day, end_day, *sport_params],
        )
        for row in stream_rows:
            daily_stream_counts[str(row["day"])] = int(row["c"])

        hr_rows = self._fetchall(
            """
            SELECT a.activity_day AS day, COUNT(*) AS c
            FROM activities a
            JOIN streams s ON s.activity_id = a.id
            WHERE a.activity_day BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
              AND s.heartrate IS NOT NULL
            """
            + sport_sql
            + """
            GROUP BY day
            """,
            [start_day, end_day, *sport_params],
        )
        for row in hr_rows:
            daily_hr_counts[str(row["day"])] = int(row["c"])

        observed_trimp = self.observed_trimp_history(
            bounds=bounds,
            since_day=start_day,
            until_day=end_day,
            sport_filter=sport_filter,
        )
        points: list[DailyLoadPoint] = []
        current = date.fromisoformat(start_day)
        end = date.fromisoformat(end_day)
        while current <= end:
            current_text = current.isoformat()
            activity_count = daily_activity_counts.get(current_text, 0)
            stream_count = daily_stream_counts.get(current_text, 0)
            hr_count = daily_hr_counts.get(current_text, 0)
            if activity_count == 0:
                status = "REST"
                observed = None
                effective = 0.0
            elif stream_count == 0:
                status = "UNKNOWN"
                observed = None
                effective = 0.0
            elif hr_count == 0:
                status = "PARTIAL"
                observed = None
                effective = 0.0
            else:
                status = "OBSERVED"
                observed = round(observed_trimp.get(current_text, 0.0), 1)
                effective = observed
            points.append(
                DailyLoadPoint(
                    date=current_text,
                    status=status,
                    observed_trimp=observed,
                    effective_trimp=effective,
                    activity_count=activity_count,
                    stream_points=stream_count,
                    heartrate_points=hr_count,
                )
            )
            current = current.fromordinal(current.toordinal() + 1)
        return points

    def effective_trimp_history(
        self,
        start_day: str,
        end_day: str,
        *,
        bounds: list[int],
        sport_filter: str | None = None,
    ) -> dict[str, float]:
        return {
            point.date: point.effective_trimp
            for point in self.daily_load_points_between(
                start_day, end_day, bounds=bounds, sport_filter=sport_filter
            )
        }

    def activity_moving_time(self, activity_id: int) -> int | None:
        row = self._fetchone("SELECT moving_time FROM activities WHERE id = ?", [activity_id])
        return int(row["moving_time"]) if row and row["moving_time"] is not None else None

    def stream_hr_velocity_rows(self, activity_id: int, min_velocity: float) -> list[dict[str, object]]:
        return self._fetchall(
            """
            SELECT time_offset, heartrate, velocity, grade FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL AND velocity IS NOT NULL
              AND velocity > ?
            ORDER BY time_offset
            """,
            [activity_id, min_velocity],
        )

    def stream_hr_velocity_simple_rows(self, activity_id: int, min_velocity: float) -> list[dict[str, object]]:
        return self._fetchall(
            """
            SELECT heartrate, velocity FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL AND velocity > ?
            ORDER BY time_offset
            """,
            [activity_id, min_velocity],
        )

    def stream_hr_velocity_time_rows(self, activity_id: int) -> list[dict[str, object]]:
        return self._fetchall(
            """
            SELECT time_offset, heartrate, velocity FROM streams
            WHERE activity_id=? AND heartrate IS NOT NULL
            ORDER BY time_offset
            """,
            [activity_id],
        )

    def activity_hr_summary(self, activity_id: int) -> tuple[float | None, int]:
        row = self._fetchone(
            """
            SELECT AVG(heartrate) AS avg_hr, COUNT(*) AS n
            FROM streams WHERE activity_id=? AND heartrate IS NOT NULL
            """,
            [activity_id],
        )
        return (float(row["avg_hr"]), int(row["n"] or 0)) if row and row["avg_hr"] is not None else (None, 0)

    def activity_avg_velocity(self, activity_id: int) -> float | None:
        row = self._fetchone(
            "SELECT AVG(velocity) AS avg_vel FROM streams WHERE activity_id=? AND velocity IS NOT NULL",
            [activity_id],
        )
        return float(row["avg_vel"]) if row and row["avg_vel"] is not None else None

    def stream_hr_time_rows(self, activity_id: int) -> list[dict[str, object]]:
        return self._fetchall(
            """
            SELECT time_offset, heartrate FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL
            ORDER BY time_offset
            """,
            [activity_id],
        )

    def stream_altitude_rows(self, activity_id: int) -> list[dict[str, object]]:
        return self._fetchall(
            """
            SELECT time_offset, altitude FROM streams
            WHERE activity_id=? AND altitude IS NOT NULL
            ORDER BY time_offset
            """,
            [activity_id],
        )

    def stream_counts_for_activity(self, activity_id: int) -> tuple[int, int]:
        """Return (stream_count, hr_count) for an activity.

        Used by the materializer to classify completeness.
        """
        row = self._fetchone(
            """
        SELECT COUNT(*) AS stream_count,
               SUM(CASE WHEN heartrate IS NOT NULL THEN 1 ELSE 0 END) AS hr_count
        FROM streams
        WHERE activity_id = ?
        """,
            [activity_id],
        )
        return int(row["stream_count"] or 0), int(row["hr_count"] or 0)

    def zone_seconds_for_activity(self, activity_id: int, bounds: list[int]) -> tuple[int, int, int, int, int]:
        """Return (z1, z2, z3, z4, z5) second counts using precomputed zone bounds.

        Parameter order [b[0], b[0], b[1], b[1], b[2], b[2], b[3], b[-2], activity_id]
        is preserved verbatim to keep results byte-identical.
        """
        b = bounds
        row = self._fetchone(
            """
        SELECT
          SUM(CASE WHEN heartrate < ? THEN 1 ELSE 0 END) AS z1,
          SUM(CASE WHEN heartrate >= ? AND heartrate < ? THEN 1 ELSE 0 END) AS z2,
          SUM(CASE WHEN heartrate >= ? AND heartrate < ? THEN 1 ELSE 0 END) AS z3,
          SUM(CASE WHEN heartrate >= ? AND heartrate < ? THEN 1 ELSE 0 END) AS z4,
          SUM(CASE WHEN heartrate >= ? THEN 1 ELSE 0 END) AS z5
        FROM streams
        WHERE activity_id = ? AND heartrate IS NOT NULL
        """,
            [b[0], b[0], b[1], b[1], b[2], b[2], b[3], b[-2], activity_id],
        )
        return tuple(int(row[f"z{idx}"] or 0) for idx in range(1, 6))

    def daily_fact_sums(self, activity_day: str, metric_version: int) -> dict[str, object] | None:
        """Return the SUM aggregates over activity_metric_facts for one day and metric version.

        Used when rolling up per-activity facts into daily_load_facts.
        """
        return self._fetchone(
            """
            SELECT
              SUM(distance_m) AS distance_m,
              SUM(moving_time_s) AS moving_time_s,
              SUM(elevation_gain_m) AS elevation_gain_m,
              SUM(zone4_seconds) AS zone4_seconds,
              SUM(zone5_seconds) AS zone5_seconds,
              SUM(anomaly_count) AS anomaly_count
            FROM activity_metric_facts
            WHERE activity_day = CAST(? AS DATE) AND metric_version = ?
            """,
            [activity_day, metric_version],
        )

    def rolling_load_aggregate(self, start: str, as_of_day: str, metric_version: int) -> dict[str, object] | None:
        """Return the rolling-window load aggregate from daily_load_facts between start and as_of_day.

        Filters for scope='all', sport_type='all'. Used by _materialize_rolling_facts.
        """
        return self._fetchone(
            """
            SELECT
              COUNT(*) AS days,
              SUM(activity_count) AS activity_count,
              SUM(CASE WHEN activity_count > 0 THEN 1 ELSE 0 END) AS active_days,
              SUM(CASE WHEN activity_count = 0 THEN 1 ELSE 0 END) AS rest_days,
              SUM(observed_trimp) AS observed_trimp,
              SUM(effective_trimp) AS effective_trimp,
              SUM(distance_m) AS distance_m,
              SUM(moving_time_s) AS moving_time_s,
              SUM(elevation_gain_m) AS elevation_gain_m,
              SUM(high_zone_seconds) AS high_zone_seconds,
              SUM(anomaly_count) AS anomaly_count
            FROM daily_load_facts
            WHERE day BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
              AND scope = 'all'
              AND sport_type = 'all'
              AND metric_version = ?
            """,
            [start, as_of_day, metric_version],
        )

    def training_model_row(self, as_of_day: str, metric_version: int) -> dict[str, object] | None:
        """Return the fitness/fatigue/form/zones row from training_model_daily for as_of_day.

        Filters for scope='all', sport_type='all'.
        """
        return self._fetchone(
            """
            SELECT fitness, fatigue, form, form_zone, acwr_zone, acwr
            FROM training_model_daily
            WHERE day = CAST(? AS DATE) AND scope = 'all' AND sport_type = 'all' AND metric_version = ?
            """,
            [as_of_day, metric_version],
        )

    def rolling_cardiac_metric_rows(self, start: str, as_of_day: str, metric_version: int) -> list[dict[str, object]]:
        """Return per-activity cardiac metric rows from activity_metric_facts for the rolling window.

        Columns: cardiac_cost, adjusted_cardiac_cost, hr_recovery_median_rate, cardiac_drift_pct.
        Used to compute rolling medians.
        """
        return self._fetchall(
            """
            SELECT cardiac_cost, adjusted_cardiac_cost, hr_recovery_median_rate, cardiac_drift_pct
            FROM activity_metric_facts
            WHERE activity_day BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
              AND metric_version = ?
            """,
            [start, as_of_day, metric_version],
        )

    def activity_trimp(self, activity_id: int, *, bounds: list[int]) -> float:
        """Compute TRIMP for an activity using explicit zone bounds.

        Args:
            activity_id: The activity to compute TRIMP for.
            bounds: Precomputed integer zone upper bounds from zone_bounds().
                    Caller is responsible for obtaining bounds from (hr_max, hr_rest).
                    No default — callers must compute bounds explicitly.
        """
        row = self._fetchone(
            "SELECT " + build_trimp_sql(bounds) + " FROM streams WHERE activity_id = ?",
            [activity_id],
        )
        return round(float(row["trimp"]), 1) if row and row["trimp"] is not None else 0.0

    def max_heartrate_to_date(self, activity_day: str) -> int | None:
        """Return the running max heartrate observed up to and including activity_day.

        Used by the materializer to compute zone bounds for each activity based on
        observations available at the time of that activity, not the all-time max.

        Returns int or None when no HR samples exist up to that date.
        """
        row = self._fetchone(
            """
            SELECT MAX(s.heartrate) AS hr_max
            FROM streams s
            JOIN activities a ON a.id = s.activity_id
            WHERE s.heartrate IS NOT NULL
              AND a.activity_day <= CAST(? AS DATE)
            """,
            [activity_day],
        )
        return int(row["hr_max"]) if row and row["hr_max"] is not None else None

    def activity_hr_range(self, activity_id: int) -> tuple[int | None, int | None]:
        """Return (min_hr, max_hr) from stream heartrate samples for an activity.

        Used to persist provenance (observed_min_hr, observed_max_hr) alongside
        each materialised activity fact.

        Returns (None, None) when the activity has no HR samples.
        """
        row = self._fetchone(
            """
            SELECT MIN(heartrate) AS min_hr, MAX(heartrate) AS max_hr
            FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL
            """,
            [activity_id],
        )
        if row and row["min_hr"] is not None:
            return int(row["min_hr"]), int(row["max_hr"])
        return None, None

    def activity_cc(self, activity_id: int, min_velocity: float) -> float | None:
        row = self._fetchone(
            """
            SELECT AVG(heartrate) AS avg_hr, AVG(velocity) AS avg_vel
            FROM streams WHERE activity_id = ? AND heartrate IS NOT NULL
              AND velocity > ?
            """,
            [activity_id, min_velocity],
        )
        if not row or not row["avg_hr"] or not row["avg_vel"] or float(row["avg_vel"]) <= 0:
            return None
        return round(float(row["avg_hr"]) / float(row["avg_vel"]), 2)

    def activity_median_heartrate(self, activity_id: int) -> float | None:
        row = self._fetchone(
            """
            SELECT median(heartrate) AS median_hr
            FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL
            """,
            [activity_id],
        )
        return float(row["median_hr"]) if row and row["median_hr"] is not None else None

    def max_heartrate(self) -> float | None:
        row = self._fetchone("SELECT MAX(heartrate) AS hr FROM streams WHERE heartrate IS NOT NULL")
        return float(row["hr"]) if row and row["hr"] is not None else None

    def activity_z5_seconds(self, activity_id: int, z5_threshold: int) -> int:
        return int(
            self._scalar(
                "SELECT COUNT(*) AS sec FROM streams WHERE activity_id = ? AND heartrate >= ?",
                [activity_id, z5_threshold],
            )
            or 0
        )

    def activity_efficiency_rows(self) -> list[dict[str, object]]:
        return self._fetchall(
            """
            SELECT a.activity_day AS day, a.sport_type,
                   a.distance / 1000 AS dist_km, a.moving_time / 60.0 AS time_min,
                   a.total_elevation_gain AS elev,
                   AVG(s.heartrate) AS avg_hr, AVG(s.velocity) AS avg_vel
            FROM activities a
            JOIN streams s ON a.id = s.activity_id
            WHERE s.heartrate IS NOT NULL AND s.velocity > 0
            GROUP BY a.id, a.activity_day, a.sport_type, a.distance, a.moving_time, a.total_elevation_gain
            HAVING avg_hr > 0 AND avg_vel > 0
            """
        )

    def total_distance_km_between(self, start_day: str, end_day: str, sports: tuple[str, ...] | list[str]) -> float:
        if not sports:
            return 0.0
        placeholders = ",".join("?" * len(sports))
        row = self._fetchone(
            f"""
            SELECT SUM(distance)/1000 AS km FROM activities
            WHERE sport_type IN ({placeholders})
              AND activity_day >= CAST(? AS DATE)
              AND activity_day <= CAST(? AS DATE)
            """,
            [*sports, start_day, end_day],
        )
        return float(row["km"] or 0.0) if row else 0.0

    def insert_stream_rows_chunked(
        self,
        activity_id: int,
        rows: Iterable[dict],
        chunk_size: int = 5000,
    ) -> int:
        payload = list(rows)
        total = len(payload)
        if total == 0:
            return 0
        self.begin()
        try:
            self._insert_stream_rows(activity_id, payload, chunk_size)
            self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            self.rollback()
            raise
        self.commit()
        return total

    def replace_stream_rows_chunked(
        self,
        activity_id: int,
        rows: Iterable[dict],
        chunk_size: int = 5000,
    ) -> int:
        payload = list(rows)
        if not payload:
            return 0
        self.begin()
        try:
            self._execute("DELETE FROM streams WHERE activity_id = ?", [activity_id])
            self._insert_stream_rows(activity_id, payload, chunk_size)
            self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            self.rollback()
            raise
        self.commit()
        return len(payload)

    def _insert_stream_rows(self, activity_id: int, rows: list[dict], chunk_size: int) -> None:
        for start in range(0, len(rows), chunk_size):
            chunk = rows[start : start + chunk_size]
            bound = [
                (
                    activity_id,
                    row["time_offset"],
                    row.get("heartrate"),
                    row.get("velocity"),
                    row.get("altitude"),
                    row.get("cadence"),
                    row.get("lat"),
                    row.get("lng"),
                    row.get("grade"),
                    row.get("gap_speed"),
                    row.get("gap_distance"),
                    row.get("is_moving"),
                    row.get("values_json"),
                )
                for row in chunk
            ]
            self._executemany(
                """
                INSERT INTO streams
                (activity_id, time_offset, heartrate, velocity, altitude, cadence,
                 lat, lng, grade, gap_speed, gap_distance, is_moving, values_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(activity_id, time_offset) DO UPDATE SET
                    heartrate=excluded.heartrate,
                    velocity=excluded.velocity,
                    altitude=excluded.altitude,
                    cadence=excluded.cadence,
                    lat=excluded.lat,
                    lng=excluded.lng,
                    grade=excluded.grade,
                    gap_speed=excluded.gap_speed,
                    gap_distance=excluded.gap_distance,
                    is_moving=excluded.is_moving,
                    values_json=excluded.values_json
                """,
                bound,
            )

    def delete_stream_rows_for_activity(self, activity_id: int) -> None:
        self.begin()
        try:
            self._execute("DELETE FROM streams WHERE activity_id = ?", [activity_id])
            self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            self.rollback()
            raise
        self.commit()

    def upsert_stream_channel_metadata(
        self,
        activity_id: int,
        channel_key: str,
        original_size: int | None,
        resolution: str | None,
        series_type: str | None,
        fetched_at: str | None,
        batch_id: str | None,
        status: str,
        error: str | None,
        commit: bool = True,
    ) -> None:
        if commit:
            self.begin()
        try:
            self._execute(
                """
                INSERT INTO stream_channels (
                    activity_id, channel_key, original_size, resolution, series_type,
                    fetched_at, batch_id, status, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(activity_id, channel_key) DO UPDATE SET
                    original_size=excluded.original_size,
                    resolution=excluded.resolution,
                    series_type=excluded.series_type,
                    fetched_at=excluded.fetched_at,
                    batch_id=excluded.batch_id,
                    status=excluded.status,
                    error=excluded.error
                """,
                [
                    activity_id,
                    channel_key,
                    original_size,
                    resolution,
                    series_type,
                    fetched_at or self._now_iso(),
                    batch_id,
                    status,
                    error,
                ],
            )
            if commit:
                self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            if commit:
                self.rollback()
            raise
        if commit:
            self.commit()

    def replace_stream_rows_and_channel_metadata(
        self,
        activity_id: int,
        rows: Iterable[dict],
        metadata: Iterable[dict],
        chunk_size: int = 5000,
    ) -> int:
        payload = list(rows)
        self.begin()
        try:
            self._execute("DELETE FROM streams WHERE activity_id = ?", [activity_id])
            self._execute("DELETE FROM stream_channels WHERE activity_id = ?", [activity_id])
            self._insert_stream_rows(activity_id, payload, chunk_size)
            for item in metadata:
                self.upsert_stream_channel_metadata(
                    activity_id=activity_id,
                    channel_key=item["channel_key"],
                    original_size=item.get("original_size"),
                    resolution=item.get("resolution"),
                    series_type=item.get("series_type"),
                    fetched_at=item.get("fetched_at"),
                    batch_id=item.get("batch_id"),
                    status=item.get("status", "available"),
                    error=item.get("error"),
                    commit=False,
                )
            self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            self.rollback()
            raise
        self.commit()
        return len(payload)

    def merge_stream_channel_values(
        self,
        activity_id: int,
        rows: Iterable[dict],
        metadata: Iterable[dict],
        missing_channel_keys: Iterable[str],
    ) -> int:
        payload = list(rows)
        self.begin()
        try:
            for row in payload:
                if "time_offset" not in row:
                    continue
                existing = self._fetchone(
                    "SELECT values_json FROM streams WHERE activity_id=? AND time_offset=?",
                    [activity_id, row["time_offset"]],
                )
                if existing is None:
                    continue
                existing_map = json.loads(str(existing["values_json"])) if existing.get("values_json") else {}
                values_map = existing_map | (row.get("values") or {})
                self._execute(
                    "UPDATE streams SET values_json=? WHERE activity_id=? AND time_offset=?",
                    [json.dumps(values_map, ensure_ascii=True), activity_id, row["time_offset"]],
                )
            for channel_key in missing_channel_keys:
                self._execute(
                    """
                    INSERT INTO stream_channels (activity_id, channel_key, fetched_at, status)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(activity_id, channel_key) DO UPDATE SET status=excluded.status
                    """,
                    [activity_id, channel_key, self._now_iso(), "unavailable"],
                )
            for item in metadata:
                self.upsert_stream_channel_metadata(
                    activity_id=activity_id,
                    channel_key=item["channel_key"],
                    original_size=item.get("original_size"),
                    resolution=item.get("resolution"),
                    series_type=item.get("series_type"),
                    fetched_at=item.get("fetched_at"),
                    batch_id=item.get("batch_id"),
                    status=item.get("status", "available"),
                    error=item.get("error"),
                    commit=False,
                )
            self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            self.rollback()
            raise
        self.commit()
        return len(payload)

    def activities_missing_stream_channels(
        self,
        *,
        since: str | None = None,
        limit: int | None = None,
        requested_channels: Iterable[str],
    ) -> list[dict]:
        channel_list = list(requested_channels)
        rows = self._fetchall(
            """
            SELECT a.id, a.date
            FROM activities a
            WHERE EXISTS (SELECT 1 FROM streams s WHERE s.activity_id = a.id)
              AND (? IS NULL OR a.activity_day >= CAST(? AS DATE))
            ORDER BY a.activity_day DESC, a.id DESC
            """,
            [since, since],
        )
        results: list[dict] = []
        for row in rows:
            if limit is not None and len(results) >= limit:
                break
            activity_id = int(row["id"])
            missing_channels: list[str] = []
            metadata_missing = False
            for channel in channel_list:
                meta = self._fetchone(
                    """
                    SELECT status FROM stream_channels
                    WHERE activity_id=? AND channel_key=?
                    """,
                    [activity_id, channel],
                )
                if meta is None:
                    metadata_missing = True
                    missing_channels.append(channel)
                    continue
                status = meta["status"]
                if status in {"missing", "error"}:
                    missing_channels.append(channel)
                    continue
                if status == "unavailable":
                    continue
                if status != "available":
                    missing_channels.append(channel)
                    continue
                if channel in {"distance", "watts", "temp"}:
                    value_rows = self._fetchall(
                        """
                        SELECT values_json
                        FROM streams
                        WHERE activity_id=?
                          AND values_json IS NOT NULL
                        """,
                        [activity_id],
                    )
                    if not any(channel in (json.loads(str(item["values_json"])) if item["values_json"] else {}) for item in value_rows):
                        missing_channels.append(channel)
            if missing_channels or metadata_missing:
                results.append(
                    {
                        "activity_id": activity_id,
                        "missing_channels": sorted(set(missing_channels)),
                        "metadata_missing": metadata_missing,
                    }
                )
        return results

    def stream_channel_coverage(self) -> dict[str, int]:
        row = self._fetchone(
            """
            SELECT
                COUNT(*) AS channels,
                COUNT(DISTINCT activity_id) AS activities_with_channel_metadata,
                SUM(CASE WHEN status='available' THEN 1 ELSE 0 END) AS available_channels,
                SUM(CASE WHEN status='unavailable' THEN 1 ELSE 0 END) AS unavailable_channels,
                SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS error_channels
            FROM stream_channels
            """
        )
        return {
            "channels": int(row["channels"] or 0) if row else 0,
            "activities_with_channel_metadata": int(row["activities_with_channel_metadata"] or 0) if row else 0,
            "available_channels": int(row["available_channels"] or 0) if row else 0,
            "unavailable_channels": int(row["unavailable_channels"] or 0) if row else 0,
            "error_channels": int(row["error_channels"] or 0) if row else 0,
        }

    # Zones
    def latest_athlete_zones(self) -> str | None:
        row = self._fetchone("SELECT zones_json FROM athlete_zones ORDER BY fetched_at DESC LIMIT 1")
        return str(row["zones_json"]) if row else None

    def insert_athlete_zones(self, fetched_at: str, zones_json: str) -> None:
        self._execute(
            "INSERT INTO athlete_zones (id, fetched_at, zones_json) VALUES (?, ?, ?)",
            [self._next_id("athlete_zones"), fetched_at, zones_json],
        )
        self._commit_if_standalone()

    # Kudos
    def list_kudos(self, limit: int = 100) -> list[dict[str, object]]:
        return self._fetchall(
            """
            SELECT activity_id, firstname, lastname, fetched_at
            FROM kudos
            ORDER BY fetched_at DESC
            LIMIT ?
            """,
            [limit],
        )

    def kudos_for_activity(self, activity_id: int) -> list[dict[str, object]]:
        return self._fetchall(
            """
            SELECT activity_id, firstname, lastname, fetched_at
            FROM kudos
            WHERE activity_id = ?
            ORDER BY firstname, lastname
            """,
            [activity_id],
        )

    def upsert_kudos(self, activity_id: int, firstname: str, lastname: str, fetched_at: str) -> None:
        self._execute(
            """
            INSERT INTO kudos (activity_id, firstname, lastname, fetched_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(activity_id, firstname, lastname) DO UPDATE SET
              fetched_at = excluded.fetched_at
            """,
            [activity_id, firstname, lastname, fetched_at],
        )
        self._commit_if_standalone()

    # Sync metadata
    def append_sync_log(
        self,
        *,
        timestamp: str,
        status: str,
        activities_seen: int | None,
        activities_new: int | None,
        streams_fetched: int | None,
        details_fetched: int | None,
        api_calls: int | None,
        error: str | None,
        kudos_fetched: int | None,
    ) -> None:
        self._execute(
            """
            INSERT INTO sync_log (
                id, timestamp, status, activities_seen, activities_new,
                streams_fetched, details_fetched, api_calls, error, kudos_fetched
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                self._next_id("sync_log"),
                timestamp,
                status,
                activities_seen,
                activities_new,
                streams_fetched,
                details_fetched,
                api_calls,
                error,
                kudos_fetched,
            ],
        )
        self._commit_if_standalone()

    def read_sync_log(self, limit: int = 20) -> list[RepositorySyncLogEntry]:
        rows = self._fetchall(
            """
            SELECT timestamp, status, activities_seen, activities_new,
                   streams_fetched, details_fetched, api_calls, error, kudos_fetched
            FROM sync_log
            ORDER BY id DESC
            LIMIT ?
            """,
            [limit],
        )
        return [
            RepositorySyncLogEntry(
                timestamp=str(row["timestamp"]),
                status=str(row["status"]),
                activities_seen=row["activities_seen"],
                activities_new=row["activities_new"],
                streams_fetched=row["streams_fetched"],
                details_fetched=row["details_fetched"],
                api_calls=row["api_calls"],
                error=row["error"],
                kudos_fetched=row["kudos_fetched"],
            )
            for row in rows
        ]

    # Refresh runtime metadata
    def get_refresh_state(self) -> RefreshStateRow:
        row = self._fetchone("SELECT * FROM refresh_state WHERE id = 1")
        if row is None:
            self._execute("INSERT INTO refresh_state (id) VALUES (1)")
            self._commit_if_standalone()
            row = self._fetchone("SELECT * FROM refresh_state WHERE id = 1")
        return RefreshStateRow(
            id=int(row["id"]),
            last_success_at=row["last_success_at"],
            last_attempt_at=row["last_attempt_at"],
            last_status=row["last_status"],
            last_error_code=row["last_error_code"],
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            backoff_until=row["backoff_until"],
            checkpoint_stage=row["checkpoint_stage"],
            checkpoint_cursor=row["checkpoint_cursor"],
        )

    def acquire_refresh_lease(self, owner: str, expires_at: str, now: str) -> bool:
        self.get_refresh_state()
        existing = self._fetchone(
            """
            SELECT lease_owner, lease_expires_at
            FROM refresh_state
            WHERE id = 1
            """
        )
        if (
            existing is not None
            and existing["lease_owner"] is not None
            and existing["lease_expires_at"] is not None
            and str(existing["lease_expires_at"]) >= now
        ):
            return False
        self._execute(
            """
            UPDATE refresh_state
            SET lease_owner = ?, lease_expires_at = ?
            WHERE id = 1
            """,
            [owner, expires_at],
        )
        self._commit_if_standalone()
        return True

    def release_refresh_lease(self, owner: str) -> None:
        self._execute(
            """
            UPDATE refresh_state
            SET lease_owner = NULL, lease_expires_at = NULL
            WHERE id = 1 AND lease_owner = ?
            """,
            [owner],
        )
        self._commit_if_standalone()

    def renew_refresh_lease(self, owner: str, expires_at: str) -> bool:
        existing = self._fetchone("SELECT lease_owner FROM refresh_state WHERE id = 1")
        if existing is None or existing["lease_owner"] != owner:
            return False
        self._execute(
            """
            UPDATE refresh_state
            SET lease_expires_at = ?
            WHERE id = 1 AND lease_owner = ?
            """,
            [expires_at, owner],
        )
        self._commit_if_standalone()
        return True

    def set_checkpoint(self, stage: str, cursor: str | None) -> None:
        self.get_refresh_state()
        self._execute(
            """
            UPDATE refresh_state
            SET checkpoint_stage = ?, checkpoint_cursor = ?
            WHERE id = 1
            """,
            [stage, cursor],
        )
        self._commit_if_standalone()

    def record_refresh_attempt(self, at: str) -> None:
        self.get_refresh_state()
        self._execute("UPDATE refresh_state SET last_attempt_at = ? WHERE id = 1", [at])
        self._commit_if_standalone()

    def record_refresh_success(self, at: str) -> None:
        self.get_refresh_state()
        self._execute(
            """
            UPDATE refresh_state
            SET last_success_at = ?, last_attempt_at = ?, last_status = 'ok',
                last_error_code = NULL, backoff_until = NULL
            WHERE id = 1
            """,
            [at, at],
        )
        self._commit_if_standalone()

    def record_refresh_failure(self, at: str, reason_code: str, backoff_until: str | None) -> None:
        if reason_code not in ALLOWED_REASON_CODES:
            raise ValueError(f"Unknown refresh failure reason: {reason_code}")
        self.get_refresh_state()
        self._execute(
            """
            UPDATE refresh_state
            SET last_attempt_at = ?, last_status = 'failed',
                last_error_code = ?, backoff_until = ?
            WHERE id = 1
            """,
            [at, reason_code, backoff_until],
        )
        self._commit_if_standalone()

    def enqueue_refresh_request(self, reason: str, requested_for_day: str, requested_at: str | None = None) -> bool:
        timestamp = requested_at or requested_for_day
        existing = self._fetchone(
            """
            SELECT id
            FROM refresh_requests
            WHERE reason = ? AND requested_for_day = ? AND consumed_at IS NULL
            LIMIT 1
            """,
            [reason, requested_for_day],
        )
        if existing is not None:
            return False
        self._execute(
            """
            INSERT INTO refresh_requests (id, reason, requested_for_day, requested_at)
            VALUES (?, ?, ?, ?)
            """,
            [self._next_id("refresh_requests"), reason, requested_for_day, timestamp],
        )
        self._commit_if_standalone()
        return True

    def pending_refresh_requests(self) -> list[RefreshRequestRow]:
        rows = self._fetchall(
            """
            SELECT id, reason, requested_for_day, requested_at, consumed_at
            FROM refresh_requests
            WHERE consumed_at IS NULL
            ORDER BY id
            """
        )
        return [
            RefreshRequestRow(
                id=int(row["id"]),
                reason=str(row["reason"]),
                requested_for_day=str(row["requested_for_day"]),
                requested_at=str(row["requested_at"]),
                consumed_at=row["consumed_at"],
            )
            for row in rows
        ]

    def mark_refresh_requests_consumed(self, consumed_at: str) -> int:
        pending = self.pending_refresh_requests()
        self._execute(
            "UPDATE refresh_requests SET consumed_at = ? WHERE consumed_at IS NULL",
            [consumed_at],
        )
        self._commit_if_standalone()
        return len(pending)

    def activities_missing_streams(self, since: str | None = None) -> list[RepositoryActivityRow]:
        rows = self._fetchall(
            """
            SELECT a.id, a.date, a.name, a.sport_type, a.distance, a.moving_time,
                   a.elapsed_time, a.total_elevation_gain, a.summary_json,
                   a.detail_json, a.synced_at
            FROM activities a
            LEFT JOIN streams s ON s.activity_id = a.id
            WHERE s.activity_id IS NULL
              AND (? IS NULL OR a.activity_day >= CAST(? AS DATE))
            GROUP BY a.id, a.date, a.name, a.sport_type, a.distance, a.moving_time,
                     a.elapsed_time, a.total_elevation_gain, a.summary_json,
                     a.detail_json, a.synced_at, a.activity_day
            ORDER BY a.activity_day DESC, a.id DESC
            """,
            [since, since],
        )
        return [self._to_activity_row(row) for row in rows]

    def activities_missing_details(self, since: str | None = None) -> list[RepositoryActivityRow]:
        rows = self._fetchall(
            """
            SELECT id, date, name, sport_type, distance, moving_time,
                   elapsed_time, total_elevation_gain, summary_json,
                   detail_json, synced_at
            FROM activities
            WHERE detail_json IS NULL
              AND (? IS NULL OR activity_day >= CAST(? AS DATE))
            ORDER BY activity_day DESC, id DESC
            """,
            [since, since],
        )
        return [self._to_activity_row(row) for row in rows]

    def _to_activity_row(self, row) -> RepositoryActivityRow:
        return RepositoryActivityRow(
            id=int(row["id"]),
            date=str(row["date"]),
            name=str(row["name"]),
            sport_type=str(row["sport_type"]),
            distance=float(row["distance"] or 0.0),
            moving_time=int(row["moving_time"] or 0),
            elapsed_time=int(row["elapsed_time"] or 0),
            total_elevation_gain=float(row["total_elevation_gain"] or 0.0),
            summary_json=row["summary_json"],
            detail_json=row["detail_json"],
            synced_at=row["synced_at"],
        )
