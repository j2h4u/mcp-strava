---
analysis_date: 2026-06-01
last_mapped_commit: d16b5fd
scope: full-repo
---
# Architecture

**Analysis Date:** 2026-06-01

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                         Interfaces Layer                                  │
│   HTTP MCP (FastMCP streamable)   CLI (python -m mcp_strava)             │
│   `interfaces/mcp_http.py`        `cli.py` / `__main__.py`              │
└──────────┬───────────────────────────────────────┬───────────────────────┘
           │ calls                                 │ calls
           ▼                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        Application Layer                                  │
│  metric_services.py  product_facts.py  aggregate_services.py            │
│  freshness.py  mirror_coverage.py                                       │
│  `application/`                                                          │
└──────────┬───────────────────────────────────────┬───────────────────────┘
           │ reads via                             │ writes via
           ▼                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         Adapters Layer                                    │
│  ┌─────────────────────────────┐   ┌──────────────────────────────────┐  │
│  │  adapters/duckdb/           │   │  adapters/strava/                │  │
│  │  connection.py  (MirrorConn,│   │  client.py   (StravaClient)      │  │
│  │  ReadConn, process RLock)   │   │  transport.py  token_provider.py │  │
│  │  repository.py (DuckDBRepo) │   │  token_refresh.py  rate_limit.py │  │
│  │  schema.py + registry DDL   │   │  clock.py  types.py              │  │
│  │  aggregate_queries.py       │   │                                  │  │
│  │  read_model_materializer.py │   └──────────────────────────────────┘  │
│  └─────────────────────────────┘                                         │
└──────────┬────────────────────────────────────────────────────────────────┘
           │ persists to
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  DuckDB Mirror  (`/runtime/data/strava.duckdb`)                          │
│  activities · streams · stream_channels · kudos                          │
│  activity_metric_facts · daily_load_facts · training_model_daily         │
│  rolling_period_facts · refresh_state · refresh_requests · sync_log      │
└──────────────────────────────────────────────────────────────────────────┘

Alongside the read/write path, the background refresh pipeline feeds the DB:

┌──────────────────────────────────────────────────────────────────────────┐
│  Refresh Pipeline (`refresh/`)                                           │
│  worker.py → runtime.py → _sync_ops.py                                  │
│  bootstrap.py  policy.py  checkpoints.py  health.py  freshness.py       │
└──────────┬─────────────────────────────────────────────────────────────  ┘
           │ uses adapters/strava/ + adapters/duckdb/
           ▼
     Strava API  →  DuckDB Mirror

The deploy layer owns process lifecycle:
  deploy/entrypoint.py → preflight → deploy/service.py
  service.py: threads refresh_worker.run_forever + mcp_http.main()
