---
analysis_date: 2026-05-22
last_mapped_commit: b207e64f8293ddb0b3432562705b96a0a0264082
---
# Architecture

**Analysis Date:** 2026-05-22

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Interfaces                                                           │
│ `src/mcp_strava/cli.py`  `src/mcp_strava/interfaces/mcp_http.py`     │
├──────────────────────────────────────────────────────────────────────┤
│ Application services                                                  │
│ `src/mcp_strava/application/*`                                       │
├──────────────────────────────────────────────────────────────────────┤
│ Domain and refresh orchestration                                      │
│ `src/mcp_strava/{metrics,training,analytics,report,trends,refresh}`  │
├──────────────────────────────────────────────────────────────────────┤
│ Adapters and infrastructure                                           │
│ `src/mcp_strava/adapters/*`  `src/mcp_strava/db.py`  `src/mcp_strava/sync.py`
├──────────────────────────────────────────────────────────────────────┤
│ Runtime and deployment helpers                                        │
│ `src/mcp_strava/deploy/*`  `deploy/*`                                │
└──────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| CLI dispatcher | Exposes legacy operator commands, product commands, and maintenance gates | `src/mcp_strava/cli.py` |
| MCP HTTP server | Exposes the read-only tool surface over streamable HTTP | `src/mcp_strava/interfaces/mcp_http.py` |
| Product services | Builds service envelopes for workouts, reports, freshness, and comparisons | `src/mcp_strava/application/*` |
| Service registry | Whitelists the product services exposed to future dispatch | `src/mcp_strava/application/registry.py` |
| SQLite repository | Owns all read/write SQL against the local mirror | `src/mcp_strava/adapters/sqlite/repository.py` |
| SQLite safety gate | Validates schema, integrity, backups, and migration parity | `src/mcp_strava/adapters/sqlite/{schema,migrations,backup}.py` |
| Strava adapter | Handles OAuth refresh, rate limits, HTTP transport, and token files | `src/mcp_strava/adapters/strava/*` |
| Refresh runtime | Runs staged daily refresh and backfill orchestration with leases | `src/mcp_strava/refresh/*` |
| Domain analytics | Computes metrics, training models, reports, and trend output | `src/mcp_strava/{metrics,training,analytics,report,trends}.py` |
| Deployment helpers | Validates runtime DB and prepares container state | `src/mcp_strava/deploy/*` and `deploy/*` |

## Pattern Overview

**Overall:** layered service-envelope architecture with a read-only MCP surface and a compatibility CLI on top of shared application services.

**Key Characteristics:**
- `ServiceEnvelope`, `FreshnessMetadata`, `CompletenessMetadata`, `ServiceWarning`, and `ServiceRationale` are the public service contract in `src/mcp_strava/types.py`.
- Interface code stays thin: `src/mcp_strava/cli.py` and `src/mcp_strava/interfaces/mcp_http.py` delegate to application services instead of recomputing analytics.
- IO is isolated behind adapters: SQLite access lives in `src/mcp_strava/adapters/sqlite/`, Strava HTTP and OAuth live in `src/mcp_strava/adapters/strava/`.
- Refresh is explicit and staged: `src/mcp_strava/refresh/runtime.py` coordinates summaries, streams, details, schema validation, and kudos with a DB lease.

## Layers

**Interface layer**
- Purpose: expose operator and MCP entry points.
- Location: `src/mcp_strava/cli.py`, `src/mcp_strava/interfaces/mcp_http.py`, `src/mcp_strava/__main__.py`.
- Contains: command dispatch, JSON rendering, MCP tool registration, transport security checks.
- Depends on: application services, settings, refresh runtime, repository helpers.
- Used by: `python -m mcp_strava`, `python -m mcp_strava.interfaces.mcp_http`.

**Application layer**
- Purpose: assemble product-ready payloads from repository rows and analytics primitives.
- Location: `src/mcp_strava/application/`.
- Contains: workout listings, workout detail, daily report, weekly summary, freshness metadata, period comparison, fitness-state projection, metric registry.
- Depends on: `SQLiteRepository`, `DbConn`, `RefreshPolicy`, `metrics.py`, `training.py`, `analytics.py`, `report.py`, `settings.py`.
- Used by: CLI product commands and MCP tools.

**Domain/computation layer**
- Purpose: compute training signals, summaries, and derived metrics.
- Location: `src/mcp_strava/{metrics,training,analytics,report,trends,cardiac_drift}.py`.
- Contains: TRIMP, Banister model, ACWR, progressive signal, workout enrichment, drift detection, weekly digest, daily report, and trend calculations.
- Depends on: `src/mcp_strava/constants.py`, `src/mcp_strava/types.py`, `src/mcp_strava/adapters/sqlite/repository.py`.
- Used by: application services and legacy CLI commands.

