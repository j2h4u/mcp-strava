# Phase 08: DuckDB Primary Storage & Aggregate Analytics Surface - Pattern Map

**Mapped:** 2026-05-25
**Files analyzed:** 39
**Analogs found:** 39 / 39

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `pyproject.toml` | config | dependency resolution | `pyproject.toml` | exact |
| `uv.lock` | config | dependency resolution | `uv.lock` | exact |
| `src/mcp_strava/adapters/duckdb/__init__.py` | provider | import/export | `src/mcp_strava/adapters/sqlite/__init__.py` | role-match |
| `src/mcp_strava/adapters/duckdb/connection.py` | utility | file-I/O, CRUD | `src/mcp_strava/adapters/sqlite/connection.py` | role-match |
| `src/mcp_strava/adapters/duckdb/schema.py` | config | validation, migration | `src/mcp_strava/adapters/sqlite/schema.py` | role-match |
| `src/mcp_strava/adapters/duckdb/migrations.py` | migration | batch, file-I/O | `src/mcp_strava/adapters/sqlite/migrations.py` | role-match |
| `src/mcp_strava/adapters/duckdb/repository.py` | service/repository | CRUD, batch | `src/mcp_strava/adapters/sqlite/repository.py` | role-match |
| `src/mcp_strava/adapters/duckdb/aggregate_queries.py` | service/repository | request-response, transform | `src/mcp_strava/adapters/sqlite/repository.py` + `src/mcp_strava/adapters/sqlite/read_model_materializer.py` | partial |
| `src/mcp_strava/adapters/duckdb/read_model_materializer.py` or refit equivalent | service | batch, transform | `src/mcp_strava/adapters/sqlite/read_model_materializer.py` | role-match |
| `src/mcp_strava/db.py` | utility | connection, request-response | `src/mcp_strava/db.py` | exact |
| `src/mcp_strava/settings.py` | config | env parsing | `src/mcp_strava/settings.py` | exact |
| `src/mcp_strava/types.py` | model | transform | `src/mcp_strava/types.py` | exact |
| `src/mcp_strava/application/metric_registry.py` | registry | transform | `src/mcp_strava/application/metric_registry.py` | exact |
| `src/mcp_strava/application/aggregate_services.py` | service | request-response, transform | `src/mcp_strava/application/metric_services.py` | role-match |
| `src/mcp_strava/application/metric_services.py` | service | request-response, transform | `src/mcp_strava/application/metric_services.py` | exact |
| `src/mcp_strava/application/freshness.py` | service | request-response, event signaling | `src/mcp_strava/application/freshness.py` | exact |
| `src/mcp_strava/interfaces/mcp_http.py` | controller/interface | request-response | `src/mcp_strava/interfaces/mcp_http.py` | exact |
| `src/mcp_strava/devtools/mcp_client/client.py` | utility/test-client | request-response, benchmark | `src/mcp_strava/devtools/mcp_client/client.py` | exact |
| `src/mcp_strava/deploy/preflight.py` | utility | file-I/O, validation | `src/mcp_strava/deploy/preflight.py` | exact |
| `src/mcp_strava/deploy/healthcheck.py` | utility | request-response, validation | `src/mcp_strava/deploy/healthcheck.py` | exact |
| `src/mcp_strava/deploy/service.py` | provider/supervisor | event-driven | `src/mcp_strava/deploy/service.py` | exact |
| `src/mcp_strava/deploy/entrypoint.py` | provider | batch, startup validation | `src/mcp_strava/deploy/entrypoint.py` | exact |
| `src/mcp_strava/refresh/runtime.py` | service | event-driven, batch | `src/mcp_strava/refresh/runtime.py` | exact |
| `src/mcp_strava/refresh/worker.py` | service | event-driven, batch | `src/mcp_strava/refresh/worker.py` | exact |
| `src/mcp_strava/refresh/bootstrap.py` | service/config | request-response, batch | `src/mcp_strava/refresh/bootstrap.py` | exact |
| `src/mcp_strava/refresh/_sync_ops.py` | service | batch, file-I/O | `src/mcp_strava/refresh/_sync_ops.py` | exact |
| `deploy/Dockerfile` | config | build, runtime | `deploy/Dockerfile` | exact |
| `deploy/docker-compose.yml` | config | deployment | `deploy/docker-compose.yml` | exact |
| `Justfile` | config | command orchestration | `Justfile` | exact |
| `docs/deployment.md` | documentation | operational runbook | `docs/deployment.md` | exact |
| `tests/test_duckdb_migration.py` | test | batch, file-I/O | `tests/test_sqlite_safety.py` | role-match |
| `tests/test_duckdb_repository.py` | test | CRUD, file-I/O | `tests/test_repository_boundary.py` | role-match |
| `tests/test_training_aggregates.py` | test | request-response, transform | `tests/test_read_model_queries.py` + `tests/test_metric_services.py` | role-match |
| `tests/test_duckdb_concurrency_guards.py` | test | event-driven, security | `tests/test_repository_boundary.py` + `tests/test_refresh_runtime.py` | partial |
| `tests/test_mcp_surface.py` | test | request-response | `tests/test_mcp_surface.py` | exact |
| `tests/test_mcp_latency_gate.py` | test | request-response, benchmark | `tests/test_mcp_latency_gate.py` | exact |
| `tests/test_docker_runtime.py` | test | deployment, smoke | `tests/test_docker_runtime.py` | exact |
| `tests/test_metric_registry.py` | test | registry, transform | `tests/test_metric_registry.py` | exact |
| `tests/test_metric_services.py` | test | request-response, transform | `tests/test_metric_services.py` | exact |

## Pattern Assignments

### `src/mcp_strava/adapters/duckdb/__init__.py` (provider, import/export)

**Analog:** `src/mcp_strava/adapters/sqlite/__init__.py`

**Export pattern** (lines 1-23):