```

## Component Responsibilities

| Component | Responsibility | Key File(s) |
|-----------|----------------|-------------|
| `interfaces/mcp_http.py` | FastMCP HTTP server, tool registration, response caching, security guards | `src/mcp_strava/interfaces/mcp_http.py` |
| `cli.py` | Thin dispatcher for all operator commands (report, workouts, admin catchup, compact, sql) | `src/mcp_strava/cli.py` |
| `application/metric_services.py` | Read-model–backed metric queries returned as `ServiceEnvelope` | `src/mcp_strava/application/metric_services.py` |
| `application/product_facts.py` | Narrative-ready daily/weekly/historical fact bundles assembled from metric services | `src/mcp_strava/application/product_facts.py` |
| `application/aggregate_services.py` | Bucketed time-series aggregate queries over read-model fact tables | `src/mcp_strava/application/aggregate_services.py` |
| `application/freshness.py` | Freshness metadata assembly from refresh state | `src/mcp_strava/application/freshness.py` |
| `metric_registry.py` | Central registry of metric IDs, bundles, status fact specs, and registry-owned fact-column SQL metadata (core-level: imported by both application and adapters, so it lives below both to avoid an adapter→application dependency) | `src/mcp_strava/metric_registry.py` |
| `adapters/duckdb/repository.py` | All DuckDB reads and writes behind explicit unit-of-work; process-level RLock | `src/mcp_strava/adapters/duckdb/repository.py` |
| `adapters/duckdb/connection.py` | `MirrorConn` (write/admin), `ReadConn` (thread-local reused read), process RLock | `src/mcp_strava/adapters/duckdb/connection.py` |
| `adapters/duckdb/schema.py` | Static schema, table/column inventory constants, aggregate views, and migration policy; `activity_metric_facts` DDL is generated by `metric_registry.py` | `src/mcp_strava/adapters/duckdb/schema.py` |
| `adapters/duckdb/read_model_materializer.py` | Computes and upserts activity_metric_facts, daily_load_facts, training_model_daily, rolling_period_facts from dirty queue | `src/mcp_strava/adapters/duckdb/read_model_materializer.py` |
| `adapters/duckdb/aggregate_queries.py` | SQL-backed aggregate fact queries (status facts, window aggregates) | `src/mcp_strava/adapters/duckdb/aggregate_queries.py` |
| `adapters/strava/client.py` | `StravaClient` facade: `api_request()`, `refresh_token()`; single wiring of transport chain | `src/mcp_strava/adapters/strava/client.py` |
| `adapters/strava/transport.py` | Low-level HTTP to Strava API, rate-limit policy enforcement | `src/mcp_strava/adapters/strava/transport.py` |
| `adapters/strava/token_provider.py` | File-backed OAuth token provider with automatic refresh | `src/mcp_strava/adapters/strava/token_provider.py` |
| `adapters/strava/token_refresh.py` | OAuth token refresh HTTP logic | `src/mcp_strava/adapters/strava/token_refresh.py` |
| `refresh/worker.py` | Polling loop: check policy → run_once → stream backfill → materialize dirty | `src/mcp_strava/refresh/worker.py` |
| `refresh/runtime.py` | Refresh orchestration: stage sequencing (SUMMARIES → STREAMS → DETAILS → READ_MODEL_MATERIALIZE → KUDOS) | `src/mcp_strava/refresh/runtime.py` |
| `refresh/_sync_ops.py` | Atomic sync operations called by runtime (fetch summaries, streams, details, kudos, materialize) | `src/mcp_strava/refresh/_sync_ops.py` |
| `refresh/bootstrap.py` | Wires collaborators (transport chain, clock, policy) for refresh pipeline | `src/mcp_strava/refresh/bootstrap.py` |
| `refresh/policy.py` | `RefreshPolicy`: configurable interval, batch sizes, backfill limits | `src/mcp_strava/refresh/policy.py` |
| `refresh/checkpoints.py` | `Stage` enum defining refresh pipeline stage names and ordering | `src/mcp_strava/refresh/checkpoints.py` |
| `deploy/entrypoint.py` | Container entry: runs DB preflight then `exec`s into `deploy/service.py` | `src/mcp_strava/deploy/entrypoint.py` |
| `deploy/service.py` | Single-owner DuckDB process: threads refresh worker + serves MCP HTTP | `src/mcp_strava/deploy/service.py` |
| `deploy/preflight.py` | Validates DB existence, schema, and health before startup | `src/mcp_strava/deploy/preflight.py` |
| `maintenance/compact.py` | Admin compaction: rewrites DuckDB to reclaim space | `src/mcp_strava/maintenance/compact.py` |
| `sync.py` | Public API for refresh operations used by CLI (`backfill_activities`, `sync_activities`) | `src/mcp_strava/sync.py` |
| `settings.py` | Typed frozen `Settings` dataclass; env-var loading; singleton cache | `src/mcp_strava/settings.py` |
| `types.py` | Shared data contracts: `StravaActivity`, `ServiceEnvelope`, `DailyLoadPoint`, repo row types | `src/mcp_strava/types.py` |
| `metrics.py` | Pure metric computation functions (cardiac drift, HR zones, cardiac cost, etc.) | `src/mcp_strava/metrics.py` |
| `training.py` | Training model: fitness/fatigue/form forward simulation (`forward_simulate`) | `src/mcp_strava/training.py` |
| `hr_zones.py` | HR zone bound computation from hr_max and hr_rest | `src/mcp_strava/hr_zones.py` |
| `cardiac_drift.py` | Pure cardiac drift computation | `src/mcp_strava/cardiac_drift.py` |
| `constants.py` | `Config` class: zone coefficients, training sport list, other constants | `src/mcp_strava/constants.py` |

## Pattern Overview

**Overall:** Ports and Adapters (Hexagonal Architecture) with a dirty-queue read model.

**Key Characteristics:**
- Strict layer separation: `interfaces/` → `application/` → `adapters/` → storage. No layer skips permitted.
- All DuckDB access goes through `DuckDBRepository` (`adapters/duckdb/repository.py`). No raw DuckDB calls in application or interface code.
- Single-owner DuckDB process: one process holds the exclusive write lock and serves HTTP + runs the refresh scheduler as a daemon thread. CLI admin commands require stopping the owner first.
- Dirty-queue read model: writes to `activities`/`streams` enqueue rows into `metric_dirty_activities`; the materializer computes pre-aggregated facts asynchronously.
- Registry-owned schema slice: `activity_metric_facts` table DDL and late additive column SQL are rendered from `metric_registry.py`; `schema.py` keeps the explicit migration allowlist and unsafe-DDL guard.
- All services return `ServiceEnvelope` (data + freshness + completeness + warnings + rationale) — a uniform contract for both MCP and CLI consumers.

## Layers

**Interfaces Layer:**
- Purpose: Expose product services to external consumers (MCP clients, operator CLI)
- Location: `src/mcp_strava/interfaces/`, `src/mcp_strava/cli.py`
- Contains: FastMCP tool registrations, HTTP security guards, response caching, CLI command dispatcher
- Depends on: `application/` services, `types.py`, `settings.py`
- Used by: MCP clients (Hermes, Claude Desktop), operator shell

**Application Layer:**
- Purpose: Compose repository reads into `ServiceEnvelope` responses; no business logic touching raw API or SQL
- Location: `src/mcp_strava/application/`
- Contains: metric services, product fact bundles, aggregate services, freshness assembly, and mirror coverage; root-level `metric_registry.py` provides shared registry metadata consumed by application and adapters
- Depends on: `adapters/duckdb/` (read via `ReadConn`/`DuckDBRepository`), `metrics.py`, `training.py`, `hr_zones.py`
- Used by: interfaces layer only

**Adapters Layer:**
- Purpose: Isolate all external I/O (DuckDB storage, Strava HTTP API) behind clean boundaries
- Location: `src/mcp_strava/adapters/duckdb/`, `src/mcp_strava/adapters/strava/`
- Contains: repository (all SQL), connection management, schema DDL, materializer, StravaClient facade, transport chain (OAuth → rate-limit → HTTP)
- Depends on: `settings.py`, `types.py`, `constants.py`, `duckdb` package, stdlib `urllib`
- Used by: application layer (reads), refresh pipeline (writes)

**Core Utilities (package root):**
- Purpose: Pure functions and domain types shared across all layers
- Location: `src/mcp_strava/` (root-level modules)
- Contains: `metrics.py`, `training.py`, `hr_zones.py`, `cardiac_drift.py`, `sports.py`, `constants.py`, `metric_registry.py`, `types.py`, `settings.py`
- Depends on: stdlib only (no adapters, no application layer)
- Used by: all other layers

**Refresh Pipeline:**
- Purpose: Background maintenance of the Strava mirror — fetch from API, store to DuckDB, trigger read-model materialization
- Location: `src/mcp_strava/refresh/`
- Contains: worker (polling loop), runtime (stage orchestrator), _sync_ops (atomic fetch operations), bootstrap, policy, checkpoints, health
- Depends on: `adapters/strava/`, `adapters/duckdb/`, `settings.py`
- Used by: `deploy/service.py` (daemon thread), `sync.py` (CLI), `cli.py` (admin catchup)

**Deploy Layer:**
- Purpose: Container lifecycle: preflight validation, single-owner process startup, state file
- Location: `src/mcp_strava/deploy/`
- Contains: `entrypoint.py` (preflight + exec), `service.py` (thread refresh + serve MCP), `preflight.py`, `healthcheck.py`, `smoke.py`
- Depends on: `interfaces/`, `refresh/worker`, `deploy/preflight`
- Used by: Docker container CMD

## Data Flow

### MCP Tool Request (read path)

1. FastMCP receives HTTP request → dispatches to registered tool handler (`interfaces/mcp_http.py:build_mcp_server`)
2. Tool handler calls application service (e.g., `get_fitness_state_service`) wrapped in `_run_logged_tool` or `_run_cached_logged_tool`
3. Application service opens `ReadConn` (thread-local cached connection) → `DuckDBRepository.from_connection(conn)`
4. Repository executes parameterized SQL queries against fact tables (`activity_metric_facts`, `training_model_daily`, `rolling_period_facts`)
5. Service assembles `ServiceEnvelope` with data + `FreshnessMetadata` + `CompletenessMetadata` + warnings
6. MCP layer serializes via `dc_to_dict(envelope, round_floats=True)` and returns structured JSON

### Refresh Pipeline (write path)

1. `deploy/service.py` starts daemon thread → `refresh/worker.run_forever()`
2. Worker polls every N seconds → `run_pending_once()` → `_run_pending_cycle()`
3. Cycle checks `refresh_state` and `refresh_requests` → determines if refresh or stream backfill is due
4. `refresh_runtime.run_once()` executes stages in order: SUMMARIES → STREAMS → DETAILS → SCHEMA_VALIDATE → READ_MODEL_MATERIALIZE → KUDOS
5. Each stage in `refresh/_sync_ops.py` fetches from Strava API via `StravaTransport` and writes to DuckDB via `DuckDBRepository`
6. On each write (`upsert_activity_summary`, `update_activity_detail`), repository auto-enqueues dirty row into `metric_dirty_activities`
7. Worker calls `_materialize_dirty_read_model()` → `read_model_materializer` computes per-activity metric facts → upserts into fact tables

### OAuth Token Chain

1. `StravaTransport` calls `token_provider.get_token()`
2. `FileTokenProvider` reads token file; if expired, calls `TokenRefreshTransport.refresh()`
3. `TokenRefreshTransport` POSTs to Strava OAuth endpoint with client_id + client_secret
4. New token written back to token file; returned to transport for Authorization header

### Admin CLI Command

1. Operator runs `python -m mcp_strava admin catchup` → `cli.py:cmd_catchup()`
2. CLI acquires `MirrorConn` (fails with `MirrorDbLocked` if owner process is running)
3. Calls `backfill_activities(since=...)` → `refresh_runtime.run_catchup()`
4. Then calls `refresh_runtime.run_stream_channel_catchup()` for missing stream data
5. Results serialized to JSON or human-readable table

**State Management:**
- All persistent state in DuckDB mirror at `settings.database_path` (default `/runtime/data/strava.duckdb`)
- `refresh_state` table: last success, lease owner, checkpoint stage, backoff_until
- `refresh_requests` table: queued refresh triggers from MCP signal_first_use
- `metric_dirty_activities` table: dirty queue for read-model materialization
- Settings: singleton frozen `Settings` cached per env-var fingerprint; reset via `reset_settings_cache()`

## Key Abstractions

**`ServiceEnvelope`:**
- Purpose: Uniform response wrapper for all product services
- Definition: `src/mcp_strava/types.py`
- Fields: `data`, `freshness: FreshnessMetadata`, `completeness: CompletenessMetadata`, `warnings: list[ServiceWarning]`, `rationale: list[ServiceRationale]`
- Pattern: All application services return `ServiceEnvelope`; MCP layer calls `dc_to_dict(envelope, round_floats=True)`

**`DuckDBRepository`:**
- Purpose: Single point of contact for all DuckDB reads and writes
- Definition: `src/mcp_strava/adapters/duckdb/repository.py`
- Pattern: Context manager (`with DuckDBRepository.from_path(p) as repo`); explicit `begin()`/`commit()`/`rollback()`; process RLock acquired on transaction open
- Factory methods: `from_path(db_path)`, `from_connection(conn)`

**`MirrorConn` / `ReadConn`:**
- Purpose: Scoped DuckDB connection management
- Definition: `src/mcp_strava/adapters/duckdb/connection.py`
- `MirrorConn`: opens exclusive connection (write/admin), closes on `__exit__`; raises `MirrorDbLocked` if another process holds the file
- `ReadConn`: thread-local cached read connection; evicts on exception

**`StravaClient`:**
- Purpose: Facade for all Strava API interactions; single transport wiring path
- Definition: `src/mcp_strava/adapters/strava/client.py`
- Methods: `api_request(path) -> (data, rate_headers)`, `refresh_token() -> str`
- Injection seam: accepts `transport` parameter for test/guard injection without real credentials

**`RefreshPolicy`:**
- Purpose: Configurable parameters for refresh loop (interval, batch sizes, limits)
- Definition: `src/mcp_strava/refresh/policy.py`
- Source: `RefreshPolicy.from_settings(settings)` reads `settings.refresh.*`

**`Stage` enum:**
- Purpose: Ordered pipeline stage names with checkpoint semantics
- Definition: `src/mcp_strava/refresh/checkpoints.py`
- Values: `SUMMARIES`, `STREAMS`, `DETAILS`, `SCHEMA_VALIDATE`, `READ_MODEL_MATERIALIZE`, `KUDOS`, `COMPLETE`, `STREAMS_BACKFILL`, `DETAILS_BACKFILL`, `STREAM_CHANNELS_BACKFILL`

## Entry Points

**Container (production):**
- Location: `src/mcp_strava/deploy/entrypoint.py`
- Triggers: Docker CMD (`python -m mcp_strava.deploy.entrypoint`)
- Responsibilities: DB preflight validation → `os.execvp` into `deploy/service.py`

**Service process:**
- Location: `src/mcp_strava/deploy/service.py`
- Triggers: invoked by entrypoint; starts refresh daemon thread, then calls `mcp_http.main()`

**MCP HTTP server:**
- Location: `src/mcp_strava/interfaces/mcp_http.py`
- Triggers: `app.run(transport="streamable-http")` inside `mcp_http.main()`
- Exposes tools: `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, `project_fitness_state`, `get_training_aggregates`
- Exposes prompts: `strava_daily_training_brief`, `strava_weekly_training_digest`, `strava_shoe_mileage_watchdog`

