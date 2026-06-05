"""DuckDB repository boundary for primary Strava mirror storage."""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TypedDict, cast

import duckdb

from mcp_strava.adapters.duckdb.connection import (
    DuckDBConn,
    duckdb_process_lock,
    open_expected_mirror_db,
    open_fixture_db,
)
from mcp_strava.adapters.duckdb.source_hashing import canonical_semantic_value, semantic_json_hash
from mcp_strava.constants import Config
from mcp_strava.metrics import discounted_effective_trimp
from mcp_strava.sports import SPORT_TRAINING as TRAINING_SPORTS
from mcp_strava.types import (
    ALLOWED_REASON_CODES,
    DailyLoadPoint,
    ReadModelMetadata,
    RefreshRequestRow,
    RefreshStateRow,
    RepositoryActivityRow,
    RepositorySyncLogEntry,
)

# The generic DB-API row boundary. A raw row out of DuckDB is a heterogeneous
# mapping of column name -> cell value whose static shape the fetch helpers
# cannot know, so the honest type is ``dict[str, object]`` — NOT ``dict[str,
# Any]``. ``object`` keeps the values opaque (so a stray ``row["x"] + 1`` is a
# type error, not silently ``Any``) while still allowing the ``str(...)`` /
# ``bool(...)`` narrowing the repository does. Each public read method then casts
# this generic row to a precise ``TypedDict`` (the *RowDict types below) via
# ``_one``/``_all``, so the unavoidable ``Any -> typed`` narrowing happens
# exactly once, at the ``_fetchall``/``_fetchone`` consumption boundary.
Row = dict[str, object]


# ─── Typed row shapes (per-query result contracts) ───
#
# These TypedDicts describe the column shape each read query returns. Casting the
# generic ``Row`` to one of these (via ``_one``/``_all``) lets ``row["id"]`` stay
# (no caller churn) while typing the access precisely: ``int(row["id"])`` is then
# ``int(int)``, not ``int(Any)``. Numeric cells are typed ``int | None`` /
# ``float | None`` because aggregates (SUM/AVG) and outer-joined columns can be
# SQL NULL; the repository narrows the None with ``or 0`` / ``is not None``.


class _IdRow(TypedDict):
    id: int


class _DayCountRow(TypedDict):
    """``day``/``c`` grouped-count rows from the daily-load count queries."""

    day: object
    c: int


class _TrimpDayRow(TypedDict):
    day: object
    trimp: float | None


class _TrimpDaySportRow(TypedDict):
    day: object
    sport: object
    trimp: float | None


class _DirtyActivityRow(TypedDict):
    """A row of ``metric_dirty_activities`` (``SELECT *``); the materialization
    variant additionally carries the joined ``source_hash`` column."""

    activity_id: int
    activity_day: object
    metric_version: int
    source_revision: int
    reason: str
    queued_at: object
    attempt_count: int
    last_error: str | None
    source_hash: str


class _SourceStateRow(TypedDict):
    activity_id: int
    activity_day: object
    summary_hash: str
    detail_hash: str
    streams_hash: str
    channels_hash: str
    source_hash: str
    source_revision: int
    changed_at: object


@dataclass(frozen=True)
class ActivityMaterializationSource:
    activity: RepositoryActivityRow
    source_hash: str
    source_revision: int


@dataclass(frozen=True)
class ActivityStreamScalars:
    stream_count: int
    hr_count: int
    min_hr: int | None
    max_hr: int | None
    cardiac_cost: float | None
    median_hr: float | None


@dataclass(frozen=True)
class ActivityZoneTrimp:
    zone1_seconds: int
    zone2_seconds: int
    zone3_seconds: int
    zone4_seconds: int
    zone5_seconds: int
    trimp: float


class _SourceRevisionRow(TypedDict):
    source_hash: str
    source_revision: int


class _SourceComponents(TypedDict):
    """Computed provenance hashes for one activity (all values are strings)."""

    activity_day: str
    summary_hash: str
    detail_hash: str
    streams_hash: str
    channels_hash: str
    source_hash: str


class _LogicVersionRow(TypedDict):
    metric_version: int
    logic_fingerprint: str
    changed_at: object


class _ScalarVersionRow(TypedDict):
    v: int | None


class _LeaseRow(TypedDict):
    lease_owner: str | None
    lease_expires_at: object


class _ChannelStatusRow(TypedDict):
    status: str


class _ValuesJsonRow(TypedDict):
    values_json: object


# ─── Wide fact-read TypedDicts (public repository read boundary) ───
#
# Each TypedDict below maps one SELECTed column set to a concrete shape so
# that application-layer callers never see ``dict[str, Any]``. The cast from
# ``Row`` (``dict[str, object]``) to these TypedDicts happens via ``_all``/
# ``_one`` — exactly one controlled cast per public read method.
#
# Nullable columns (SQL NULL / outer-join) are typed ``X | None``.
# DATE columns come back as ISO strings (see ``_normalize_cell``).