```python
"""SQLite safety and migration adapter APIs."""

from mcp_strava.adapters.sqlite.backup import create_timestamped_backup, enforce_backup_retention
from mcp_strava.adapters.sqlite.connection import create_empty_mirror, open_expected_mirror_db
from mcp_strava.adapters.sqlite.migrations import (
    ParitySnapshot,
    evaluate_parity,
    run_migrations,
    run_preflight,
)
from mcp_strava.adapters.sqlite.repository import SQLiteRepository

__all__ = [
    "create_empty_mirror",
    "open_expected_mirror_db",
    "create_timestamped_backup",
    "enforce_backup_retention",
    "run_preflight",
    "run_migrations",
    "ParitySnapshot",
    "evaluate_parity",
    "SQLiteRepository",
]
```

**Apply:** expose DuckDB connection, migration, preflight/parity, repository, and aggregate query symbols explicitly. Do not use a barrel file for unrelated application services.

### `src/mcp_strava/adapters/duckdb/connection.py` (utility, file-I/O/CRUD)

**Analog:** `src/mcp_strava/adapters/sqlite/connection.py`

**Connection policy pattern** (lines 7-25):

```python
def _apply_connection_pragmas(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    conn.execute("PRAGMA busy_timeout=5000")


def open_expected_mirror_db(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    uri = f"file:{db_path}?mode=rw"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    _apply_connection_pragmas(conn)
    return conn


def open_fixture_db(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(Path(path)), check_same_thread=False)
    _apply_connection_pragmas(conn)
    return conn
```

**DuckDB adaptation:** keep separate expected-runtime and fixture opens. For expected runtime, fail closed when the file is absent and default to read-write only inside the owner process. For healthcheck/smoke, prefer HTTP/owner-process validation over opening the live DuckDB file directly.

### `src/mcp_strava/adapters/duckdb/schema.py` (config, validation/migration)

**Analog:** `src/mcp_strava/adapters/sqlite/schema.py`

**Inventory pattern** (lines 8-31):

```python
BASE_TABLES_V1: tuple[str, ...] = ("activities", "streams", "athlete_zones", "sync_log", "kudos")
REFRESH_TABLES_V2: tuple[str, ...] = ("refresh_state", "refresh_requests")
READ_MODEL_TABLES_V5: tuple[str, ...] = (
    "activity_source_state",
    "metric_dirty_activities",
    "activity_metric_facts",
    "daily_load_facts",
    "training_model_daily",
    "rolling_period_facts",
    "read_model_refresh_runs",
)
MIGRATION_LOG_TABLES_V7: tuple[str, ...] = ("schema_migration_log",)

REQUIRED_TABLES_BY_VERSION: dict[int, tuple[str, ...]] = {
    1: BASE_TABLES_V1,
    2: BASE_TABLES_V1 + REFRESH_TABLES_V2,
    3: BASE_TABLES_V1 + REFRESH_TABLES_V2 + ("stream_channels",),
    7: BASE_TABLES_V1 + REFRESH_TABLES_V2 + ("stream_channels",) + READ_MODEL_TABLES_V6 + MIGRATION_LOG_TABLES_V7,
}
```

**Read-model fact column pattern** (lines 161-197, 198-241, 242-285):

```python
"activity_metric_facts": (
    "activity_id",
    "activity_day",
    "sport_type",
    "source_hash",
    "source_revision",
    "metric_version",
    "computed_at",
    "completeness_status",
    "missing_reasons_json",
    "trimp",
    "zone1_seconds",
    "zone2_seconds",
    "zone3_seconds",
    "zone4_seconds",
    "zone5_seconds",
    "hr_recovery_median_rate",
    "cardiac_cost",
    "adjusted_cardiac_cost",
    "cardiac_drift_pct",
    "hrr_pct",
    "distance_m",
    "moving_time_s",
    "elapsed_time_s",
    "elevation_gain_m",
    "heartrate_sample_count",
    "stream_sample_count",
),
"daily_load_facts": (
    "day",
    "scope",
    "sport_type",
    "metric_version",
    "computed_at",
    "completeness_status",
    "missing_reasons_json",
    "activity_count",
    "stream_point_count",
    "heartrate_point_count",
    "observed_trimp",
    "effective_trimp",
    "distance_m",
    "moving_time_s",
    "elevation_gain_m",
),
"training_model_daily": (
    "day",
    "scope",
    "sport_type",
    "metric_version",
    "computed_at",
    "completeness_status",
    "missing_reasons_json",
    "fitness",
    "fatigue",
    "form",
    "form_zone",
    "acwr",
),
```

**Index/query readiness pattern** (lines 426-449):

```python
"idx_activity_metric_day_sport_version": {
    "table": "activity_metric_facts",
    "columns": ("activity_day", "sport_type", "metric_version"),
    "partial": False,
},
"idx_daily_load_day_scope_sport_version": {
    "table": "daily_load_facts",
    "columns": ("day", "scope", "sport_type", "metric_version"),
    "partial": False,
},
"idx_training_model_day_scope_sport_version": {
    "table": "training_model_daily",
    "columns": ("day", "scope", "sport_type", "metric_version"),
    "partial": False,
},
```

**DuckDB adaptation:** define typed DuckDB tables and aggregate-ready views here, not in service handlers. Convert canonical days to `DATE`. Preserve source/fact tables listed in Context D-08. Add views for typed activity/fact rows rather than physical period aggregate tables until benchmarks require them.

### `src/mcp_strava/adapters/duckdb/migrations.py` (migration, batch/file-I/O)

**Analogs:** `src/mcp_strava/adapters/sqlite/migrations.py`, `src/mcp_strava/adapters/sqlite/backup.py`

**Backup pattern** from `backup.py` (lines 35-84):

