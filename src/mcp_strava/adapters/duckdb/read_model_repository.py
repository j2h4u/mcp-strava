"""Read-model status and fact-read repository methods."""

from __future__ import annotations

from typing import Any

from mcp_strava.adapters.duckdb.hydrated_activity_sql import (
    activity_hydration_joins,
    hydrated_activity_fact_select,
)
from mcp_strava.adapters.duckdb.read_model_fact_write_repository import ReadModelFactWriteRepositoryMixin
from mcp_strava.adapters.duckdb.read_model_logic_repository import ReadModelLogicRepositoryMixin
from mcp_strava.adapters.duckdb.read_model_source_repository import ReadModelSourceRepositoryMixin
from mcp_strava.adapters.duckdb.repository_models import (
    ActivityMetricFactRow,
    DailyLoadFactRow,
    RollingPeriodFactRow,
    TrainingModelDayRow,
)
from mcp_strava.adapters.duckdb.repository_utils import as_int as _as_int
from mcp_strava.types import ReadModelMetadata


class ReadModelRepositoryMixin(
    ReadModelSourceRepositoryMixin,
    ReadModelFactWriteRepositoryMixin,
    ReadModelLogicRepositoryMixin,
):
    # Read-model fact queries
    def read_model_status(self, metric_version: int | None = None) -> dict[str, Any]:
        if not self._read_model_enabled():
            return {
                "status": "unavailable",
                "last_materialized_at": None,
                "dirty_count": 0,
                "oldest_dirty_day": None,
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
        facts_summary = self._fetchone(
            """
            SELECT MAX(computed_at) AS last_materialized_at
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

        status = "current"
        stale_reason = None
        if dirty_count > 0:
            status = "stale"
            stale_reason = "dirty_queue_not_empty"
        elif last_materialized_at is None:
            status = "unavailable"
            stale_reason = "no_materialized_facts"

        metadata = ReadModelMetadata(
            status=status,
            last_materialized_at=last_materialized_at,
            dirty_count=dirty_count,
            oldest_dirty_day=str(dirty["oldest_dirty_day"]) if dirty and dirty["oldest_dirty_day"] else None,
            stale_reason=stale_reason,
        )
        return {
            "status": metadata.status,
            "last_materialized_at": metadata.last_materialized_at,
            "dirty_count": metadata.dirty_count,
            "oldest_dirty_day": metadata.oldest_dirty_day,
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
            SELECT f.*,
                   {hydrated_activity_fact_select()}
            FROM activity_metric_facts f
            LEFT JOIN activities a ON a.id = f.activity_id
            {activity_hydration_joins()}
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
                SELECT f.*,
                       {hydrated_activity_fact_select()}
                FROM activity_metric_facts f
                LEFT JOIN activities a ON a.id = f.activity_id
                {activity_hydration_joins()}
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