**Refresh orchestration layer**
- Purpose: run the staged mirror refresh and backfill flows.
- Location: `src/mcp_strava/refresh/`.
- Contains: `RefreshPolicy`, freshness evaluation, checkpoint stages, runtime lease handling, and sync step helpers.
- Depends on: SQLite repository, Strava transport, token refresh transport, settings.
- Used by: `src/mcp_strava/sync.py`, `src/mcp_strava/cli.py`, deployment maintenance commands.

**Adapter/infrastructure layer**
- Purpose: isolate SQLite and Strava integrations from business logic.
- Location: `src/mcp_strava/adapters/sqlite/`, `src/mcp_strava/adapters/strava/`, `src/mcp_strava/db.py`, `src/mcp_strava/sync.py`.
- Contains: connection policy, repository methods, schema validation, backup/migration, OAuth token refresh, rate limiting, HTTP transport, compatibility wrappers.
- Depends on: stdlib `sqlite3`, `urllib`, `fcntl`, local `.env` token/config files.
- Used by: every higher layer that needs persistence or live Strava access.

**Deployment/runtime layer**
- Purpose: prepare, validate, and launch the containerized runtime.
- Location: `src/mcp_strava/deploy/` and `deploy/`.
- Contains: runtime DB preflight, runtime preparation, container entrypoint, MCP smoke checker, Dockerfile, compose file, gateway registration helper.
- Depends on: SQLite validation and MCP HTTP interface.
- Used by: Docker startup and gateway rollout workflows.

## Data Flow

### Primary Read Path

1. MCP tool invocation enters `src/mcp_strava/interfaces/mcp_http.py` and is registered with `FastMCP`.
2. Tool handlers call application services in `src/mcp_strava/application/` such as `get_fitness_state_service()` or `list_workouts_service()`.
3. Application services open `DbConn` or use an injected connection, wrap the result in `ServiceEnvelope`, and return JSON-safe dataclasses.
4. Repository methods in `src/mcp_strava/adapters/sqlite/repository.py` fetch activities, streams, refresh state, and load history from SQLite.
5. Domain helpers in `src/mcp_strava/{metrics,training,analytics,report}.py` enrich and aggregate the rows before they are serialized with `dc_to_dict()`.

### CLI Product Path

1. `src/mcp_strava/cli.py` dispatches commands such as `report`, `weekly`, `workouts`, `workout`, and `freshness`.
2. Product commands reuse the same application services used by the MCP surface.
3. Legacy admin commands still call `src/mcp_strava/db.py`, `src/mcp_strava/sync.py`, and the refresh runtime for sync, backfill, preflight, and migration operations.

### Refresh Path

1. `src/mcp_strava/deploy/entrypoint.py` validates the runtime DB and then starts `src/mcp_strava/interfaces/mcp_http.py`.
2. `src/mcp_strava/refresh/runtime.py` acquires a lease in `refresh_state`, checks backoff and checkpoint state, and runs staged sync work.
3. `src/mcp_strava/refresh/_sync_ops.py` fetches summaries, streams, details, schema checks, and kudos through `src/mcp_strava/adapters/strava/`.
4. `src/mcp_strava/adapters/sqlite/repository.py` persists the mirror, `src/mcp_strava/adapters/sqlite/backup.py` creates backups, and `src/mcp_strava/adapters/sqlite/migrations.py` enforces parity gates.

**State Management:**
- `src/mcp_strava/settings.py` caches resolved settings in-process and derives the runtime, freshness, and network policy from environment or `.env`.
- `src/mcp_strava/metrics.py` keeps a module-level `_hr_max_cache`.
- `src/mcp_strava/refresh/runtime.py` stores live progress in SQLite via `refresh_state` and `refresh_requests`.
- `src/mcp_strava/adapters/strava/rate_limit.py` keeps quota state in memory for the lifetime of a refresh run.

## Key Abstractions

**ServiceEnvelope**
- Purpose: carry product data plus freshness, completeness, warnings, and rationale together.
- Examples: `src/mcp_strava/types.py`, `src/mcp_strava/application/*.py`, `src/mcp_strava/interfaces/mcp_http.py`.
- Pattern: dataclass payload returned by all product services.

**SQLiteRepository**
- Purpose: own all SQLite queries and writes for the local mirror.
- Examples: `src/mcp_strava/adapters/sqlite/repository.py`.
- Pattern: explicit repository boundary with small query methods and chunked bulk writes.

**RefreshPolicy / Stage**
- Purpose: describe freshness thresholds, lease durations, and checkpoint progression.
- Examples: `src/mcp_strava/refresh/policy.py`, `src/mcp_strava/refresh/checkpoints.py`.
- Pattern: policy object plus enumerated stages for staged runtime orchestration.

**StravaTransport / FileTokenProvider / TokenRefreshTransport**
- Purpose: separate data fetch, token refresh, and token persistence.
- Examples: `src/mcp_strava/adapters/strava/transport.py`, `src/mcp_strava/adapters/strava/token_provider.py`, `src/mcp_strava/adapters/strava/token_refresh.py`.
- Pattern: injectable collaborators with fail-closed `StravaUnavailable` errors.