```python
def create_timestamped_backup(
    source_db: str | Path,
    backups_dir: str | Path | None = None,
) -> Path:
    return _create_backup(source_db, backups_dir=backups_dir)

def _create_backup(...):
    src = Path(source_db)
    target_dir = Path(backups_dir) if backups_dir else (src.parent / "backups")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_backup_path(target_dir, label)

    src_conn = sqlite3.connect(str(src), check_same_thread=False)
    dst_conn = sqlite3.connect(str(target), check_same_thread=False)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    if not target.exists() or target.stat().st_size <= 0:
        raise RuntimeError(f"Backup failed or empty: {target}")

    with sqlite3.connect(str(target)) as verify_conn:
        row = verify_conn.execute("PRAGMA integrity_check").fetchone()
    if not row or str(row[0]).lower() != "ok":
        raise RuntimeError(f"Backup integrity check failed for {target}: {detail}")
```

**Parity dataclass pattern** (lines 28-62):

```python
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
```

**Migration runner pattern** (lines 926-968):

```python
def run_migrations(db_path: str | Path) -> PreflightReport:
    path = Path(db_path)
    before = run_preflight(path)
    backup_path = create_timestamped_backup(path)
    ...
    conn = sqlite3.connect(str(path), check_same_thread=False)
    try:
        current = read_user_version(conn)
        for spec in migration_specs():
            if current < spec.version:
                spec.apply(conn)
                current = read_user_version(conn)
                if current != spec.version:
                    raise RuntimeError(
                        f"Migration {spec.version} did not set user_version correctly: {current}"
                    )
                _record_migration(conn, spec)
        conn.commit()
    finally:
        conn.close()

    after = run_preflight(path)

    for table, before_count in before.row_counts.items():
        if after.row_counts.get(table) != before_count:
            raise RuntimeError(
                f"Post-migration row parity failed for {table}: {before_count} != {after.row_counts.get(table)}"
            )
```

**DuckDB adaptation:** migration is one-shot SQLite backup/copy to DuckDB. It must block on active refresh lease, use controlled casts, report cast failures, run source/fact/coverage parity, and pin the pre-Phase-8 SQLite backup outside normal retention. Keep SQLite import only inside migration tooling.

### `src/mcp_strava/adapters/duckdb/repository.py` (repository, CRUD/batch)

**Analog:** `src/mcp_strava/adapters/sqlite/repository.py`

**Lifetime pattern** (lines 73-96):

```python
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
```

**Fact upsert pattern** (lines 369-405):

```python
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
```

**Read-model status pattern** (lines 430-515):

```python
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
    ...
    status = "current"
    stale_reason = None
    if not versions and last_materialized_at is None:
        status = "unavailable"
        stale_reason = "no_materialized_facts"
    elif dirty_count > 0:
        status = "stale"
        stale_reason = "dirty_queue_not_empty"
```

**Half-open fact query pattern** (lines 547-580, 602-626):

```python
where = ["f.activity_day >= ?", "f.activity_day < ?"]
params: list[object] = [start_day, end_day]
if sport is not None:
    where.append("f.sport_type = ?")
    params.append(sport)
...
FROM activity_metric_facts f
LEFT JOIN activities a ON a.id = f.activity_id
WHERE {" AND ".join(where)}
ORDER BY f.activity_day DESC, f.activity_id DESC
```

```python
where = ["day >= ?", "day < ?", "scope = ?", "sport_type = ?"]
params: list[object] = [start_day, end_day, scope, sport or "all"]
...
FROM daily_load_facts
WHERE {" AND ".join(where)}
ORDER BY day ASC
```

**Refresh lease pattern** (lines 1815-1847):

```python
def get_refresh_state(self) -> RefreshStateRow:
    row = self.conn.execute("SELECT * FROM refresh_state WHERE id = 1").fetchone()
    if row is None:
        self.conn.execute("INSERT INTO refresh_state (id) VALUES (1)")
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM refresh_state WHERE id = 1").fetchone()
    return RefreshStateRow(...)

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
```

**DuckDB adaptation:** keep repository as the only SQL boundary for runtime. The query builder may emit whitelisted SQL templates, but MCP/application callers should pass product parameters and registry metric specs only.

### `src/mcp_strava/adapters/duckdb/aggregate_queries.py` (query layer, request-response/transform)

**Analogs:** `src/mcp_strava/adapters/sqlite/repository.py`, `src/mcp_strava/adapters/sqlite/read_model_materializer.py`

**Prepared facts aggregation pattern** from materializer (lines 282-361):

```python
for window in ROLLING_WINDOWS:
    start = (as_of - timedelta(days=window - 1)).isoformat()
    row = repo.conn.execute(
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
          SUM(elevation_gain_m) AS elevation_gain_m
        FROM daily_load_facts
        WHERE day BETWEEN ? AND ?
          AND scope = 'all'
          AND sport_type = 'all'
          AND metric_version = ?
        """,
        (start, as_of_day, metric_version),
    ).fetchone()
```

**Hot query guard pattern** from `tests/test_read_model_queries.py` (lines 511-528):

```python
hot_methods = [
    "fetch_latest_training_model_day",
    "fetch_activity_metric_facts",
    "fetch_activity_metric_fact",
    "fetch_daily_load_facts",
    "fetch_rolling_period_facts",
]
...
if "SUBSTR(" in segment.upper():
    violations.append(method)

assert violations == []
```

**DuckDB adaptation:** build only whitelisted query templates for buckets `day`, `week`, `month`, `year`, `all_time`, and rolling windows `7`, `14`, `28`, `42`, `90`. Use native `DATE`, half-open intervals, `time_bucket`, `weighted_avg`, `sum`, `ratio_of_sums`, `quantile_cont`, and distribution queries from registry metadata. Do not accept raw SQL, table names, or arbitrary column names.

### `src/mcp_strava/adapters/duckdb/read_model_materializer.py` or refit equivalent (service, batch/transform)

**Analog:** `src/mcp_strava/adapters/sqlite/read_model_materializer.py`

**Completeness and provenance pattern** (lines 104-173):

