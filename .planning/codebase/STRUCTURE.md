---
analysis_date: 2026-05-26
last_mapped_commit: ab203ab
analysis_scope:
  - README.md
  - mcp-content/
  - tests/
---
# Codebase Structure

**Analysis Date:** 2026-05-26

## Directory Layout

```text
mcp-strava/
├── README.md                         # Product, setup, Docker, runtime, and MCP boundary contract
├── mcp-content/                      # MCP prompt content copied into the runtime image
│   └── prompts/
│       ├── strava_daily_training_brief.md
│       ├── strava_weekly_training_digest.md
│       └── strava_shoe_mileage_watchdog.md
└── tests/                            # Architecture, storage, MCP, refresh, deployment, and product contracts
    ├── __init__.py
    ├── fixtures/
    │   └── fake_mcp_server.py
    ├── test_application_reports.py
    ├── test_application_services.py
    ├── test_application_workouts.py
    ├── test_cli_surface.py
    ├── test_docker_runtime.py
    ├── test_duckdb_concurrency_guards.py
    ├── test_duckdb_migration.py
    ├── test_duckdb_repository.py
    ├── test_full_fidelity_mirror.py
    ├── test_load_status.py
    ├── test_mcp_latency_gate.py
    ├── test_mcp_sdk_contract.py
    ├── test_mcp_surface.py
    ├── test_mcp_test_client.py
    ├── test_metric_registry.py
    ├── test_metric_services.py
    ├── test_phase01_validation.py
    ├── test_phase4_e2e.py
    ├── test_product_fact_bundles.py
    ├── test_read_model_materialization.py
    ├── test_read_model_queries.py
    ├── test_refresh_runtime.py
    ├── test_repo_hygiene.py
    ├── test_repository_boundary.py
    ├── test_security_guards.py
    ├── test_settings.py
    ├── test_smoke.py
    ├── test_sqlite_safety.py
    ├── test_strava_adapter.py
    └── test_training_aggregates.py
```

## Directory Purposes

**`README.md`:**
- Purpose: operator-facing project contract for the local Strava mirror, MCP training-metrics server, Strava OAuth setup, Docker smoke flow, runtime state, and MCP boundary.
- Contains: product summary, requirements, token setup, Docker usage, useful commands, runtime state table, Strava rate-limit notes, and read-only MCP boundary.
- Key files: `README.md`.

**`mcp-content/`:**
- Purpose: committed MCP prompt content copied into the Docker image and served by `src/mcp_strava/interfaces/mcp_http.py`.
- Contains: prompt markdown under `mcp-content/prompts/`.
- Key files: `mcp-content/prompts/strava_daily_training_brief.md`, `mcp-content/prompts/strava_weekly_training_digest.md`, `mcp-content/prompts/strava_shoe_mileage_watchdog.md`.

**`mcp-content/prompts/`:**
- Purpose: define agent workflows in Russian without changing the product tool surface.
- Contains: daily training brief, weekly training digest, and shoe mileage watchdog prompts.
- Key files: `mcp-content/prompts/strava_daily_training_brief.md`, `mcp-content/prompts/strava_weekly_training_digest.md`, `mcp-content/prompts/strava_shoe_mileage_watchdog.md`.

**`tests/`:**
- Purpose: executable architecture map and regression suite for MCP surface, CLI/admin separation, repositories, refresh runtime, DuckDB migration, read-model materialization, settings, deployment, and product payloads.
- Contains: `test_*.py` files with pytest-style tests, AST guards, DB fixtures, fake transports, product envelope assertions, and Docker source-contract checks.
- Key files: `tests/test_mcp_surface.py`, `tests/test_cli_surface.py`, `tests/test_repository_boundary.py`, `tests/test_refresh_runtime.py`, `tests/test_docker_runtime.py`, `tests/test_metric_services.py`, `tests/test_training_aggregates.py`.

**`tests/fixtures/`:**
- Purpose: test-only helpers for MCP client behavior.
- Contains: a minimal JSON-RPC MCP server that supports initialize, tool list, tool call, and failure responses.
- Key files: `tests/fixtures/fake_mcp_server.py`.

## Key File Locations

