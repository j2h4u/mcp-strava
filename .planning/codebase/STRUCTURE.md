---
analysis_date: 2026-05-22
last_mapped_commit: b207e64f8293ddb0b3432562705b96a0a0264082
---
# Codebase Structure

**Analysis Date:** 2026-05-22

## Directory Layout

```text
mcp-strava/
├── AGENTS.md
├── SKILL.md
├── pyproject.toml
├── uv.lock
├── deploy/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── gateway_register.py
└── src/
    └── mcp_strava/
        ├── application/
        ├── adapters/
        ├── deploy/
        ├── interfaces/
        └── refresh/
```

## Directory Purposes

**`src/mcp_strava/`**
- Purpose: the installable Python package.
- Contains: CLI, MCP interface, settings, types, constants, analytics, refresh runtime, adapters, and deployment helpers.
- Key files: `src/mcp_strava/__main__.py`, `src/mcp_strava/cli.py`, `src/mcp_strava/settings.py`, `src/mcp_strava/types.py`.

**`src/mcp_strava/application/`**
- Purpose: product-service composition layer.
- Contains: service envelopes, freshness metadata, workout/report services, metric registry, and service allowlist.
- Key files: `src/mcp_strava/application/__init__.py`, `src/mcp_strava/application/metric_services.py`, `src/mcp_strava/application/reports.py`, `src/mcp_strava/application/workouts.py`, `src/mcp_strava/application/freshness.py`.

**`src/mcp_strava/adapters/`**
- Purpose: persistence and external-system boundaries.
- Contains: SQLite connection/repository/migration code and Strava OAuth/transport/rate-limit code.
- Key files: `src/mcp_strava/adapters/sqlite/repository.py`, `src/mcp_strava/adapters/sqlite/migrations.py`, `src/mcp_strava/adapters/strava/transport.py`, `src/mcp_strava/adapters/strava/token_provider.py`.

**`src/mcp_strava/refresh/`**
- Purpose: staged mirror refresh orchestration.
- Contains: freshness evaluation, checkpoint stages, runtime lease handling, and sync helpers.
- Key files: `src/mcp_strava/refresh/runtime.py`, `src/mcp_strava/refresh/_sync_ops.py`, `src/mcp_strava/refresh/freshness.py`, `src/mcp_strava/refresh/checkpoints.py`.

**`src/mcp_strava/interfaces/`**
- Purpose: public service interfaces.
- Contains: the streamable HTTP MCP server.
- Key files: `src/mcp_strava/interfaces/mcp_http.py`.

**`src/mcp_strava/deploy/`**
- Purpose: runtime validation and preparation helpers.
- Contains: preflight, runtime preparation, container entrypoint, and MCP smoke checks.
- Key files: `src/mcp_strava/deploy/preflight.py`, `src/mcp_strava/deploy/prepare_runtime.py`, `src/mcp_strava/deploy/entrypoint.py`, `src/mcp_strava/deploy/smoke.py`.

**`deploy/`**
- Purpose: repo-level Docker and gateway deployment assets.
- Contains: container build definition, compose file, and gateway registration helper.
- Key files: `deploy/Dockerfile`, `deploy/docker-compose.yml`, `deploy/gateway_register.py`.

## Key File Locations

**Entry Points:**
- `src/mcp_strava/__main__.py`: package entrypoint that forwards to the CLI.
- `src/mcp_strava/cli.py`: operator command dispatcher.
- `src/mcp_strava/interfaces/mcp_http.py`: MCP server entrypoint.
- `src/mcp_strava/deploy/entrypoint.py`: container startup entrypoint.
- `src/mcp_strava/deploy/preflight.py`: runtime DB validation command.
- `src/mcp_strava/deploy/prepare_runtime.py`: live runtime preparation helper.
- `src/mcp_strava/deploy/smoke.py`: MCP smoke checker.
- `deploy/gateway_register.py`: gateway registration helper.