```python
missing: list[str] = []
if activity.detail_json is None:
    missing.append("missing_details")
if stream_count == 0:
    missing.append("missing_streams")
if hr_count == 0:
    missing.append("missing_hr")
completeness = "complete"
if "missing_streams" in missing:
    completeness = "unknown"
elif missing:
    completeness = "partial"

return {
    "activity_id": activity_id,
    "activity_day": dirty_row["activity_day"],
    "sport_type": activity.sport_type,
    "source_hash": source["source_hash"],
    "source_revision": int(source["source_revision"]),
    "metric_version": metric_version,
    "computed_at": computed_at,
    "completeness_status": completeness,
    "missing_reasons_json": _json_list(missing),
    "trimp": enriched.trimp,
    "heartrate_sample_count": hr_count,
    "stream_sample_count": stream_count,
}
```

**Transaction pattern** (lines 387-455):

```python
repo.conn.execute("BEGIN")
try:
    activity_count = 0
    for dirty in dirty_rows:
        fact = _activity_fact(repo, dirty, metric_version, computed_at)
        repo.upsert_activity_metric_fact(fact)
        activity_count += 1
        if renew_lease is not None:
            renew_lease()
    ...
    repo.record_read_model_refresh_run(...)
    cleared = repo.clear_dirty_activity_rows(dirty_rows)
except Exception as exc:
    repo.conn.rollback()
```

**DuckDB adaptation:** keep expensive stream-derived metric computation below MCP request paths. Refresh/materialization should run inside the single DuckDB-owning process or through an owner-process DB actor.

### `src/mcp_strava/application/metric_registry.py` and `src/mcp_strava/types.py` (registry/model, transform)

**Analogs:** same files.

**Metric registry helper pattern** from `metric_registry.py` (lines 100-132):

```python
def _metric(
    metric_id: str,
    label: str,
    unit: str,
    source: str,
    scope: str,
    sport_scope: str,
    comparison_mode: str,
    directionality: str,
    exposed_in: list[str],
    description: str = "",
    calculation: str | None = None,
    requirements: list[str] | None = None,
    missing_reasons: list[str] | None = None,
) -> MetricDefinition:
    calculation_text = calculation or _CALCULATION_BY_METRIC_ID.get(metric_id, "")
    if not calculation_text:
        raise ValueError(f"Missing calculation description for metric: {metric_id}")
    return MetricDefinition(...)
```

**Existing aggregation semantics pattern** from `metric_registry.py` (lines 142-166, 178-193):

```python
"distance_km": _metric(..., "sum", "higher_is_more", ["list_workouts", "get_workout_detail", "compare_periods"]),
"avg_hr": _metric(..., "avg", "context", ["list_workouts", "get_workout_detail", "compare_periods"]),
"hr_recovery_median_bpm_per_min": _metric(..., "median", "higher_is_better", ["get_workout_detail", "compare_periods"]),
"cardiac_cost": _metric(..., "median", "lower_is_better", ["get_workout_detail", "compare_periods"]),
"fitness": _metric(..., "last", "higher_is_more", ["get_fitness_state", "compare_periods"]),
"form_zone": _metric(..., "none", "context", ["get_fitness_state"]),
```

**Metric definition dataclass pattern** from `types.py` (lines 895-909):

```python
@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    label: str
    unit: str
    source: str
    scope: str
    sport_scope: str
    comparison_mode: str
    directionality: str
    requirements: list[str]
    missing_reasons: list[str]
    exposed_in: list[str]
    calculation: str
    description: str = ""
```

**Apply:** extend the dataclass rather than hard-coding aggregate math in handlers. Add fields for aggregate mode, denominator/weight/numerator columns, fact source, bundle ids, supported buckets/scopes, quantiles, and version policy. Add `get_training_aggregates` to the tool id allowlist and expose bundle membership from the registry.

### `src/mcp_strava/application/aggregate_services.py` (service, request-response/transform)

**Analog:** `src/mcp_strava/application/metric_services.py`

**Service envelope pattern** (lines 310-343):

```python
def get_fitness_state_service(..., connection=None) -> ServiceEnvelope:
    checked_at = now or datetime.now()
    with _connection_context(connection) as conn:
        repo = SQLiteRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, checked_at, _policy(), signal_first_use=signal_first_use)
        read_model = _read_model_status(repo)
        ...

    completeness = CompletenessMetadata(
        status=_status_from_read_model(read_model, has_data=bool(data), missing=missing),
        missing=missing,
        coverage=_coverage_with_read_model(read_model, {"metrics": sorted(data.keys())}),
    )
    return ServiceEnvelope(
        data=data,
        freshness=freshness,
        completeness=completeness,
        warnings=[],
        rationale=_rationale("Metric bundle projected from materialized read-model facts."),
    )
```

**Validation pattern** (lines 771-804):

```python
def _validated_custom_series(custom_daily_trimp, today_day: date, target_day: date) -> dict[str, float]:
    if not isinstance(custom_daily_trimp, list):
        raise ValueError("custom_daily_trimp must be a list")
    ...
    if day < today_day or day > target_day:
        raise ValueError("custom_daily_trimp rows must be within today..target_date")
    if trimp < 0:
        raise ValueError("custom_daily_trimp.trimp must be non-negative")
```

**Apply:** validate product parameters before hitting the aggregate query layer: date range/as_of_day, bucket enum, metric ids or bundle, scope enum, sport filters, include-empty flag, and window_days whitelist. Return `ServiceEnvelope` with factual aggregate rows and completeness/freshness metadata.

### `src/mcp_strava/application/metric_services.py` (service, compare rewrite)

**Analog:** same file.

**Current compare path to replace** (lines 661-760):

