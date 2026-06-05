"""Read-model state, dirty-queue, and fact-table repository methods."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, TypeVar

import duckdb

from mcp_strava.adapters.duckdb.connection import DuckDBConn
from mcp_strava.adapters.duckdb.repository_models import (
    ActivityMetricFactRow,
    DailyLoadFactRow,
    DirtyActivityRow,
    LogicVersionRow,
    RollingPeriodFactRow,
    SourceComponents,
    SourceRevisionRow,
    SourceStateRow,
    TrainingModelDayRow,
)
from mcp_strava.adapters.duckdb.repository_utils import Row
from mcp_strava.adapters.duckdb.repository_utils import as_int as _as_int
from mcp_strava.adapters.duckdb.repository_utils import as_str as _as_str
from mcp_strava.adapters.duckdb.repository_utils import safe_identifier as _safe_identifier
from mcp_strava.adapters.duckdb.source_hashing import canonical_semantic_value, semantic_json_hash
from mcp_strava.types import ReadModelMetadata

# See repository.py stream insert batching for the same DuckDB VALUES-parse rationale.
_FACT_UPSERT_BATCH_ROWS = 250

T = TypeVar("T")


class _ReadModelRepositoryHost(Protocol):
    conn: DuckDBConn
    _read_model_enabled_cache: bool | None
    _current_metric_version_cache: int | None

    def _commit_if_standalone(self) -> None: ...

    def _execute(self, sql: str, params: Iterable[object] | None = None) -> object: ...

    def _fetchone(self, sql: str, params: Iterable[object] | None = None) -> Row | None: ...

    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]: ...

    @staticmethod
    def _one(row: Row | None) -> T | None: ...

    @staticmethod
    def _all(rows: list[Row]) -> list[T]: ...

    def _table_columns(self, table: str) -> set[str]: ...

    def _table_exists(self, table: str) -> bool: ...

    def _next_id(self, table: str) -> int: ...

    def _now_iso(self) -> str: ...


class ReadModelRepositoryMixin(_ReadModelRepositoryHost):
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

    def _read_activity_source_components(self, activity_id: int) -> SourceComponents | None:
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

        summary_hash = semantic_json_hash(activity.get("summary_json"))
        detail_hash = semantic_json_hash(activity.get("detail_json"))

        stream_columns = sorted(self._table_columns("streams"))
        streams: list[Row] = []
        if stream_columns:
            quoted_cols = ", ".join(stream_columns)
            rows = self._fetchall(
                f"SELECT {quoted_cols} FROM streams WHERE activity_id = ? ORDER BY time_offset",
                [activity_id],
            )
            for row in rows:
                if "values_json" in row:
                    row["values_json"] = canonical_semantic_value(row["values_json"])
                streams.append(row)
        streams_hash = semantic_json_hash(streams)

        channels = self._fetchall(
            """
            SELECT channel_key, original_size, resolution, series_type, status, error
            FROM stream_channels
            WHERE activity_id = ?
            ORDER BY channel_key
            """,
            [activity_id],
        )
        channels_hash = semantic_json_hash(channels)

        source_payload = {
            "activity": {
                key: canonical_semantic_value(value)
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
            "source_hash": semantic_json_hash(source_payload),
        }

    def update_activity_source_state_and_enqueue_dirty(
        self,
        activity_id: int,
        *,
        reason: str = "source_changed",
        metric_version: int,
        queued_at: str | None = None,
    ) -> bool:
        if not self._read_model_enabled():
            return False
        components = self._read_activity_source_components(activity_id)
        if components is None:
            return False

        existing: SourceRevisionRow | None = self._one(
            self._fetchone(
                """
                SELECT source_hash, source_revision
                FROM activity_source_state
                WHERE activity_id = ?
                """,
                [activity_id],
            )
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

    def dirty_activity_rows(
        self, metric_version: int | None = None, activity_id: int | None = None
    ) -> list[DirtyActivityRow]:
        where: list[str] = []
        params: list[object] = []
        if metric_version is not None:
            where.append("metric_version = ?")
            params.append(metric_version)
        if activity_id is not None:
            where.append("activity_id = ?")
            params.append(activity_id)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        return self._all(
            self._fetchall(
                f"""
                SELECT *
                FROM metric_dirty_activities
                {where_sql}
                ORDER BY activity_day, activity_id, metric_version
                """,
                params,
            )
        )

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
                activity_id=_as_int(row["activity_id"]),
                activity_day=_as_str(row["activity_day"]),
                metric_version=metric_version,
                source_revision=_as_int(row["source_revision"]),
                reason=reason,
                queued_at=queued_at,
            )
        self._commit_if_standalone()
        return len(rows)

    def dirty_activity_rows_for_materialization(
        self,
        metric_version: int,
        limit: int | None = None,
    ) -> list[DirtyActivityRow]:
        base_sql = """
            SELECT d.*, s.source_hash
            FROM metric_dirty_activities d
            JOIN activity_source_state s ON s.activity_id = d.activity_id
            WHERE d.metric_version = ?
            ORDER BY d.activity_day, d.activity_id
        """
        if limit is None:
            return self._all(self._fetchall(base_sql, [metric_version]))

        rows: list[DirtyActivityRow] = self._all(self._fetchall(base_sql + " LIMIT ?", [metric_version, limit]))
        if not rows:
            return rows

        # WR-04: never return a PARTIAL day. The daily/rolling rollups sum
        # activity_metric_facts at this metric_version; if a day's activities are
        # split across batches (some materialized at N+1, the rest still queued),
        # that day under-counts until later batches land — yet the daily fact is
        # written as complete. Extend the batch to whole-day boundaries so every
        # activity for each day in the batch is materialized together. Rows are
        # ordered by (activity_day, activity_id), so only the LAST day in the
        # limited slice can be partially cut; pull in its remaining dirty rows.
        last_day = _as_str(rows[-1]["activity_day"])
        claimed_ids = {_as_int(r["activity_id"]) for r in rows if _as_str(r["activity_day"]) == last_day}
        remainder: list[DirtyActivityRow] = self._all(
            self._fetchall(
                base_sql.replace(
                    "WHERE d.metric_version = ?", "WHERE d.metric_version = ? AND d.activity_day = CAST(? AS DATE)"
                ),
                [metric_version, last_day],
            )
        )
        rows.extend(row for row in remainder if _as_int(row["activity_id"]) not in claimed_ids)
        return rows

    def clear_dirty_activity_rows(self, rows: Iterable[DirtyActivityRow]) -> int:
        count = 0
        for row in rows:
            activity_id = _as_int(row["activity_id"])
            activity_day = _as_str(row["activity_day"])
            metric_version = _as_int(row["metric_version"])
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

    def source_state_for_activity(self, activity_id: int) -> SourceStateRow | None:
        return self._one(
            self._fetchone(
                "SELECT * FROM activity_source_state WHERE activity_id = ?",
                [activity_id],
            )
        )

    def _upsert_fact(self, table: str, values: dict[str, object], conflict_columns: tuple[str, ...]) -> None:
        self._upsert_facts_batch(table, [values], conflict_columns)

    def _upsert_facts_batch(self, table: str, rows: list[dict[str, object]], conflict_columns: tuple[str, ...]) -> None:
        """Upsert many fact rows in batched multi-row INSERT … ON CONFLICT statements.

        One codepath for both single and many rows (``_upsert_fact`` delegates here), so
        the batched and per-row paths can never diverge. All rows must share the first
        row's column set (callers build them from one literal shape); a row missing a key
        raises KeyError below — fail loud, not silent. Rows are chunked at
        _FACT_UPSERT_BATCH_ROWS. The conflict columns must be unique across the batch
        (the fact keys are: per (day|as_of_day, scope, sport_type, window?, metric_version)
        or (activity_id, metric_version) — unique within one materialize pass), or DuckDB
        rejects a row that the same statement would touch twice.
        """
        if not rows:
            return
        _safe_identifier(table)
        columns = tuple(_safe_identifier(col) for col in rows[0])
        for col in conflict_columns:
            _safe_identifier(col)
        placeholder = "(" + ", ".join("?" for _ in columns) + ")"
        update_columns = [col for col in columns if col not in conflict_columns]
        assignments = ", ".join(f"{col}=excluded.{col}" for col in update_columns)
        conflict = ", ".join(conflict_columns)
        column_list = ", ".join(columns)
        for start in range(0, len(rows), _FACT_UPSERT_BATCH_ROWS):
            chunk = rows[start : start + _FACT_UPSERT_BATCH_ROWS]
            params: list[object] = []
            for row in chunk:
                params.extend(row[col] for col in columns)
            values_clause = ", ".join([placeholder] * len(chunk))
            self._execute(
                f"INSERT INTO {table} ({column_list}) VALUES {values_clause}"
                f" ON CONFLICT({conflict}) DO UPDATE SET {assignments}",
                params,
            )

    def upsert_activity_metric_fact(self, values: dict[str, object]) -> None:
        self._upsert_fact("activity_metric_facts", values, ("activity_id", "metric_version"))

    def upsert_activity_metric_facts(self, rows: list[dict[str, object]]) -> None:
        self._upsert_facts_batch("activity_metric_facts", rows, ("activity_id", "metric_version"))

    def upsert_daily_load_fact(self, values: dict[str, object]) -> None:
        self._upsert_fact("daily_load_facts", values, ("day", "scope", "sport_type", "metric_version"))

    def upsert_daily_load_facts(self, rows: list[dict[str, object]]) -> None:
        self._upsert_facts_batch("daily_load_facts", rows, ("day", "scope", "sport_type", "metric_version"))

    def upsert_training_model_daily_fact(self, values: dict[str, object]) -> None:
        self._upsert_fact("training_model_daily", values, ("day", "scope", "sport_type", "metric_version"))

    def upsert_training_model_daily_facts(self, rows: list[dict[str, object]]) -> None:
        self._upsert_facts_batch("training_model_daily", rows, ("day", "scope", "sport_type", "metric_version"))

    def upsert_rolling_period_fact(self, values: dict[str, object]) -> None:
        self._upsert_fact(
            "rolling_period_facts",
            values,
            ("as_of_day", "window_days", "scope", "sport_type", "metric_version"),
        )

    def upsert_rolling_period_facts(self, rows: list[dict[str, object]]) -> None:
        self._upsert_facts_batch(
            "rolling_period_facts",
            rows,
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
        return _as_int(payload["id"])

    # Read-model logic version (system-managed metric_version source of truth)
    def _max_fact_metric_version(self) -> int | None:
        """Max metric_version present across the four fact tables, or None when
        all are empty. Used as the seed/fallback when the sidecar is unseeded."""
        row = self._fetchone(
            """
            SELECT MAX(metric_version) AS v
            FROM (
                SELECT metric_version FROM activity_metric_facts
                UNION ALL
                SELECT metric_version FROM daily_load_facts
                UNION ALL
                SELECT metric_version FROM training_model_daily
                UNION ALL
                SELECT metric_version FROM rolling_period_facts
            ) all_facts
            """
        )
        if row is None or row.get("v") is None:
            return None
        return _as_int(row["v"])

    def current_logic_version(self) -> LogicVersionRow | None:
        """Return the singleton sidecar row ({metric_version, logic_fingerprint,
        changed_at}) or None when the table is empty/absent (unseeded DB)."""
        try:
            return self._one(
                self._fetchone(
                    """
                    SELECT metric_version, logic_fingerprint, changed_at
                    FROM read_model_logic_version
                    WHERE id=1
                    """
                )
            )
        except duckdb.CatalogException:
            # Sidecar table absent (schema not created yet / fail-soft path) — unseeded.
            return None

    def current_metric_version(self) -> int:
        """Return the system-managed metric_version.

        The sidecar is the single source of truth. The constructor seeds it
        whenever the schema exists, so on a healthy DB `stored` is never None;
        the only None case is the schema-missing fail-soft path (no read model
        yet), where 1 is the sane default. Memoized for the repo lifetime;
        bump_logic_version() clears the memo so a post-bump read sees the new int.
        """
        if self._current_metric_version_cache is not None:
            return self._current_metric_version_cache
        stored = self.current_logic_version()
        resolved = int(stored["metric_version"]) if stored is not None else 1
        self._current_metric_version_cache = resolved
        return resolved

    def bump_logic_version(self, metric_version: int, logic_fingerprint: str, changed_at: str) -> None:
        """Upsert the singleton sidecar row to (metric_version, fingerprint, ts).

        After the upsert commits, invalidate the current_metric_version memo on
        THIS repo instance (cycle-2 HIGH): the recompute path bumps to N+1 and
        immediately needs current_metric_version() to return N+1 so the
        materialize version and the enqueued dirty rows agree. Clearing the memo
        here is the single guaranteed point that closes that — callers never have
        to remember to reset it.
        """
        self._execute(
            """
            INSERT INTO read_model_logic_version (id, metric_version, logic_fingerprint, changed_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                metric_version=excluded.metric_version,
                logic_fingerprint=excluded.logic_fingerprint,
                changed_at=excluded.changed_at
            """,
            [metric_version, logic_fingerprint, changed_at],
        )
        self._commit_if_standalone()
        self._current_metric_version_cache = None

    # Read-model fact queries
    def read_model_status(self, metric_version: int | None = None) -> dict[str, Any]:
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

        dirty_count = _as_int(dirty["dirty_count"]) if dirty else 0
        last_materialized_at = None
        if run and run["last_materialized_at"]:
            last_materialized_at = str(run["last_materialized_at"])
        elif facts_summary and facts_summary["last_materialized_at"]:
            last_materialized_at = str(facts_summary["last_materialized_at"])
        # metric_versions_present is a DuckDB LIST aggregate — an opaque ``object``
        # cell. Narrow it to a concrete list before iterating/coercing the elements.
        raw_versions = facts_summary["metric_versions_present"] if facts_summary else None
        versions: list[int] = sorted(_as_int(v) for v in raw_versions) if isinstance(raw_versions, list) else []

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
    ) -> TrainingModelDayRow | None:
        if not self._read_model_enabled():
            return None
        where = ["metric_version = ?", "scope = ?", "sport_type = ?"]
        params: list[object] = [metric_version, scope, sport or "all"]
        if as_of_day is not None:
            where.append("day <= CAST(? AS DATE)")
            params.append(as_of_day)
        return self._one(
            self._fetchone(
                f"""
                SELECT *
                FROM training_model_daily
                WHERE {" AND ".join(where)}
                ORDER BY day DESC
                LIMIT 1
                """,
                params,
            )
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
    ) -> list[ActivityMetricFactRow]:
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
            where.append(
                "(f.activity_day < CAST(? AS DATE) OR (f.activity_day = CAST(? AS DATE) AND f.activity_id < ?))"
            )
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
        return self._all(self._fetchall(sql, params))

    def fetch_activity_metric_fact(
        self, activity_id: int, metric_version: int | None = None
    ) -> ActivityMetricFactRow | None:
        if not self._read_model_enabled():
            return None
        where = ["f.activity_id = ?"]
        params: list[object] = [activity_id]
        if metric_version is not None:
            where.append("f.metric_version = ?")
            params.append(metric_version)
        return self._one(
            self._fetchone(
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
        )

    def fetch_daily_load_facts(
        self,
        start_day: str,
        end_day: str,
        *,
        scope: str,
        sport: str | None = None,
        metric_version: int | None = None,
    ) -> list[DailyLoadFactRow]:
        if not self._read_model_enabled():
            return []
        where = ["day >= CAST(? AS DATE)", "day < CAST(? AS DATE)", "scope = ?", "sport_type = ?"]
        params: list[object] = [start_day, end_day, scope, sport or "all"]
        if metric_version is not None:
            where.append("metric_version = ?")
            params.append(metric_version)
        return self._all(
            self._fetchall(
                f"""
                SELECT *
                FROM daily_load_facts
                WHERE {" AND ".join(where)}
                ORDER BY day ASC
                """,
                params,
            )
        )

    def fetch_rolling_period_facts(
        self,
        as_of_day: str,
        window_days: int,
        *,
        scope: str,
        sport: str | None = None,
        metric_version: int | None = None,
    ) -> RollingPeriodFactRow | None:
        if not self._read_model_enabled():
            return None
        where = ["as_of_day = CAST(? AS DATE)", "window_days = ?", "scope = ?", "sport_type = ?"]
        params: list[object] = [as_of_day, window_days, scope, sport or "all"]
        if metric_version is not None:
            where.append("metric_version = ?")
            params.append(metric_version)
        return self._one(
            self._fetchone(
                f"""
                SELECT *
                FROM rolling_period_facts
                WHERE {" AND ".join(where)}
                ORDER BY metric_version DESC
                LIMIT 1
                """,
                params,
            )
        )

    def fetch_rolling_period_facts_by_windows(
        self,
        as_of_day: str,
        window_days: tuple[int, ...],
        *,
        scope: str,
        sport: str | None = None,
        metric_version: int | None = None,
    ) -> dict[int, RollingPeriodFactRow]:
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
        typed_rows: list[RollingPeriodFactRow] = self._all(
            self._fetchall(
                f"""
                SELECT *
                FROM rolling_period_facts
                WHERE {" AND ".join(where)}
                ORDER BY window_days ASC, metric_version DESC
                """,
                params,
            )
        )
        by_window: dict[int, RollingPeriodFactRow] = {}
        for row in typed_rows:
            window = _as_int(row["window_days"])
            by_window.setdefault(window, row)
        return by_window