class ActivityMetricFactRow(TypedDict):
    """Row returned by ``fetch_activity_metric_facts`` / ``fetch_activity_metric_fact``.

    Columns: ``activity_metric_facts f`` (SELECT *) joined with
    ``activities a`` (name, date, summary_json, detail_json).
    Metric-specific numeric columns (trimp, zone*_seconds, etc.) are all
    nullable because a fact row is written incrementally — a column is NULL
    until the activity is (re)materialised with that metric.
    """

    # ── PK / identity ──
    activity_id: object  # int stored as BIGINT; object to match _normalize_cell
    activity_day: object  # DATE → ISO str
    metric_version: object  # BIGINT
    # ── Completeness ──
    completeness_status: object  # VARCHAR
    missing_reasons_json: object  # VARCHAR (JSON list)
    source_revision: object  # BIGINT
    computed_at: object  # VARCHAR timestamp
    # ── Core metric columns (nullable — NULL until materialised) ──
    trimp: object  # DOUBLE | NULL
    distance_m: object  # DOUBLE | NULL
    moving_time_s: object  # BIGINT | NULL
    elapsed_time_s: object  # BIGINT | NULL
    elevation_gain_m: object  # DOUBLE | NULL
    zone1_seconds: object  # BIGINT | NULL
    zone2_seconds: object  # BIGINT | NULL
    zone3_seconds: object  # BIGINT | NULL
    zone4_seconds: object  # BIGINT | NULL
    zone5_seconds: object  # BIGINT | NULL
    hr_recovery_pause_count: object  # BIGINT | NULL
    hr_recovery_total_rest_sec: object  # BIGINT | NULL
    hr_recovery_median_rate: object  # DOUBLE | NULL
    hr_recovery_best_rate: object  # DOUBLE | NULL
    hr_recovery_worst_rate: object  # DOUBLE | NULL
    hr_recovery_avg_rate: object  # DOUBLE | NULL
    vertical_speed_vmh: object  # DOUBLE | NULL
    vertical_speed_total_ascent_m: object  # DOUBLE | NULL
    vertical_speed_duration_hours: object  # DOUBLE | NULL
    cardiac_cost: object  # DOUBLE | NULL
    adjusted_cardiac_cost: object  # DOUBLE | NULL
    cardiac_drift_pct: object  # DOUBLE | NULL
    cardiac_drift_significant: object  # BIGINT | NULL
    cardiac_drift_severity: object  # VARCHAR | NULL
    cardiac_drift_quality: object  # VARCHAR | NULL
    hrr_pct: object  # DOUBLE | NULL
    anomaly_count: object  # BIGINT | NULL
    start_time_local: object  # VARCHAR | NULL
    sport_type: object  # VARCHAR
    # ── Joined from activities ──
    activity_name: object  # VARCHAR | NULL
    activity_date: object  # VARCHAR | NULL
    summary_json: object  # VARCHAR | NULL
    detail_json: object  # VARCHAR | NULL


class DailyLoadFactRow(TypedDict):
    """Row returned by ``fetch_daily_load_facts``.

    Columns: ``SELECT * FROM daily_load_facts``.
    """

    day: object  # DATE → ISO str
    scope: object  # VARCHAR
    sport_type: object  # VARCHAR
    metric_version: object  # BIGINT
    computed_at: object  # VARCHAR
    completeness_status: object  # VARCHAR
    missing_reasons_json: object  # VARCHAR
    activity_count: object  # BIGINT
    stream_point_count: object  # BIGINT
    heartrate_point_count: object  # BIGINT
    observed_trimp: object  # DOUBLE | NULL
    effective_trimp: object  # DOUBLE
    distance_m: object  # DOUBLE
    moving_time_s: object  # BIGINT
    elevation_gain_m: object  # DOUBLE
    zone4_seconds: object  # BIGINT
    zone5_seconds: object  # BIGINT
    high_zone_seconds: object  # BIGINT
    anomaly_count: object  # BIGINT


class TrainingModelDayRow(TypedDict):
    """Row returned by ``fetch_latest_training_model_day``.

    Columns: ``SELECT * FROM training_model_daily``.
    """

    day: object  # DATE → ISO str
    scope: object  # VARCHAR
    sport_type: object  # VARCHAR
    metric_version: object  # BIGINT
    computed_at: object  # VARCHAR
    completeness_status: object  # VARCHAR
    missing_reasons_json: object  # VARCHAR
    effective_trimp: object  # DOUBLE
    observed_trimp: object  # DOUBLE | NULL
    fitness: object  # DOUBLE | NULL
    fatigue: object  # DOUBLE | NULL
    form: object  # DOUBLE | NULL
    form_zone: object  # VARCHAR | NULL
    acwr_zone: object  # VARCHAR | NULL
    acwr: object  # DOUBLE | NULL
    load_7d: object  # DOUBLE | NULL
    load_28d: object  # DOUBLE | NULL
    load_42d: object  # DOUBLE | NULL
    input_days: object  # BIGINT
    missing_days: object  # BIGINT


