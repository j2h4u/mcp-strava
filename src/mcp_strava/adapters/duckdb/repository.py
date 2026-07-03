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
from mcp_strava.adapters.duckdb.repository_models import (
    ActivitySourcePayload,
    ActivitySourcePayloadRow,
    ActivitySummaryRecord,
)
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
from mcp_strava.adapters.duckdb.schema_tables import BRONZE_PAYLOAD_SCHEMA_SQL
from mcp_strava.adapters.duckdb.source_hashing import raw_payload_hash, semantic_json_hash
from mcp_strava.adapters.duckdb.stream_write_repository import StreamWriteRepositoryMixin


def _emit(event: str, **fields: object) -> None:
    """Emit a structured JSON diagnostic event to stdout (house log style)."""
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


@dataclass
class DuckDBRepository(ReadModelRepositoryMixin, StreamWriteRepositoryMixin):
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
        """Create additive storage extensions and seed schema sidecars."""
        self._ensure_bronze_payload_schema()
        self._backfill_bronze_activity_payloads_from_legacy()
        self._bootstrap_legacy_source_state_from_bronze()
        self._seed_logic_version()

    def _ensure_bronze_payload_schema(self) -> None:
        """Create the source-payload namespace for existing mirrors."""
        with duckdb_process_lock():
            has_payload_table = self.conn.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'bronze'
                  AND table_name = 'activity_payloads'
                LIMIT 1
                """
            ).fetchone()
            if has_payload_table is not None:
                columns = {
                    str(cast("tuple[object, ...]", row)[0])
                    for row in self.conn.execute(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'bronze'
                          AND table_name = 'activity_payloads'
                        """
                    ).fetchall()
                }
                if "recorded_at" not in columns:
                    self.conn.execute(
                        """
                        ALTER TABLE bronze.activity_payloads
                        ADD COLUMN recorded_at VARCHAR
                        """
                    )
                    self.conn.execute(
                        """
                        UPDATE bronze.activity_payloads
                        SET recorded_at = fetched_at
                        WHERE recorded_at IS NULL
                        """
                    )
            self.conn.execute(BRONZE_PAYLOAD_SCHEMA_SQL)

    def _backfill_bronze_activity_payloads_from_legacy(self) -> None:
        """Seed bronze payloads from existing activity raw columns once."""
        if not self._table_exists("activities"):
            return
        if self._bronze_legacy_payloads_are_backfilled():
            return
        rows = self._fetchall(
            """
            SELECT id, activity_day, summary_json, detail_json, synced_at
            FROM activities
            WHERE summary_json IS NOT NULL OR detail_json IS NOT NULL
            """
        )
        for row in rows:
            activity_id = _as_int(row["id"])
            activity_day = str(row["activity_day"]) if row["activity_day"] is not None else None
            fetched_at = str(row["synced_at"] or self._now_iso())
            self._backfill_legacy_activity_payload(
                activity_id=activity_id,
                activity_day=activity_day,
                payload_kind="summary",
                endpoint="/athlete/activities",
                fetched_at=fetched_at,
                payload_json=row["summary_json"],
            )
            self._backfill_legacy_activity_payload(
                activity_id=activity_id,
                activity_day=activity_day,
                payload_kind="detail",
                endpoint=f"/activities/{activity_id}",
                fetched_at=fetched_at,
                payload_json=row["detail_json"],
            )

    def _backfill_legacy_activity_payload(
        self,
        *,
        activity_id: int,
        activity_day: str | None,
        payload_kind: str,
        endpoint: str,
        fetched_at: str,
        payload_json: object,
    ) -> None:
        if not isinstance(payload_json, str):
            return
        exists = self._fetchone(
            """
            SELECT 1
            FROM bronze.activity_payloads
            WHERE activity_id = ?
              AND payload_kind = ?
              AND payload_json = ?
              AND migrated_from_legacy = TRUE
            LIMIT 1
            """,
            [activity_id, payload_kind, payload_json],
        )
        if exists is not None:
            return
        self.write_activity_payload(
            ActivitySourcePayload(
                activity_id=activity_id,
                activity_day=activity_day,
                payload_kind=payload_kind,
                endpoint=endpoint,
                fetched_at=fetched_at,
                payload_json=payload_json,
                raw_hash=raw_payload_hash(payload_json),
                modeled_projection_hash=semantic_json_hash(payload_json),
                schema_status="clean",
                migrated_from_legacy=True,
            )
        )

    def _bronze_legacy_payloads_are_backfilled(self) -> bool:
        row = self._fetchone(
            """
            SELECT
                (
                    SELECT COUNT(*)
                    FROM activities
                    WHERE summary_json IS NOT NULL
                ) + (
                    SELECT COUNT(*)
                    FROM activities
                    WHERE detail_json IS NOT NULL
                ) AS legacy_payload_count,
                (
                    SELECT COUNT(*)
                    FROM bronze.activity_payloads
                    WHERE migrated_from_legacy = TRUE
                ) AS migrated_payload_count
            """
        )
        if row is None:
            return False
        return _as_int(row["migrated_payload_count"]) >= _as_int(row["legacy_payload_count"])

    def _bootstrap_legacy_source_state_from_bronze(self) -> None:
        """Seed source state from migrated legacy payloads once per activity.

        This is only for upgraded mirrors that still lack any materialized
        read-model provenance. If facts already exist, the mirror is already
        current enough for reopen and we leave legacy bronze rows alone.
        """
        if not self._read_model_enabled():
            return
        if self._has_read_model_provenance():
            return
        metric_version = self.current_metric_version()
        rows = self._fetchall(
            """
            SELECT DISTINCT p.activity_id
            FROM bronze.latest_activity_payloads p
            LEFT JOIN activity_source_state s ON s.activity_id = p.activity_id
            LEFT JOIN activity_metric_facts f
              ON f.activity_id = p.activity_id
             AND f.metric_version = ?
            WHERE p.migrated_from_legacy = TRUE
              AND s.activity_id IS NULL
              AND f.activity_id IS NULL
            ORDER BY p.activity_id
            """,
            [metric_version],
        )
        for row in rows:
            self.update_activity_source_state_and_enqueue_dirty(
                _as_int(row["activity_id"]),
                reason="bronze_payload_changed",
                metric_version=metric_version,
            )

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

    def write_activity_payload(self, payload: ActivitySourcePayload) -> None:
        """Append one raw Strava activity payload to the bronze namespace."""
        latest = self.latest_activity_payload(payload.activity_id, payload.payload_kind)
        if latest is not None and latest["raw_hash"] == payload.raw_hash:
            return
        self._execute(
            """
            INSERT INTO bronze.activity_payloads (
                activity_id,
                activity_day,
                payload_kind,
                endpoint,
                fetched_at,
                payload_json,
                raw_hash,
                modeled_projection_hash,
                schema_status,
                drift_fingerprint,
                recorded_at,
                migrated_from_legacy
            ) VALUES (?, CAST(? AS DATE), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                payload.activity_id,
                payload.activity_day,
                payload.payload_kind,
                payload.endpoint,
                payload.fetched_at,
                payload.payload_json,
                payload.raw_hash,
                payload.modeled_projection_hash,
                payload.schema_status,
                payload.drift_fingerprint,
                self._now_iso(),
                payload.migrated_from_legacy,
            ],
        )
        self._commit_if_standalone()

    def latest_activity_payload(self, activity_id: int, payload_kind: str) -> ActivitySourcePayloadRow | None:
        row = self._fetchone(
            """
            SELECT
                activity_id,
                activity_day,
                payload_kind,
                endpoint,
                fetched_at,
                payload_json,
                raw_hash,
                modeled_projection_hash,
                schema_status,
                drift_fingerprint,
                migrated_from_legacy
            FROM bronze.latest_activity_payloads
            WHERE activity_id = ? AND payload_kind = ?
            """,
            [activity_id, payload_kind],
        )
        return cast("ActivitySourcePayloadRow | None", row)

    def activity_ids_with_bronze_payloads(self) -> list[int]:
        rows = self._fetchall(
            """
            SELECT DISTINCT activity_id
            FROM bronze.latest_activity_payloads
            ORDER BY activity_id
            """
        )
        return [_as_int(row["activity_id"]) for row in rows]

    def activity_ids_with_source_bronze_payloads(self) -> list[int]:
        """Return activities whose latest bronze payload came from source ingest."""
        rows = self._fetchall(
            """
            SELECT DISTINCT activity_id
            FROM bronze.latest_activity_payloads
            WHERE migrated_from_legacy = FALSE
            ORDER BY activity_id
            """
        )
        return [_as_int(row["activity_id"]) for row in rows]

    def activity_ids_needing_source_state_bootstrap(self) -> list[int]:
        """Return bronze-backed activities that still lack current provenance.

        Migrated legacy payloads are only included when the mirror has not yet
        materialized any read-model facts. That keeps reopen of already-current
        mirrors from fabricating dirty rows while still allowing a legacy-only
        DB to seed provenance exactly once.
        """
        if self._has_read_model_provenance():
            return []
        metric_version = self.current_metric_version()
        rows = self._fetchall(
            """
            SELECT DISTINCT activity_id
            FROM (
                SELECT activity_id
                FROM bronze.latest_activity_payloads
                WHERE migrated_from_legacy = FALSE
                UNION
                SELECT p.activity_id
                FROM bronze.latest_activity_payloads p
                LEFT JOIN activity_source_state s ON s.activity_id = p.activity_id
                LEFT JOIN activity_metric_facts f
                  ON f.activity_id = p.activity_id
                 AND f.metric_version = ?
                WHERE p.migrated_from_legacy = TRUE
                  AND s.activity_id IS NULL
                  AND f.activity_id IS NULL
            )
            ORDER BY activity_id
            """,
            [metric_version],
        )
        return [_as_int(row["activity_id"]) for row in rows]

    def _has_read_model_provenance(self) -> bool:
        return (
            self._fetchone(
                """
            SELECT 1
            FROM (
                SELECT 1 FROM activity_metric_facts
                UNION ALL
                SELECT 1 FROM daily_load_facts
                UNION ALL
                SELECT 1 FROM training_model_daily
                UNION ALL
                SELECT 1 FROM rolling_period_facts
                UNION ALL
                SELECT 1 FROM read_model_refresh_runs
            ) provenance
            LIMIT 1
            """
            )
            is not None
        )

    def insert_activity_summary_if_missing(self, record: ActivitySummaryRecord) -> bool:
        """Create the modeled activity shell for a bronze summary, without updates."""
        existing = self._fetchone("SELECT 1 FROM activities WHERE id = ? LIMIT 1", [record.activity_id])
        if existing is not None:
            return False
        self._execute(
            """
            INSERT INTO activities (
                id, activity_day, name, sport_type, distance, moving_time,
                elapsed_time, total_elevation_gain, summary_json, synced_at
            ) VALUES (?, CAST(? AS DATE), ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record.activity_id,
                record.date[:10],
                record.name,
                record.sport_type,
                record.distance,
                record.moving_time,
                record.elapsed_time,
                record.total_elevation_gain,
                record.summary_json,
                record.synced_at,
            ],
        )
        self._commit_if_standalone()
        return True

    def upsert_activity_summary(self, record: ActivitySummaryRecord) -> None:
        self.begin()
        try:
            self._execute(
                """
                INSERT INTO activities (
                    id, activity_day, name, sport_type, distance, moving_time,
                    elapsed_time, total_elevation_gain, summary_json, synced_at
                ) VALUES (?, CAST(? AS DATE), ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    activity_day=excluded.activity_day,
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
                    record.activity_id,
                    record.date[:10],
                    record.name,
                    record.sport_type,
                    record.distance,
                    record.moving_time,
                    record.elapsed_time,
                    record.total_elevation_gain,
                    record.summary_json,
                    record.synced_at,
                ],
            )
            self.update_activity_source_state_and_enqueue_dirty(
                record.activity_id, metric_version=self.current_metric_version()
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
