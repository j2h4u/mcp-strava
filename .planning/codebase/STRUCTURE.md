---
analysis_date: 2026-06-01
last_mapped_commit: d16b5fd
scope: full-repo
---
# Codebase Structure

**Analysis Date:** 2026-06-01

## Directory Layout

```
mcp-strava/
├── src/mcp_strava/           # Main package
│   ├── adapters/             # External I/O adapters (DuckDB, Strava API)
│   │   ├── duckdb/           # DuckDB storage adapter
│   │   └── strava/           # Strava HTTP adapter (transport, OAuth)
│   ├── application/          # Application services (product logic, metric assembly)
│   ├── deploy/               # Container lifecycle (entrypoint, service, preflight)
│   ├── devtools/             # Developer tooling (MCP test client)
│   │   └── mcp_client/
│   ├── interfaces/           # External-facing interfaces (MCP HTTP server)
│   ├── maintenance/          # Admin operations (compact)
│   ├── refresh/              # Background mirror refresh pipeline
│   ├── __init__.py           # Package exports (Settings, get_settings, load_settings)
│   ├── __main__.py           # `python -m mcp_strava` dispatcher → cli.main()
│   ├── api_schema.py         # API schema definitions
│   ├── cardiac_drift.py      # Pure cardiac drift computation
│   ├── cli.py                # Operator CLI dispatcher (all commands)
│   ├── constants.py          # Config class: zone coefficients, sport lists
│   ├── hr_zones.py           # HR zone bound computation
│   ├── mcp_content.py        # Prompt file loader
│   ├── metrics.py            # Pure metric computation functions
│   ├── settings.py           # Typed Settings dataclass, env-var loader
│   ├── sports.py             # Sport type classification helpers
│   ├── strava_api_reference.py  # Strava API field documentation
│   ├── sync.py               # Public refresh API (backfill_activities, sync_activities)
│   ├── training.py           # Training model: fitness/fatigue/form forward_simulate
│   └── types.py              # Shared data contracts (StravaActivity, ServiceEnvelope, ...)
├── tests/                    # Test suite
│   ├── fixtures/             # Fake MCP server and other test fixtures
│   ├── conftest.py           # Shared pytest fixtures
│   ├── _fixtures_duckdb.py   # DuckDB fixture helpers
│   └── test_*.py             # Test modules (34 files)
├── deploy/                   # Docker deployment files
│   ├── docker-compose.yml    # Container orchestration
│   ├── Dockerfile            # Image definition
│   ├── .dockerignore
│   └── gateway_register.py   # MCP gateway registration script
├── mcp-content/
│   └── prompts/              # MCP prompt markdown files
│       ├── strava_daily_training_brief.md
│       ├── strava_weekly_training_digest.md
│       └── strava_shoe_mileage_watchdog.md
├── docs/
│   ├── private/              # Coach/sports-medicine notes (not for CI)
│   ├── sport/                # Domain research docs (cardiac drift, cross-activity)
│   └── tech/                 # Technical docs (deployment, kudos API)
├── data/
│   └── backups/              # DB backup storage (gitignored)
├── skills/                   # Project-local agent skills
├── .planning/                # GSD planning artifacts
│   ├── codebase/             # Codebase map documents (this directory)
│   ├── phases/               # Phase plan + summary files
│   ├── quick/                # Quick task files
│   ├── debug/                # Debugging session notes
│   └── config.json           # GSD configuration
├── Justfile                  # Developer task runner (just admin compact, etc.)
├── pyproject.toml            # Package metadata, dependencies, tool config
└── .env                      # Local env overrides (gitignored)
```

## Directory Purposes

**`src/mcp_strava/adapters/duckdb/`:**
- Purpose: All DuckDB access — connection management, schema DDL, repository (read/write), materializer, aggregate queries
- Key files: `connection.py` (MirrorConn, ReadConn, RLock), `repository.py` (DuckDBRepository — all SQL methods), `schema.py` (DUCKDB_SCHEMA_SQL, table/column constants), `read_model_materializer.py` (dirty-queue processor), `aggregate_queries.py` (status fact and window queries)

**`src/mcp_strava/adapters/strava/`:**
- Purpose: Strava HTTP API client — transport chain (OAuth → rate-limit → HTTP), token management
- Key files: `client.py` (StravaClient facade, `_build_strava_transport` wiring), `transport.py` (HTTP), `token_provider.py` (file-backed OAuth), `token_refresh.py` (OAuth refresh), `rate_limit.py` (RateLimitPolicy), `clock.py` (SystemClock/SystemSleeper), `types.py` (StravaUnavailable, Clock, Sleeper protocols)

