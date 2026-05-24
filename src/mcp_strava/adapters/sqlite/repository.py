"""SQLite repository boundary for activities, streams, zones, kudos, and sync metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Iterable

from mcp_strava.adapters.sqlite.connection import open_expected_mirror_db, open_fixture_db
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
    return value


def _semantic_json_hash(value: object) -> str:
    payload = json.dumps(
        _canonical_semantic_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class SQLiteRepository:
    """Focused SQLite repository with explicit unit-of-work lifetime."""

    conn: object

    @classmethod
    def from_path(cls, db_path: str | Path, expected_mirror: bool = False) -> "SQLiteRepository":
        path = Path(db_path)
        conn = open_expected_mirror_db(path) if expected_mirror else open_fixture_db(path)
        return cls(conn=conn)

    @classmethod
    def from_connection(cls, conn: object) -> "SQLiteRepository":
        return cls(conn=conn)

    def __enter__(self) -> "SQLiteRepository":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.conn.close()

    def close(self) -> None:
        self.conn.close()

    # Read-model invalidation
    def _read_model_enabled(self) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='activity_source_state'"
        ).fetchone()
        return row is not None

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    def _activity_day_for_source_state(self, activity_id: int) -> str | None:
        row = self.conn.execute("SELECT date FROM activities WHERE id = ?", (activity_id,)).fetchone()
        if row is None or row["date"] is None:
            return None
        return str(row["date"])[:10]

    def _read_activity_source_components(self, activity_id: int) -> dict[str, object] | None:
        activity = self.conn.execute(
            """
            SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
                   total_elevation_gain, summary_json, detail_json
            FROM activities
            WHERE id = ?
            """,
            (activity_id,),
        ).fetchone()
        if activity is None:
            return None

        activity_map = dict(activity)
        summary_hash = _semantic_json_hash(activity_map.get("summary_json"))
        detail_hash = _semantic_json_hash(activity_map.get("detail_json"))

        stream_columns = [row[1] for row in self.conn.execute("PRAGMA table_info(streams)").fetchall()]
        streams: list[dict[str, object]] = []
        if stream_columns:
            quoted_cols = ", ".join(stream_columns)
            rows = self.conn.execute(
                f"SELECT {quoted_cols} FROM streams WHERE activity_id = ? ORDER BY time_offset",
                (activity_id,),
            ).fetchall()
            for row in rows:
                item = dict(row)
                if "values_json" in item:
                    item["values_json"] = _canonical_semantic_value(item["values_json"])
                streams.append(item)
        streams_hash = _semantic_json_hash(streams)

        channels: list[dict[str, object]] = []
        has_channels = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='stream_channels'"
        ).fetchone()
        if has_channels is not None:
            rows = self.conn.execute(
                """
                SELECT channel_key, original_size, resolution, series_type, status, error
                FROM stream_channels
                WHERE activity_id = ?
                ORDER BY channel_key
                """,
                (activity_id,),
            ).fetchall()
            channels = [dict(row) for row in rows]
        channels_hash = _semantic_json_hash(channels)

        source_payload = {
            "activity": {
                key: _canonical_semantic_value(value)
                for key, value in activity_map.items()
                if key not in {"summary_json", "detail_json"}
            },
            "summary_hash": summary_hash,
            "detail_hash": detail_hash,
            "streams_hash": streams_hash,
            "channels_hash": channels_hash,
        }
        return {
            "activity_day": str(activity["date"])[:10],
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

        existing = self.conn.execute(
            """
            SELECT source_hash, source_revision
            FROM activity_source_state
            WHERE activity_id = ?
            """,
            (activity_id,),
        ).fetchone()
        if existing is not None and existing["source_hash"] == components["source_hash"]:
            return False

        source_revision = 1 if existing is None else int(existing["source_revision"]) + 1
        changed_at = queued_at or self._now_iso()
        self.conn.execute(
            """
            INSERT INTO activity_source_state (
                activity_id, activity_day, summary_hash, detail_hash, streams_hash,
                channels_hash, source_hash, source_revision, changed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            (
                activity_id,
                components["activity_day"],
                components["summary_hash"],
                components["detail_hash"],
                components["streams_hash"],
                components["channels_hash"],
                components["source_hash"],
                source_revision,
                changed_at,
            ),
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
        self.conn.execute(
            """
            INSERT INTO metric_dirty_activities (
                activity_id, activity_day, metric_version, source_revision,
                reason, queued_at, attempt_count, last_error
            ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL)
            ON CONFLICT(activity_id, activity_day, metric_version) DO UPDATE SET
                source_revision=excluded.source_revision,
                reason=excluded.reason,
                queued_at=excluded.queued_at,
                attempt_count=0,
                last_error=NULL
            """,
            (activity_id, activity_day, metric_version, source_revision, reason, queued_at),
        )

    def dirty_activity_rows(self, metric_version: int | None = None) -> list[object]:
        if metric_version is None:
            return self.conn.execute(
                """
                SELECT *
                FROM metric_dirty_activities
                ORDER BY activity_day, activity_id, metric_version
                """
            ).fetchall()
        return self.conn.execute(
            """
            SELECT *
            FROM metric_dirty_activities
            WHERE metric_version = ?
            ORDER BY activity_day, activity_id
            """,
            (metric_version,),
        ).fetchall()

    def mark_dirty_activity_attempt_failed(
        self,
        activity_id: int,
        activity_day: str,
        metric_version: int,
        last_error: str,
    ) -> None:
        self.conn.execute(
            """
            UPDATE metric_dirty_activities
            SET attempt_count = attempt_count + 1, last_error = ?
            WHERE activity_id = ? AND activity_day = ? AND metric_version = ?
            """,
            (last_error, activity_id, activity_day, metric_version),
        )
        self.conn.commit()

    def enqueue_metric_version_recompute(self, metric_version: int, reason: str, queued_at: str) -> int:
        if not self._read_model_enabled():
            return 0
        rows = self.conn.execute(
            """
            SELECT activity_id, activity_day, source_revision
            FROM activity_source_state
            ORDER BY activity_day, activity_id
            """
        ).fetchall()
        for row in rows:
            self.enqueue_metric_dirty_activity(
                activity_id=int(row["activity_id"]),
                activity_day=row["activity_day"],
                metric_version=metric_version,
                source_revision=int(row["source_revision"]),
                reason=reason,
                queued_at=queued_at,
            )
        self.conn.commit()
        return len(rows)

    def dirty_activity_rows_for_materialization(
        self,
        metric_version: int,
        limit: int | None = None,
    ) -> list[object]:
        sql = """
            SELECT d.*, s.source_hash
            FROM metric_dirty_activities d
            JOIN activity_source_state s ON s.activity_id = d.activity_id
            WHERE d.metric_version = ?
            ORDER BY d.activity_day, d.activity_id
        """
        params: list[object] = [metric_version]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return self.conn.execute(sql, params).fetchall()

    def clear_dirty_activity_rows(self, rows: Iterable[object]) -> int:
        count = 0
        for row in rows:
            cur = self.conn.execute(
                """
                DELETE FROM metric_dirty_activities
                WHERE activity_id = ? AND activity_day = ? AND metric_version = ?
                """,
                (row["activity_id"], row["activity_day"], row["metric_version"]),
            )
            count += cur.rowcount
        return count

    def source_state_for_activity(self, activity_id: int) -> object | None:
        return self.conn.execute(
            "SELECT * FROM activity_source_state WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()

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
        self.conn.execute(sql, tuple(values[col] for col in columns))

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
        columns = tuple(values.keys())
        placeholders = ", ".join("?" for _ in columns)
        cur = self.conn.execute(
            f"INSERT INTO read_model_refresh_runs ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(values[col] for col in columns),
        )
        return int(cur.lastrowid)

    # Read-model fact queries
    def _read_model_metadata_versions(self, metric_version: int | None = None) -> list[int]:
        if not self._read_model_enabled():
            return []
        params: list[object] = []
        where = ""
        if metric_version is not None:
            where = "WHERE metric_version = ?"
            params.append(metric_version)
        versions: set[int] = set()
        for table in (
            "activity_metric_facts",
            "daily_load_facts",
            "training_model_daily",
            "rolling_period_facts",
        ):
            rows = self.conn.execute(
                f"SELECT DISTINCT metric_version FROM {table} {where}",
                params,
            ).fetchall()
            versions.update(int(row["metric_version"]) for row in rows if row["metric_version"] is not None)
        return sorted(versions)

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

        dirty = self.conn.execute(
            """
            SELECT COUNT(*) AS dirty_count, MIN(activity_day) AS oldest_dirty_day
            FROM metric_dirty_activities
            WHERE 1=1
            """
            + metric_sql,
            params,
        ).fetchone()
        run = self.conn.execute(
            """
            SELECT MAX(finished_at) AS last_materialized_at
            FROM read_model_refresh_runs
            WHERE status = 'ok'
            """
            + metric_sql,
            params,
        ).fetchone()
        last_fact = self.conn.execute(
            """
            SELECT MAX(computed_at) AS last_materialized_at FROM (
                SELECT computed_at, metric_version FROM activity_metric_facts
                UNION ALL
                SELECT computed_at, metric_version FROM daily_load_facts
                UNION ALL
                SELECT computed_at, metric_version FROM training_model_daily
                UNION ALL
                SELECT computed_at, metric_version FROM rolling_period_facts
            )
            WHERE 1=1
            """
            + metric_sql,
            params,
        ).fetchone()

        dirty_count = int(dirty["dirty_count"] or 0) if dirty else 0
        last_materialized_at = None
        if run and run["last_materialized_at"]:
            last_materialized_at = str(run["last_materialized_at"])
        elif last_fact and last_fact["last_materialized_at"]:
            last_materialized_at = str(last_fact["last_materialized_at"])
        versions = self._read_model_metadata_versions(metric_version)

        status = "current"
        stale_reason = None
        if not versions and last_materialized_at is None:
            status = "unavailable"
            stale_reason = "no_materialized_facts"
        elif dirty_count > 0:
            status = "stale"
            stale_reason = "dirty_queue_not_empty"

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
    ) -> object | None:
        if not self._read_model_enabled():
            return None
        sport_type = sport or "all"
        where = [
            "metric_version = ?",
            "scope = ?",
            "sport_type = ?",
        ]
        params: list[object] = [metric_version, scope, sport_type]
        if as_of_day is not None:
            where.append("day <= ?")
            params.append(as_of_day)
        return self.conn.execute(
            f"""
            SELECT *
            FROM training_model_daily
            WHERE {" AND ".join(where)}
            ORDER BY day DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

    def fetch_activity_metric_facts(
        self,
        start_day: str,
        end_day: str,
        *,
        sport: str | None = None,
        metric_version: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> list[object]:
        if not self._read_model_enabled():
            return []
        where = ["f.activity_day >= ?", "f.activity_day < ?"]
        params: list[object] = [start_day, end_day]
        if sport is not None:
            where.append("f.sport_type = ?")
            params.append(sport)
        if metric_version is not None:
            where.append("f.metric_version = ?")
            params.append(metric_version)
        if cursor is not None:
            where.append("(f.activity_day < ? OR (f.activity_day = ? AND f.activity_id < ?))")
            params.extend([cursor, cursor, cursor])
        sql = f"""
            SELECT f.*, a.name AS activity_name, a.date AS activity_date, a.summary_json
            FROM activity_metric_facts f
            LEFT JOIN activities a ON a.id = f.activity_id
            WHERE {" AND ".join(where)}
            ORDER BY f.activity_day DESC, f.activity_id DESC
        """
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return self.conn.execute(sql, params).fetchall()

    def fetch_activity_metric_fact(self, activity_id: int, metric_version: int | None = None) -> object | None:
        if not self._read_model_enabled():
            return None
        where = ["f.activity_id = ?"]
        params: list[object] = [activity_id]
        if metric_version is not None:
            where.append("f.metric_version = ?")
            params.append(metric_version)
        return self.conn.execute(
            f"""
            SELECT f.*, a.name AS activity_name, a.date AS activity_date, a.summary_json
            FROM activity_metric_facts f
            LEFT JOIN activities a ON a.id = f.activity_id
            WHERE {" AND ".join(where)}
            ORDER BY f.metric_version DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

    def fetch_daily_load_facts(
        self,
        start_day: str,
        end_day: str,
        *,
        scope: str,
        sport: str | None = None,
        metric_version: int | None = None,
    ) -> list[object]:
        if not self._read_model_enabled():
            return []
        where = ["day >= ?", "day < ?", "scope = ?", "sport_type = ?"]
        params: list[object] = [start_day, end_day, scope, sport or "all"]
        if metric_version is not None:
            where.append("metric_version = ?")
            params.append(metric_version)
        return self.conn.execute(
            f"""
            SELECT *
            FROM daily_load_facts
            WHERE {" AND ".join(where)}
            ORDER BY day ASC
            """,
            params,
        ).fetchall()

    def fetch_rolling_period_facts(
        self,
        as_of_day: str,
        window_days: int,
        *,
        scope: str,
        sport: str | None = None,
        metric_version: int | None = None,
    ) -> object | None:
        if not self._read_model_enabled():
            return None
        where = ["as_of_day = ?", "window_days = ?", "scope = ?", "sport_type = ?"]
        params: list[object] = [as_of_day, window_days, scope, sport or "all"]
        if metric_version is not None:
            where.append("metric_version = ?")
            params.append(metric_version)
        return self.conn.execute(
            f"""
            SELECT *
            FROM rolling_period_facts
            WHERE {" AND ".join(where)}
            ORDER BY metric_version DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

    # Activities
    def recent_activities(self, limit: int = 15) -> list[RepositoryActivityRow]:
        rows = self.conn.execute(
            """
            SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
                   total_elevation_gain, summary_json, detail_json, synced_at
            FROM activities
            ORDER BY date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._to_activity_row(r) for r in rows]

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
            where.append("SUBSTR(date, 1, 10) >= ?")
            params.append(start_date)
        if end_date is not None:
            where.append("SUBSTR(date, 1, 10) <= ?")
            params.append(end_date)
        if sport is not None:
            where.append("sport_type = ?")
            params.append(sport)
        if cursor is not None:
            where.append("date < ?")
            params.append(cursor)

        where_sql = " WHERE " + " AND ".join(where) if where else ""
        rows = self.conn.execute(
            """
            SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
                   total_elevation_gain, summary_json, detail_json, synced_at
            FROM activities
            """
            + where_sql
            + """
            ORDER BY date DESC, id DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        return [self._to_activity_row(r) for r in rows]

    def activity_by_id(self, activity_id: int) -> RepositoryActivityRow | None:
        row = self.conn.execute(
            """
            SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
                   total_elevation_gain, summary_json, detail_json, synced_at
            FROM activities
            WHERE id = ?
            """,
            (activity_id,),
        ).fetchone()
        return self._to_activity_row(row) if row else None

    def activity_rows_between(self, start_day: str, end_day: str) -> list[RepositoryActivityRow]:
        rows = self.conn.execute(
            """
            SELECT id, date, name, sport_type, distance, moving_time, elapsed_time,
                   total_elevation_gain, summary_json, detail_json, synced_at
            FROM activities
            WHERE SUBSTR(date, 1, 10) BETWEEN ? AND ?
            ORDER BY date ASC
            """,
            (start_day, end_day),
        ).fetchall()
        return [self._to_activity_row(r) for r in rows]

    def daily_activity_presence(self, day: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM activities WHERE SUBSTR(date, 1, 10) = ? LIMIT 1",
            (day,),
        ).fetchone()
        return row is not None

    def first_activity_day(self, sport_filter: str | None = None) -> str | None:
        sport_sql, sport_params = self._sport_where_clause(sport_filter)
        row = self.conn.execute(
            """
            SELECT MIN(SUBSTR(date,1,10)) as day
            FROM activities a
            WHERE 1=1
            """
            + sport_sql,
            sport_params,
        ).fetchone()
        return row["day"] if row and row["day"] else None

    def latest_activity_at(self) -> str | None:
        """Return the newest local activity timestamp."""
        row = self.conn.execute("SELECT MAX(date) as latest FROM activities").fetchone()
        return row["latest"] if row and row["latest"] else None

    def latest_activity_id(self) -> int | None:
        """Return the id for the newest local activity by activity date."""
        row = self.conn.execute(
            """
            SELECT id
            FROM activities
            ORDER BY date DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
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
        self.conn.execute("BEGIN")
        try:
            self.conn.execute(
                """
                INSERT INTO activities (
                    id, date, name, sport_type, distance, moving_time,
                    elapsed_time, total_elevation_gain, summary_json, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
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
                (
                    activity_id,
                    date,
                    name,
                    sport_type,
                    distance,
                    moving_time,
                    elapsed_time,
                    total_elevation_gain,
                    summary_json,
                    synced_at,
                ),
            )
            self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            self.conn.rollback()
            raise
        self.conn.commit()

    def update_activity_detail(self, activity_id: int, detail_json: str) -> None:
        self.conn.execute("BEGIN")
        try:
            self.conn.execute(
                "UPDATE activities SET detail_json = ? WHERE id = ?",
                (detail_json, activity_id),
            )
            self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            self.conn.rollback()
            raise
        self.conn.commit()

    # Streams and load
    def _stream_column_set(self) -> set[str]:
        return {row[1] for row in self.conn.execute("PRAGMA table_info(streams)").fetchall()}

    def activity_stream_rows(self, activity_id: int) -> list[tuple]:
        stream_columns = self._stream_column_set()
        values_expr = "values_json" if "values_json" in stream_columns else "NULL AS values_json"
        return self.conn.execute(
            f"""
            SELECT activity_id, time_offset, heartrate, velocity, altitude,
                   cadence, lat, lng, grade, gap_speed, gap_distance, is_moving, {values_expr}
            FROM streams
            WHERE activity_id = ?
            ORDER BY time_offset ASC
            """,
            (activity_id,),
        ).fetchall()

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
        since_day: str | None = None,
        until_day: str | None = None,
        sport_filter: str | None = None,
    ) -> dict[str, float]:
        where = ["s.heartrate IS NOT NULL"]
        params: list[object] = []
        if since_day is not None:
            where.append("SUBSTR(a.date,1,10) >= ?")
            params.append(since_day)
        if until_day is not None:
            where.append("SUBSTR(a.date,1,10) <= ?")
            params.append(until_day)
        sport_sql, sport_params = self._sport_where_clause(sport_filter)
        params.extend(sport_params)

        rows = self.conn.execute(
            """
            SELECT SUBSTR(a.date,1,10) as day,
                   """
            + Config.SQL.TRIMP_S
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
        ).fetchall()
        return {r["day"]: round(r["trimp"], 1) for r in rows}

    def daily_load_status(self, day: str) -> RepositoryDailyLoadStatus:
        activity_row = self.conn.execute(
            "SELECT COUNT(*) FROM activities WHERE SUBSTR(date, 1, 10) = ?",
            (day,),
        ).fetchone()
        stream_row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM streams s
            JOIN activities a ON a.id = s.activity_id
            WHERE SUBSTR(a.date, 1, 10) = ?
            """,
            (day,),
        ).fetchone()
        hr_row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM streams s
            JOIN activities a ON a.id = s.activity_id
            WHERE SUBSTR(a.date, 1, 10) = ?
              AND s.heartrate IS NOT NULL
            """,
            (day,),
        ).fetchone()

        activity_count = int(activity_row[0] if activity_row else 0)
        stream_count = int(stream_row[0] if stream_row else 0)
        hr_count = int(hr_row[0] if hr_row else 0)

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
        sport_filter: str | None = None,
    ) -> list[DailyLoadPoint]:
        daily_activity_counts: dict[str, int] = {}
        daily_stream_counts: dict[str, int] = {}
        daily_hr_counts: dict[str, int] = {}

        sport_sql, sport_params = self._sport_where_clause(sport_filter)

        act_rows = self.conn.execute(
            """
            SELECT SUBSTR(date,1,10) as day, COUNT(*) as c
            FROM activities
            WHERE SUBSTR(date,1,10) BETWEEN ? AND ?
            """
            + (sport_sql.replace("a.", "") if sport_sql else "")
            + """
            GROUP BY day
            """,
            [start_day, end_day, *sport_params],
        ).fetchall()
        for row in act_rows:
            daily_activity_counts[row["day"]] = int(row["c"])

        stream_rows = self.conn.execute(
            """
            SELECT SUBSTR(a.date,1,10) as day, COUNT(*) as c
            FROM activities a
            JOIN streams s ON s.activity_id = a.id
            WHERE SUBSTR(a.date,1,10) BETWEEN ? AND ?
            """
            + sport_sql
            + """
            GROUP BY day
            """,
            [start_day, end_day, *sport_params],
        ).fetchall()
        for row in stream_rows:
            daily_stream_counts[row["day"]] = int(row["c"])

        hr_rows = self.conn.execute(
            """
            SELECT SUBSTR(a.date,1,10) as day, COUNT(*) as c
            FROM activities a
            JOIN streams s ON s.activity_id = a.id
            WHERE SUBSTR(a.date,1,10) BETWEEN ? AND ?
              AND s.heartrate IS NOT NULL
            """
            + sport_sql
            + """
            GROUP BY day
            """,
            [start_day, end_day, *sport_params],
        ).fetchall()
        for row in hr_rows:
            daily_hr_counts[row["day"]] = int(row["c"])

        observed_trimp = self.observed_trimp_history(
            since_day=start_day,
            until_day=end_day,
            sport_filter=sport_filter,
        )
        points: list[DailyLoadPoint] = []
        current = start_day
        while current <= end_day:
            activity_count = daily_activity_counts.get(current, 0)
            stream_count = daily_stream_counts.get(current, 0)
            hr_count = daily_hr_counts.get(current, 0)
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
                observed = round(observed_trimp.get(current, 0.0), 1)
                effective = observed
            points.append(
                DailyLoadPoint(
                    date=current,
                    status=status,
                    observed_trimp=observed,
                    effective_trimp=effective,
                    activity_count=activity_count,
                    stream_points=stream_count,
                    heartrate_points=hr_count,
                )
            )
            y, m, d = map(int, current.split("-"))
            from datetime import date, timedelta
            current = (date(y, m, d) + timedelta(days=1)).isoformat()
        return points

    def effective_trimp_history(
        self,
        start_day: str,
        end_day: str,
        *,
        sport_filter: str | None = None,
    ) -> dict[str, float]:
        return {
            point.date: point.effective_trimp
            for point in self.daily_load_points_between(start_day, end_day, sport_filter=sport_filter)
        }

    def activity_moving_time(self, activity_id: int) -> int | None:
        row = self.conn.execute("SELECT moving_time FROM activities WHERE id=?", (activity_id,)).fetchone()
        return int(row["moving_time"]) if row and row["moving_time"] is not None else None

    def stream_hr_velocity_rows(self, activity_id: int, min_velocity: float) -> list[object]:
        return self.conn.execute(
            """
            SELECT time_offset, heartrate, velocity, grade FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL AND velocity IS NOT NULL
              AND velocity > ?
            ORDER BY time_offset
            """,
            (activity_id, min_velocity),
        ).fetchall()

    def stream_hr_velocity_simple_rows(self, activity_id: int, min_velocity: float) -> list[object]:
        return self.conn.execute(
            """
            SELECT heartrate, velocity FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL AND velocity > ?
            ORDER BY time_offset
            """,
            (activity_id, min_velocity),
        ).fetchall()

    def stream_hr_velocity_time_rows(self, activity_id: int) -> list[object]:
        return self.conn.execute(
            """
            SELECT time_offset, heartrate, velocity FROM streams
            WHERE activity_id=? AND heartrate IS NOT NULL
            ORDER BY time_offset
            """,
            (activity_id,),
        ).fetchall()

    def activity_hr_summary(self, activity_id: int) -> tuple[float | None, int]:
        row = self.conn.execute(
            """
            SELECT AVG(heartrate) as avg_hr, COUNT(*) as n
            FROM streams WHERE activity_id=? AND heartrate IS NOT NULL
            """,
            (activity_id,),
        ).fetchone()
        return (row["avg_hr"], int(row["n"] or 0)) if row else (None, 0)

    def activity_avg_velocity(self, activity_id: int) -> float | None:
        row = self.conn.execute(
            "SELECT AVG(velocity) as avg_vel FROM streams WHERE activity_id=? AND velocity IS NOT NULL",
            (activity_id,),
        ).fetchone()
        return row["avg_vel"] if row else None

    def stream_hr_time_rows(self, activity_id: int) -> list[object]:
        return self.conn.execute(
            """
            SELECT time_offset, heartrate FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL
            ORDER BY time_offset
            """,
            (activity_id,),
        ).fetchall()

    def stream_altitude_rows(self, activity_id: int) -> list[object]:
        return self.conn.execute(
            """
            SELECT time_offset, altitude FROM streams
            WHERE activity_id=? AND altitude IS NOT NULL
            ORDER BY time_offset
            """,
            (activity_id,),
        ).fetchall()

    def activity_trimp(self, activity_id: int) -> float:
        row = self.conn.execute(
            "SELECT " + Config.SQL.TRIMP + " FROM streams WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()
        return round(row["trimp"], 1) if row and row["trimp"] is not None else 0.0

    def activity_cc(self, activity_id: int, min_velocity: float) -> float | None:
        row = self.conn.execute(
            """
            SELECT AVG(heartrate) as avg_hr, AVG(velocity) as avg_vel
            FROM streams WHERE activity_id = ? AND heartrate IS NOT NULL
              AND velocity > ?
            """,
            (activity_id, min_velocity),
        ).fetchone()
        if not row or not row["avg_hr"] or not row["avg_vel"] or row["avg_vel"] <= 0:
            return None
        return round(row["avg_hr"] / row["avg_vel"], 2)

    def activity_median_heartrate(self, activity_id: int) -> float | None:
        row = self.conn.execute(
            """
            SELECT heartrate FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL
            ORDER BY heartrate
            LIMIT 1 OFFSET (
                SELECT COUNT(*) FROM streams
                WHERE activity_id = ? AND heartrate IS NOT NULL
            ) / 2
            """,
            (activity_id, activity_id),
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def max_heartrate(self) -> float | None:
        row = self.conn.execute("SELECT MAX(heartrate) as hr FROM streams WHERE heartrate IS NOT NULL").fetchone()
        return float(row["hr"]) if row and row["hr"] is not None else None

    def activity_z5_seconds(self, activity_id: int, z5_threshold: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as sec FROM streams WHERE activity_id = ? AND heartrate >= ?",
            (activity_id, z5_threshold),
        ).fetchone()
        return int(row["sec"] or 0) if row else 0

    def activity_efficiency_rows(self) -> list[object]:
        return self.conn.execute(
            """
            SELECT SUBSTR(a.date, 1, 10) as day, a.sport_type,
                   a.distance / 1000 as dist_km, a.moving_time / 60.0 as time_min,
                   a.total_elevation_gain as elev,
                   AVG(s.heartrate) as avg_hr, AVG(s.velocity) as avg_vel
            FROM activities a
            JOIN streams s ON a.id = s.activity_id
            WHERE s.heartrate IS NOT NULL AND s.velocity > 0
            GROUP BY a.id
            HAVING avg_hr > 0 AND avg_vel > 0
            """
        ).fetchall()

    def total_distance_km_between(self, start_day: str, end_day: str, sports: tuple[str, ...] | list[str]) -> float:
        if not sports:
            return 0.0
        placeholders = ",".join("?" * len(sports))
        row = self.conn.execute(
            f"""
            SELECT SUM(distance)/1000 as km FROM activities
            WHERE sport_type IN ({placeholders})
              AND SUBSTR(date,1,10) >= ?
              AND SUBSTR(date,1,10) <= ?
            """,
            [*sports, start_day, end_day],
        ).fetchone()
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

        has_values_json = "values_json" in self._stream_column_set()

        self.conn.execute("BEGIN")
        try:
            for start in range(0, total, chunk_size):
                chunk = payload[start : start + chunk_size]
                if has_values_json:
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
                    self.conn.executemany(
                        """
                        INSERT OR REPLACE INTO streams
                        (activity_id, time_offset, heartrate, velocity, altitude, cadence,
                         lat, lng, grade, gap_speed, gap_distance, is_moving, values_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        bound,
                    )
                else:
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
                        )
                        for row in chunk
                    ]
                    self.conn.executemany(
                        """
                        INSERT OR REPLACE INTO streams
                        (activity_id, time_offset, heartrate, velocity, altitude, cadence,
                         lat, lng, grade, gap_speed, gap_distance, is_moving)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        bound,
                    )
            self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            self.conn.rollback()
            raise
        self.conn.commit()

        return total

    def replace_stream_rows_chunked(
        self,
        activity_id: int,
        rows: Iterable[dict],
        chunk_size: int = 5000,
    ) -> int:
        payload = list(rows)
        total = len(payload)
        if total == 0:
            return 0

        has_values_json = "values_json" in self._stream_column_set()

        self.conn.execute("BEGIN")
        try:
            self.conn.execute("DELETE FROM streams WHERE activity_id = ?", (activity_id,))
            for start in range(0, total, chunk_size):
                chunk = payload[start : start + chunk_size]
                if has_values_json:
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
                    self.conn.executemany(
                        """
                        INSERT OR REPLACE INTO streams
                        (activity_id, time_offset, heartrate, velocity, altitude, cadence,
                         lat, lng, grade, gap_speed, gap_distance, is_moving, values_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        bound,
                    )
                else:
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
                        )
                        for row in chunk
                    ]
                    self.conn.executemany(
                        """
                        INSERT OR REPLACE INTO streams
                        (activity_id, time_offset, heartrate, velocity, altitude, cadence,
                         lat, lng, grade, gap_speed, gap_distance, is_moving)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        bound,
                    )
            self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            self.conn.rollback()
            raise
        self.conn.commit()
        return total

    def delete_stream_rows_for_activity(self, activity_id: int) -> None:
        self.conn.execute("BEGIN")
        try:
            self.conn.execute("DELETE FROM streams WHERE activity_id = ?", (activity_id,))
            self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            self.conn.rollback()
            raise
        self.conn.commit()

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
            self.conn.execute("BEGIN")
        try:
            self.conn.execute(
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
                (
                    activity_id,
                    channel_key,
                    original_size,
                    resolution,
                    series_type,
                    fetched_at,
                    batch_id,
                    status,
                    error,
                ),
            )
            if commit:
                self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            if commit:
                self.conn.rollback()
            raise
        if commit:
            self.conn.commit()

    def replace_stream_rows_and_channel_metadata(
        self,
        activity_id: int,
        rows: Iterable[dict],
        metadata: Iterable[dict],
        chunk_size: int = 5000,
    ) -> int:
        payload = list(rows)
        total = len(payload)
        has_values_json = "values_json" in self._stream_column_set()
        self.conn.execute("BEGIN")
        try:
            self.conn.execute("DELETE FROM streams WHERE activity_id = ?", (activity_id,))
            self.conn.execute("DELETE FROM stream_channels WHERE activity_id = ?", (activity_id,))
            for start in range(0, total, chunk_size):
                chunk = payload[start : start + chunk_size]
                if has_values_json:
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
                    self.conn.executemany(
                        """
                        INSERT OR REPLACE INTO streams
                        (activity_id, time_offset, heartrate, velocity, altitude, cadence,
                         lat, lng, grade, gap_speed, gap_distance, is_moving, values_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        bound,
                    )
                else:
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
                    self.conn.executemany(
                        """
                        INSERT OR REPLACE INTO streams
                        (activity_id, time_offset, heartrate, velocity, altitude, cadence,
                         lat, lng, grade, gap_speed, gap_distance, is_moving, values_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        bound,
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
            self.conn.rollback()
            raise
        self.conn.commit()
        return total

    def merge_stream_channel_values(
        self,
        activity_id: int,
        rows: Iterable[dict],
        metadata: Iterable[dict],
        missing_channel_keys: Iterable[str],
    ) -> int:
        payload = list(rows)
        self.conn.execute("BEGIN")
        try:
            for row in payload:
                if "time_offset" not in row:
                    continue
                existing = self.conn.execute(
                    "SELECT values_json FROM streams WHERE activity_id=? AND time_offset=?",
                    (activity_id, row["time_offset"]),
                ).fetchone()
                if existing is None:
                    continue
                existing_map = json.loads(existing[0]) if existing and existing[0] else {}
                values_map = existing_map | (row.get("values") or {})
                self.conn.execute(
                    "UPDATE streams SET values_json=? WHERE activity_id=? AND time_offset=?",
                    (json.dumps(values_map, ensure_ascii=True), activity_id, row["time_offset"]),
                )
            for channel_key in missing_channel_keys:
                self.conn.execute(
                    """
                    INSERT INTO stream_channels (activity_id, channel_key, status)
                    VALUES (?, ?, ?)
                    ON CONFLICT(activity_id, channel_key) DO UPDATE SET status=excluded.status
                    """,
                    (activity_id, channel_key, "unavailable"),
                )
            for item in metadata:
                status = item.get("status", "available")
                self.conn.execute(
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
                        status=CASE
                            WHEN stream_channels.status='available' AND excluded.status!='available'
                            THEN stream_channels.status
                            ELSE excluded.status
                        END,
                        error=excluded.error
                    """,
                    (
                        activity_id,
                        item["channel_key"],
                        item.get("original_size"),
                        item.get("resolution"),
                        item.get("series_type"),
                        item.get("fetched_at"),
                        item.get("batch_id"),
                        status,
                        item.get("error"),
                    ),
                )
            self.update_activity_source_state_and_enqueue_dirty(activity_id)
        except Exception:
            self.conn.rollback()
            raise
        self.conn.commit()
        return len(payload)

    def activities_missing_stream_channels(
        self,
        *,
        since: str | None = None,
        limit: int | None = None,
        requested_channels: Iterable[str],
    ) -> list[dict]:
        channel_list = list(requested_channels)
        has_channel_table = (
            self.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='stream_channels'").fetchone()
            is not None
        )
        rows = self.conn.execute(
            """
            SELECT a.id, a.date
            FROM activities a
            WHERE EXISTS (SELECT 1 FROM streams s WHERE s.activity_id = a.id)
              AND (? IS NULL OR SUBSTR(a.date, 1, 10) >= ?)
            ORDER BY a.date DESC
            """,
            (since, since),
        ).fetchall()
        results: list[dict] = []
        for row in rows:
            if limit is not None and len(results) >= limit:
                break
            activity_id = int(row["id"])
            missing_channels: list[str] = []
            metadata_missing = False
            for channel in channel_list:
                meta = None
                if has_channel_table:
                    meta = self.conn.execute(
                        """
                        SELECT status FROM stream_channels
                        WHERE activity_id=? AND channel_key=?
                        """,
                        (activity_id, channel),
                    ).fetchone()
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
                    has_value = self.conn.execute(
                        """
                        SELECT 1
                        FROM streams
                        WHERE activity_id=?
                          AND values_json IS NOT NULL
                          AND json_extract(values_json, '$.' || ?) IS NOT NULL
                        LIMIT 1
                        """,
                        (activity_id, channel),
                    ).fetchone()
                    if has_value is None:
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
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='stream_channels'"
        ).fetchone()
        if exists is None:
            return {
                "channels": 0,
                "activities_with_channel_metadata": 0,
                "available_channels": 0,
                "unavailable_channels": 0,
                "error_channels": 0,
            }
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS channels,
                COUNT(DISTINCT activity_id) AS activities_with_channel_metadata,
                SUM(CASE WHEN status='available' THEN 1 ELSE 0 END) AS available_channels,
                SUM(CASE WHEN status='unavailable' THEN 1 ELSE 0 END) AS unavailable_channels,
                SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS error_channels
            FROM stream_channels
            """
        ).fetchone()
        return {
            "channels": int(row["channels"] or 0),
            "activities_with_channel_metadata": int(row["activities_with_channel_metadata"] or 0),
            "available_channels": int(row["available_channels"] or 0),
            "unavailable_channels": int(row["unavailable_channels"] or 0),
            "error_channels": int(row["error_channels"] or 0),
        }

    # Zones
    def latest_athlete_zones(self) -> str | None:
        row = self.conn.execute(
            "SELECT zones_json FROM athlete_zones ORDER BY fetched_at DESC LIMIT 1"
        ).fetchone()
        return str(row[0]) if row else None

    def insert_athlete_zones(self, fetched_at: str, zones_json: str) -> None:
        self.conn.execute(
            "INSERT INTO athlete_zones (fetched_at, zones_json) VALUES (?, ?)",
            (fetched_at, zones_json),
        )
        self.conn.commit()

    # Kudos
    def list_kudos(self, limit: int = 100) -> list[tuple]:
        return self.conn.execute(
            """
            SELECT activity_id, firstname, lastname, fetched_at
            FROM kudos
            ORDER BY fetched_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def upsert_kudos(self, activity_id: int, firstname: str, lastname: str, fetched_at: str) -> None:
        self.conn.execute(
            """
            INSERT INTO kudos (activity_id, firstname, lastname, fetched_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(activity_id, firstname, lastname) DO UPDATE SET
              fetched_at = excluded.fetched_at
            """,
            (activity_id, firstname, lastname, fetched_at),
        )
        self.conn.commit()

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
        self.conn.execute(
            """
            INSERT INTO sync_log (
                timestamp, status, activities_seen, activities_new,
                streams_fetched, details_fetched, api_calls, error, kudos_fetched
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                status,
                activities_seen,
                activities_new,
                streams_fetched,
                details_fetched,
                api_calls,
                error,
                kudos_fetched,
            ),
        )
        self.conn.commit()

    def read_sync_log(self, limit: int = 20) -> list[RepositorySyncLogEntry]:
        rows = self.conn.execute(
            """
            SELECT timestamp, status, activities_seen, activities_new,
                   streams_fetched, details_fetched, api_calls, error, kudos_fetched
            FROM sync_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            RepositorySyncLogEntry(
                timestamp=r[0],
                status=r[1],
                activities_seen=r[2],
                activities_new=r[3],
                streams_fetched=r[4],
                details_fetched=r[5],
                api_calls=r[6],
                error=r[7],
                kudos_fetched=r[8],
            )
            for r in rows
        ]

    # Refresh runtime metadata
    def get_refresh_state(self) -> RefreshStateRow:
        row = self.conn.execute("SELECT * FROM refresh_state WHERE id = 1").fetchone()
        if row is None:
            self.conn.execute("INSERT INTO refresh_state (id) VALUES (1)")
            self.conn.commit()
            row = self.conn.execute("SELECT * FROM refresh_state WHERE id = 1").fetchone()
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
        cur = self.conn.execute(
            """
            UPDATE refresh_state
            SET lease_owner = ?, lease_expires_at = ?
            WHERE id = 1
              AND (lease_owner IS NULL OR lease_expires_at IS NULL OR lease_expires_at < ?)
            """,
            (owner, expires_at, now),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def release_refresh_lease(self, owner: str) -> None:
        self.conn.execute(
            """
            UPDATE refresh_state
            SET lease_owner = NULL, lease_expires_at = NULL
            WHERE id = 1 AND lease_owner = ?
            """,
            (owner,),
        )
        self.conn.commit()

    def renew_refresh_lease(self, owner: str, expires_at: str) -> bool:
        was_in_transaction = self.conn.in_transaction
        cur = self.conn.execute(
            """
            UPDATE refresh_state
            SET lease_expires_at = ?
            WHERE id = 1 AND lease_owner = ?
            """,
            (expires_at, owner),
        )
        if not was_in_transaction:
            self.conn.commit()
        return cur.rowcount > 0

    def set_checkpoint(self, stage: str, cursor: str | None) -> None:
        self.conn.execute(
            """
            UPDATE refresh_state
            SET checkpoint_stage = ?, checkpoint_cursor = ?
            WHERE id = 1
            """,
            (stage, cursor),
        )
        self.conn.commit()

    def record_refresh_attempt(self, at: str) -> None:
        self.conn.execute(
            "UPDATE refresh_state SET last_attempt_at = ? WHERE id = 1",
            (at,),
        )
        self.conn.commit()

    def record_refresh_success(self, at: str) -> None:
        self.conn.execute(
            """
            UPDATE refresh_state
            SET last_success_at = ?, last_attempt_at = ?, last_status = 'ok',
                last_error_code = NULL, backoff_until = NULL
            WHERE id = 1
            """,
            (at, at),
        )
        self.conn.commit()

    def record_refresh_failure(self, at: str, reason_code: str, backoff_until: str | None) -> None:
        if reason_code not in ALLOWED_REASON_CODES:
            raise ValueError(f"Unknown refresh failure reason: {reason_code}")
        self.conn.execute(
            """
            UPDATE refresh_state
            SET last_attempt_at = ?, last_status = 'failed',
                last_error_code = ?, backoff_until = ?
            WHERE id = 1
            """,
            (at, reason_code, backoff_until),
        )
        self.conn.commit()

    def enqueue_refresh_request(self, reason: str, requested_for_day: str, requested_at: str | None = None) -> bool:
        timestamp = requested_at or requested_for_day
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO refresh_requests (reason, requested_for_day, requested_at)
            VALUES (?, ?, ?)
            """,
            (reason, requested_for_day, timestamp),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def pending_refresh_requests(self) -> list[RefreshRequestRow]:
        rows = self.conn.execute(
            """
            SELECT id, reason, requested_for_day, requested_at, consumed_at
            FROM refresh_requests
            WHERE consumed_at IS NULL
            ORDER BY id
            """
        ).fetchall()
        return [
            RefreshRequestRow(
                id=int(row["id"]),
                reason=row["reason"],
                requested_for_day=row["requested_for_day"],
                requested_at=row["requested_at"],
                consumed_at=row["consumed_at"],
            )
            for row in rows
        ]

    def mark_refresh_requests_consumed(self, consumed_at: str) -> int:
        cur = self.conn.execute(
            "UPDATE refresh_requests SET consumed_at = ? WHERE consumed_at IS NULL",
            (consumed_at,),
        )
        self.conn.commit()
        return cur.rowcount

    def activities_missing_streams(self, since: str | None = None) -> list[RepositoryActivityRow]:
        rows = self.conn.execute(
            """
            SELECT a.id, a.date, a.name, a.sport_type, a.distance, a.moving_time,
                   a.elapsed_time, a.total_elevation_gain, a.summary_json,
                   a.detail_json, a.synced_at
            FROM activities a
            LEFT JOIN streams s ON s.activity_id = a.id
            WHERE s.activity_id IS NULL
              AND (? IS NULL OR SUBSTR(a.date, 1, 10) >= ?)
            GROUP BY a.id
            ORDER BY a.date DESC
            """,
            (since, since),
        ).fetchall()
        return [self._to_activity_row(row) for row in rows]

    def activities_missing_details(self, since: str | None = None) -> list[RepositoryActivityRow]:
        rows = self.conn.execute(
            """
            SELECT id, date, name, sport_type, distance, moving_time,
                   elapsed_time, total_elevation_gain, summary_json,
                   detail_json, synced_at
            FROM activities
            WHERE detail_json IS NULL
              AND (? IS NULL OR SUBSTR(date, 1, 10) >= ?)
            ORDER BY date DESC
            """,
            (since, since),
        ).fetchall()
        return [self._to_activity_row(row) for row in rows]

    def _to_activity_row(self, row) -> RepositoryActivityRow:
        return RepositoryActivityRow(
            id=row["id"],
            date=row["date"],
            name=row["name"],
            sport_type=row["sport_type"],
            distance=row["distance"],
            moving_time=row["moving_time"],
            elapsed_time=row["elapsed_time"],
            total_elevation_gain=row["total_elevation_gain"],
            summary_json=row["summary_json"],
            detail_json=row["detail_json"],
            synced_at=row["synced_at"],
        )