**Entry Points:**
- `README.md`: documents operator entrypoints `just test`, `just smoke`, `just mcp-smoke-full`, `just mcp-read-model-perf`, `just mcp-list-tools`, and `uv run pytest -q`.
- `tests/test_phase01_validation.py`: asserts `python -m mcp_strava` usage and that `Justfile` routes to Docker/MCP smoke commands.
- `tests/test_mcp_test_client.py`: tests `src/mcp_strava/devtools/mcp_client/cli.py` and `src/mcp_strava/devtools/mcp_client/client.py` as MCP smoke entrypoints.
- `tests/test_docker_runtime.py`: asserts `deploy/Dockerfile`, `deploy/docker-compose.yml`, `src/mcp_strava/deploy/entrypoint.py`, `src/mcp_strava/deploy/healthcheck.py`, and `src/mcp_strava/deploy/prepare_runtime.py` runtime entrypoints.

**Configuration:**
- `README.md`: documents `.env`, `/opt/docker/mcp-strava/.env`, `/opt/docker/mcp-strava/live.env`, and runtime DB paths.
- `tests/test_settings.py`: tests `src/mcp_strava/settings.py` defaults, environment overrides, `.env` compatibility, and invalid setting rejection.
- `tests/test_phase01_validation.py`: verifies `pyproject.toml` package name, Python version, setuptools `src` layout, and absence of `scripts` project entrypoints.
- `tests/test_repo_hygiene.py`: verifies `.gitignore` patterns for `.env`, `.planning/config.json`, and database state under `data/`.

**MCP Surface:**
- `mcp-content/prompts/strava_daily_training_brief.md`: daily brief prompt using `list_workouts`, `get_workout_detail`, `get_fitness_state`, and `project_fitness_state`.
- `mcp-content/prompts/strava_weekly_training_digest.md`: weekly digest prompt using `compare_periods`, `list_workouts`, `get_workout_detail`, and `get_fitness_state`.
- `mcp-content/prompts/strava_shoe_mileage_watchdog.md`: shoe mileage watchdog prompt that refuses to infer gear facts if the MCP surface lacks them.
- `tests/test_mcp_surface.py`: asserts MCP tools, prompt names, schemas, annotations, structured output, short-lived cache, float rounding, and forbidden product fields.
- `tests/test_mcp_sdk_contract.py`: checks FastMCP streamable HTTP, tool annotations, transport security settings, and streamable HTTP client APIs.

**Product Services:**
- `tests/test_application_workouts.py`: asserts `src/mcp_strava.application.workouts` is absent and `src/mcp_strava/application/metric_services.py` is the workout application surface.
- `tests/test_application_reports.py`: asserts `src/mcp_strava.application.reports` is absent and `src/mcp_strava/application/product_facts.py` is the report/fact surface.
- `tests/test_application_services.py`: tests `src/mcp_strava/application/freshness.py` freshness metadata and first-use refresh request behavior.
- `tests/test_metric_services.py`: tests `src/mcp_strava/application/metric_services.py` service envelopes for fitness, workouts, detail, comparisons, projections, and DuckDB routing.
- `tests/test_product_fact_bundles.py`: tests `src/mcp_strava/application/product_facts.py` daily, weekly, historical, status, and gear-fact bundles.
- `tests/test_training_aggregates.py`: tests `src/mcp_strava/application/aggregate_services.py` aggregate requests, product bundles, buckets, scopes, and validation.

**Metric Registry and Read Model:**
- `tests/test_metric_registry.py`: verifies `src/mcp_strava/application/metric_registry.py` metric ids, aggregate modes, bundles, supported buckets/scopes/windows, materialized fact column registry, and docs sync.
- `tests/test_read_model_queries.py`: verifies `src/mcp_strava/adapters/sqlite/repository.py` read-model status, fact queries, half-open ranges, fail-soft behavior, indexed hot query plans, and DuckDB aggregate query guardrails.
- `tests/test_read_model_materialization.py`: verifies SQLite and DuckDB read-model materializers, dirty queue clearing, model/fact writes, and materialization limits.
- `tests/test_load_status.py`: checks load-status helpers using `src/mcp_strava/adapters/sqlite/repository.py`, `src/mcp_strava/db.py`, and `src/mcp_strava/training.py`.