```python
def compare_periods_service(..., sport: str | None = None, ...):
    with _connection_context(connection) as conn:
        repo = SQLiteRepository.from_connection(conn)
        freshness = build_freshness_metadata(repo, checked_at, _policy(), signal_first_use=signal_first_use)
        read_model = _read_model_status(repo)
        period_a_rows = repo.fetch_activity_metric_facts(period_a_start, _next_day(period_a_end), ...)
        period_b_rows = repo.fetch_activity_metric_facts(period_b_start, _next_day(period_b_end), ...)
        model_a = repo.fetch_latest_training_model_day(CURRENT_METRIC_VERSION, as_of_day=period_a_end)
        model_b = repo.fetch_latest_training_model_day(CURRENT_METRIC_VERSION, as_of_day=period_b_end)
        rolling_a = {window: repo.fetch_rolling_period_facts(period_a_end, window, ...) for window in rolling_windows}
        rolling_b = {window: repo.fetch_rolling_period_facts(period_b_end, window, ...) for window in rolling_windows}
```

**Comparison output metadata pattern** (lines 509-542):

```python
return {
    "period_a": {"value": a_value, "sample_size": len(values_a)},
    "period_b": {"value": b_value, "sample_size": len(values_b)},
    "delta": delta,
    "delta_pct": delta_pct,
    "trend_direction": trend,
    "sample_size": {"period_a": len(values_a), "period_b": len(values_b)},
    "coverage": {"period_a": 1.0 if values_a else 0.0, "period_b": 1.0 if values_b else 0.0},
    "missing_reasons": missing,
    "metric_version_status": _version_status(rows_a or [], rows_b or []),
}
```

**Apply:** make `compare_periods_service` call `aggregate_services.query(..., bucket="all_time")` twice and format deltas. Remove the separate row-scanning maps (`ACTIVITY_SCALAR_FACTS`, `MODEL_FACTS`, `ROLLING_FACTS`, `COMPARE_PERIODS_HANDLERS`) once the registry-backed aggregate specs cover the same metrics.

### `src/mcp_strava/application/freshness.py` (service, request-response/event signaling)

**Analog:** same file.

**Freshness metadata pattern** (lines 45-73):

```python
def build_freshness_metadata(
    repo: SQLiteRepository,
    now: datetime,
    policy: RefreshPolicy,
    *,
    signal_first_use: bool = True,
) -> FreshnessMetadata:
    state = repo.get_refresh_state()
    last_activity_at = repo.latest_activity_at()
    freshness_state = evaluate_freshness(state, now, policy)
    today = now.date().isoformat()

    refresh_requested = False
    if signal_first_use and not _refresh_blocked(state, now) and not _refreshed_today(state.last_success_at, today):
        refresh_requested = repo.enqueue_refresh_request("first_use_of_day", today, now.isoformat())

    return FreshnessMetadata(...)
```

**Apply:** keep request-time freshness in application logic, not MCP tool design. Aggregate responses should include mirror freshness/read-model freshness metadata and may signal first-use refresh through the existing below-MCP queue.

### `src/mcp_strava/interfaces/mcp_http.py` (controller/interface, request-response)

**Analog:** same file.

**Tool allowlist and instructions pattern** (lines 25-37):

```python
MCP_TOOL_NAMES = (
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
)

MCP_INSTRUCTIONS = """Read-only factual training metrics from the local Strava mirror.
Do not invent or request sync, admin, debug, raw SQL, token, or raw Strava capabilities.
...
interpretation belongs to the calling agent."""
```

**Logged structured tool pattern** (lines 77-98):

```python
def _run_logged_tool(name: str, operation) -> dict[str, Any]:
    started = time.perf_counter()
    _emit_log("mcp_tool_call_started", tool=name)
    try:
        payload = _envelope_payload(operation())
    except Exception as exc:
        _emit_log("mcp_tool_call_failed", tool=name, duration_ms=..., error_type=type(exc).__name__, error=str(exc))
        raise
    _emit_log("mcp_tool_call_finished", tool=name, duration_ms=..., warnings_count=len(payload.get("warnings") or []), data_shape=_data_shape(payload.get("data")))
    return payload
```

**Tool registration pattern** (lines 212-235):

```python
@server.tool(
    name="compare_periods",
    description="Compares factual metrics between two date periods.",
    annotations=_tool_annotations(),
    structured_output=True,
)
def compare_periods(...):
    return _run_logged_tool(
        "compare_periods",
        lambda: compare_periods_service(..., signal_first_use=False),
    )
```

**Apply:** add `get_training_aggregates` here only as a product-level read-only tool. Keep structured output, read-only annotations, logging, and no admin/raw/sync/SQL parameters.

### `src/mcp_strava/devtools/mcp_client/client.py`, `tests/test_mcp_surface.py`, `tests/test_mcp_latency_gate.py` (MCP smoke/perf)

**Analogs:** same files.

**Client tool list pattern** from `client.py` (lines 19-33):

```python
EXPECTED_TOOL_NAMES = {
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
}

LATENCY_TOOL_ORDER = [
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
]
```

**Default latency calls pattern** from `client.py` (lines 272-302):

```python
return [
    {"name": "get_fitness_state", "arguments": {}},
    {"name": "list_workouts", "arguments": {"limit": 10}},
    {"name": "get_workout_detail", "arguments": {"workout_id": workout_id}},
    {"name": "compare_periods", "arguments": {...}},
    {"name": "project_fitness_state", "arguments": {...}},
]
```

**Surface exactness test pattern** from `tests/test_mcp_surface.py` (lines 16-22, 66-73):

```python
EXPECTED_TOOL_NAMES = (
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
)

assert mcp_http.MCP_TOOL_NAMES == EXPECTED_TOOL_NAMES
assert "sync" in mcp_http.MCP_INSTRUCTIONS
assert "raw SQL" in mcp_http.MCP_INSTRUCTIONS
```

**Latency gate coverage pattern** from `tests/test_mcp_latency_gate.py` (lines 90-98):

```python
calls = default_warm_latency_calls(workout_id=701, today="2026-05-24")

assert {call["name"] for call in calls} == EXPECTED_TOOL_NAMES
assert all(isinstance(call.get("arguments"), dict) for call in calls)
```

**Apply:** add `get_training_aggregates` to exact allowlists, live smoke calls, warm latency calls, and tests. Keep p95 threshold at 100 ms through `Justfile`.