**`src/mcp_strava/application/`:**
- Purpose: Product-facing services — all reads from DuckDB fact tables assembled into `ServiceEnvelope`
- Key files: `metric_services.py` (fitness state, workouts, period comparison, projection), `product_facts.py` (daily brief, weekly digest, historical fact bundles), `aggregate_services.py` (bucketed time-series), `freshness.py` (freshness metadata), `mirror_coverage.py` (stream coverage report)
- Note: `metric_registry.py` (METRIC_REGISTRY, AGGREGATE_METRIC_BUNDLES, STATUS_FACT_REGISTRY) lives at the package root (`src/mcp_strava/metric_registry.py`), not under `application/` — it is core schema imported by both application and adapters

**`src/mcp_strava/deploy/`:**
- Purpose: Container startup and lifecycle
- Key files: `entrypoint.py` (container CMD: preflight → exec service), `service.py` (owner process: thread refresh worker + serve MCP), `preflight.py` (DB existence + schema validation), `healthcheck.py` (liveness probe), `smoke.py` (post-start smoke test)

**`src/mcp_strava/refresh/`:**
- Purpose: Background pipeline that keeps the DuckDB mirror in sync with Strava
- Key files: `worker.py` (polling loop, `run_forever`, `run_pending_once`), `runtime.py` (`run_once`, `run_catchup`, `run_stream_channel_catchup` — stage orchestration), `_sync_ops.py` (atomic fetch and write operations per stage), `bootstrap.py` (collaborator wiring), `policy.py` (RefreshPolicy), `checkpoints.py` (Stage enum), `health.py` (cycle health tracking), `freshness.py` (refresh freshness query)

**`src/mcp_strava/interfaces/`:**
- Purpose: MCP HTTP server — tool and prompt registration, security enforcement, response caching
- Key files: `mcp_http.py` (FastMCP server, all tool handlers, `build_mcp_server`, `validate_http_settings`)

**`src/mcp_strava/maintenance/`:**
- Purpose: Admin maintenance operations
- Key files: `compact.py` (`compact_database`, `storage_stats`)

**`src/mcp_strava/devtools/mcp_client/`:**
- Purpose: Developer tool for testing MCP surface manually
- Key files: `client.py`, `cli.py`

**`tests/`:**
- Purpose: Full test suite — unit, integration, contract, and E2E tests against in-memory or fixture DuckDB
- Key files: `conftest.py` (shared fixtures), `_fixtures_duckdb.py` (DuckDB test helpers), `fixtures/fake_mcp_server.py` (MCP server fixture)

**`deploy/`:**
- Purpose: Docker container definition and compose configuration
- Note: `docker-compose.yml` lives here (not in `/opt/docker/`) because this is a build-from-source project; runtime data and secrets live in `/opt/docker/mcp-strava/`

**`mcp-content/prompts/`:**
- Purpose: Markdown prompt templates loaded by `mcp_content.py` and served via MCP `@server.prompt()`

## Key File Locations

**Entry Points:**
- `src/mcp_strava/__main__.py`: `python -m mcp_strava` dispatches to `cli.main()`
- `src/mcp_strava/deploy/entrypoint.py`: container CMD entry, runs preflight then execs service
- `src/mcp_strava/deploy/service.py`: owner process (threads refresh + HTTP)
- `src/mcp_strava/interfaces/mcp_http.py`: FastMCP server definition and `main()`
- `src/mcp_strava/refresh/worker.py`: standalone refresh worker `main()`

**Configuration:**
- `src/mcp_strava/settings.py`: `Settings`, `get_settings()`, `load_settings()`, all env-var keys
- `pyproject.toml`: package metadata, ruff/pyright config, test config
- `deploy/docker-compose.yml`: container runtime configuration

**Core Logic:**
- `src/mcp_strava/adapters/duckdb/repository.py`: all DuckDB reads/writes (2295 lines)
- `src/mcp_strava/cli.py`: all operator commands
- `src/mcp_strava/application/metric_services.py`: primary MCP tool backends
- `src/mcp_strava/refresh/runtime.py`: refresh stage orchestration
- `src/mcp_strava/refresh/_sync_ops.py`: individual sync operations
- `src/mcp_strava/types.py`: shared data contracts
- `src/mcp_strava/metrics.py`: pure metric computation

**Schema:**
- `src/mcp_strava/adapters/duckdb/schema.py`: static schema, `DUCKDB_TABLES`, `DATE_COLUMNS`, and additive migration policy; `activity_metric_facts` column SQL is generated from `src/mcp_strava/metric_registry.py`

**Testing:**
- `tests/conftest.py`: shared fixtures (in-memory DuckDB, settings overrides)
- `tests/_fixtures_duckdb.py`: DuckDB-specific test helpers

## Naming Conventions

**Files:**
- `snake_case.py` for all Python modules
- `_sync_ops.py`: leading underscore signals internal-only module (not public API)
- `test_<subject>.py` for test files, colocated in `tests/` (not next to source)

**Directories:**
- `snake_case` for all package directories
- Layer names match architecture: `adapters/`, `application/`, `interfaces/`, `deploy/`, `refresh/`, `maintenance/`

