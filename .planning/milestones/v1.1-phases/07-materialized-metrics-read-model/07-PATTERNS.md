# Phase 07: materialized-metrics-read-model - Pattern Map

**Mapped:** 2026-05-24
**Files analyzed:** 14
**Analogs found:** 14 / 14

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/mcp_strava/adapters/sqlite/schema.py` | migration | CRUD | `src/mcp_strava/adapters/sqlite/schema.py` | exact |
| `src/mcp_strava/adapters/sqlite/migrations.py` | migration | batch | `src/mcp_strava/adapters/sqlite/migrations.py` | exact |
| `src/mcp_strava/adapters/sqlite/repository.py` | repository/service | CRUD | `src/mcp_strava/adapters/sqlite/repository.py` | exact |
| `src/mcp_strava/refresh/checkpoints.py` | config | event-driven | `src/mcp_strava/refresh/checkpoints.py` | exact |
| `src/mcp_strava/refresh/runtime.py` | service | batch | `src/mcp_strava/refresh/runtime.py` | exact |
| `src/mcp_strava/refresh/_sync_ops.py` | service | event-driven | `src/mcp_strava/refresh/_sync_ops.py` | exact |
| `src/mcp_strava/application/metric_services.py` | service | request-response | `src/mcp_strava/application/metric_services.py` | exact |
| `src/mcp_strava/interfaces/mcp_http.py` | controller | request-response | `src/mcp_strava/interfaces/mcp_http.py` | exact |
| `src/mcp_strava/devtools/mcp_client/client.py` | utility | request-response | `src/mcp_strava/devtools/mcp_client/client.py` | exact |
| `tests/test_metric_services.py` | test | request-response | `tests/test_metric_services.py` | exact |
| `tests/test_refresh_runtime.py` | test | batch | `tests/test_refresh_runtime.py` | exact |
| `tests/test_sqlite_safety.py` | test | file-I/O | `tests/test_sqlite_safety.py` | exact |
| `tests/test_security_guards.py` | test | transform | `tests/test_security_guards.py` | exact |
| `tests/test_mcp_surface.py` / `tests/test_mcp_test_client.py` | test | request-response | `tests/test_mcp_surface.py` / `tests/test_mcp_test_client.py` | exact |

## Pattern Assignments

### `src/mcp_strava/adapters/sqlite/schema.py` (migration, CRUD)
**Analog:** `src/mcp_strava/adapters/sqlite/schema.py`

**Inventory/version pattern** (lines 8-17, 127-146):
```python
BASE_TABLES_V1: tuple[str, ...] = ("activities", "streams", "athlete_zones", "sync_log", "kudos")
...
REQUIRED_TABLES_BY_VERSION: dict[int, tuple[str, ...]] = { ... }
REQUIRED_INDEXES_BY_VERSION: dict[int, dict[str, dict[str, object]]] = { ... }
```

**Validation failure pattern** (lines 225-255):
```python
def validate_required_inventory(conn: sqlite3.Connection) -> None:
    ...
    if not _table_exists(conn, table):
        raise RuntimeError(f"Missing required table: {table}")
    ...
    if missing:
        raise RuntimeError(f"Missing required columns in {table}: {', '.join(missing)}")
```

### `src/mcp_strava/adapters/sqlite/migrations.py` (migration, batch)
**Analog:** `src/mcp_strava/adapters/sqlite/migrations.py`

**Imports + gate pipeline style** (lines 1-18):
```python
"""Explicit migration gate: preflight -> backup -> migrate -> post-check -> parity."""
from mcp_strava.adapters.sqlite.backup import create_timestamped_backup
from mcp_strava.adapters.sqlite.schema import (
    PreflightReport, integrity_check, row_counts, read_user_version,
    run_preflight_checks, validate_required_inventory, set_user_version,
)
```

**Idempotent DDL pattern** (lines 132-161):
```python
conn.executescript("""
CREATE TABLE IF NOT EXISTS refresh_state (...);
INSERT OR IGNORE INTO refresh_state (id) VALUES (1);
...
CREATE UNIQUE INDEX IF NOT EXISTS idx_refresh_requests_dedupe ...
""")
set_user_version(conn, 2)
```

### `src/mcp_strava/adapters/sqlite/repository.py` (repository/service, CRUD)
**Analog:** `src/mcp_strava/adapters/sqlite/repository.py`

**Unit-of-work + factory pattern** (lines 23-43):
```python
@dataclass
class SQLiteRepository:
    conn: object
    @classmethod
    def from_path(...)
    @classmethod
    def from_connection(...)