### `src/mcp_strava/deploy/preflight.py`, `healthcheck.py`, `service.py`, `entrypoint.py` (deploy/runtime)

**Analogs:** same files.

**Current preflight direct DB-open pattern to refit** from `preflight.py` (lines 75-103):

```python
def validate_runtime_db(path: Path, *, quick: bool = False) -> dict[str, object]:
    if not path.exists():
        raise RuntimeError(f"Expected runtime DB does not exist: {path}")

    with open_expected_mirror_db(path) as conn:
        if quick:
            activity_count = int(conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0])
            return {"path": str(path), "quick": True, "activity_count": activity_count}

        validate_required_inventory(conn)
        _validate_phase6_versioned_stream_inventory(conn)
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        ...
```

**Current healthcheck direct DB-open pattern to refit** from `healthcheck.py` (lines 58-66):

```python
def main() -> int:
    try:
        validate_runtime_db(Path(os.environ["MCP_STRAVA_DB_PATH"]), quick=True)
        _validate_children()
        _validate_http()
    except Exception as exc:
        print(f"healthcheck failed: {exc}", file=sys.stderr)
        return 1
    return 0
```

**Current multi-child supervisor pattern to replace** from `service.py` (lines 50-65):

```python
def _child_specs() -> list[ChildSpec]:
    specs: list[ChildSpec] = []
    if _refresh_worker_enabled():
        specs.append(
            ChildSpec(
                name="refresh",
                command=[sys.executable, "-m", "mcp_strava.refresh.worker"],
            )
        )
    specs.append(
        ChildSpec(
            name="mcp-http",
            command=[sys.executable, "-m", "mcp_strava.interfaces.mcp_http"],
        )
    )
    return specs
```

**Entrypoint validation pattern** from `entrypoint.py` (lines 24-38):

```python
db_path = Path(os.environ["MCP_STRAVA_DB_PATH"])
try:
    if _needs_migration(db_path):
        run_migrations(db_path)
    validate_runtime_db(db_path, quick=False)
except Exception as exc:
    print(f"entrypoint preflight failed: {exc}", file=sys.stderr)
    return 1

os.execvp(
    sys.executable,
    [sys.executable, "-m", "mcp_strava.deploy.service"],
)
```

**Apply:** Phase 8 must change topology so one process owns the DuckDB read-write connection. Healthcheck should validate child/HTTP/owner status without independently opening the live DuckDB file read-write. Entry/startup preflight can validate offline before the owner process starts.

### `src/mcp_strava/refresh/runtime.py`, `worker.py`, `bootstrap.py`, `_sync_ops.py` (refresh runtime)

**Analogs:** same files.

**Lease-gated refresh pattern** from `runtime.py` (lines 45-128):

```python
now_iso = _now_iso(clock)
expires_at = _plus_seconds_iso(clock, policy.lease_duration_seconds)
if not repo.acquire_refresh_lease(owner, expires_at, now_iso):
    return RefreshSkipped("refresh_in_progress")

try:
    state = repo.get_refresh_state()
    if state.backoff_until and state.backoff_until > now_iso:
        return RefreshSkipped("refresh_delayed")
    ...
    repo.set_checkpoint(Stage.READ_MODEL_MATERIALIZE.value, None)
    _sync_ops.materialize_read_model_stage(
        repo,
        CURRENT_METRIC_VERSION,
        now_iso,
        _lease_renewer(repo, clock, owner, policy.lease_duration_seconds),
    )
    ...
finally:
    repo.release_refresh_lease(owner)
```

**Worker polling pattern to move in-process** from `worker.py` (lines 183-221):

```python
def run_forever(...):
    resolved_poll_seconds = poll_seconds
    if resolved_poll_seconds is None:
        resolved_poll_seconds = _poll_seconds(os.environ.get("MCP_STRAVA_REFRESH_POLL_SECONDS"))
    if emit_start:
        _emit("refresh_worker_started", poll_seconds=resolved_poll_seconds)

    while stop_event is None or not stop_event.is_set():
        try:
            run_pending_once(emit_idle=False)
        except Exception as exc:
            _emit("refresh_worker_error", error_type=type(exc).__name__)
        ...
```

**Apply:** preserve lease/backoff/checkpoint semantics. Replace separate read-write process opens with in-process scheduling, an owner-process queue, or a single owner abstraction selected by the planner.

### `src/mcp_strava/settings.py`, `src/mcp_strava/db.py`, `pyproject.toml`, `uv.lock` (config/dependencies)

**Analogs:** same files.

**Settings key/default pattern** from `settings.py` (lines 31-56, 149-170):

```python
@dataclass(frozen=True)
class Settings:
    database_path: Path
    token_path: Path
    runtime_profile: str
    http: HttpSettings
    freshness: FreshnessSettings
    refresh: RefreshSettings

_KEYS = {
    'MCP_STRAVA_DB_PATH',
    'MCP_STRAVA_TOKEN_PATH',
    ...
}

database_path = Path(resolve('MCP_STRAVA_DB_PATH', str(root / 'data' / 'strava.db')))
```

**DbConn pattern to refit** from `db.py` (lines 21-39):

```python
def _db_path() -> str:
    return str(get_settings().database_path)

class DbConn:
    """Context manager for SQLite connections - auto-closes on exit."""

    def __enter__(self):
        self.conn = open_expected_mirror_db(_db_path())
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()
```

**Dependency pattern** from `pyproject.toml` (lines 5-12):

```toml
[project]
name = "mcp-strava"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = ["mcp>=1.27.1,<1.28", "PyYAML>=6.0.2,<7"]

[project.optional-dependencies]
test = ["pytest"]
```

**Apply:** add `duckdb` only after the human package-legitimacy checkpoint required by research. Keep `MCP_STRAVA_DB_PATH` as a storage-neutral key but change defaults/docs/container values to a `.duckdb` path if the planner chooses that spelling. Update `uv.lock`.

