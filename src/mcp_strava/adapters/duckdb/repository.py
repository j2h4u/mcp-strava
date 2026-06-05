"""DuckDB repository boundary for primary Strava mirror storage."""

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import duckdb

from mcp_strava.adapters.duckdb.connection import (
    DuckDBConn,
    duckdb_process_lock,
    open_expected_mirror_db,
    open_fixture_db,
)
from mcp_strava.adapters.duckdb.read_model_repository import ReadModelRepositoryMixin
from mcp_strava.adapters.duckdb.repository_utils import (
    Row,
)
from mcp_strava.adapters.duckdb.repository_utils import (
    as_int as _as_int,
)
from mcp_strava.adapters.duckdb.repository_utils import (
    normalize_cell as _normalize_cell,
)
from mcp_strava.adapters.duckdb.repository_utils import (
    safe_identifier as _safe_identifier,
)


def _emit(event: str, **fields: object) -> None:
    """Emit a structured JSON diagnostic event to stdout (house log style)."""
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


# Stream-row insert column order (must match the streams table) and the per-statement
# row cap for batched multi-row INSERTs in _insert_stream_rows. See that method for why.
_STREAM_INSERT_COLUMNS = (
    "activity_id",
    "time_offset",
    "heartrate",
    "velocity",
    "altitude",
    "cadence",
    "lat",
    "lng",
    "grade",
    "gap_speed",
    "gap_distance",
    "is_moving",
    "values_json",
)
_STREAM_INSERT_STMT_ROWS = 250