**Configuration:**
- `pyproject.toml`: package metadata, setuptools build config, and pytest configuration.
- `uv.lock`: dependency lockfile for the repo’s pinned environment.
- `src/mcp_strava/settings.py`: runtime settings loader and cache.
- `.gitignore`: ignores `.env`, local databases, caches, build artifacts, and `.planning/config.json`.

**Core Logic:**
- `src/mcp_strava/application/`: MCP-facing product service assembly.
- `src/mcp_strava/{metrics,training,analytics,report,trends}.py`: domain computation and reporting.
- `src/mcp_strava/adapters/sqlite/repository.py`: all SQLite queries and writes.
- `src/mcp_strava/adapters/strava/`: live Strava access and token refresh.
- `src/mcp_strava/refresh/`: daily refresh runtime and backfill orchestration.

**Deployment/Runtime:**
- `src/mcp_strava/deploy/`: startup and runtime safety checks.
- `deploy/`: Docker and gateway rollout files.

## Naming Conventions

**Files:**
- Lower snake case for modules and helpers: `metrics.py`, `token_refresh.py`, `prepare_runtime.py`, `gateway_register.py`.
- `__init__.py` files are used as small facades, not as large implementation modules.
- Entry points use `__main__.py`, `cli.py`, or `entrypoint.py` naming.

**Directories:**
- Package subdomains are nouns or service areas: `application/`, `adapters/`, `refresh/`, `interfaces/`, `deploy/`.
- Vendor-boundary directories are nested by system: `adapters/sqlite/` and `adapters/strava/`.

**Types and services:**
- Dataclasses and service envelopes use PascalCase names in `src/mcp_strava/types.py`.
- Command and service functions use snake_case, with CLI handlers using `cmd_*` in `src/mcp_strava/cli.py`.

## Where to Add New Code

**New MCP tool or product view:**
- Primary code: `src/mcp_strava/application/`.
- HTTP exposure: `src/mcp_strava/interfaces/mcp_http.py`.
- Shared types: `src/mcp_strava/types.py`.

**New SQLite query or mutation:**
- Primary code: `src/mcp_strava/adapters/sqlite/repository.py`.
- Schema safety or migration gate: `src/mcp_strava/adapters/sqlite/{schema,migrations,backup}.py`.
- Connection policy: `src/mcp_strava/adapters/sqlite/connection.py`.

**New Strava API behavior:**
- Primary code: `src/mcp_strava/adapters/strava/`.
- Error normalization: `src/mcp_strava/adapters/strava/types.py`.
- Legacy compatibility wrappers: `src/mcp_strava/db.py` and `src/mcp_strava/sync.py`.

**New refresh stage or freshness rule:**
- Primary code: `src/mcp_strava/refresh/`.
- Settings knobs: `src/mcp_strava/settings.py`.
- Product-service freshness metadata: `src/mcp_strava/application/freshness.py`.

**New deployment or runtime helper:**
- Runtime safety checks: `src/mcp_strava/deploy/`.
- Docker/gateway assets: `deploy/`.

**New shared constants or dataclasses:**
- Shared types: `src/mcp_strava/types.py`.
- Shared thresholds and sport registry: `src/mcp_strava/constants.py` and `src/mcp_strava/sports.py`.

## Special Directories

**`deploy/`**
- Purpose: repository-level container and gateway integration assets.
- Generated: No.
- Committed: Yes.

**`src/mcp_strava/adapters/sqlite/`**
- Purpose: persistence boundary for the local mirror.
- Generated: No.
- Committed: Yes.

**`src/mcp_strava/adapters/strava/`**
- Purpose: outbound Strava integration boundary.
- Generated: No.
- Committed: Yes.

**`src/mcp_strava/refresh/`**
- Purpose: mirror freshness and staged sync orchestration.
- Generated: No.
- Committed: Yes.

**`src/mcp_strava/application/`**
- Purpose: product-service composition layer used by CLI and MCP.
- Generated: No.
- Committed: Yes.

---

*Structure analysis: 2026-05-22*