**Repository and Storage:**
- `tests/test_repository_boundary.py`: verifies repository methods, SQLite direct-access guardrails, hot load paths through repositories, and DuckDB routing via `repository_from_connection`.
- `tests/test_duckdb_repository.py`: verifies `src/mcp_strava/adapters/duckdb/repository.py` has no generic SQL surface and serializes transactions/reads.
- `tests/test_duckdb_concurrency_guards.py`: verifies deploy/service health behavior around DuckDB owner-process and refresh-worker concurrency.
- `tests/test_sqlite_safety.py`: verifies SQLite fixture creation, backups, migrations, preflight, parity checks, and backup retention.
- `tests/test_full_fidelity_mirror.py`: verifies lossless stream inventory, stream channel metadata, atomic replacement, conflict/malformed counts, and stream value preservation.
- `tests/test_duckdb_migration.py`: verifies SQLite-to-DuckDB cutover, backups, parity, cast errors, active lease rejection, and canonical live DuckDB runtime path.

**Refresh and Strava Integration:**
- `tests/test_refresh_runtime.py`: tests staged `src/mcp_strava/refresh/*` behavior, fake Strava transports, leases, idempotent refresh requests, worker materialization, stream-channel backfill, and sync wrapper constraints.
- `tests/test_strava_adapter.py`: tests `src/mcp_strava/adapters/strava/*` token provider, token refresh, rate-limit policy, transport, and failure normalization.
- `tests/test_security_guards.py`: verifies sync/admin boundaries, no direct storage outside adapters, local-network Docker policy, and safe refresh/backfill wrappers.

**Deployment and Runtime:**
- `tests/test_docker_runtime.py`: verifies Python/DuckDB runtime dependency, Dockerfile, compose, healthcheck, preflight, entrypoint sequencing, prepare-runtime, runbook contracts, and no public port binding.
- `tests/test_mcp_latency_gate.py`: verifies warm MCP latency gate, default 100 ms p95 threshold, startup timing separation, and product-bundle aggregate calls.
- `tests/test_phase4_e2e.py`: verifies CLI freshness JSON path against a fixture SQLite mirror without Strava network.

**Smoke and Baseline Behavior:**
- `tests/test_smoke.py`: imports package modules and verifies core pure functions, daily report behavior, metrics, sports registry, settings defaults, and package paths.
- `tests/test_phase01_validation.py`: verifies foundational packaging, module entrypoint, fail-closed DB connection, empty fixture creation, and Docker smoke command routing.

## Naming Conventions

**Files:**
- Use lower snake case for prompt files under `mcp-content/prompts/`, for example `mcp-content/prompts/strava_daily_training_brief.md`.
- Use `test_<area>.py` for tests under `tests/`, for example `tests/test_mcp_surface.py`, `tests/test_refresh_runtime.py`, and `tests/test_duckdb_repository.py`.
- Use `fake_<thing>.py` for test fakes under `tests/fixtures/`, for example `tests/fixtures/fake_mcp_server.py`.
- Use `__init__.py` only to mark `tests/` as a package; `tests/__init__.py` is empty.

**Directories:**
- Place MCP content by type under `mcp-content/prompts/`.
- Place all pytest modules directly under `tests/` unless the file is a reusable test helper under `tests/fixtures/`.
- Do not add generated caches under `tests/__pycache__/`; treat `tests/__pycache__/` as generated runtime output.

**Test Functions:**
- Use `test_<contract_or_behavior>()` names in `tests/test_*.py`, for example `test_mcp_tool_allowlist_is_exact()` in `tests/test_mcp_surface.py`.
- Use helper factories with leading underscores in `tests/test_*.py`, for example `_repo_with_facts()` in `tests/test_read_model_queries.py` and `_aggregate_fixture()` in `tests/test_training_aggregates.py`.
- Use named fixture classes such as `FakeStravaTransport`, `FakeClock`, and `FakeSleeper` in `tests/test_refresh_runtime.py` when a behavior needs injected collaborators.