**Classes:**
- `PascalCase`: `DuckDBRepository`, `StravaClient`, `ServiceEnvelope`, `RefreshPolicy`, `MirrorConn`, `ReadConn`
- `PascalCase` for dataclasses: `Settings`, `AthleteSettings`, `HttpSettings`, `RefreshResult`, `RefreshSkipped`

**Functions and variables:**
- `snake_case` for all functions and variables
- `_prefixed` for module-private helpers: `_build_strava_transport`, `_run_pending_cycle`, `_emit`
- `cmd_*` prefix for CLI command handler functions in `cli.py`

**Constants:**
- `UPPER_SNAKE_CASE`: `DUCKDB_TABLES`, `CURRENT_METRIC_VERSION`, `PRODUCT_SERVICE_NAMES`, `MCP_TOOL_NAMES`

**Type aliases:**
- `Row = dict[str, Any]` in `repository.py`

## Where to Add New Code

**New MCP tool:**
1. Add application service function in `src/mcp_strava/application/metric_services.py` (or new file in `application/` for distinct domain)
2. Register tool in `src/mcp_strava/interfaces/mcp_http.py` inside `build_mcp_server()` using `@server.tool()`
3. Add to `MCP_TOOL_NAMES` tuple in `interfaces/mcp_http.py`
4. Add to `PRODUCT_SERVICES` dict in `application/registry.py` if CLI-accessible
5. Tests: `tests/test_mcp_surface.py` (MCP contract) + `tests/test_application_services.py` (service logic)

**New CLI command:**
1. Add `cmd_<name>(args)` function in `src/mcp_strava/cli.py`
2. Register in `COMMANDS` or `ADMIN_COMMANDS` dict at bottom of `cli.py`
3. Tests: `tests/test_cli_surface.py`

**New metric computation:**
1. Pure function with no DuckDB/Strava dependency → `src/mcp_strava/metrics.py` or new root-level module
2. If stored in `activity_metric_facts` → add SQL metadata to `src/mcp_strava/metric_registry.py`; `adapters/duckdb/schema.py` consumes the generated DDL/add-column SQL and keeps the safety policy
3. Update materializer in `adapters/duckdb/read_model_materializer.py`, add repository fetch/query methods as needed, and add aggregate metadata if the metric is exposed through aggregate tools
4. Tests: `tests/test_metrics_pure.py` for pure functions; `tests/test_read_model_materialization.py` and `tests/test_schema_drift.py` for materializer/schema behavior

**New DuckDB read query:**
1. Add method to `DuckDBRepository` in `src/mcp_strava/adapters/duckdb/repository.py`
2. Use `self._fetchall()` or `self._fetchone()` (never raw `conn.execute()` outside the repo)
3. Tests: `tests/test_duckdb_repository.py`

**New adapter (external service):**
1. Create `src/mcp_strava/adapters/<service>/` directory with `__init__.py`
2. Follow strava adapter pattern: client facade + transport + types
3. Wire into settings if config needed

**New refresh pipeline stage:**
1. Add `Stage` value to `src/mcp_strava/refresh/checkpoints.py`
2. Add sync operation in `src/mcp_strava/refresh/_sync_ops.py`
3. Insert stage into `_DAILY_STAGE_ORDER` or `_BACKFILL_STAGE_ORDER` in `src/mcp_strava/refresh/runtime.py`
4. Tests: `tests/test_refresh_runtime.py`

**New settings key:**
1. Add env-var name to `_KEYS` set in `src/mcp_strava/settings.py`
2. Add field to appropriate sub-settings dataclass (`AthleteSettings`, `HttpSettings`, etc.)
3. Wire default and parsing in `load_settings()` / `_build_settings()`

**Utilities:**
- Shared pure helpers with no I/O: `src/mcp_strava/` root level (alongside `metrics.py`, `hr_zones.py`)
- Test helpers shared across test files: `tests/conftest.py` or `tests/_fixtures_duckdb.py`

## Special Directories

**`.planning/`:**
- Purpose: GSD planning artifacts — phase plans, summaries, codebase maps, debug notes
- Generated: Partially (phase summaries generated by GSD)
- Committed: Yes

**`data/backups/`:**
- Purpose: DB backup files created by `maintenance/compact.py` before compaction
- Generated: Yes (by compact command)
- Committed: No (gitignored)

**`deploy/`:**
- Purpose: Docker deployment definition; lives in-repo because image is built from source
- Generated: No
- Committed: Yes

**`mcp-content/prompts/`:**
- Purpose: Prompt markdown files loaded at runtime by `mcp_content.py`; registered as MCP prompts
- Generated: No
- Committed: Yes — prompt changes require a container rebuild

**`skills/`:**
- Purpose: Project-local agent skills available to GSD commands
- Generated: No
- Committed: Yes

> Note: the former `src/mcp_strava/adapters/sqlite/` adapter was removed in commit `22b7045` (Phase 08) when the project migrated to DuckDB. No SQLite source remains in the tree.

---

*Structure analysis: 2026-06-01*
