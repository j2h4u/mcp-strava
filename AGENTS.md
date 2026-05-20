<!-- GSD:project-start source:PROJECT.md -->
## Project

**mcp-strava**

mcp-strava is a local Strava mirror and training analytics service for one primary user. Today it is a Python CLI over a SQLite database populated from Strava; this project refactors it into a service-shaped codebase with core training logic, a SQLite repository, a Strava API adapter, and separate CLI and HTTP MCP control surfaces.

The long-term shape is a Docker-packaged local MCP server connected to the user's local MCP network. The MCP surface should expose workouts, analytics, reports, and recommendations, not operational sync/admin controls.

**Core Value:** Preserve the local Strava mirror and keep trusted training analytics working while the service is refactored into clean core, repository, adapter, CLI, and MCP boundaries.

### Constraints

- **Data preservation**: Existing `data/strava.db` must not be deleted or overwritten during refactor; schema work requires backup/preflight/verification.
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
- Python 3.13.5 - All runtime code in `scripts/strava_lib/*.py`, the CLI in `scripts/cli.py`, and smoke tests in `tests/test_smoke.py`.
- Bash - `Justfile` task runner syntax and shell execution.
## Runtime
- CPython 3.13.5 in this workspace.
- Standard-library-only runtime; imports under `scripts/` and `tests/` are `sqlite3`, `urllib.request`, `json`, `dataclasses`, `typing`, and other stdlib modules.
- Not detected.
- No `requirements.txt`, `pyproject.toml`, `poetry.lock`, `Pipfile`, or other Python lockfile is present.
- Execution is driven directly with `python3` and `just`.
## Frameworks
- None detected.
- The codebase uses a custom package layout under `scripts/strava_lib/` instead of a web or app framework.
- None detected.
- Verification uses the custom runner in `scripts/run_tests.py` with tests in `tests/test_smoke.py`; `pytest` is intentionally not the primary entrypoint.
- `just` - Local command runner defined in `Justfile`.
- `python3` - Direct script execution for CLI and tests.
## Key Dependencies
- `sqlite3` (stdlib) - Local persistence layer used by `scripts/strava_lib/db.py` against `data/strava.db`.
- `urllib.request` / `urllib.error` / `urllib.parse` (stdlib) - Direct HTTP client for Strava OAuth and API requests in `scripts/strava_lib/db.py` and `scripts/strava_lib/sync.py`.
- `json` (stdlib) - Serialization for API payloads, DB blobs, and CLI output across `scripts/cli.py`, `scripts/strava_lib/db.py`, `scripts/strava_lib/sync.py`, and `scripts/strava_lib/types.py`.
- Local filesystem state - `.env` for secrets/config, `data/strava.db` for SQLite persistence, and `references/` for supporting research notes.
- `dataclasses` / `typing` (stdlib) - Data contracts in `scripts/strava_lib/types.py` and `scripts/strava_lib/api_schema.py`.
## Configuration
- Environment variables are loaded manually from `.env` in `scripts/strava_lib/db.py::load_env()`.
- Token refresh writes updated values back to `.env` in `scripts/strava_lib/db.py::save_env()`.
- Required Strava auth variables: `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`, `STRAVA_ACCESS_TOKEN`.
- `Justfile` defines the local command surface.
- `scripts/run_tests.py` is the verification harness.
- `.gitignore` excludes `.env` and `data/*.db*`.
## Platform Requirements
- Python 3.13.x with access to the repo checkout.
- Writable `data/` directory for SQLite files.
- Network access to `https://www.strava.com` for token refresh and API calls.
- No separate deployment target is detected.
- The code runs as a local CLI process against a checked-in repo plus local SQLite state.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Module files are lower-case with underscores, for example `scripts/strava_lib/constants.py`, `scripts/strava_lib/training.py`, `scripts/strava_lib/report.py`, and `tests/test_smoke.py`.
- The only top-level executable entrypoints in this repo are plain Python scripts such as `scripts/cli.py` and `scripts/run_tests.py`.
- Use `snake_case` for all functions and helpers, for example `calc_banister()`, `calc_weekly_plan()`, `refresh_token()`, and `load_tests()`.
- Command handlers in `scripts/cli.py` follow the `cmd_*` prefix, for example `cmd_activities()`, `cmd_sync()`, and `cmd_report()`.
- Private helpers use a leading underscore, for example `_fetch_with_retry()`, `_form_zone()`, `_sim_one_day()`, and `_decoupling_invalid()`.
- Use `snake_case` for locals and module variables, for example `daily_trimp`, `alpha_fitness`, `after_param`, and `_hr_max_cache`.
- Module-level constants use `UPPER_CASE`, for example `DB_PATH`, `ENV_PATH`, `STREAM_KEYS`, and `COMMANDS`.
- Use `PascalCase` for dataclasses and classes, for example `Config`, `DbConn`, `StravaActivity`, `WeeklyPlan`, and `DailyReport`.
- Type names live in `scripts/strava_lib/types.py` and are used as the shared data contract between modules.
## Code Style
- The codebase uses standard Python formatting with no repo-local formatter config detected.
- Imports are grouped by standard library first, then local `strava_lib` imports, as seen in `scripts/cli.py`, `scripts/strava_lib/report.py`, and `scripts/strava_lib/metrics.py`.
- Section dividers and docstrings are used heavily to separate CLI, model, analytics, and sync responsibilities.
- Prefer small, domain-named functions over deep class hierarchies.
- Keep orchestration thin at the edge and push computation into `scripts/strava_lib/*.py`.
- Use dataclasses for structured results instead of raw dicts once data crosses a module boundary.
## Import Organization
- Not detected. Imports use direct package paths such as `from strava_lib.constants import Config`.
## Error Handling
- Hard failures raise `RuntimeError` with actionable messages in auth and API code, for example `scripts/strava_lib/db.py` in `refresh_token()` and `api_request()`.
- Missing or insufficient data usually returns `None` instead of throwing, especially in metric functions such as `calc_efficiency_factor()`, `calc_hr_recovery()`, and `calc_vertical_speed()`.
- CLI commands print user-facing errors to `stderr` and exit non-zero on failure, as in `scripts/cli.py` and `scripts/strava_lib/sync.py`.
- Sync code catches transient network and HTTP problems, retries, and logs failures to `sync_log` in `data/strava.db` through `scripts/strava_lib/sync.py`.
## Logging
- Command output is usually JSON on stdout.
- Progress, retries, and sync status go to stderr in `scripts/strava_lib/sync.py`.
- Success and failure indicators are text-based and intentionally minimal, for example `✓` and `✗` in `cmd_log()` in `scripts/cli.py`.
## Comments
- Comments explain domain decisions, thresholds, and rationale, not trivial syntax.
- Section headers and inline notes are used to explain why metrics were removed, why thresholds exist, and why particular data gates are applied.
- Comments often mention the business reason for a rule, for example the steady-state requirement in `scripts/strava_lib/metrics.py` or the training-signal rationale in `scripts/strava_lib/report.py`.
- Not used. Python docstrings are the primary documentation style.
## Function Design
- Functions are generally small and single-purpose.
- CLI handlers in `scripts/cli.py` are thin wrappers around one query or one library call.
- Core analytics functions in `scripts/strava_lib/*.py` are pure where possible and return typed records instead of mutating shared state.
- Prefer explicit positional or keyword parameters with simple data structures.
- `conn` is the standard database handle name.
- Dates are usually passed as `YYYY-MM-DD` strings or `datetime.date` objects depending on the module.
- Structured results use dataclasses from `scripts/strava_lib/types.py`.
- Optional computations return `None` when data is missing or invalid rather than sentinel numeric values.
- CLI handlers print their output instead of returning it.
## Module Design
- Modules expose functions and dataclasses directly; `scripts/strava_lib/__init__.py` is empty and does not act as a barrel file.
- Shared constants live in `scripts/strava_lib/constants.py`, and shared types live in `scripts/strava_lib/types.py`.
- Not used.
## Practical Rules
- Keep new business logic in `scripts/strava_lib/`, not in `scripts/cli.py`.
- Keep new result shapes in `scripts/strava_lib/types.py` so downstream code stays typed and consistent.
- Keep validation gates close to the metric they protect, as in `scripts/strava_lib/metrics.py` and `scripts/strava_lib/training.py`.
- Prefer explicit, readable thresholds in `Config` over inline magic numbers.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## System Overview
```text
```
## Component Responsibilities
| Component | Responsibility | File |
|-----------|----------------|------|
| CLI dispatcher | Parse subcommands and print JSON or tabular output | `scripts/cli.py` |
| Sync pipeline | Incremental Strava ingest, backfill, kudos sync, rate limiting | `scripts/strava_lib/sync.py` |
| Database/auth layer | SQLite lifecycle, `.env` token refresh, API requests, TRIMP history queries | `scripts/strava_lib/db.py` |
| Typed contracts | Dataclasses for API payloads, metrics, plans, reports, and serialization | `scripts/strava_lib/types.py` |
| Sports registry | Sport semantics for training/running/HR-based filtering | `scripts/strava_lib/sports.py` |
| Metrics layer | Activity enrichment, decoupling, cardiac drift, HR recovery, vertical speed | `scripts/strava_lib/metrics.py` |
| Drift algorithm | Pure Jenks-based cardiac drift implementation used by metrics | `scripts/strava_lib/cardiac_drift.py` |
| Training layer | Banister model, progressive signal, weekly plan, forward simulation | `scripts/strava_lib/training.py` |
| Weekly analytics | Rolling window load/efficiency summaries and trend output | `scripts/strava_lib/analytics.py` |
| Daily report | 14-day panorama, ACWR, recommendation, safety warnings | `scripts/strava_lib/report.py` |
| Trend analysis | Weekly form/TiZ/crash-rate output | `scripts/strava_lib/trends.py` |
| Schema validation | Machine-readable Strava payload contract checks | `scripts/strava_lib/api_schema.py` |
| Human API reference | Field map and endpoint notes for Strava payloads | `scripts/strava_lib/strava_api_reference.py` |
| Smoke runner | Import and behavior smoke checks without pytest dependency | `scripts/run_tests.py` |
## Pattern Overview
- `scripts/cli.py` stays as a dispatcher; domain work lives in `scripts/strava_lib/*.py`.
- `types.py` is the contract boundary between modules and JSON output.
- `db.py` owns all Strava HTTP access, auth refresh, and SQLite connection details.
- `report.py`, `analytics.py`, and `training.py` orchestrate computed outputs from shared primitives instead of reimplementing formulas.
- `cardiac_drift.py` keeps the expensive Jenks-based drift algorithm isolated from the rest of the data model code.
- `api_schema.py` and `strava_api_reference.py` are adjacent validation/reference layers, not part of the hot path.
## Layers
- Purpose: expose user-facing commands and format results.
- Location: `scripts/cli.py`
- Contains: `cmd_activities`, `cmd_sync`, `cmd_report`, `cmd_weekly`, `cmd_trend`, `cmd_stats`, `cmd_gear`, `cmd_sql`, `cmd_log`, `cmd_kudos`
- Depends on: `db.py`, `sync.py`, `training.py`, `analytics.py`, `report.py`, `trends.py`, `types.py`
- Used by: direct CLI invocation
- Purpose: compute derived training and analytics signals.
- Location: `scripts/strava_lib/metrics.py`, `scripts/strava_lib/training.py`, `scripts/strava_lib/analytics.py`, `scripts/strava_lib/report.py`, `scripts/strava_lib/trends.py`, `scripts/strava_lib/cardiac_drift.py`
- Contains: enrichment, Banister EWMA, progressive signal, weekly plan, rolling windows, recommendation logic, Jenks-based drift clustering
- Depends on: `types.py`, `constants.py`, `sports.py`, `db.py`
- Used by: `cli.py`, smoke tests, and neighboring modules
- Purpose: fetch Strava data, refresh tokens, and persist/query SQLite.
- Location: `scripts/strava_lib/db.py`, `scripts/strava_lib/sync.py`
- Contains: `DbConn`, `init_db`, `refresh_token`, `api_request`, `sync_activities`, `backfill_activities`
- Depends on: standard library `sqlite3`, `urllib`, `json`, `os`
- Used by: all higher-level modules that need activity history or live API calls
- Purpose: centralize schemas, dataclasses, and sport semantics.
- Location: `scripts/strava_lib/types.py`, `scripts/strava_lib/constants.py`, `scripts/strava_lib/sports.py`
- Contains: dataclass models, SQL fragments, sport-type registry, serializer helper
- Depends on: each other in a one-way order (`constants.py` imports `sports.py`)
- Used by: every computation module and CLI output path
- Purpose: describe Strava response shape and detect schema drift.
- Location: `scripts/strava_lib/api_schema.py`, `scripts/strava_lib/strava_api_reference.py`
- Contains: endpoint schemas, unknown-key detection, Summit-field checks, human-readable field catalog
- Depends on: `strava_api_reference.py` as the human source and `api_schema.py` as the machine-readable representation
- Used by: review tooling and future validation work; not wired into the current runtime path
## Data Flow
### Primary Request Path: Daily Report
### Ingest Path: Sync
### Analytics Paths
- Local persistence lives in `data/strava.db` with WAL sidecars `data/strava.db-wal` and `data/strava.db-shm`.
- `scripts/strava_lib/metrics.py` keeps a module-level `_hr_max_cache`.
- `scripts/strava_lib/sync.py` keeps per-run `RateLimiter` state in memory.
- `scripts/strava_lib/constants.py` attaches SQL fragments to `Config.SQL` at import time.
## Key Abstractions
- Purpose: single configuration tree for athlete profile, thresholds, model constants, and SQL fragments.
- Examples: `scripts/strava_lib/constants.py:17`
- Pattern: nested classes with eager, import-time values
- Purpose: stable schema for downstream modules and JSON output.
- Examples: `scripts/strava_lib/types.py:293`, `scripts/strava_lib/types.py:498`
- Pattern: parse raw API payloads into typed objects, then serialize via `dc_to_dict()`
- Purpose: encode sport semantics once and reuse them across analytics, planning, and filtering.
- Examples: `scripts/strava_lib/sports.py:23`
- Pattern: central registry plus helper predicates like `is_training()` and `is_running()`
- Purpose: create short-lived SQLite connections with WAL mode and row access by column name.
- Examples: `scripts/strava_lib/db.py:21`
- Pattern: context manager around `sqlite3.connect(..., check_same_thread=False)`
- Purpose: prevent Strava API quota overruns and honor server-reported rate headers.
- Examples: `scripts/strava_lib/sync.py:21`
- Pattern: local token bucket plus header-driven override
## Entry Points
- Location: `scripts/cli.py:325`
- Triggers: `python3 scripts/cli.py <command> [args]`
- Responsibilities: command dispatch, output formatting, process exit codes
- Location: `scripts/run_tests.py:25`
- Triggers: `python3 scripts/run_tests.py`
- Responsibilities: load `tests/test_smoke.py`, execute all `test_*` functions, report pass/fail
- Location: `tests/test_smoke.py:29`
- Triggers: `scripts/run_tests.py` or manual import
- Responsibilities: verify imports, pure functions, daily report path, and registry behavior
- Location: `Justfile`
- Triggers: `just test`
- Responsibilities: forward to the smoke runner
## Architectural Constraints
- **Threading:** synchronous single-process CLI. No async runtime, queue worker, or background service is present.
- **SQLite access:** `DbConn` uses WAL and `check_same_thread=False`, but the commands run as short-lived one-shot processes.
- **Global state:** module-level `_hr_max_cache` in `metrics.py`, `Config.SQL` late binding in `constants.py`, and `RateLimiter` counters in `sync.py`.
- **Circular imports:** no active cycle is required for runtime flow. `constants.py` imports `sports.py` after `Config` is defined, then attaches SQL fragments.
- **Token storage:** `refresh_token()` writes new credentials back to `.env`; the file is local configuration, not a secretless cache.
- **Validation boundary:** `api_schema.py` exists as a validation layer, but current runtime commands do not call it.
## Anti-Patterns
### Fat CLI
### Raw Dict Leakage
## Error Handling
- `sync.py` retries network and HTTP failures with backoff and 429 handling.
- `db.py` refreshes OAuth tokens on 401 and converts token-refresh problems into actionable `RuntimeError`s.
- `report.py` and `analytics.py` return `None` when there is not enough data rather than inventing defaults.
- `cli.py` wraps sync commands with traceback printing and a last-chance sync_log write.
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
