<!-- GSD:project-start source:PROJECT.md -->
## Project

**mcp-strava**

mcp-strava is a local Strava mirror and training analytics service for one primary user. It is a service-shaped Python codebase with core training logic, a DuckDB primary-storage repository, a Strava API adapter, and separate CLI and HTTP MCP control surfaces.

The long-term shape is a Docker-packaged local MCP server connected to the user's local MCP network. The MCP surface should expose workouts, analytics, reports, and recommendations, not operational sync/admin controls.

**Core Value:** Preserve the local Strava mirror and keep trusted training analytics working while the service is refactored into clean core, repository, adapter, CLI, and MCP boundaries.

### Constraints

- **Data preservation**: The DuckDB mirror `data/strava.duckdb` must not be deleted or overwritten during refactor; schema work requires backup/preflight/verification.
- **Rate limits**: Strava API calls are expensive and rate-limited; avoid plans that require full resync unless explicitly approved.
- **MCP boundary**: MCP exposes workouts, analytics, reports, and recommendations only; operational sync/admin/debug capabilities stay below the MCP surface.
- **Sync policy**: The local mirror should refresh automatically at least once per day; request-time freshness checks belong in core/application logic, not in MCP tool design.
- **Deployment target**: Future runtime should fit Docker and the local MCP gateway/network, but the first milestone should establish clean service boundaries before full rollout.
- **Local-first security**: Default HTTP serving must be local/container-network safe and avoid public unauthenticated exposure.
- **Testing**: Existing behavior must remain verifiable with `just test`; new boundaries need targeted tests for repositories, migrations, freshness, and MCP tools.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.14+ - Runtime code in `src/mcp_strava/` (package layout), with package metadata in `pyproject.toml`.
- Bash - `Justfile` task runner syntax and shell execution.
## Runtime
- CPython 3.14, packaged for a Docker container runtime.
- Single-owner DuckDB process serving MCP over HTTP with an in-process mirror-refresh scheduler (`deploy/service.py`).
- Dependencies are declared in `pyproject.toml` and managed with `uv`.
## Frameworks
- `mcp` (`mcp>=1.27.1,<1.28`) - MCP SDK powering the HTTP tool surface in `interfaces/mcp_http.py`.
- `duckdb` (`duckdb>=1.5.3,<1.6`) - Embedded analytical database; the only runtime storage engine.
- `PyYAML` (`PyYAML>=6.0.2,<7`) - Reference/config parsing.
- `pytest` (dev/test extra) - Test framework; tests live in `tests/`.
- `uv` - Dependency and execution manager (`uv run ...`).
- `just` - Local command runner defined in `Justfile`.
## Key Dependencies
- `duckdb` - Local persistence and analytical queries via `src/mcp_strava/adapters/duckdb/` against `data/strava.duckdb`.
- `mcp` - Server framework exposing the read-only product tool surface.
- `urllib` (stdlib) - HTTP client for Strava OAuth and API requests in the Strava adapter and `sync.py`.
- `json`, `dataclasses`, `typing` (stdlib) - Serialization and typed data contracts across `cli.py`, `db.py`, `sync.py`, and `types.py`.
- Local filesystem state - `.env` for secrets/config, `data/strava.duckdb` for the DuckDB mirror, and `references/` for supporting research notes.
## Configuration
- Typed settings resolve from environment variables in `src/mcp_strava/settings.py` (cached `Settings`).
- Storage path: `MCP_STRAVA_DB_PATH` (default `data/strava.duckdb`; canonical container path `/runtime/data/strava.duckdb`).
- Other keys: `MCP_STRAVA_TOKEN_PATH`, `MCP_STRAVA_RUNTIME_PROFILE`, HTTP binding (`MCP_STRAVA_HTTP_HOST/PORT`, `MCP_STRAVA_ALLOW_CONTAINER_BIND`, `MCP_STRAVA_ALLOWED_HOSTS/ORIGINS`), freshness (`MCP_STRAVA_FRESHNESS_WARN/MAX_AGE_HOURS`), and refresh (`MCP_STRAVA_REFRESH_INTERVAL_SECONDS`, batch sizes).
- Required Strava auth variables: `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`, `STRAVA_ACCESS_TOKEN`; token refresh persists updated values back to the token file.
- `Justfile` defines the local command surface; `just test` runs `uv run pytest -q`.
- `.gitignore` excludes `.env` and `data/` database files.
## Platform Requirements
- Python 3.14+ with `uv` available.
- Writable `data/` directory for the DuckDB mirror file.
- Network access to `https://www.strava.com` for token refresh and API calls.
- Docker runtime for the packaged MCP service; CLI commands also run directly against the local checkout.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Module files are lower-case with underscores, for example `src/mcp_strava/constants.py`, `src/mcp_strava/training.py`, and `tests/test_read_model_queries.py`.
- Code is organized as the importable package `mcp_strava` under `src/`; imports use absolute paths such as `from mcp_strava.adapters.duckdb.repository import DuckDBRepository`.
- Use `snake_case` for all functions and helpers, for example `calc_banister()`, `refresh_token()`, and `repository_from_path()`.
- CLI command handlers follow the `cmd_*` prefix, for example `cmd_report()`, `cmd_workouts()`, and `cmd_admin()`.
- Private helpers use a leading underscore, for example `_db_path()`, `_open_storage_connection()`, and `_run_logged_tool()`.
- Module-level constants use `UPPER_CASE`, for example `MCP_TOOL_NAMES`, `ADMIN_COMMANDS`, `COMMANDS`, and `CANONICAL_DUCKDB_RUNTIME_PATH`.
- Use `PascalCase` for dataclasses and classes, for example `Settings`, `DbConn`, `DuckDBRepository`, and `StravaActivity`.
- Shared type names live in `src/mcp_strava/types.py` as the data contract between modules.
## Code Style
- Standard Python formatting; no repo-local formatter config is enforced.
- Imports are grouped standard library first, then `mcp_strava` package imports.
- Docstrings and section dividers separate CLI, core training/metrics, adapter, and service responsibilities.
- Prefer small, domain-named functions over deep class hierarchies.
- Keep orchestration thin at the edges (CLI, MCP) and push computation into core/application modules.
- Use dataclasses for structured results instead of raw dicts once data crosses a module boundary.
## Import Organization
- Absolute package imports rooted at `mcp_strava` (e.g. `from mcp_strava.application import freshness`); no implicit relative imports across layers.
## Error Handling
- Hard failures raise `RuntimeError` with actionable messages in auth and API code, for example in `db.py` and the Strava adapter.
- Missing or insufficient data usually returns `None` instead of throwing, especially in metric functions such as `calc_efficiency_factor()` and `calc_hr_recovery()`.
- CLI commands print user-facing errors to `stderr` and exit non-zero on failure.
- Refresh/sync code catches transient network and HTTP problems, retries, and logs failures through `sync.py` and `refresh/`.
## Logging
- CLI command output is usually JSON on stdout.
- The service and MCP tools emit structured JSON log events (e.g. `mcp_tool_call_started`/`_finished`) to stdout.
- Progress, retries, and sync status go to stderr.
## Comments
- Comments explain domain decisions, thresholds, and rationale, not trivial syntax.
- Section headers and inline notes explain why thresholds exist and why particular data gates are applied.
- Python docstrings are the primary documentation style.
## Function Design
- Functions are generally small and single-purpose.
- CLI handlers are thin wrappers around one application service or repository call.
- Core analytics functions are pure where possible and return typed records instead of mutating shared state.
- Prefer explicit positional or keyword parameters with simple data structures.
- `conn` is the standard database handle name (a DuckDB connection).
- Dates are passed as `YYYY-MM-DD` strings or `datetime.date` objects depending on the module.
- Structured results use dataclasses from `src/mcp_strava/types.py`.
- Optional computations return `None` when data is missing or invalid rather than sentinel numeric values.
## Module Design
- Modules expose functions and dataclasses directly; layer boundaries are enforced by package structure (`adapters/`, `application/`, `interfaces/`, `deploy/`, `refresh/`).
- Shared constants live in `src/mcp_strava/constants.py`; shared types in `src/mcp_strava/types.py`.
- `db.py` is a thin facade re-exporting `DbConn`, `repository_from_connection`, `repository_from_path`, `refresh_token`, `api_request`, and `get_daily_trimp_history`.
## Practical Rules
- Keep new business logic in core/application modules, not in `cli.py`.
- Keep new result shapes in `src/mcp_strava/types.py` so downstream code stays typed and consistent.
- Keep validation gates close to the metric they protect, as in `metrics.py` and `training.py`.
- Prefer explicit, readable thresholds in `Config` over inline magic numbers.
- All persistence goes through the DuckDB adapter (`adapters/duckdb/`); never reach for another storage engine.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## System Overview
```text
Strava API ──► refresh/ + sync.py ──► DuckDB mirror (data/strava.duckdb)
                                            │
   core training/metrics ◄── application/ ◄─┤
                                            │
        CLI (cli.py) ──────────────────────┤
        MCP HTTP (interfaces/mcp_http.py) ──┘
   deploy/service.py: single-owner DuckDB process = MCP HTTP + in-process refresh scheduler
```
## Component Responsibilities
| Component | Responsibility | File |
|-----------|----------------|------|
| CLI dispatcher | Parse product + `admin` subcommands and print JSON/tabular output | `src/mcp_strava/cli.py` |
| Application services | Freshness, metric services, product facts, aggregates, mirror coverage | `src/mcp_strava/application/` |
| Core training | Banister model, progressive signal, weekly plan, forward simulation | `src/mcp_strava/training.py` |
| Core metrics | Enrichment, decoupling, HR recovery, vertical speed | `src/mcp_strava/metrics.py` |
| Drift algorithm | Pure Jenks-based cardiac drift implementation used by metrics | `src/mcp_strava/cardiac_drift.py` |
| Sports registry | Sport semantics for training/running/HR-based filtering | `src/mcp_strava/sports.py` |
| Typed contracts | Dataclasses for payloads, metrics, plans, reports, serialization | `src/mcp_strava/types.py` |
| DB facade | Thin re-export of repository factories, auth, API requests, TRIMP history | `src/mcp_strava/db.py` |
| Sync + refresh | Incremental ingest, backfill, scheduling, freshness policy | `src/mcp_strava/sync.py`, `src/mcp_strava/refresh/` |
| DuckDB adapter | Connection, schema, repository, read-model materializer, aggregate queries | `src/mcp_strava/adapters/duckdb/` |
| MCP HTTP surface | Six read-only product tools over MCP | `src/mcp_strava/interfaces/mcp_http.py` |
| Deploy/runtime | Single-owner service, preflight, runtime prep, healthcheck, entrypoint | `src/mcp_strava/deploy/` |
| Settings | Typed env-driven runtime configuration | `src/mcp_strava/settings.py` |
## Pattern Overview
- `cli.py` is a dispatcher; domain work lives in core modules and `application/`.
- `types.py` is the contract boundary between modules and JSON output.
- `adapters/duckdb/` owns all persistence; `adapters/strava/` owns Strava HTTP/auth.
- `db.py` is a thin facade over the DuckDB repository factories and Strava transport.
- `application/` orchestrates computed outputs from core primitives instead of reimplementing formulas.
- `cardiac_drift.py` keeps the expensive Jenks-based drift algorithm isolated.
- MCP exposes exactly six read-only product tools; sync/admin/debug stay below the MCP surface.
## Layers
- Purpose: expose user-facing commands and format results.
- Location: `src/mcp_strava/cli.py`
- Contains: product handlers (`cmd_report`, `cmd_weekly`, `cmd_workouts`, `cmd_workout`, `cmd_freshness`) and `cmd_admin` dispatching `ADMIN_COMMANDS` (`mirror-coverage`, `token-refresh`, `catchup`, `compact`, `sql`, `raw`, `log`, `db-preflight`, `db-check`)
- Depends on: `application/`, `db.py`, `sync.py`, `refresh/`, `types.py`
- Used by: direct CLI invocation
- Purpose: request-time orchestration and freshness gating.
- Location: `src/mcp_strava/application/` (`freshness.py`, `metric_services.py`, `product_facts.py`, `aggregate_services.py`, `mirror_coverage.py`, `registry.py`, `metric_registry.py`)
- Depends on: core modules and the DuckDB repository
- Used by: `cli.py` and `interfaces/mcp_http.py`
- Purpose: compute derived training and analytics signals.
- Location: `src/mcp_strava/training.py`, `metrics.py`, `cardiac_drift.py`, `sports.py`, `constants.py`, `types.py`
- Depends on: `types.py`, `constants.py`, `sports.py`
- Used by: application services and CLI
- Purpose: fetch Strava data, refresh tokens, ingest, and persist/query DuckDB.
- Location: `src/mcp_strava/db.py`, `sync.py`, `refresh/`, `adapters/strava/`, `adapters/duckdb/`
- Contains: `DbConn`, `repository_from_connection`, `repository_from_path`, `refresh_token`, `api_request`, `DuckDBRepository`, schema/materializer/aggregate queries, refresh scheduler
- Depends on: `duckdb`, `urllib`, `json`
- Used by: all higher-level modules needing activity history or live API calls
- Purpose: serve the read-only product surface and run the packaged service.
- Location: `src/mcp_strava/interfaces/mcp_http.py`, `src/mcp_strava/deploy/`
- Contains: `MCP_TOOL_NAMES` (`get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, `project_fitness_state`, `get_training_aggregates`), single-owner service, preflight, runtime prep, healthcheck, entrypoint
- Depends on: `mcp` SDK, application services, settings
- Used by: the Docker runtime and local MCP network
## Data Flow
### Ingest Path
- `refresh/` and `sync.py` pull from the Strava API, parse via `types.py`, and persist to `data/strava.duckdb` through the DuckDB repository; the read-model materializer maintains derived tables.
### Request Path
- CLI/MCP calls go through `application/` services that read from the DuckDB repository, apply freshness gates, and return typed/serialized results.
### State
- Persistence lives in `data/strava.duckdb` (canonical container path `/runtime/data/strava.duckdb`).
- `deploy/service.py` runs one owner DuckDB process; the refresh scheduler runs in-process.
- Per-run `RateLimiter` state and metric caches live in memory for the process lifetime.
## Key Abstractions
- Purpose: typed env-driven runtime configuration.
- Examples: `src/mcp_strava/settings.py` (`Settings`, `get_settings()`)
- Pattern: frozen dataclasses resolved from `MCP_STRAVA_*` env keys, cached per environment
- Purpose: single configuration tree for athlete profile, thresholds, and model constants.
- Examples: `src/mcp_strava/constants.py` (`Config`)
- Pattern: nested classes with eager, import-time values
- Purpose: stable schema for downstream modules and JSON output.
- Examples: `src/mcp_strava/types.py`
- Pattern: parse raw API payloads into typed objects, then serialize
- Purpose: own all persistence behind one interface.
- Examples: `src/mcp_strava/adapters/duckdb/repository.py` (`DuckDBRepository`)
- Pattern: repository over a DuckDB connection, with connection/schema/materializer helpers
- Purpose: prevent Strava API quota overruns and honor server-reported rate headers.
- Examples: `src/mcp_strava/sync.py`
- Pattern: local token bucket plus header-driven override
## Entry Points
- Location: `src/mcp_strava/cli.py`
- Triggers: `uv run python -m mcp_strava <command> [args]`
- Responsibilities: command dispatch, output formatting, process exit codes
- Location: `src/mcp_strava/deploy/service.py`
- Triggers: container entrypoint (`deploy/entrypoint.py`)
- Responsibilities: run the single-owner DuckDB process serving MCP HTTP plus the in-process refresh scheduler
- Location: `src/mcp_strava/interfaces/mcp_http.py`
- Triggers: the service process
- Responsibilities: expose the six read-only product tools over MCP HTTP
- Location: `Justfile` / `tests/`
- Triggers: `just test` → `uv run pytest -q`
- Responsibilities: run the pytest suite against `tests/`
## Architectural Constraints
- **Single-owner DuckDB:** exactly one process owns the DuckDB file; the runtime is DuckDB-only with a per-thread-connection policy. No separate child processes.
- **MCP boundary:** MCP exposes only the six read-only product tools; sync/admin/debug stay below MCP (CLI `admin` subcommands).
- **Freshness:** request-time freshness checks live in `application/freshness.py` and `refresh/`, not in MCP tool design.
- **Token storage:** `refresh_token()` writes new credentials back to the token file; it is local configuration, not a secretless cache.
- **Global state:** in-memory metric caches and `RateLimiter` counters; `Config` values bind at import time.
## Error Handling
- `sync.py`/`refresh/` retry network and HTTP failures with backoff and 429 handling.
- The Strava adapter refreshes OAuth tokens on 401 and converts token-refresh problems into actionable `RuntimeError`s.
- Application services return `None`/empty results when there is not enough data rather than inventing defaults.
- MCP tools emit structured failure events and never expose sync/admin/debug capabilities.
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