```

**Transactional replace pattern** (lines 678-742):
```python
self.conn.execute("BEGIN")
try:
    self.conn.execute("DELETE FROM streams WHERE activity_id = ?", (activity_id,))
    ...
except Exception:
    self.conn.rollback()
    raise
self.conn.commit()
```

**Query-shape anti-pattern to remove in Phase 7** (lines 74-78, 120, 253-257):
```python
where.append("SUBSTR(date, 1, 10) >= ?")
where.append("SUBSTR(date, 1, 10) <= ?")
```

### `src/mcp_strava/refresh/checkpoints.py` (config, event-driven)
**Analog:** `src/mcp_strava/refresh/checkpoints.py`

**Stage enum + transition map pattern** (lines 8-33):
```python
class Stage(StrEnum):
    SUMMARIES = "summaries"
    STREAMS = "streams"
    ...
NEXT_STAGE_DAILY: dict[Stage, Stage] = { ... }
```

### `src/mcp_strava/refresh/runtime.py` (service, batch)
**Analog:** `src/mcp_strava/refresh/runtime.py`

**Lease acquisition/release guard** (lines 48-53, 111-113):
```python
if not repo.acquire_refresh_lease(owner, expires_at, now_iso):
    return RefreshSkipped("refresh_in_progress")
...
finally:
    repo.release_refresh_lease(owner)
```

**Stage checkpoint sequencing** (lines 80-96):
```python
repo.set_checkpoint(Stage.SUMMARIES.value, None)
...
repo.set_checkpoint(Stage.SCHEMA_VALIDATE.value, None)
...
repo.set_checkpoint(Stage.COMPLETE.value, None)
```

**Long-job lease renewal pattern** (lines 178-182, 214-222):
```python
renewed = repo.renew_refresh_lease(owner, _plus_seconds_iso(clock, lease_seconds))
if not renewed:
    raise RuntimeError("refresh lease lost during stream-channel backfill")
```

### `src/mcp_strava/refresh/_sync_ops.py` (service, event-driven)
**Analog:** `src/mcp_strava/refresh/_sync_ops.py`

**Sync operation orchestration pattern** (lines 180-212):
```python
for raw in data:
    act = parse_strava_activity(raw)
    existing = repo.activity_by_id(act.id)
    repo.upsert_activity_summary(...)
```

**Checkpoint during incremental loops** (lines 223-244):
```python
for activity in repo.activities_missing_streams(since):
    repo.set_checkpoint(checkpoint_stage.value, str(activity.id))
    response = transport.fetch(...)
```

### `src/mcp_strava/application/metric_services.py` (service, request-response)
**Analog:** `src/mcp_strava/application/metric_services.py`

**Current forbidden MCP recompute imports (guard target)** (lines 11, 16, 18):
```python
from mcp_strava.analytics import weekly_digest
from mcp_strava.metrics import check_hr_anomalies, check_z5_minutes, enrich_activity
from mcp_strava.report import daily_report_from_connection
```

**Service envelope contract pattern** (lines 448-459):
```python
completeness = CompletenessMetadata(...)
return ServiceEnvelope(
    data=data,
    freshness=freshness,
    completeness=completeness,
    warnings=warnings,
    rationale=[...],
)
```

### `src/mcp_strava/interfaces/mcp_http.py` (controller, request-response)
**Analog:** `src/mcp_strava/interfaces/mcp_http.py`

**Tool allowlist/forbidden guard pattern** (lines 24-57):
```python
MCP_TOOL_NAMES = (...)
FORBIDDEN_TOOL_NAMES = {...}
```

**Per-tool latency log wrapper pattern** (lines 97-118):
```python
started = time.perf_counter()
...
_emit_log("mcp_tool_call_finished", tool=name, duration_ms=...)
```

### `src/mcp_strava/devtools/mcp_client/client.py` (utility, request-response)
**Analog:** `src/mcp_strava/devtools/mcp_client/client.py`

**Async client wrapper + timeout pattern** (lines 39-57, 96-107, 166-176):
```python
class StdioMcpClient:
    ...
    result = await session.call_tool(..., read_timeout_seconds=timedelta(...))
```

**Surface assertion pattern** (lines 231-238):
```python
missing = sorted(EXPECTED_TOOL_NAMES - tool_names)
forbidden = sorted(FORBIDDEN_TOOL_NAMES & tool_names)
if missing or forbidden:
    raise McpClientError(...)