**Product Identifiers:**
- Keep MCP tool ids in lower snake case, as asserted by `tests/test_mcp_surface.py`: `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, `project_fitness_state`, `get_training_aggregates`.
- Keep MCP prompt ids aligned with prompt filenames in `mcp-content/prompts/`, as asserted by `tests/test_mcp_surface.py`: `strava_daily_training_brief`, `strava_weekly_training_digest`, `strava_shoe_mileage_watchdog`.
- Keep aggregate bundle ids in lower snake case, as asserted by `tests/test_training_aggregates.py` and `tests/test_mcp_test_client.py`: `daily_brief`, `weekly_digest`, `historical_facts`, plus registry-only bundles such as `period_comparison` and `sport_efficiency`.

## Where to Add New Code

**New MCP Prompt:**
- Primary code: add markdown under `mcp-content/prompts/`.
- Registration and allowlist: update `src/mcp_strava/interfaces/mcp_http.py`.
- Tests: update `tests/test_mcp_surface.py` with prompt name, content-backed loading, and no tool-surface expansion assertions.

**New MCP Tool:**
- Primary code: add the service in `src/mcp_strava/application/` and expose it in `src/mcp_strava/interfaces/mcp_http.py`.
- Metric facts: add registry definitions in `src/mcp_strava/application/metric_registry.py` when the tool exposes metrics.
- Tests: update `tests/test_mcp_surface.py`, `tests/test_metric_registry.py`, `tests/test_metric_services.py` or `tests/test_training_aggregates.py`, and `tests/test_mcp_test_client.py`.

**New Product CLI Command:**
- Primary code: route through `src/mcp_strava/cli.py` and an application service in `src/mcp_strava/application/`.
- Registry: update `src/mcp_strava/application/registry.py` if the command is part of product service dispatch.
- Tests: update `tests/test_cli_surface.py` and `tests/test_security_guards.py` to keep the product/admin split intact.

**New Admin or Refresh Operation:**
- Primary code: add to `src/mcp_strava/refresh/`, `src/mcp_strava/sync.py`, `src/mcp_strava/cli.py`, or `src/mcp_strava/deploy/`.
- Storage safety: use repository methods in `src/mcp_strava/adapters/duckdb/` or `src/mcp_strava/adapters/sqlite/`.
- Tests: update `tests/test_refresh_runtime.py`, `tests/test_cli_surface.py`, `tests/test_security_guards.py`, and deployment/preflight tests in `tests/test_docker_runtime.py`.

**New Repository Query or Mutation:**
- Primary code: add storage-specific methods in `src/mcp_strava/adapters/duckdb/repository.py` or `src/mcp_strava/adapters/sqlite/repository.py`.
- Read-model path: update `src/mcp_strava/adapters/duckdb/aggregate_queries.py` or materializers under `src/mcp_strava/adapters/*/read_model_materializer.py` when query performance matters.
- Tests: update `tests/test_repository_boundary.py`, `tests/test_duckdb_repository.py`, `tests/test_read_model_queries.py`, and `tests/test_read_model_materialization.py`.

**New Metric or Aggregate Bundle:**
- Primary code: update `src/mcp_strava/application/metric_registry.py`.
- Materialization: update `src/mcp_strava/adapters/duckdb/read_model_materializer.py` and SQLite compatibility materializer as needed.
- Tests: update `tests/test_metric_registry.py`, `tests/test_training_aggregates.py`, `tests/test_product_fact_bundles.py`, and `tests/test_read_model_materialization.py`.

**New Deployment Behavior:**
- Primary code: add runtime helper under `src/mcp_strava/deploy/` or repo-level asset under `deploy/`.
- Documentation: update `README.md` for user-visible commands or runtime state.
- Tests: update `tests/test_docker_runtime.py`, `tests/test_security_guards.py`, and MCP smoke/latency tests when runtime behavior changes.

**New Test Fixture:**
- Primary code: add reusable fixture helpers under `tests/fixtures/` only if shared across multiple test modules.
- Local fixtures: keep one-off DB builders or fakes inside the relevant `tests/test_*.py` file.
- Tests: keep fixture files import-safe and free of live network, live `/opt/docker/mcp-strava`, or real `data/strava.db` mutation.

## Special Directories

**`mcp-content/`:**
- Purpose: runtime prompt content for MCP.
- Generated: No.
- Committed: Yes.

**`mcp-content/prompts/`:**
- Purpose: content-backed prompt definitions served by the MCP interface.
- Generated: No.
- Committed: Yes.

**`tests/`:**
- Purpose: pytest test suite and architecture contract suite.
- Generated: No.
- Committed: Yes.

**`tests/fixtures/`:**
- Purpose: reusable test-only fakes such as the stdio JSON-RPC MCP server.
- Generated: No.
- Committed: Yes.

**`tests/__pycache__/`:**
- Purpose: Python bytecode cache created by test runs.
- Generated: Yes.
- Committed: No.

---

*Structure analysis: 2026-05-26*