**Operator CLI:**
- Location: `src/mcp_strava/cli.py` (dispatched from `__main__.py`)
- Triggers: `python -m mcp_strava <command>`
- User commands: `report daily`, `weekly`, `workouts recent`, `workout analyze`, `freshness`
- Admin commands: `admin catchup`, `admin compact`, `admin sql`, `admin mirror-coverage`, `admin log`, `admin db-check`

**Refresh worker (standalone):**
- Location: `src/mcp_strava/refresh/worker.py`
- Triggers: `python -m mcp_strava.refresh.worker [--once]`; disabled for live DuckDB runtime (owner process runs it in-thread)

## Architectural Constraints

- **DuckDB single-owner:** DuckDB allows only one writer process. The `deploy/service.py` owner holds the exclusive lock; CLI admin commands (`MirrorConn`) will raise `MirrorDbLocked` if the owner is running. Use `just admin <cmd>` which stops the container first.
- **Threading:** Single-owner process uses two threads: FastMCP worker threads (each with its own `ReadConn`) and one daemon refresh thread. The process-level `_DUCKDB_PROCESS_LOCK` (RLock) serializes all write operations across threads.
- **Global state:** `_CACHED_SETTINGS` dict in `settings.py` (env-var keyed singleton); `_TOOL_RESPONSE_CACHE` dict in `interfaces/mcp_http.py` (30 s TTL, 32-entry LRU); `_thread_state` threading.local in `connection.py`; `_DUCKDB_PROCESS_LOCK` RLock in `connection.py`.
- **Circular imports:** Refresh bootstrap imports `adapters/strava/__init__` which re-exports `_build_strava_transport`. Application services import from `adapters/duckdb` but not from `refresh/` or `interfaces/`.
- **Read-model opt-in:** If `activity_source_state` table does not exist (schema migration not applied), all read-model paths return empty/unavailable gracefully via `_read_model_enabled()` check.