@dataclass
class DuckDBRepository(ReadModelRepositoryMixin):
    """Focused DuckDB repository with explicit unit-of-work lifetime."""

    conn: DuckDBConn
    _transaction_depth: int = field(default=0, init=False, repr=False)
    _transaction_lock_held: bool = field(default=False, init=False, repr=False)
    _read_model_enabled_cache: bool | None = field(default=None, init=False, repr=False)
    # One-shot memo for current_metric_version(): the unseeded fallback scans 4
    # UNION ALL'd fact tables, so the resolved version is cached for the repo
    # lifetime. None is the sentinel for "not yet resolved"; bump_logic_version()
    # resets it to None so a post-bump read re-reads the freshly-written sidecar.
    _current_metric_version_cache: int | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_path(cls, db_path: str | Path, expected_mirror: bool = False) -> DuckDBRepository:
        path = Path(db_path)
        conn = open_expected_mirror_db(path) if expected_mirror else open_fixture_db(path)
        repo = cls(conn=conn)
        repo._ensure_schema_extensions()
        return repo

    @classmethod
    def from_connection(cls, conn: DuckDBConn) -> DuckDBRepository:
        repo = cls(conn=conn)
        repo._ensure_schema_extensions()
        return repo

    def _ensure_schema_extensions(self) -> None:
        """Seed the read_model_logic_version sidecar on construction."""
        self._seed_logic_version()

    def _seed_logic_version(self) -> None:
        """Idempotently seed the read_model_logic_version singleton with the
        CURRENT live fingerprint, so the first refresh after deploy sees
        stored == live and does NOT recompute (adopt-current by construction).

        Tolerates ONLY the table-not-created-yet case (CatalogException) — the
        schema-missing / repo-opened-before-create_schema fail-soft path — by
        emitting a structured event and skipping. Anything else (e.g.
        compute_logic_fingerprint() failing to read source) propagates loudly:
        on this deployment getsource always works, and a real failure should
        crash, not silently leave the sidecar unseeded.
        """
        try:
            existing = self.conn.execute("SELECT 1 FROM read_model_logic_version WHERE id=1").fetchone()
            if existing is not None:
                return
            from mcp_strava.metric_registry import compute_logic_fingerprint

            fingerprint = compute_logic_fingerprint()
            seed_version = self._max_fact_metric_version() or 1
            self.conn.execute(
                """
                INSERT INTO read_model_logic_version (id, metric_version, logic_fingerprint, changed_at)
                VALUES (1, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING
                """,
                [seed_version, fingerprint, self._now_iso()],
            )
        except duckdb.CatalogException as exc:  # table absent (schema-missing fail-soft); everything else fails loud
            _emit(
                "read_model_logic_version_seed_skipped",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )

    def __enter__(self) -> DuckDBRepository:
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb) -> None:
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

    def _fetchone(self, sql: str, params: Iterable[object] | None = None) -> Row | None:
        if self._transaction_depth > 0:
            result = self.conn.execute(sql, list(params or []))
            row = result.fetchone()
        else:
            with duckdb_process_lock():
                result = self.conn.execute(sql, list(params or []))
                row = result.fetchone()
        if row is None:
            return None
        # ``result.description`` is typed ``list[tuple[str, ...]]`` (the typed conn
        # gives us column names for free); the cell tuple is ``tuple[Any, ...]``, so
        # the single ``Any -> object`` narrowing is pinned here by casting the row.
        columns = [item[0] for item in result.description]
        return {
            column: _normalize_cell(value)
            for column, value in zip(columns, cast("tuple[object, ...]", row), strict=False)
        }

    def _fetchall(self, sql: str, params: Iterable[object] | None = None) -> list[Row]:
        if self._transaction_depth > 0:
            result = self.conn.execute(sql, list(params or []))
            rows = result.fetchall()
        else:
            with duckdb_process_lock():
                result = self.conn.execute(sql, list(params or []))
                rows = result.fetchall()
        columns = [item[0] for item in result.description]
        return [
            {
                column: _normalize_cell(value)
                for column, value in zip(columns, cast("tuple[object, ...]", row), strict=False)
            }
            for row in rows
        ]

    @staticmethod
    def _one[T](row: Row | None) -> T | None:
        """Narrow a generic fetched row to a per-query ``TypedDict`` shape ``T``.

        The cast is the documented contract that the SELECT's column list matches
        ``T``; it is a no-op at runtime (the dict is unchanged), so ``row["key"]``
        access keeps working while the type checker now sees the precise field
        types. Centralizing it here keeps the ``Any``/``object``-to-typed step in
        one auditable place instead of scattered inline casts.
        """
        return cast("T | None", row)

    @staticmethod
    def _all[T](rows: list[Row]) -> list[T]:
        """List counterpart of :meth:`_one` — narrow each fetched row to ``T``."""
        return cast("list[T]", rows)

    def _scalar(self, sql: str, params: Iterable[object] | None = None) -> object | None:
        # Single-column scalar reads. ``fetchone()`` yields ``tuple[Any, ...] | None``;
        # casting the tuple to ``tuple[object, ...]`` narrows ``row[0]`` from ``Any``
        # to ``object`` here, so every ``_scalar`` caller works against an opaque
        # value it must explicitly coerce (``int(...)``/``str(...)``) rather than a
        # silently-propagating ``Any``.
        if self._transaction_depth > 0:
            row = self.conn.execute(sql, list(params or [])).fetchone()
        else:
            with duckdb_process_lock():
                row = self.conn.execute(sql, list(params or [])).fetchone()
        return cast("tuple[object, ...]", row)[0] if row is not None else None

    def _scalar_int(self, sql: str, params: Iterable[object] | None = None) -> int:
        """Run a scalar COUNT/aggregate query and return a plain ``int``.

        The single controlled place where the unavoidable ``Any -> int`` narrowing
        on a raw DB-API scalar happens, so public count methods stay fully typed and
        no ``reportAny`` leaks out of the repository. A NULL/absent scalar (e.g.
        ``COUNT(*)`` on an empty table never NULLs, but ``SUM`` can) collapses to 0.
        The ``isinstance`` narrows ``Any -> int`` for the type checker (DuckDB
        returns Python ``int`` for COUNT/SUM aggregates); a non-int/None scalar
        means the query was misused as a counter, so fail loudly rather than coerce.
        """
        # Assign through an ``object``-typed local: _scalar returns ``Any | None``,
        # and ``object`` erases the ``Any`` so the isinstance narrowing below gives
        # the type checker a concrete ``int`` (no reportAny leak past this point).
        value: object = self._scalar(sql, params)
        if value is None:
            return 0
        if not isinstance(value, int):
            raise TypeError(f"_scalar_int expected an integer scalar, got {type(value).__name__}")
        return value

    def _table_columns(self, table: str) -> set[str]:
        _safe_identifier(table)
        with duckdb_process_lock():
            rows = self.conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        # PRAGMA table_info returns (cid, name, type, ...); column 1 is the name.
        # Cast the row tuple so ``row[1]`` is ``object`` (then ``str(...)``), not ``Any``.
        return {str(cast("tuple[object, ...]", row)[1]) for row in rows}

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
        _safe_identifier(table)
        value = self._scalar(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table}")
        return _as_int(value, default=1)

    def _now_iso(self) -> str:
        return datetime.now(UTC).replace(tzinfo=None).isoformat()

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
            self.update_activity_source_state_and_enqueue_dirty(
                activity_id, metric_version=self.current_metric_version()
            )
        except Exception:
            self.rollback()
            raise
        self.commit()

    def update_activity_detail(self, activity_id: int, detail_json: str) -> None:
        self.begin()
        try:
            self._execute("UPDATE activities SET detail_json = ? WHERE id = ?", [detail_json, activity_id])
            self.update_activity_source_state_and_enqueue_dirty(
                activity_id, metric_version=self.current_metric_version()
            )
        except Exception:
            self.rollback()
            raise
        self.commit()

    def daily_fact_sums_between(self, start_day: str, end_day: str, metric_version: int) -> dict[str, dict[str, Any]]:
        """Return per-day SUM aggregates over activity_metric_facts for a date range.

        One GROUP BY range scan replaces the materializer's N single-day reads when
        rolling per-activity facts into daily_load_facts — the dominant read cost on a
        full-history recompute (~one read per calendar day, ~2000 on a multi-year
        mirror). Keyed by ISO day string. Days with no facts (REST/UNKNOWN/PARTIAL) are
        simply absent from the result; the caller substitutes an all-NULL row, matching
        the no-GROUP-BY shape the old per-day query returned for an empty day.
        """
        rows = self._fetchall(
            """
            SELECT
              activity_day AS day,
              SUM(distance_m) AS distance_m,
              SUM(moving_time_s) AS moving_time_s,
              SUM(elevation_gain_m) AS elevation_gain_m,
              SUM(zone4_seconds) AS zone4_seconds,
              SUM(zone5_seconds) AS zone5_seconds,
              SUM(anomaly_count) AS anomaly_count
            FROM activity_metric_facts
            WHERE activity_day BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
              AND metric_version = ?
            GROUP BY activity_day
            """,
            [start_day, end_day, metric_version],
        )
        return {str(row["day"]): row for row in rows}

    def rolling_load_aggregate(self, start: str, as_of_day: str, metric_version: int) -> dict[str, Any]:
        """Return the rolling-window load aggregate from daily_load_facts between start and as_of_day.

        Filters for scope='all', sport_type='all'. Used by _materialize_rolling_facts. A
        no-GROUP-BY aggregate always yields exactly one row, so the result is never None.
        """
        row = self._fetchone(
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
        assert row is not None  # SUM/COUNT with no GROUP BY always returns one row
        return row

    def training_model_row(self, as_of_day: str, metric_version: int) -> dict[str, Any] | None:
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

    def rolling_cardiac_metric_rows(self, start: str, as_of_day: str, metric_version: int) -> list[dict[str, Any]]:
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
            self.update_activity_source_state_and_enqueue_dirty(
                activity_id, metric_version=self.current_metric_version()
            )
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
            self.update_activity_source_state_and_enqueue_dirty(
                activity_id, metric_version=self.current_metric_version()
            )
        except Exception:
            self.rollback()
            raise
        self.commit()
        return len(payload)

    def _insert_stream_rows(self, activity_id: int, rows: list[dict], chunk_size: int) -> None:
        # DuckDB is columnar: a per-row ``executemany`` — and the never-firing
        # ``ON CONFLICT DO UPDATE`` this used to carry — runs ~3.5x slower than batched
        # multi-row INSERTs. Every caller writes a clean slate (replace_* DELETE the
        # activity's rows first; insert_stream_rows_chunked targets a fresh activity), so a
        # plain INSERT is correct and a genuine (activity_id, time_offset) duplicate SHOULD
        # fail loudly rather than silently upsert. The per-statement row count is capped
        # (not the caller's chunk_size) because DuckDB parses the VALUES literal and that
        # cost grows with the placeholder count; 250 rows stays one statement for
        # test-size blocks while keeping long rides off the quadratic-parse tail.
        columns = ", ".join(_STREAM_INSERT_COLUMNS)
        placeholder = "(" + ", ".join(["?"] * len(_STREAM_INSERT_COLUMNS)) + ")"
        step = min(chunk_size, _STREAM_INSERT_STMT_ROWS)
        for start in range(0, len(rows), step):
            chunk = rows[start : start + step]
            params: list[object] = []
            for row in chunk:
                params.extend(
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
                )
            values_clause = ", ".join([placeholder] * len(chunk))
            self._execute(f"INSERT INTO streams ({columns}) VALUES {values_clause}", params)

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
                self.update_activity_source_state_and_enqueue_dirty(
                    activity_id, metric_version=self.current_metric_version()
                )
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
            self.update_activity_source_state_and_enqueue_dirty(
                activity_id, metric_version=self.current_metric_version()
            )
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
            self.update_activity_source_state_and_enqueue_dirty(
                activity_id, metric_version=self.current_metric_version()
            )
        except Exception:
            self.rollback()
            raise
        self.commit()
        return len(payload)