### `deploy/Dockerfile`, `deploy/docker-compose.yml`, `Justfile`, `docs/deployment.md` (deployment/config/docs)

**Analogs:** same files.

**Docker runtime env pattern** from `deploy/Dockerfile` (lines 1-12, 27-30):

```dockerfile
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MCP_STRAVA_RUNTIME_PROFILE=container \
    MCP_STRAVA_HTTP_HOST=0.0.0.0 \
    MCP_STRAVA_HTTP_PORT=8080 \
    MCP_STRAVA_ALLOW_CONTAINER_BIND=1 \
    MCP_STRAVA_DB_PATH=/runtime/data/strava.db \
    MCP_STRAVA_TOKEN_PATH=/runtime/.env \
    MCP_STRAVA_REFRESH_INTERVAL_SECONDS=3600

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -m mcp_strava.deploy.healthcheck
```

**Compose network/bind pattern** from `deploy/docker-compose.yml` (lines 8-24):

```yaml
environment:
  MCP_STRAVA_RUNTIME_PROFILE: container
  MCP_STRAVA_HTTP_HOST: 0.0.0.0
  MCP_STRAVA_HTTP_PORT: "8080"
  MCP_STRAVA_ALLOW_CONTAINER_BIND: "1"
  MCP_STRAVA_DB_PATH: /runtime/data/strava.db
  MCP_STRAVA_TOKEN_PATH: /runtime/.env
volumes:
  - /opt/docker/mcp-strava:/runtime
expose: ["8080"]
```

**Justfile acceptance gate pattern** (lines 9-24):

```make
test:
    {{compose}} build
    {{compose}} up -d --force-recreate --remove-orphans --wait --wait-timeout 90
    {{compose}} exec -T mcp-strava {{smoke}}

mcp-read-model-perf samples="20" warmup="2" p95_ms="100":
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli perf-read-model --samples {{samples}} --warmup {{warmup}} --p95-ms {{p95_ms}} --compact --url http://127.0.0.1:8080/mcp
```

**Runbook pattern** from `docs/deployment.md` (lines 46-108):