**Settings**
- Purpose: resolve runtime paths, HTTP bind policy, and freshness thresholds.
- Examples: `src/mcp_strava/settings.py`, `src/mcp_strava/deploy/preflight.py`.
- Pattern: immutable dataclass with cached loader and explicit validation.

## Entry Points

**Package CLI**
- Location: `src/mcp_strava/__main__.py`
- Triggers: `python -m mcp_strava`
- Responsibilities: forward to the CLI dispatcher.

**Operator CLI**
- Location: `src/mcp_strava/cli.py`
- Triggers: direct module execution or package entrypoint.
- Responsibilities: product commands, sync/admin commands, reporting, and maintenance gates.

**MCP HTTP Server**
- Location: `src/mcp_strava/interfaces/mcp_http.py`
- Triggers: `python -m mcp_strava.interfaces.mcp_http`
- Responsibilities: build a read-only `FastMCP` server and expose the five public tools.

**Runtime Preflight**
- Location: `src/mcp_strava/deploy/preflight.py`
- Triggers: container health check, startup validation, runtime validation commands.
- Responsibilities: fail closed if the SQLite mirror is missing or structurally invalid.

**Runtime Prep**
- Location: `src/mcp_strava/deploy/prepare_runtime.py`
- Triggers: operator preparation step for the live Docker runtime.
- Responsibilities: copy or back up the live DB, write `live.env`, and validate the target mirror.

## Architectural Constraints

- **Threading:** the main application path is synchronous; no async runtime or worker queue exists outside the MCP SDK client smoke helper.
- **Global state:** `src/mcp_strava/metrics.py` caches HR max, `src/mcp_strava/settings.py` caches resolved settings, and `src/mcp_strava/adapters/strava/rate_limit.py` keeps in-memory quota state.
- **Circular imports:** `src/mcp_strava/constants.py` imports sport helpers at module end after `Config` is defined; keep that ordering intact.
- **Local-only exposure:** `src/mcp_strava/interfaces/mcp_http.py` rejects unsafe bind settings unless the profile explicitly allows container binding.
- **Data safety:** `src/mcp_strava/adapters/sqlite/migrations.py` always backs up before migration and rechecks parity after the write.

## Anti-Patterns

### Fat Edge Handler

**What happens:** business logic is reimplemented in `src/mcp_strava/cli.py` or `src/mcp_strava/interfaces/mcp_http.py` instead of using the application layer.
**Why it's wrong:** it duplicates enrichment and freshness logic, increases drift between CLI and MCP responses, and makes testing harder.
**Do this instead:** add or extend a service in `src/mcp_strava/application/` and have the edge handler call it.

### Unsafe Mirror Mutation

**What happens:** the live mirror is edited without a preflight, backup, or parity check.
**Why it's wrong:** this can destroy the local Strava mirror or leave it structurally inconsistent.
**Do this instead:** route changes through `src/mcp_strava/adapters/sqlite/{schema,migrations,backup}.py` or the deployment helpers in `src/mcp_strava/deploy/`.

### MCP Admin Leakage

**What happens:** operational commands are surfaced as MCP tools.
**Why it's wrong:** the MCP surface is intended to be read-only and product-focused.
**Do this instead:** keep sync, backfill, DB maintenance, and debug flows below the MCP boundary in `src/mcp_strava/cli.py` and `src/mcp_strava/deploy/`.

## Error Handling

**Strategy:** fail closed on IO boundaries, return typed `None`/partial completeness when data is missing, and convert external failures into product-safe reasons.

**Patterns:**
- `StravaUnavailable` in `src/mcp_strava/adapters/strava/types.py` normalizes network, auth, and rate-limit failures.
- `src/mcp_strava/deploy/preflight.py` and `src/mcp_strava/adapters/sqlite/schema.py` raise `RuntimeError` when the mirror is invalid.
- `src/mcp_strava/cli.py` prints user-facing failures to stderr and exits non-zero for sync and maintenance commands.
- Product services keep usable payloads and annotate missing data through `CompletenessMetadata` and warnings.

## Cross-Cutting Concerns

**Logging:** CLI command output is mostly stdout JSON or compact text, while sync and maintenance failures write to stderr.
**Validation:** `src/mcp_strava/settings.py`, `src/mcp_strava/interfaces/mcp_http.py`, and `src/mcp_strava/deploy/preflight.py` validate runtime policy before serving traffic.
**Authentication:** `src/mcp_strava/adapters/strava/token_provider.py` owns the token file, while `src/mcp_strava/adapters/strava/token_refresh.py` owns OAuth refresh.
**Freshness:** every product service builds freshness metadata from the local mirror before returning data.

---

*Architecture analysis: 2026-05-22*