class RollingPeriodFactRow(TypedDict):
    """Row returned by ``fetch_rolling_period_facts`` /
    ``fetch_rolling_period_facts_by_windows``.

    Columns: ``SELECT * FROM rolling_period_facts``.
    """

    as_of_day: object  # DATE → ISO str
    window_days: object  # BIGINT
    scope: object  # VARCHAR
    sport_type: object  # VARCHAR
    metric_version: object  # BIGINT
    computed_at: object  # VARCHAR
    completeness_status: object  # VARCHAR
    missing_reasons_json: object  # VARCHAR
    activity_count: object  # BIGINT
    active_days: object  # BIGINT
    rest_days: object  # BIGINT
    observed_trimp: object  # DOUBLE | NULL
    effective_trimp: object  # DOUBLE
    distance_m: object  # DOUBLE
    moving_time_s: object  # BIGINT
    elevation_gain_m: object  # DOUBLE
    high_zone_seconds: object  # BIGINT
    anomaly_count: object  # BIGINT
    fitness: object  # DOUBLE | NULL
    fatigue: object  # DOUBLE | NULL
    form: object  # DOUBLE | NULL
    form_zone: object  # VARCHAR | NULL
    acwr_zone: object  # VARCHAR | NULL
    acwr: object  # DOUBLE | NULL
    median_cardiac_cost: object  # DOUBLE | NULL
    median_adjusted_cardiac_cost: object  # DOUBLE | NULL
    median_hr_recovery: object  # DOUBLE | NULL
    median_cardiac_drift_pct: object  # DOUBLE | NULL


def _emit(event: str, **fields: object) -> None:
    """Emit a structured JSON diagnostic event to stdout (house log style)."""
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


# A few internal queries must interpolate table/column names (DuckDB does not
# parameterize identifiers). All current callers pass schema-defined literals,
# never Strava-sourced strings — but this guard rejects anything that is not a
# bare SQL identifier, so a future mistake fails loudly instead of allowing
# injection. Defense-in-depth for the single-user threat model.
_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

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

# Per-statement row cap for batched fact upserts (_upsert_facts_batch). Same rationale
# as _STREAM_INSERT_STMT_ROWS: one multi-row INSERT collapses the materializer's per-day
# loops (~141 Banister-warmup days) to ~1-2 statements, but DuckDB parses the VALUES
# literal so the cap keeps long ranges off the quadratic-parse tail.
_FACT_UPSERT_BATCH_ROWS = 250


def _safe_identifier(name: str) -> str:
    if not _SQL_IDENTIFIER.match(name):
        raise ValueError(f"unsafe SQL identifier (not a bare table/column name): {name!r}")
    return name


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
    parts = [
        f"SUM(CASE WHEN {h}heartrate < {bounds[0]} THEN 1 ELSE 0 END) * {c[0]}",
        *(
            f"SUM(CASE WHEN {h}heartrate >= {bounds[i - 1]} AND {h}heartrate < {bounds[i]} THEN 1 ELSE 0 END) * {c[i]}"
            for i in range(1, len(bounds) - 1)
        ),
        f"SUM(CASE WHEN {h}heartrate >= {bounds[-2]} THEN 1 ELSE 0 END) * {c[-1]}",
    ]
    return "(" + " +\n                ".join(parts) + ") / 60.0 as trimp"


def _normalize_cell(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    return value


# ─── Typed cell accessors (object -> scalar narrowing) ───
#
# A raw row's cell is ``object`` (see ``Row`` above). For the wide, all-nullable
# aggregate/stream rows — where a per-shape TypedDict would be ~20 near-identical
# "every column is ``int|float|None``" definitions — these helpers narrow a single
# cell instead. They are the structured-row analogue of casting to a TypedDict:
# explicit, centralized, and (unlike a bare cast) they validate at runtime, so a
# column that is unexpectedly non-numeric fails loudly here rather than silently
# coercing. ``None`` collapses to ``default`` (SQL NULL from an empty SUM/AVG or
# an outer join), matching the ``int(x or 0)`` idiom they replace.


def _as_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, (float, str)):
        return int(value)
    raise TypeError(f"expected an int-like cell, got {type(value).__name__}")


def _as_float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"expected a float-like cell, got {type(value).__name__}")


def _as_str(value: object) -> str:
    return str(value)


def _as_int_opt(value: object) -> int | None:
    """Narrow a nullable cell to ``int | None`` (preserve SQL NULL as None)."""
    return None if value is None else _as_int(value)