```

### `tests/test_metric_services.py` (test, request-response)
**Analog:** `tests/test_metric_services.py`

**Fixture DB + migration-before-test pattern** (lines 55-106):
```python
def _create_base_db(path: Path) -> sqlite3.Connection:
    ...
    run_migrations(path)
```

**Envelope-shape assertions** (lines 267-270):
```python
assert set(payload) == {"data", "freshness", "completeness", "warnings", "rationale"}
```

### `tests/test_refresh_runtime.py` (test, batch)
**Analog:** `tests/test_refresh_runtime.py`

**Fake clock/transport deterministic runtime tests** (lines 26-38, 51-58, 152-165):
```python
class FakeClock: ...
class FakeStravaTransport: ...
result = run_once(...)
assert state.checkpoint_stage == Stage.COMPLETE.value
```

### `tests/test_sqlite_safety.py` (test, file-I/O)
**Analog:** `tests/test_sqlite_safety.py`

**Backup/preflight/migration safety gate tests** (lines 158-179, 181-203, 242-257):
```python
report = run_preflight(db_path)
...
backup_path = create_timestamped_backup(...)
...
run_migrations(fixture); run_migrations(fixture)
```

### `tests/test_security_guards.py` / `tests/test_mcp_surface.py` / `tests/test_mcp_test_client.py`
**Analog:** these same test files

**Import boundary static guard pattern** (`test_security_guards.py` lines 241-260):
```python
def _import_violations(rel_path: str, disallowed_prefixes: tuple[str, ...]) -> list[str]:
    ...
```

**MCP allowlist exactness tests** (`test_mcp_surface.py` lines 76-81):
```python
assert mcp_http.MCP_TOOL_NAMES == EXPECTED_TOOL_NAMES
assert FORBIDDEN_TOOL_NAMES.isdisjoint(set(mcp_http.MCP_TOOL_NAMES))
```

**Scriptable MCP client assertions** (`test_mcp_test_client.py` lines 36-73):
```python
steps = [{"action": "list_tools", "expect": {...}}, ...]
with pytest.raises(McpClientError, ...):
    ...
```

## Shared Patterns

### Atomic Source-Write + Transaction Discipline
**Source:** `src/mcp_strava/adapters/sqlite/repository.py` (lines 678-742), `src/mcp_strava/refresh/_sync_ops.py` (lines 193-206)
**Apply to:** all source-mutating repository methods in Phase 7 (`summary/detail/stream replace/channel merge/unavailable metadata`)

### Stage/Lease Refresh Runtime Control
**Source:** `src/mcp_strava/refresh/runtime.py` (lines 48-53, 80-96, 178-182, 214-222)
**Apply to:** new read-model materialization stage and long recompute loops

### MCP Read-Only Boundary + Tool Logging
**Source:** `src/mcp_strava/interfaces/mcp_http.py` (lines 24-57, 97-118, 164-253)
**Apply to:** forbid recompute/admin controls and preserve per-tool structured latency logs

### Envelope/Freshness/Completeness Contract
**Source:** `src/mcp_strava/application/metric_services.py` (lines 448-459, 527-542, 760-771)
**Apply to:** all read-model-backed services; include partial/stale metadata instead of inline recompute

### Safety/Migration/Boundary Test Style
**Source:** `tests/test_sqlite_safety.py`, `tests/test_refresh_runtime.py`, `tests/test_security_guards.py`, `tests/test_mcp_surface.py`
**Apply to:** v5 migration tests, dirty-queue invariants, MCP no-recompute/no-admin boundaries, and perf harness tests

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `src/mcp_strava/adapters/sqlite/read_model_materializer.py` (if introduced) | service | batch | No dedicated materializer module exists yet; closest behavior is split between `refresh/runtime.py` and `refresh/_sync_ops.py`. |
| `tests/test_mcp_latency_gate.py` (if introduced) | test | request-response | No existing p95 tool-latency gate test file yet; closest analog is `devtools/mcp_client/client.py` plus `tests/test_mcp_test_client.py`. |

## Metadata

**Analog search scope:** `src/mcp_strava/adapters/sqlite`, `src/mcp_strava/refresh`, `src/mcp_strava/application`, `src/mcp_strava/interfaces`, `src/mcp_strava/devtools/mcp_client`, `tests/`
**Files scanned:** 14
**Pattern extraction date:** 2026-05-24