```markdown
Before accepting the materialized read-model runtime, validate against the live Docker state or a copied live database. Keep the pinned pre-Phase-7 backup until migration, materialization, parity, Docker smoke, and the p95 gate have all passed.
...
just test
...
just mcp-read-model-perf
...
The p95 gate covers all product MCP tools: `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, and `project_fitness_state`.
```

**Apply:** update DB path/import checks to DuckDB, preserve container network safety, preserve `just test`, add six-tool smoke/perf coverage, and update the runbook to Phase 8 backup/cutover/rollback wording.

### Test Files (tests, validation)

**Migration tests:** `tests/test_duckdb_migration.py`

**Analog:** `tests/test_sqlite_safety.py`

**Temp fixture and no-live-path pattern** (lines 12-134, 346-351):

```python
def _create_fixture_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE activities (...);
        CREATE TABLE streams (...);
        CREATE TABLE athlete_zones (...);
        CREATE TABLE sync_log (...);
        CREATE TABLE kudos (...);
        """
    )
    ...
    conn.execute("PRAGMA user_version=0")
    conn.commit()
    conn.close()

def test_full_fidelity_migration_tests_use_temp_paths_only(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.db"
    _create_fixture_db(fixture)
    resolved = fixture.resolve()
    assert "/data/strava.db" not in str(resolved)
    assert "/opt/docker/mcp-strava" not in str(resolved)
```

**Parity test pattern** (lines 284-311):

```python
preserved_tables = ("activities", "streams", "athlete_zones", "sync_log", "kudos")
with sqlite3.connect(fixture) as conn:
    before_counts = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in preserved_tables}

run_migrations(fixture)

with sqlite3.connect(fixture) as conn:
    after_counts = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in preserved_tables}

assert after_counts == before_counts
```

**Repository tests:** `tests/test_duckdb_repository.py`

**Analog:** `tests/test_repository_boundary.py`

**Repository method and lease patterns** (lines 348-398):

```python
expected = {
    "get_refresh_state",
    "acquire_refresh_lease",
    "release_refresh_lease",
    "set_checkpoint",
    "record_refresh_attempt",
    "record_refresh_success",
    "record_refresh_failure",
    "enqueue_refresh_request",
    "pending_refresh_requests",
    "mark_refresh_requests_consumed",
}
assert expected <= set(dir(SQLiteRepository))

with SQLiteRepository.from_path(fixture) as repo:
    assert repo.acquire_refresh_lease("owner-a", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")
    assert not repo.acquire_refresh_lease("owner-b", "2026-05-21T12:10:00Z", "2026-05-21T12:00:00Z")
```

**Aggregate tests:** `tests/test_training_aggregates.py`

**Analog:** `tests/test_read_model_queries.py`

**Fixture and half-open range pattern** (lines 114-140, 373-392):

```python
def _repo_with_facts(path: Path) -> SQLiteRepository:
    conn = _create_base_db(path)
    _insert_activity(conn, 701, "2026-05-20", sport_type="Run", with_hr=True)
    _insert_activity(conn, 702, "2026-05-21", sport_type="Run", with_hr=True)
    _insert_activity(conn, 703, "2026-05-19", sport_type="Hike", with_hr=False)
    conn.executemany(
        """
        INSERT INTO activity_metric_facts (...)
        """
    )

rows = repo.fetch_activity_metric_facts(
    "2026-05-20",
    "2026-05-22",
    sport="Run",
    metric_version=1,
    limit=10,
)
assert [row["activity_id"] for row in rows] == [702, 701]
```

**MCP surface tests:** update `tests/test_mcp_surface.py`

**Analog:** `tests/test_mcp_surface.py`

**Structured output and annotation pattern** (lines 161-212):

```python
server = mcp_http.build_mcp_server()
tools = asyncio.run(server.list_tools())
assert tuple(tool.name for tool in tools) == EXPECTED_TOOL_NAMES
for tool in tools:
    annotations = tool.annotations
    assert annotations.readOnlyHint is True
    assert annotations.destructiveHint is False
    assert annotations.idempotentHint is True
    assert annotations.openWorldHint is False
    assert tool.inputSchema is not None

content, payload = asyncio.run(server.call_tool(tool_name, arguments))
assert set(payload.keys()) == {"data", "freshness", "completeness", "warnings", "rationale"}
assert READ_MODEL_METADATA_KEYS <= set(payload["completeness"]["coverage"]["read_model"])
```

**Metric registry tests:** update `tests/test_metric_registry.py`

**Analog:** `tests/test_metric_registry.py`

**Allowlist and mapping pattern** (lines 100-108, 205-211):

```python
ALLOWED_TOOLS = {
    "get_fitness_state",
    "list_workouts",
    "get_workout_detail",
    "compare_periods",
    "project_fitness_state",
}

mapped = set(metric_services.COMPARE_PERIODS_HANDLERS.keys())
assert metric_services.COMPARE_PERIODS_SKIP_REASONS == {}
for metric_id, definition in METRIC_REGISTRY.items():
    if definition.comparison_mode == "none" or "compare_periods" not in definition.exposed_in:
        continue
    assert metric_id in mapped, f"{metric_id} must be mapped"
```

**Security boundary pattern:** `tests/test_metric_services.py` (lines 17-29):

```python
FORBIDDEN_KEYS = {
    "recommendation",
    "action",
    "intensity",
    "on_track",
    "should",
    "ready",
    "best_scenario",
    "sync_log",
    "sql",
    "token",
    "raw_strava",
}
```

**Apply:** add tests for aggregate rows carrying bucket bounds, units, aggregation mode, denominator, sample size, activity/null/excluded counts, completeness, missing reasons, metric version status, materialized timestamp, mirror freshness, and read-model freshness.

## Shared Patterns

### No Raw/Admin MCP Surface

**Source:** `src/mcp_strava/interfaces/mcp_http.py` lines 33-37 and `tests/test_metric_services.py` lines 17-29

**Apply to:** `interfaces/mcp_http.py`, `application/aggregate_services.py`, `application/metric_services.py`, `tests/test_mcp_surface.py`, `tests/test_training_aggregates.py`

```python
MCP_INSTRUCTIONS = """Read-only factual training metrics from the local Strava mirror.
Do not invent or request sync, admin, debug, raw SQL, token, or raw Strava capabilities.
...
interpretation belongs to the calling agent."""
```

### Shared Service Envelope

**Source:** `src/mcp_strava/types.py` lines 860-889

**Apply to:** all MCP-facing application services

```python
@dataclass
class CompletenessMetadata:
    """Factual completeness state for a service payload."""

    status: str
    missing: list[str] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)

@dataclass
class ServiceEnvelope:
    """Shared product service response envelope."""

    data: Any
    freshness: FreshnessMetadata
    completeness: CompletenessMetadata
    warnings: list[ServiceWarning] = field(default_factory=list)
    rationale: list[ServiceRationale] = field(default_factory=list)
```

### Metric Version and Completeness Metadata

**Source:** `src/mcp_strava/adapters/sqlite/repository.py` lines 500-515 and `src/mcp_strava/application/metric_services.py` lines 500-506

**Apply to:** DuckDB repository, aggregate query layer, `compare_periods`

```python
versions = self._read_model_metadata_versions(metric_version)
...
return {
    "status": metadata.status,
    "last_materialized_at": metadata.last_materialized_at,
    "dirty_count": metadata.dirty_count,
    "oldest_dirty_day": metadata.oldest_dirty_day,
    "metric_versions_present": metadata.metric_versions_present,
    "stale_reason": metadata.stale_reason,
}
```

```python
def _version_status(rows_a: list, rows_b: list) -> str:
    versions = {int(row["metric_version"]) for row in rows_a + rows_b if row["metric_version"] is not None}
    if not versions:
        return "missing"
    if len(versions) > 1:
        return "mixed"
    return "consistent"
```

### Single Writer Lease Semantics

**Source:** `src/mcp_strava/refresh/runtime.py` lines 45-59 and `src/mcp_strava/adapters/sqlite/repository.py` lines 1835-1847

**Apply to:** migration cutover gate, refresh runtime, owner-process concurrency guard tests

```python
if not repo.acquire_refresh_lease(owner, expires_at, now_iso):
    return RefreshSkipped("refresh_in_progress")
```

### Docker-First Verification

**Source:** `Justfile` lines 9-24

**Apply to:** phase acceptance and all Docker/runtime plan tasks

```make
test:
    {{compose}} build
    {{compose}} up -d --force-recreate --remove-orphans --wait --wait-timeout 90
    {{compose}} exec -T mcp-strava {{smoke}}

mcp-read-model-perf samples="20" warmup="2" p95_ms="100":
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli perf-read-model --samples {{samples}} --warmup {{warmup}} --p95-ms {{p95_ms}} --compact --url http://127.0.0.1:8080/mcp
```

## No Analog Found

There is no exact existing standalone analog for `src/mcp_strava/adapters/duckdb/aggregate_queries.py`; use the repository hot query methods and read-model materializer aggregate SQL as partial analogs. No raw SQL builder or public SQL surface exists in the codebase, and Phase 8 should not introduce one.

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `src/mcp_strava/adapters/duckdb/aggregate_queries.py` | service/repository | request-response, transform | No standalone aggregate-query module exists yet; closest patterns are repository fact queries and materializer rolling aggregation. |

## Metadata

**Analog search scope:** `src/mcp_strava/**`, `tests/**`, `deploy/**`, `Justfile`, `pyproject.toml`, `docs/deployment.md`
**Files scanned:** 80+
**Project skills:** checked `.codex/skills` and `.agents/skills`; neither exists in this checkout.
**Pattern extraction date:** 2026-05-25