## Anti-Patterns

### Calling `MirrorConn` while the owner process is running

**What happens:** Opening a second DuckDB write connection raises `MirrorDbLocked`.
**Why it's wrong:** DuckDB enforces exclusive write access per file; a second writer corrupts the DB or fails loudly.
**Do this instead:** Use `ReadConn` for read-only application code; use `just admin <cmd>` for write admin operations (stops the owner container, runs the command, restarts).

### Bypassing `DuckDBRepository` with raw `conn.execute()`

**What happens:** Code in `cli.py:cmd_sql()` and `cmd_log()` uses `MirrorConn` + raw `conn.execute()` directly.
**Why it's wrong:** Bypasses the process RLock and semantic hash logic; should only be done for operator-facing diagnostic queries.
**Do this instead:** All non-diagnostic reads and writes go through `DuckDBRepository` methods.

### Adding application logic inside `interfaces/mcp_http.py`

**What happens:** Tool handlers would contain metric computation or SQL queries.
**Why it's wrong:** Breaks the layer contract; MCP layer must remain a thin delegation to `application/` services.
**Do this instead:** Add a new function in `application/metric_services.py` or `application/product_facts.py` and call it from the tool handler.

## Error Handling

**Strategy:** Fail-closed with structured error surfacing.

**Patterns:**
- `StravaUnavailable` exception hierarchy in `adapters/strava/types.py`; translated to rate-limit sentinel dicts or `RuntimeError` at `StravaClient` boundary
- `MirrorDbLocked` raised by `connection.py`; caught in `cli.py:cmd_admin()` with operator hint
- Refresh failures written to `refresh_state.backoff_until` and `sync_log`; operator-visible via `admin log`
- All MCP tool calls wrapped in `_run_logged_tool()` which emits structured JSON `mcp_tool_call_failed` event to stderr before re-raising
- Application services populate `ServiceEnvelope.warnings` and `completeness.missing` rather than raising for soft data gaps

## Cross-Cutting Concerns

**Logging:** Structured JSON to stdout/stderr via `print(json.dumps({...}), flush=True)`. Event key is always `"event"`. Worker emits `refresh_ok`, `refresh_failed`, `refresh_idle`, `stream_backfill_*`, `read_model_materialize_*`, `mirror_storage`. MCP layer emits `mcp_tool_call_started`, `mcp_tool_call_finished`, `mcp_tool_call_failed` with `duration_ms`, `warning_codes`, `data_shape`.

**Validation:** Settings validated at load time (env vars) and at HTTP startup (`validate_http_settings`). DB validated at container start via `deploy/preflight.py`. No runtime input validation framework — callers rely on Python type hints and explicit checks.

**Authentication:** Strava OAuth via file-backed token (`token_path` setting). MCP HTTP uses DNS rebinding protection + allowed_hosts/allowed_origins allowlists via `TransportSecuritySettings`. No user authentication on MCP surface (assumed local/trusted network).

---

*Architecture analysis: 2026-06-01*
