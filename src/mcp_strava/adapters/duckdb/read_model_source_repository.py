"""Read-model source-state and dirty-queue repository methods."""

from __future__ import annotations

from collections.abc import Iterable

from mcp_strava.adapters.duckdb.read_model_repository_host import ReadModelRepositoryHost
from mcp_strava.adapters.duckdb.repository_models import (
    DirtyActivityRow,
    SourceComponents,
    SourceRevisionRow,
    SourceStateRow,
)
from mcp_strava.adapters.duckdb.repository_utils import Row
from mcp_strava.adapters.duckdb.repository_utils import as_int as _as_int
from mcp_strava.adapters.duckdb.repository_utils import as_str as _as_str
from mcp_strava.adapters.duckdb.source_hashing import canonical_semantic_value, semantic_json_hash


class ReadModelSourceRepositoryMixin(ReadModelRepositoryHost):
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
