---
analysis_date: 2026-05-26
last_mapped_commit: ab203ab
analysis_scope:
  - README.md
  - mcp-content/
  - tests/
---
<!-- refreshed: 2026-05-26 -->
# Architecture

**Analysis Date:** 2026-05-26

## System Overview

```text
+-----------------------------------------------------------------------+
| Assistant and operator contract                                       |
| `README.md`  `mcp-content/prompts/*.md`                               |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
| Interface surfaces                                                    |
| `src/mcp_strava/interfaces/mcp_http.py`  `src/mcp_strava/cli.py`       |
| verified by `tests/test_mcp_surface.py` and `tests/test_cli_surface.py`|
+---------------------+-------------------------------+-----------------+
                      |                               |
                      v                               v
+--------------------------------------+  +-----------------------------+
| Product application services          |  | Admin and refresh controls  |
| `src/mcp_strava/application/*`         |  | `src/mcp_strava/refresh/*`  |
| verified by `tests/test_metric_*`      |  | verified by `tests/test_*`  |
+---------------------+----------------+  +--------------+--------------+
                      |                                  |
                      v                                  v
+-----------------------------------------------------------------------+
| Repository and adapter boundaries                                      |
| `src/mcp_strava/adapters/duckdb/*`  `src/mcp_strava/adapters/sqlite/*` |
| `src/mcp_strava/adapters/strava/*`  `src/mcp_strava/db.py`             |
+---------------------+-------------------------------------------------+
                      |
                      v
+-----------------------------------------------------------------------+
| Local mirror, read model, prompts, and runtime state                    |
| `/runtime/data/strava.duckdb`  `data/strava.duckdb`  `mcp-content/`    |
+-----------------------------------------------------------------------+
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| README contract | Documents the local Strava mirror, MCP boundary, Docker usage, runtime state, and Strava credential workflow | `README.md` |
| Prompt content | Provides agent-facing scenarios without adding new MCP tools or admin access | `mcp-content/prompts/strava_daily_training_brief.md`, `mcp-content/prompts/strava_weekly_training_digest.md`, `mcp-content/prompts/strava_shoe_mileage_watchdog.md` |
| MCP HTTP interface | Builds the read-only FastMCP server, tool schemas, prompt registrations, structured output, and transport security | `src/mcp_strava/interfaces/mcp_http.py`, verified by `tests/test_mcp_surface.py` |
| CLI interface | Separates product commands from namespaced admin commands and renders service envelopes as JSON/text | `src/mcp_strava/cli.py`, verified by `tests/test_cli_surface.py` and `tests/test_security_guards.py` |
| Product service registry | Keeps product-service names distinct from admin/debug/sync operations | `src/mcp_strava/application/registry.py`, verified by `tests/test_cli_surface.py` and `tests/test_security_guards.py` |
| Metric services | Own workout listing/detail, fitness state, period comparison, and projection product services | `src/mcp_strava/application/metric_services.py`, verified by `tests/test_metric_services.py` and `tests/test_application_workouts.py` |
| Product fact services | Own daily brief, weekly digest, and historical fact bundle services | `src/mcp_strava/application/product_facts.py`, verified by `tests/test_product_fact_bundles.py` and `tests/test_application_reports.py` |
| Aggregate services | Serve registry-backed aggregate rows and scenario bundles through `get_training_aggregates` | `src/mcp_strava/application/aggregate_services.py`, verified by `tests/test_training_aggregates.py` |
| Metric registry | Defines metric ids, aggregate modes, supported buckets/scopes/windows, and tool exposure | `src/mcp_strava/application/metric_registry.py`, verified by `tests/test_metric_registry.py` |
| Freshness service | Builds mirror and read-model freshness metadata and first-use refresh requests | `src/mcp_strava/application/freshness.py`, verified by `tests/test_application_services.py` |
| DuckDB repository | Owns the primary runtime repository path, serialized DuckDB access, read-model queries, and aggregate query support | `src/mcp_strava/adapters/duckdb/repository.py`, verified by `tests/test_duckdb_repository.py`, `tests/test_duckdb_concurrency_guards.py`, and `tests/test_metric_services.py` |
| SQLite repository and migrations | Preserve migration input, fixture support, backup/preflight safety, and compatibility repository behavior | `src/mcp_strava/adapters/sqlite/repository.py`, `src/mcp_strava/adapters/sqlite/migrations.py`, verified by `tests/test_sqlite_safety.py` and `tests/test_repository_boundary.py` |
| DuckDB cutover | Converts SQLite mirror state into the canonical DuckDB runtime file with parity, cast, backup, and rollback reports | `src/mcp_strava/adapters/duckdb/migrations.py`, verified by `tests/test_duckdb_migration.py` |
| Refresh runtime | Runs staged daily refresh, backfill, stream-channel backfill, leases, checkpoints, and read-model materialization | `src/mcp_strava/refresh/*`, verified by `tests/test_refresh_runtime.py` |
| Strava adapter | Owns token refresh, rate-limit policy, HTTP transport, and normalized Strava failures | `src/mcp_strava/adapters/strava/*`, verified by `tests/test_strava_adapter.py` |
| Deployment runtime | Validates and prepares the Docker runtime before serving MCP over HTTP | `src/mcp_strava/deploy/*`, `deploy/*`, verified by `tests/test_docker_runtime.py` |
| MCP test client | Provides stdio/HTTP smoke, tool-list assertions, product bundle smoke, and warm latency gates | `src/mcp_strava/devtools/mcp_client/*`, verified by `tests/test_mcp_test_client.py` and `tests/test_mcp_latency_gate.py` |

## Pattern Overview

**Overall:** read-only product MCP architecture over a local Strava mirror, with product application services sharing typed `ServiceEnvelope` output across CLI and MCP while refresh, migration, SQL, token, and sync controls stay below the MCP boundary.

**Key Characteristics:**
- `tests/test_mcp_surface.py` pins the MCP tool allowlist to `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, `project_fitness_state`, and `get_training_aggregates` from `src/mcp_strava/interfaces/mcp_http.py`.
- `tests/test_mcp_surface.py` pins prompt names to files under `mcp-content/prompts/` and verifies prompt content does not expose implementation paths or expand the tool surface in `src/mcp_strava/interfaces/mcp_http.py`.
- `tests/test_cli_surface.py` and `tests/test_security_guards.py` enforce a product/admin split in `src/mcp_strava/cli.py`; add product behavior through `src/mcp_strava/application/*` and keep admin behavior under the `admin` command namespace.
- `tests/test_metric_services.py`, `tests/test_training_aggregates.py`, and `tests/test_product_fact_bundles.py` show product services return `src/mcp_strava/types.py` service envelopes with `data`, `freshness`, `completeness`, `warnings`, and `rationale`.
- `tests/test_repository_boundary.py` and `tests/test_security_guards.py` enforce repository access through `src/mcp_strava/adapters/sqlite/*`, `src/mcp_strava/adapters/duckdb/*`, and `src/mcp_strava/db.py` instead of direct storage calls from product code.
- `tests/test_refresh_runtime.py` keeps refresh implementation in `src/mcp_strava/refresh/*` independent from `src/mcp_strava/sync.py`, with compatibility entrypoints delegating into the refresh runtime.
- `tests/test_settings.py` and `tests/test_docker_runtime.py` set the canonical active DB path to DuckDB (`data/strava.duckdb` locally and `/runtime/data/strava.duckdb` in Docker) while README runtime docs also mention `/opt/docker/mcp-strava/data/strava.db`.

## Layers

**Documentation and Prompt Layer:**
- Purpose: define the operator-visible product contract and assistant scenarios.
- Location: `README.md`, `mcp-content/prompts/`.
- Contains: setup instructions, Docker smoke commands, runtime state notes, MCP boundary rules, Russian-language daily/weekly/shoe prompt scenarios.
- Depends on: MCP tool names from `src/mcp_strava/interfaces/mcp_http.py`.
- Used by: users, operators, and MCP clients; verified by `tests/test_mcp_surface.py` for prompt names/content.

**Interface Layer:**
- Purpose: accept product requests and operator commands without embedding business logic.
- Location: `src/mcp_strava/interfaces/mcp_http.py`, `src/mcp_strava/cli.py`, `src/mcp_strava/__main__.py`.
- Contains: FastMCP server construction, HTTP transport security validation, CLI command dispatch, JSON/text rendering, admin command namespace.
- Depends on: `src/mcp_strava/application/*`, `src/mcp_strava/settings.py`, `src/mcp_strava/refresh/*`, `src/mcp_strava/adapters/*`.
- Used by: Docker runtime, local CLI, `just mcp-list-tools`, `just mcp-smoke-full`, and MCP smoke clients in `tests/test_mcp_test_client.py`.

**Application Service Layer:**
- Purpose: convert repository and domain facts into stable product envelopes.
- Location: `src/mcp_strava/application/`.
- Contains: `metric_services.py`, `aggregate_services.py`, `product_facts.py`, `freshness.py`, `mirror_coverage.py`, `metric_registry.py`, `registry.py`.
- Depends on: `src/mcp_strava/types.py`, repository factories in `src/mcp_strava/db.py`, DuckDB/SQLite repositories, metric/domain modules.
- Used by: `src/mcp_strava/interfaces/mcp_http.py` and `src/mcp_strava/cli.py`; verified by `tests/test_metric_services.py`, `tests/test_product_fact_bundles.py`, `tests/test_application_services.py`, `tests/test_application_reports.py`, and `tests/test_application_workouts.py`.

**Metric Registry and Read-Model Layer:**
- Purpose: keep MCP facts registry-backed, materialized, explainable, and bounded by supported product scopes.
- Location: `src/mcp_strava/application/metric_registry.py`, `src/mcp_strava/adapters/duckdb/read_model_materializer.py`, `src/mcp_strava/adapters/sqlite/read_model_materializer.py`, `src/mcp_strava/adapters/duckdb/aggregate_queries.py`.
- Contains: metric definitions, aggregate modes, product bundles, materialized fact table/column registries, supported bucket/scope/window allowlists, query column allowlists.
- Depends on: DuckDB/SQLite schemas in `src/mcp_strava/adapters/*/schema.py` and repository query methods.
- Used by: `get_training_aggregates` in `src/mcp_strava/application/aggregate_services.py` and all metric-service completeness metadata; verified by `tests/test_metric_registry.py`, `tests/test_read_model_queries.py`, `tests/test_read_model_materialization.py`, and `tests/test_training_aggregates.py`.

**Repository and Storage Adapter Layer:**
- Purpose: isolate mirror reads/writes, migrations, read-model queries, and storage-specific concurrency behavior.
- Location: `src/mcp_strava/adapters/duckdb/`, `src/mcp_strava/adapters/sqlite/`, `src/mcp_strava/db.py`.
- Contains: DuckDB connection helpers, DuckDB repository, SQLite repository, SQLite migration/backup/preflight, DuckDB cutover, `DbConn`, and `repository_from_connection`.
- Depends on: `duckdb`, stdlib `sqlite3`, local database files under `data/` or `/runtime/data/`.
- Used by: application services, refresh runtime, deployment preflight, and tests; verified by `tests/test_duckdb_repository.py`, `tests/test_duckdb_migration.py`, `tests/test_sqlite_safety.py`, and `tests/test_repository_boundary.py`.

**Refresh and External Adapter Layer:**
- Purpose: manage Strava API synchronization, daily freshness, backfill checkpoints, and read-model materialization below the MCP surface.
- Location: `src/mcp_strava/refresh/`, `src/mcp_strava/sync.py`, `src/mcp_strava/adapters/strava/`.
- Contains: `RefreshPolicy`, staged `run_once`, `run_backfill`, `run_backfill_stream_channels`, checkpoint stages, refresh worker, token provider, rate-limit policy, Strava transport, and stream sync operations.
- Depends on: repository boundary, Strava OAuth/token file settings, rate-limit headers, `src/mcp_strava/settings.py`.
- Used by: `src/mcp_strava/cli.py` admin commands and runtime worker paths; verified by `tests/test_refresh_runtime.py`, `tests/test_strava_adapter.py`, and `tests/test_security_guards.py`.

**Deployment and Runtime Layer:**
- Purpose: run the local/container MCP service with fail-closed storage checks and owner-process HTTP smoke tests.
- Location: `deploy/`, `src/mcp_strava/deploy/`.
- Contains: Dockerfile, compose file, gateway registration helper, entrypoint, healthcheck, preflight, prepare-runtime, and smoke tools.
- Depends on: runtime settings in `src/mcp_strava/settings.py`, `src/mcp_strava/deploy/preflight.py`, `src/mcp_strava/interfaces/mcp_http.py`.
- Used by: `just test`, `just smoke`, `just mcp-smoke-full`, `just mcp-read-model-perf`; verified by `tests/test_docker_runtime.py`, `tests/test_phase01_validation.py`, and `tests/test_mcp_latency_gate.py`.

**Test Layer:**
- Purpose: preserve architecture contracts and runtime safety through executable specs.
- Location: `tests/`, `tests/fixtures/fake_mcp_server.py`.
- Contains: scoped fixture databases, MCP server/client fakes, AST guards, Docker/source contract checks, repository tests, product-surface tests, and refresh runtime tests.
- Depends on: public modules under `src/mcp_strava/`, plus selected repo files such as `pyproject.toml`, `Justfile`, `deploy/docker-compose.yml`, `docs/metrics.md`, and `.gitignore`.
- Used by: `uv run pytest -q` from `README.md` and Docker smoke commands from `README.md`.

## Data Flow

### MCP Product Read Path

1. Client calls a tool registered by `src/mcp_strava/interfaces/mcp_http.py`; the exact allowlist is asserted in `tests/test_mcp_surface.py:183`.
2. `src/mcp_strava/interfaces/mcp_http.py` delegates to `src/mcp_strava/application/metric_services.py`, `src/mcp_strava/application/aggregate_services.py`, or `src/mcp_strava/application/product_facts.py`; delegation is exercised in `tests/test_mcp_surface.py:324`.
3. Application services query `src/mcp_strava/adapters/duckdb/repository.py` or compatibility repositories through connection/factory helpers; DuckDB routing is asserted in `tests/test_repository_boundary.py:545` and `tests/test_metric_services.py:821`.
4. Read-model methods fetch materialized facts from `activity_metric_facts`, `daily_load_facts`, `training_model_daily`, and `rolling_period_facts`; index-backed hot paths are asserted in `tests/test_read_model_queries.py:451`.
5. The service returns `src/mcp_strava/types.py` `ServiceEnvelope` data with freshness, completeness, warnings, and rationale; the five-key envelope is asserted in `tests/test_mcp_surface.py:324` and `tests/test_training_aggregates.py:1020`.

### MCP Prompt Path

1. Prompt markdown lives in `mcp-content/prompts/strava_daily_training_brief.md`, `mcp-content/prompts/strava_weekly_training_digest.md`, and `mcp-content/prompts/strava_shoe_mileage_watchdog.md`.
2. `src/mcp_strava/interfaces/mcp_http.py` loads the content-backed prompts; `tests/test_mcp_surface.py:239` verifies the prompt names and that prompt exposure does not add tools.
3. Prompt instructions route agents through product tools such as `list_workouts`, `get_workout_detail`, `compare_periods`, `get_fitness_state`, `project_fitness_state`, and `get_training_aggregates`.
4. Prompt instructions explicitly keep sync, SQL, raw Strava payloads, refresh operations, admin operations, and medical diagnoses outside the prompt-level workflow.

### CLI Product Path

1. `python -m mcp_strava` reaches `src/mcp_strava/__main__.py` and command dispatch in `src/mcp_strava/cli.py`; module usage is asserted in `tests/test_phase01_validation.py:25`.
2. Product commands use `src/mcp_strava/application/product_facts.py`, `src/mcp_strava/application/metric_services.py`, and `src/mcp_strava/application/freshness.py`; routing is asserted in `tests/test_security_guards.py:122`.
3. CLI admin commands remain under `admin` in `src/mcp_strava/cli.py`; command separation is asserted in `tests/test_cli_surface.py:344`.
4. Admin storage and refresh commands call `src/mcp_strava/refresh/*`, `src/mcp_strava/adapters/sqlite/*`, `src/mcp_strava/adapters/duckdb/*`, and `src/mcp_strava/sync.py`; dry-run and safety behavior is asserted in `tests/test_cli_surface.py:364` and `tests/test_security_guards.py:230`.

### Refresh and Read-Model Materialization Path

1. Admin or worker code calls `src/mcp_strava/refresh.run_once()` or related backfill entrypoints; daily refresh behavior is asserted in `tests/test_refresh_runtime.py:153`.
2. `src/mcp_strava/refresh/runtime.py` uses `RefreshPolicy`, checkpoint stages, and repository leases stored in `refresh_state`; freshness states are asserted in `tests/test_refresh_runtime.py:506`.
3. `src/mcp_strava/refresh/_sync_ops.py` uses `src/mcp_strava/adapters/strava/*` transport objects to fetch activities, streams, details, kudos, and channel metadata; stream-channel sync is asserted in `tests/test_refresh_runtime.py:852`.
4. Repository methods persist mirror rows and dirty read-model markers in DuckDB or SQLite compatibility fixtures; repository coverage is asserted in `tests/test_repository_boundary.py:170`.
5. The refresh worker materializes dirty read-model rows through `src/mcp_strava/refresh/worker.py` and materializer functions; bounded batching is asserted in `tests/test_refresh_runtime.py:538`.

### Deployment Runtime Path

1. `deploy/docker-compose.yml` exposes container port `8080` on the Docker network without a public host port; the contract is asserted in `tests/test_docker_runtime.py:52` and `tests/test_security_guards.py:846`.
2. `deploy/Dockerfile` copies `mcp-content/` and starts `python -m mcp_strava.deploy.entrypoint`; the contract is asserted in `tests/test_docker_runtime.py:32`.
3. `src/mcp_strava/deploy/entrypoint.py` runs migration checks and preflight before exec; sequencing is asserted in `tests/test_docker_runtime.py:265` and `tests/test_docker_runtime.py:300`.
4. Owner-process smoke and latency gates call the HTTP MCP path at `http://127.0.0.1:8080/mcp`; README commands and latency gates are asserted in `README.md` and `tests/test_mcp_latency_gate.py:29`.

**State Management:**
- Runtime paths and HTTP policy are resolved by `src/mcp_strava/settings.py`; defaults and overrides are asserted in `tests/test_settings.py:8` and `tests/test_settings.py:74`.
- Refresh state, refresh requests, leases, and pending materialization live in repository tables such as `refresh_state`, `refresh_requests`, and read-model dirty queues; behavior is asserted in `tests/test_refresh_runtime.py` and `tests/test_read_model_queries.py`.
- MCP tool responses are read-only, idempotent, and structured; annotations are asserted in `tests/test_mcp_surface.py:324`.
- Expensive MCP tool responses use a short-lived response cache in `src/mcp_strava/interfaces/mcp_http.py`; behavior is asserted in `tests/test_mcp_surface.py:420`.
- Local secrets live in `.env`/token files and are ignored by git; secret policy is asserted in `tests/test_repo_hygiene.py` and output redaction is asserted in `tests/test_docker_runtime.py:578`.

## Key Abstractions

**ServiceEnvelope:**
- Purpose: product-service result envelope carrying `data`, `freshness`, `completeness`, `warnings`, and `rationale`.
- Examples: `src/mcp_strava/types.py`, `tests/test_mcp_surface.py:62`, `tests/test_training_aggregates.py:1020`.
- Pattern: application services return typed envelopes and interface layers serialize them with `dc_to_dict`.

**FreshnessMetadata and CompletenessMetadata:**
- Purpose: make mirror age, read-model status, missing metrics, unavailable facts, and warnings machine-readable.
- Examples: `src/mcp_strava/types.py`, `src/mcp_strava/application/freshness.py`, `tests/test_application_services.py:100`, `tests/test_read_model_queries.py:12`.
- Pattern: product payloads include facts and confidence limits instead of requesting sync from MCP users.

**Metric Registry:**
- Purpose: keep all exposed metrics, aggregate behavior, source tables, supported scopes, and product bundles centrally declared.
- Examples: `src/mcp_strava/application/metric_registry.py`, `tests/test_metric_registry.py:8`, `tests/test_training_aggregates.py:1020`.
- Pattern: services and materializers use registry metadata instead of handwritten tool-specific metric lists.

**AggregateServiceRequest:**
- Purpose: describe `get_training_aggregates` requests with metric ids, metric bundles, bucket, scope, sport filters, dates, and rolling windows.
- Examples: `src/mcp_strava/application/aggregate_services.py`, `tests/test_training_aggregates.py:1020`.
- Pattern: validate product parameters before repository query execution.

**Repository Boundary:**
- Purpose: isolate DuckDB and SQLite details from domain and interface code.
- Examples: `src/mcp_strava/adapters/duckdb/repository.py`, `src/mcp_strava/adapters/sqlite/repository.py`, `src/mcp_strava/db.py`, `tests/test_repository_boundary.py:517`.
- Pattern: direct SQL/storage calls outside the allowlisted adapter boundary are rejected by AST guards.

**RefreshPolicy and Stage:**
- Purpose: configure regular refresh intervals, warn/max age, stream backfill batch sizes, and checkpoint progression.
- Examples: `src/mcp_strava/refresh/*`, `tests/test_refresh_runtime.py:153`, `tests/test_refresh_runtime.py:506`.
- Pattern: refresh work proceeds through explicit checkpoint stages with leases and idempotent refresh requests.

**Strava Transport Collaborators:**
- Purpose: separate Strava data fetch, OAuth token refresh, token persistence, and rate-limit backoff from sync orchestration.
- Examples: `src/mcp_strava/adapters/strava/*`, `tests/test_strava_adapter.py`, `tests/test_refresh_runtime.py:14`.
- Pattern: tests inject fake transports; live network is forbidden in refresh runtime tests.

**MCP Prompt Files:**
- Purpose: define user-facing assistant tasks without broadening server capabilities.
- Examples: `mcp-content/prompts/strava_daily_training_brief.md`, `mcp-content/prompts/strava_weekly_training_digest.md`, `mcp-content/prompts/strava_shoe_mileage_watchdog.md`.
- Pattern: prompts call factual tools and explicitly avoid sync/admin/raw payload behavior.

## Entry Points

**Package CLI:**
- Location: `src/mcp_strava/__main__.py`
- Triggers: `python -m mcp_strava`
- Responsibilities: forward to `src/mcp_strava/cli.py`; usage contract is asserted in `tests/test_phase01_validation.py:25`.

**Operator CLI:**
- Location: `src/mcp_strava/cli.py`
- Triggers: `python -m mcp_strava <command> [args]`
- Responsibilities: product commands (`report`, `weekly`, `workouts`, `workout`, `freshness`) and namespaced `admin` commands; command split is asserted in `tests/test_security_guards.py:86` and `tests/test_cli_surface.py:344`.

**MCP HTTP Server:**
- Location: `src/mcp_strava/interfaces/mcp_http.py`
- Triggers: Docker entrypoint, `python -m mcp_strava.interfaces.mcp_http`, and MCP smoke tests.
- Responsibilities: build FastMCP server, register product tools/prompts, enforce read-only annotations, and validate local/container HTTP security; tool and prompt contracts are asserted in `tests/test_mcp_surface.py:183`.

**Refresh Runtime:**
- Location: `src/mcp_strava/refresh/runtime.py`, `src/mcp_strava/refresh/worker.py`
- Triggers: CLI admin refresh, background worker loop, periodic refresh, first-use refresh requests.
- Responsibilities: staged refresh, backfill, lease ownership, retry/backoff, read-model materialization; worker behavior is asserted in `tests/test_refresh_runtime.py:538`.

**Deployment Entrypoint:**
- Location: `src/mcp_strava/deploy/entrypoint.py`
- Triggers: Docker `ENTRYPOINT` from `deploy/Dockerfile`.
- Responsibilities: migrate when needed, run preflight, prepare DuckDB from sibling SQLite when configured, and then exec the server; sequencing is asserted in `tests/test_docker_runtime.py:265`.

**Runtime Preflight and Preparation:**
- Location: `src/mcp_strava/deploy/preflight.py`, `src/mcp_strava/deploy/prepare_runtime.py`
- Triggers: CLI/admin runtime preparation and container startup.
- Responsibilities: fail closed on missing/corrupt DBs, copy runtime DB/env safely, avoid secret output, and validate read-model readiness; behavior is asserted in `tests/test_docker_runtime.py:151` and `tests/test_docker_runtime.py:525`.

**MCP Test Client:**
- Location: `src/mcp_strava/devtools/mcp_client/cli.py`, `src/mcp_strava/devtools/mcp_client/client.py`
- Triggers: `just mcp-smoke-full`, `just mcp-read-model-perf`, test scripts, and direct CLI calls.
- Responsibilities: list tools, call tools, assert forbidden tools absent, run live smoke, and measure warm latency; behavior is asserted in `tests/test_mcp_test_client.py` and `tests/test_mcp_latency_gate.py`.

## Architectural Constraints

- **Scope:** this mapping is intentionally scoped to `README.md`, `mcp-content/`, and `tests/`; source paths under `src/mcp_strava/` are included only where those scoped files reference or verify them.
- **MCP boundary:** `src/mcp_strava/interfaces/mcp_http.py` must expose only product/factual tools and content-backed prompts; `tests/test_mcp_surface.py` rejects sync, backfill, raw SQL, token, log, debug, and admin leakage.
- **Product/admin split:** `src/mcp_strava/cli.py` keeps product commands separate from `admin` commands; `tests/test_cli_surface.py` rejects unnamespaced sync/refresh commands and verifies admin commands do not overlap `src/mcp_strava/application/registry.py`.
- **Storage ownership:** product code must use `src/mcp_strava/adapters/duckdb/*`, `src/mcp_strava/adapters/sqlite/*`, and `src/mcp_strava/db.py`; `tests/test_repository_boundary.py` and `tests/test_security_guards.py` reject direct `sqlite3.connect` outside the allowlist.
- **Runtime database:** `src/mcp_strava/settings.py` defaults to DuckDB paths (`data/strava.duckdb` locally and `/runtime/data/strava.duckdb` in container); `tests/test_settings.py` and `tests/test_docker_runtime.py` verify the contract.
- **Threading and concurrency:** DuckDB repository reads and transactions use process locks/owner-process assumptions; `tests/test_duckdb_repository.py` and `tests/test_duckdb_concurrency_guards.py` verify serialized behavior and health checks.
- **Network safety:** refresh tests patch `urllib.request.urlopen` to forbid live network access in `tests/test_refresh_runtime.py`; Strava behavior is tested through fake transports in `tests/test_strava_adapter.py`.
- **Local-first HTTP:** `src/mcp_strava/interfaces/mcp_http.py` rejects unsafe local binds unless container binding is explicitly allowed; `tests/test_mcp_surface.py` and `tests/test_security_guards.py` verify host/origin and compose-port policy.
- **Prompt discipline:** `mcp-content/prompts/*.md` instruct agents to use product tools and not request sync/admin/raw SQL/raw Strava operations; `tests/test_mcp_surface.py` verifies prompts do not expose implementation paths.

## Anti-Patterns

### Product Logic In Edge Surfaces

**What happens:** `src/mcp_strava/cli.py` or `src/mcp_strava/interfaces/mcp_http.py` computes metrics, filters raw DB rows, or assembles report semantics directly.
**Why it's wrong:** `tests/test_security_guards.py` and `tests/test_cli_surface.py` expect product commands to route through `src/mcp_strava/application/*`, keeping CLI and MCP outputs aligned.
**Do this instead:** implement product behavior in `src/mcp_strava/application/metric_services.py`, `src/mcp_strava/application/aggregate_services.py`, or `src/mcp_strava/application/product_facts.py`, then call it from the interface.

### Operational Capability In MCP

**What happens:** MCP tools, schemas, prompts, or payload fields mention sync, backfill, raw SQL, tokens, logs, debug actions, migrations, or admin controls.
**Why it's wrong:** `tests/test_mcp_surface.py`, `tests/test_mcp_test_client.py`, and `mcp-content/prompts/*.md` define MCP as read-only and factual.
**Do this instead:** keep operational capabilities in `src/mcp_strava/cli.py`, `src/mcp_strava/refresh/*`, `src/mcp_strava/deploy/*`, and `src/mcp_strava/adapters/*`.

### Direct Storage Access Outside Adapters

**What happens:** application, domain, or interface code opens SQLite/DuckDB directly or reads raw `streams`/`activities` tables for hot product requests.
**Why it's wrong:** `tests/test_repository_boundary.py` and `tests/test_read_model_queries.py` enforce repository boundaries and indexed read-model queries.
**Do this instead:** add repository methods in `src/mcp_strava/adapters/duckdb/repository.py` or compatibility methods in `src/mcp_strava/adapters/sqlite/repository.py`, then call those from application services.

### Unbounded Refresh Or Migration Work

**What happens:** refresh, backfill, or DuckDB cutover performs live-network work or storage mutation without leases, preflight, backups, parity checks, dry-run behavior, or batch limits.
**Why it's wrong:** `tests/test_refresh_runtime.py`, `tests/test_duckdb_migration.py`, `tests/test_docker_runtime.py`, and `tests/test_sqlite_safety.py` require fail-closed, resumable, bounded behavior.
**Do this instead:** route through `src/mcp_strava/refresh/runtime.py`, `src/mcp_strava/refresh/worker.py`, `src/mcp_strava/adapters/duckdb/migrations.py`, and `src/mcp_strava/deploy/preflight.py`.

## Error Handling

**Strategy:** fail closed at IO/runtime boundaries, preserve product responses with explicit completeness/freshness metadata, and normalize external failures into typed or structured errors.

**Patterns:**
- `src/mcp_strava/adapters/strava/*` uses typed Strava failure paths such as `StravaUnavailable`; behavior is verified by `tests/test_strava_adapter.py` and fake transports in `tests/test_refresh_runtime.py`.
- `src/mcp_strava/deploy/preflight.py` and `src/mcp_strava/deploy/entrypoint.py` reject missing/corrupt DBs before serving; behavior is verified by `tests/test_docker_runtime.py:151`.
- `src/mcp_strava/application/*` returns `ServiceEnvelope` payloads with `CompletenessMetadata` instead of raising for missing facts; behavior is verified by `tests/test_mcp_surface.py:578` and `tests/test_read_model_queries.py:429`.
- `src/mcp_strava/refresh/worker.py` emits structured refresh-worker errors and logs tracebacks; behavior is verified by `tests/test_refresh_runtime.py:614`.
- `src/mcp_strava/cli.py` requires explicit live-cutover confirmation and avoids constructing Strava collaborators during DuckDB cutover; behavior is verified by `tests/test_cli_surface.py:364`.

## Cross-Cutting Concerns

**Logging:** `src/mcp_strava/cli.py` and `src/mcp_strava/refresh/worker.py` emit operator output while product MCP responses stay structured; refresh-worker error events are asserted in `tests/test_refresh_runtime.py:614`.

**Validation:** `src/mcp_strava/settings.py`, `src/mcp_strava/interfaces/mcp_http.py`, `src/mcp_strava/application/metric_registry.py`, and `src/mcp_strava/deploy/preflight.py` validate settings, transport security, metric requests, and runtime DB readiness before work proceeds.

**Authentication:** `README.md` documents `.env` Strava credentials, while `src/mcp_strava/adapters/strava/*` owns token loading/refresh and `tests/test_docker_runtime.py` asserts runtime helpers do not print secret contents.

**Freshness:** `src/mcp_strava/application/freshness.py`, `src/mcp_strava/refresh/*`, and repository read-model status methods ensure product envelopes include mirror and read-model age, dirty count, and stale reasons.

**Performance:** `src/mcp_strava/devtools/mcp_client/client.py` enforces a 100 ms default warm p95 gate in `tests/test_mcp_latency_gate.py:29`, and `tests/test_read_model_queries.py:451` verifies hot read-model queries use indexes rather than scanning streams.

**Security:** `src/mcp_strava/interfaces/mcp_http.py`, `deploy/docker-compose.yml`, `.gitignore`, and `mcp-content/prompts/*.md` keep local state secret, HTTP local/container safe, and MCP read-only; contracts are verified by `tests/test_security_guards.py` and `tests/test_repo_hygiene.py`.

---

*Architecture analysis: 2026-05-26*
