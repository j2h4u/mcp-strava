"""Read-model fact upsert and refresh-run repository methods."""

from __future__ import annotations

from mcp_strava.adapters.duckdb.read_model_repository_host import ReadModelRepositoryHost
from mcp_strava.adapters.duckdb.repository_utils import as_int as _as_int
from mcp_strava.adapters.duckdb.repository_utils import safe_identifier as _safe_identifier

# See repository.py stream insert batching for the same DuckDB VALUES-parse rationale.
_FACT_UPSERT_BATCH_ROWS = 250


class ReadModelFactWriteRepositoryMixin(ReadModelRepositoryHost):
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

    def prune_old_read_model_metric_versions(self, current_metric_version: int) -> dict[str, int]:
        """Delete superseded read-model rows and return deleted counts per table."""
        tables = (
            "activity_metric_facts",
            "daily_load_facts",
            "training_model_daily",
            "rolling_period_facts",
            "metric_dirty_activities",
        )
        deleted_counts: dict[str, int] = {}
        for table in tables:
            safe_table = _safe_identifier(table)
            row = self._fetchone(
                f"SELECT COUNT(*) AS deleted_count FROM {safe_table} WHERE metric_version < ?",
                [current_metric_version],
            )
            deleted_count = _as_int(row["deleted_count"]) if row is not None else 0
            if deleted_count > 0:
                self._execute(
                    f"DELETE FROM {safe_table} WHERE metric_version < ?",
                    [current_metric_version],
                )
            deleted_counts[table] = deleted_count
        return deleted_counts