def _as_str_opt(value: object) -> str | None:
    """Narrow a nullable cell to ``str | None`` (preserve SQL NULL as None)."""
    return None if value is None else str(value)


def _placeholders(count: int) -> str:
    return ", ".join("?" for _ in range(count))


@dataclass
class DuckDBRepository:
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

    def _read_activity_source_components(self, activity_id: int) -> _SourceComponents | None:
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

        existing: _SourceRevisionRow | None = self._one(
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
    ) -> list[_DirtyActivityRow]:
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
    ) -> list[_DirtyActivityRow]:
        base_sql = """
            SELECT d.*, s.source_hash
            FROM metric_dirty_activities d
            JOIN activity_source_state s ON s.activity_id = d.activity_id
            WHERE d.metric_version = ?
            ORDER BY d.activity_day, d.activity_id
        """
        if limit is None:
            return self._all(self._fetchall(base_sql, [metric_version]))

        rows: list[_DirtyActivityRow] = self._all(self._fetchall(base_sql + " LIMIT ?", [metric_version, limit]))
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
        remainder: list[_DirtyActivityRow] = self._all(
            self._fetchall(
                base_sql.replace(
                    "WHERE d.metric_version = ?", "WHERE d.metric_version = ? AND d.activity_day = CAST(? AS DATE)"
                ),
                [metric_version, last_day],
            )
        )
        rows.extend(row for row in remainder if _as_int(row["activity_id"]) not in claimed_ids)
        return rows

    def clear_dirty_activity_rows(self, rows: Iterable[_DirtyActivityRow]) -> int:
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

    def source_state_for_activity(self, activity_id: int) -> _SourceStateRow | None:
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

    def current_logic_version(self) -> _LogicVersionRow | None:
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

    def activity_materialization_sources(self, activity_ids: Iterable[int]) -> dict[int, ActivityMaterializationSource]:
        ids = sorted({int(activity_id) for activity_id in activity_ids})
        if not ids:
            return {}
        placeholders = _placeholders(len(ids))
        rows = self._fetchall(
            f"""
            SELECT a.id, a.date, a.name, a.sport_type, a.distance, a.moving_time,
                   a.elapsed_time, a.total_elevation_gain, a.summary_json, a.detail_json,
                   a.synced_at, s.source_hash, s.source_revision
            FROM activities a
            JOIN activity_source_state s ON s.activity_id = a.id
            WHERE a.id IN ({placeholders})
            """,
            ids,
        )
        sources: dict[int, ActivityMaterializationSource] = {}
        for row in rows:
            activity = self._to_activity_row(row)
            sources[activity.id] = ActivityMaterializationSource(
                activity=activity,
                source_hash=str(row["source_hash"]),
                source_revision=_as_int(row["source_revision"]),
            )
        return sources

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
        return _as_int(row["id"]) if row and row["id"] is not None else None

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

    # Streams and load
    def activity_stream_rows(self, activity_id: int) -> list[dict[str, Any]]:
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
        return {str(row["day"]): round(_as_float(row["trimp"]), 1) for row in rows}

    def observed_trimp_history_by_sport(
        self,
        *,
        bounds: list[int],
        since_day: str | None = None,
        until_day: str | None = None,
        sport_filter: str | None = None,
    ) -> dict[str, dict[str, float]]:
        """Return daily RAW TRIMP broken down per sport: {day -> {sport -> trimp}}.

        Sibling of observed_trimp_history that adds sport_type to the GROUP BY.
        It MUST share the same date-range / bounds / sport_filter parameters and
        the same build_trimp_sql + _sport_where_clause as observed_trimp_history,
        so the per-sport breakdown stays aligned with the per-day total (the raw
        per-sport values for a day sum to that day's undiscounted observed total).

        The discount itself is NOT applied here — these are the UNDISCOUNTED raw
        per-sport values; discounted_effective_trimp() in metrics.py owns the
        Walk multiplier. This method only supplies the per-sport map it consumes.
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
                   a.sport_type AS sport,
                   """
            + build_trimp_sql(bounds, alias="s.")
            + """
            FROM activities a
            JOIN streams s ON a.id = s.activity_id
            WHERE """
            + " AND ".join(where)
            + sport_sql
            + """
            GROUP BY day, sport
            """,
            params,
        )
        by_sport: dict[str, dict[str, float]] = {}
        for row in rows:
            day = str(row["day"])
            by_sport.setdefault(day, {})[str(row["sport"])] = round(_as_float(row["trimp"]), 1)
        return by_sport

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
            daily_activity_counts[str(row["day"])] = _as_int(row["c"])

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
            daily_stream_counts[str(row["day"])] = _as_int(row["c"])

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
            daily_hr_counts[str(row["day"])] = _as_int(row["c"])

        observed_trimp = self.observed_trimp_history(
            bounds=bounds,
            since_day=start_day,
            until_day=end_day,
            sport_filter=sport_filter,
        )
        # Per-sport raw daily TRIMP over the SAME range/bounds, used to discount the
        # Walk portion when assembling effective_trimp below. observed_trimp stays
        # the undiscounted per-day sum; only effective carries the Walk discount.
        observed_trimp_by_sport = self.observed_trimp_history_by_sport(
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
                # effective applies the Walk discount per-sport: the Walk portion of
                # this day's TRIMP counts at WALK_TRIMP_DISCOUNT, every other sport at
                # full load. observed (above) stays the undiscounted daily sum, so the
                # daily fact carries raw observed_trimp and discounted effective_trimp;
                # the Banister series downstream consumes effective_trimp.
                effective = discounted_effective_trimp(observed_trimp_by_sport.get(current_text, {}))
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
            for point in self.daily_load_points_between(start_day, end_day, bounds=bounds, sport_filter=sport_filter)
        }

    def stream_hr_velocity_simple_rows(self, activity_id: int, min_velocity: float) -> list[dict[str, Any]]:
        return self._fetchall(
            """
            SELECT heartrate, velocity FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL AND velocity > ?
            ORDER BY time_offset
            """,
            [activity_id, min_velocity],
        )

    def stream_hr_velocity_simple_rows_for_activities(
        self, activity_ids: Iterable[int], min_velocity: float
    ) -> dict[int, list[dict[str, Any]]]:
        ids = sorted({int(activity_id) for activity_id in activity_ids})
        if not ids:
            return {}
        rows = self._fetchall(
            f"""
            SELECT activity_id, heartrate, velocity FROM streams
            WHERE activity_id IN ({_placeholders(len(ids))})
              AND heartrate IS NOT NULL AND velocity > ?
            ORDER BY activity_id, time_offset
            """,
            [*ids, min_velocity],
        )
        grouped: dict[int, list[dict[str, Any]]] = {activity_id: [] for activity_id in ids}
        for row in rows:
            activity_id = _as_int(row["activity_id"])
            grouped.setdefault(activity_id, []).append({"heartrate": row["heartrate"], "velocity": row["velocity"]})
        return grouped

    def stream_hr_velocity_time_rows(self, activity_id: int) -> list[dict[str, Any]]:
        return self._fetchall(
            """
            SELECT time_offset, heartrate, velocity FROM streams
            WHERE activity_id=? AND heartrate IS NOT NULL
            ORDER BY time_offset
            """,
            [activity_id],
        )

    def stream_hr_velocity_time_rows_for_activities(
        self, activity_ids: Iterable[int]
    ) -> dict[int, list[dict[str, Any]]]:
        ids = sorted({int(activity_id) for activity_id in activity_ids})
        if not ids:
            return {}
        rows = self._fetchall(
            f"""
            SELECT activity_id, time_offset, heartrate, velocity FROM streams
            WHERE activity_id IN ({_placeholders(len(ids))}) AND heartrate IS NOT NULL
            ORDER BY activity_id, time_offset
            """,
            ids,
        )
        grouped: dict[int, list[dict[str, Any]]] = {activity_id: [] for activity_id in ids}
        for row in rows:
            activity_id = _as_int(row["activity_id"])
            grouped.setdefault(activity_id, []).append(
                {"time_offset": row["time_offset"], "heartrate": row["heartrate"], "velocity": row["velocity"]}
            )
        return grouped

    def stream_altitude_rows(self, activity_id: int) -> list[dict[str, Any]]:
        return self._fetchall(
            """
            SELECT time_offset, altitude FROM streams
            WHERE activity_id=? AND altitude IS NOT NULL
            ORDER BY time_offset
            """,
            [activity_id],
        )

    def stream_altitude_rows_for_activities(self, activity_ids: Iterable[int]) -> dict[int, list[dict[str, Any]]]:
        ids = sorted({int(activity_id) for activity_id in activity_ids})
        if not ids:
            return {}
        rows = self._fetchall(
            f"""
            SELECT activity_id, time_offset, altitude FROM streams
            WHERE activity_id IN ({_placeholders(len(ids))}) AND altitude IS NOT NULL
            ORDER BY activity_id, time_offset
            """,
            ids,
        )
        grouped: dict[int, list[dict[str, Any]]] = {activity_id: [] for activity_id in ids}
        for row in rows:
            activity_id = _as_int(row["activity_id"])
            grouped.setdefault(activity_id, []).append({"time_offset": row["time_offset"], "altitude": row["altitude"]})
        return grouped

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
        assert row is not None, "aggregate COUNT always returns a row"
        return _as_int(row["stream_count"]), _as_int(row["hr_count"])

    def activity_stream_scalars_for_materialization(
        self, activity_ids: Iterable[int], min_velocity: float
    ) -> dict[int, ActivityStreamScalars]:
        ids = sorted({int(activity_id) for activity_id in activity_ids})
        if not ids:
            return {}
        rows = self._fetchall(
            f"""
            SELECT
              activity_id,
              COUNT(*) AS stream_count,
              SUM(CASE WHEN heartrate IS NOT NULL THEN 1 ELSE 0 END) AS hr_count,
              MIN(heartrate) AS min_hr,
              MAX(heartrate) AS max_hr,
              AVG(CASE WHEN heartrate IS NOT NULL AND velocity > ? THEN heartrate ELSE NULL END) AS avg_hr_for_cc,
              AVG(CASE WHEN heartrate IS NOT NULL AND velocity > ? THEN velocity ELSE NULL END) AS avg_vel_for_cc,
              median(heartrate) AS median_hr
            FROM streams
            WHERE activity_id IN ({_placeholders(len(ids))})
            GROUP BY activity_id
            """,
            [min_velocity, min_velocity, *ids],
        )
        scalars: dict[int, ActivityStreamScalars] = {
            activity_id: ActivityStreamScalars(
                stream_count=0,
                hr_count=0,
                min_hr=None,
                max_hr=None,
                cardiac_cost=None,
                median_hr=None,
            )
            for activity_id in ids
        }
        for row in rows:
            avg_vel = _as_float(row["avg_vel_for_cc"]) if row["avg_vel_for_cc"] is not None else None
            avg_hr = _as_float(row["avg_hr_for_cc"]) if row["avg_hr_for_cc"] is not None else None
            cardiac_cost = round(avg_hr / avg_vel, 2) if avg_hr and avg_vel and avg_vel > 0 else None
            activity_id = _as_int(row["activity_id"])
            scalars[activity_id] = ActivityStreamScalars(
                stream_count=_as_int(row["stream_count"]),
                hr_count=_as_int(row["hr_count"]),
                min_hr=_as_int_opt(row["min_hr"]),
                max_hr=_as_int_opt(row["max_hr"]),
                cardiac_cost=cardiac_cost,
                median_hr=_as_float(row["median_hr"]) if row["median_hr"] is not None else None,
            )
        return scalars

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
        assert row is not None, "SUM aggregate always returns a row"
        z = [_as_int(row[f"z{idx}"]) for idx in range(1, 6)]
        return z[0], z[1], z[2], z[3], z[4]

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
        return round(_as_float(row["trimp"]), 1) if row and row["trimp"] is not None else 0.0

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
        return _as_int(row["hr_max"]) if row and row["hr_max"] is not None else None

    def max_heartrate_to_dates(self, activity_days: Iterable[str]) -> dict[str, int | None]:
        days = sorted({str(day) for day in activity_days})
        if not days:
            return {}
        rows = self._fetchall(
            f"""
            WITH requested(day) AS (
              VALUES {", ".join("(CAST(? AS DATE))" for _ in days)}
            ),
            day_hr AS (
              SELECT a.activity_day AS day, MAX(s.heartrate) AS day_hr_max
              FROM activities a
              JOIN streams s ON s.activity_id = a.id
              WHERE s.heartrate IS NOT NULL
                AND a.activity_day <= (SELECT MAX(day) FROM requested)
              GROUP BY a.activity_day
            ),
            running_hr AS (
              SELECT day,
                     MAX(day_hr_max) OVER (
                       ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                     ) AS hr_max
              FROM day_hr
            )
            SELECT r.day AS day,
                   (
                     SELECT hr_max
                     FROM running_hr h
                     WHERE h.day <= r.day
                     ORDER BY h.day DESC
                     LIMIT 1
                   ) AS hr_max
            FROM requested r
            """,
            days,
        )
        return {str(row["day"]): _as_int(row["hr_max"]) if row["hr_max"] is not None else None for row in rows}

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
            return _as_int(row["min_hr"]), _as_int(row["max_hr"])
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
        if not row or not row["avg_hr"] or not row["avg_vel"] or _as_float(row["avg_vel"]) <= 0:
            return None
        return round(_as_float(row["avg_hr"]) / _as_float(row["avg_vel"]), 2)

    def activity_median_heartrate(self, activity_id: int) -> float | None:
        row = self._fetchone(
            """
            SELECT median(heartrate) AS median_hr
            FROM streams
            WHERE activity_id = ? AND heartrate IS NOT NULL
            """,
            [activity_id],
        )
        return _as_float(row["median_hr"]) if row and row["median_hr"] is not None else None

    def activity_zone_trimp_for_bounds(
        self, bounds_by_activity_id: dict[int, list[int]]
    ) -> dict[int, ActivityZoneTrimp]:
        if not bounds_by_activity_id:
            return {}
        coeff = Config.Zones.COEFF
        values_sql: list[str] = []
        params: list[object] = []
        for activity_id, bounds in sorted(bounds_by_activity_id.items()):
            values_sql.append("(?, ?, ?, ?, ?, ?)")
            params.extend([activity_id, bounds[0], bounds[1], bounds[2], bounds[3], bounds[-2]])
        rows = self._fetchall(
            f"""
            WITH bounds(activity_id, b0, b1, b2, b3, b_last_zone) AS (
              VALUES {", ".join(values_sql)}
            )
            SELECT
              b.activity_id,
              SUM(CASE WHEN s.heartrate < b.b0 THEN 1 ELSE 0 END) AS z1,
              SUM(CASE WHEN s.heartrate >= b.b0 AND s.heartrate < b.b1 THEN 1 ELSE 0 END) AS z2,
              SUM(CASE WHEN s.heartrate >= b.b1 AND s.heartrate < b.b2 THEN 1 ELSE 0 END) AS z3,
              SUM(CASE WHEN s.heartrate >= b.b2 AND s.heartrate < b.b3 THEN 1 ELSE 0 END) AS z4,
              SUM(CASE WHEN s.heartrate >= b.b_last_zone THEN 1 ELSE 0 END) AS z5,
              (
                SUM(CASE WHEN s.heartrate < b.b0 THEN 1 ELSE 0 END) * {coeff[0]} +
                SUM(CASE WHEN s.heartrate >= b.b0 AND s.heartrate < b.b1 THEN 1 ELSE 0 END) * {coeff[1]} +
                SUM(CASE WHEN s.heartrate >= b.b1 AND s.heartrate < b.b2 THEN 1 ELSE 0 END) * {coeff[2]} +
                SUM(CASE WHEN s.heartrate >= b.b2 AND s.heartrate < b.b3 THEN 1 ELSE 0 END) * {coeff[3]} +
                SUM(CASE WHEN s.heartrate >= b.b3 AND s.heartrate < b.b_last_zone THEN 1 ELSE 0 END) * {coeff[4]} +
                SUM(CASE WHEN s.heartrate >= b.b_last_zone THEN 1 ELSE 0 END) * {coeff[5]}
              ) / 60.0 AS trimp
            FROM bounds b
            LEFT JOIN streams s ON s.activity_id = b.activity_id AND s.heartrate IS NOT NULL
            GROUP BY b.activity_id
            """,
            params,
        )
        result: dict[int, ActivityZoneTrimp] = {}
        for row in rows:
            activity_id = _as_int(row["activity_id"])
            result[activity_id] = ActivityZoneTrimp(
                zone1_seconds=_as_int(row["z1"]),
                zone2_seconds=_as_int(row["z2"]),
                zone3_seconds=_as_int(row["z3"]),
                zone4_seconds=_as_int(row["z4"]),
                zone5_seconds=_as_int(row["z5"]),
                trimp=round(_as_float(row["trimp"]), 1) if row["trimp"] is not None else 0.0,
            )
        return result

    def max_heartrate(self) -> float | None:
        row = self._fetchone("SELECT MAX(heartrate) AS hr FROM streams WHERE heartrate IS NOT NULL")
        return _as_float(row["hr"]) if row and row["hr"] is not None else None

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

    def activities_missing_stream_channels(
        self,
        *,
        since: str | None = None,
        limit: int | None = None,
        requested_channels: Iterable[str],
    ) -> list[dict[str, object]]:
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
        results: list[dict[str, object]] = []
        for row in rows:
            if limit is not None and len(results) >= limit:
                break
            activity_id = _as_int(row["id"])
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
                    if not any(
                        channel in (json.loads(str(item["values_json"])) if item["values_json"] else {})
                        for item in value_rows
                    ):
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
            "channels": _as_int(row["channels"]) if row else 0,
            "activities_with_channel_metadata": _as_int(row["activities_with_channel_metadata"]) if row else 0,
            "available_channels": _as_int(row["available_channels"]) if row else 0,
            "unavailable_channels": _as_int(row["unavailable_channels"]) if row else 0,
            "error_channels": _as_int(row["error_channels"]) if row else 0,
        }

    # Mirror coverage counts (owned here so the application layer never runs raw
    # SQL — callers receive typed ints/sets/bools, never raw DB-API rows).
    def stream_table_columns(self) -> set[str]:
        """Column names present on the ``streams`` table (via PRAGMA table_info)."""
        return self._table_columns("streams")

    def mirror_table_exists(self, table: str) -> bool:
        """True when ``table`` exists in the mirror DB (information_schema lookup)."""
        return self._table_exists(table)

    def count_activities(self) -> int:
        return self._scalar_int("SELECT COUNT(*) FROM activities")

    def count_activities_with_streams(self) -> int:
        return self._scalar_int("SELECT COUNT(DISTINCT activity_id) FROM streams")

    def count_stream_points(self) -> int:
        return self._scalar_int("SELECT COUNT(*) FROM streams")

    def count_stream_gps_points(self, *, has_latlng: bool) -> int:
        """Count stream points carrying GPS coordinates.

        Canonical schema stores GPS as separate ``lat``/``lng`` columns; an older
        variant DB may also carry a combined ``latlng`` column. ``has_latlng`` is
        the caller's column-presence check (from ``stream_table_columns``) and
        widens the predicate only when that column actually exists, so the query
        never references a missing column.
        """
        gps_where = "lat IS NOT NULL AND lng IS NOT NULL"
        if has_latlng:
            gps_where = f"({gps_where}) OR latlng IS NOT NULL"
        return self._scalar_int(f"SELECT COUNT(*) FROM streams WHERE {gps_where}")

    def count_activities_missing_channel_metadata(self) -> int:
        """Activities that have stream rows but zero ``stream_channels`` metadata."""
        return self._scalar_int(
            """
            SELECT COUNT(*)
            FROM (
                SELECT s.activity_id
                FROM streams s
                LEFT JOIN stream_channels c ON c.activity_id = s.activity_id
                GROUP BY s.activity_id
                HAVING COUNT(c.channel_key) = 0
            )
            """
        )

    def count_streams_missing_extra_values(self, *, has_values_json: bool) -> int:
        """Stream points lacking the ``values_json`` extra-channels blob.

        ``has_values_json`` is the caller's column-presence check; when the column
        is absent (older DB), every stream point counts as missing extra values.
        """
        if not has_values_json:
            return self.count_stream_points()
        return self._scalar_int("SELECT COUNT(*) FROM streams WHERE values_json IS NULL OR values_json = ''")

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
    def list_kudos(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._fetchall(
            """
            SELECT activity_id, firstname, lastname, fetched_at
            FROM kudos
            ORDER BY fetched_at DESC
            LIMIT ?
            """,
            [limit],
        )

    def kudos_for_activity(self, activity_id: int) -> list[dict[str, Any]]:
        return self._fetchall(
            """
            SELECT activity_id, firstname, lastname, fetched_at
            FROM kudos
            WHERE activity_id = ?
            ORDER BY firstname, lastname
            """,
            [activity_id],
        )

    def activities_missing_kudos(self, window_days: int | None = None) -> list[int]:
        """Activity ids that have kudos on Strava but none mirrored locally yet.

        Selects activities whose summary `kudos_count > 0` and that have no rows
        in the local `kudos` table, newest first; optionally bounded to the last
        `window_days`. Returns ids only — the caller fetches each activity's
        kudoers from the API. Keeps the raw DB-API rows inside the repository so
        callers receive typed `int`s, never positional tuples (the boundary that
        prevents the `row['id']`-on-a-tuple class of bug).
        """
        query = """
            SELECT a.id FROM activities a
            WHERE CAST(json_extract(a.summary_json, '$.kudos_count') AS INTEGER) > 0
              AND NOT EXISTS (SELECT 1 FROM kudos k WHERE k.activity_id = a.id)
        """
        params: list[object] = []
        if window_days is not None:
            query += " AND a.date >= date('now', ?)"
            params.append(f"-{window_days} days")
        query += " ORDER BY a.date DESC"
        return [_as_int(row["id"]) for row in self._fetchall(query, params)]

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
                activities_seen=_as_int_opt(row["activities_seen"]),
                activities_new=_as_int_opt(row["activities_new"]),
                streams_fetched=_as_int_opt(row["streams_fetched"]),
                details_fetched=_as_int_opt(row["details_fetched"]),
                api_calls=_as_int_opt(row["api_calls"]),
                error=_as_str_opt(row["error"]),
                kudos_fetched=_as_int_opt(row["kudos_fetched"]),
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
        assert row is not None, "refresh_state row must exist after INSERT"
        return RefreshStateRow(
            id=_as_int(row["id"]),
            last_success_at=_as_str_opt(row["last_success_at"]),
            last_attempt_at=_as_str_opt(row["last_attempt_at"]),
            last_status=_as_str_opt(row["last_status"]),
            last_error_code=_as_str_opt(row["last_error_code"]),
            lease_owner=_as_str_opt(row["lease_owner"]),
            lease_expires_at=_as_str_opt(row["lease_expires_at"]),
            backoff_until=_as_str_opt(row["backoff_until"]),
            checkpoint_stage=_as_str_opt(row["checkpoint_stage"]),
            checkpoint_cursor=_as_str_opt(row["checkpoint_cursor"]),
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
                id=_as_int(row["id"]),
                reason=str(row["reason"]),
                requested_for_day=str(row["requested_for_day"]),
                requested_at=str(row["requested_at"]),
                consumed_at=_as_str_opt(row["consumed_at"]),
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
