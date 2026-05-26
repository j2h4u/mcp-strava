---
analysis_date: 2026-05-26
last_mapped_commit: ab203ab
scope:
  - README.md
  - mcp-content
  - tests
---
# External Integrations

**Analysis Date:** 2026-05-26

## APIs & External Services

**Strava API:**
- Strava OAuth and API - `README.md` documents the OAuth application setup, browser authorization URL, and token exchange at `https://www.strava.com/oauth/token`; `tests/test_strava_adapter.py` verifies typed Strava transport behavior, 401 token refresh, retry budgets, and rate-limit headers.
  - SDK/Client: stdlib `urllib.request` and `urllib.error` wrappers in `src/mcp_strava/adapters/strava`, covered by `tests/test_strava_adapter.py`.
  - Auth: file-backed `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_ACCESS_TOKEN`, `STRAVA_REFRESH_TOKEN`, and `STRAVA_EXPIRES_AT` selected by `MCP_STRAVA_TOKEN_PATH`.

**MCP Clients / Local MCP Network:**
- Streamable HTTP MCP endpoint - `README.md` and `Justfile` use `http://127.0.0.1:8080/mcp`; `tests/test_mcp_sdk_contract.py` verifies FastMCP streamable HTTP support and `tests/test_mcp_test_client.py` verifies stdio and HTTP smoke-client behavior.
  - SDK/Client: `mcp` Python package, pinned to 1.27.1 in `uv.lock`.
  - Auth: no bearer-token or OAuth auth detected in scoped files; access is constrained through local/container networking, allowed hosts, and allowed origins in `tests/test_mcp_surface.py`.

**Docker / Local Runtime Network:**
- Docker Compose service - `Justfile` runs `docker compose -f deploy/docker-compose.yml`; `tests/test_docker_runtime.py` asserts a service named `mcp-strava`, container name `mcp-strava`, exposed port `8080`, `/opt/docker/mcp-strava:/runtime` mount, and `mcp-backends` network.
  - SDK/Client: Docker Compose CLI invoked by `Justfile`.
  - Auth: Not applicable; this is local container orchestration.

## Data Storage

**Databases:**
- DuckDB - Primary configured runtime database for local and Docker profiles.
  - Connection: `MCP_STRAVA_DB_PATH`; defaults verified in `tests/test_settings.py` are `data/strava.duckdb` locally and `/runtime/data/strava.duckdb` in Docker.
  - Client: `duckdb` 1.5.3 via repository code under `src/mcp_strava/adapters/duckdb`, exercised by `tests/test_duckdb_repository.py`, `tests/test_duckdb_migration.py`, and `tests/test_duckdb_concurrency_guards.py`.
- SQLite - Local mirror/documented compatibility store and migration/cutover source.
  - Connection: README documents `/opt/docker/mcp-strava/data/strava.db`; tests create and migrate SQLite fixtures through `src/mcp_strava/adapters/sqlite` in `tests/test_full_fidelity_mirror.py`, `tests/test_repository_boundary.py`, and `tests/test_sqlite_safety.py`.
  - Client: stdlib `sqlite3`.

**File Storage:**
- Local filesystem only - `README.md` documents `.env`, `/opt/docker/mcp-strava/.env`, `/opt/docker/mcp-strava/live.env`, and `/opt/docker/mcp-strava/data/strava.db`; `tests/test_docker_runtime.py` verifies `/opt/docker/mcp-strava:/runtime`, `/runtime/.env`, `/runtime/data/strava.duckdb`, backups, and live env preparation.
- MCP prompt content - Prompt files live in `mcp-content/prompts/strava_daily_training_brief.md`, `mcp-content/prompts/strava_weekly_training_digest.md`, and `mcp-content/prompts/strava_shoe_mileage_watchdog.md`; `tests/test_mcp_surface.py` verifies prompts are content-backed and do not expand the tool surface.

**Caching:**
- DuckDB read model - Durable materialized facts and read-model status are stored in the local database, with query/performance behavior covered by `tests/test_read_model_queries.py`, `tests/test_read_model_materialization.py`, and `tests/test_mcp_latency_gate.py`.
- MCP response cache - `tests/test_mcp_surface.py` verifies a short-lived in-process response cache for expensive MCP tools.
- No Redis, Memcached, or remote cache detected in scoped files.

## Authentication & Identity

**Auth Provider:**
- Strava OAuth 2.0 - `README.md` documents creating a Strava API application, authorizing with scopes `read,activity:read_all,profile:read_all`, exchanging an authorization code, and storing tokens in a local env file.
  - Implementation: file-backed refresh-token flow in `src/mcp_strava/adapters/strava`, verified by `tests/test_strava_adapter.py` for single-writer refresh, atomic writes, 0600 token file permissions, token refresh retry budget, and token redaction.
- MCP HTTP access control - `tests/test_mcp_surface.py` verifies local-safe bind validation, allowed host/origin checks, and rejection of wildcard `allowed_hosts` or `allowed_origins`.
  - Implementation: transport security in `src/mcp_strava/interfaces/mcp_http`.

## Monitoring & Observability

**Error Tracking:**
- None detected - scoped files do not reference Sentry, OpenTelemetry, external logging SaaS, or a hosted error tracker.

**Logs:**
- Process stdout/stderr - CLI, Docker smoke, and test clients use JSON/text process output in `Justfile`, `tests/test_cli_surface.py`, and `tests/test_mcp_test_client.py`.
- Database/runtime status rows - refresh state, refresh requests, read-model freshness, and failure reasons are exercised in `tests/test_repository_boundary.py`, `tests/test_refresh_runtime.py`, and `tests/test_duckdb_repository.py`.
- Container health - `tests/test_docker_runtime.py` and `tests/test_duckdb_concurrency_guards.py` verify owner-process health behavior and HTTP healthcheck behavior without direct live DuckDB opens.

## CI/CD & Deployment

**Hosting:**
- Local Docker Compose - `README.md`, `Justfile`, and `tests/test_docker_runtime.py` define the local container deployment path.
- Local MCP network - `tests/test_docker_runtime.py` asserts the `mcp-backends` network and no public `ports` binding.

**CI Pipeline:**
- None detected in scoped files - the remap scope does not include `.github/` or other hosted CI configuration.

## Environment Configuration

**Required env vars:**
- `MCP_STRAVA_DB_PATH`
- `MCP_STRAVA_TOKEN_PATH`
- `MCP_STRAVA_RUNTIME_PROFILE`
- `MCP_STRAVA_HTTP_HOST`
- `MCP_STRAVA_HTTP_PORT`
- `MCP_STRAVA_ALLOW_CONTAINER_BIND`
- `MCP_STRAVA_ALLOWED_HOSTS`
- `MCP_STRAVA_ALLOWED_ORIGINS`
- `MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS`
- `MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS`
- `MCP_STRAVA_REFRESH_INTERVAL_SECONDS`
- `MCP_STRAVA_STREAM_BACKFILL_BATCH_SIZE`
- `MCP_STRAVA_READ_MODEL_BATCH_SIZE`
- `MCP_STRAVA_PROJECT_ROOT`
- `MCP_STRAVA_SUPERVISOR_STATE_PATH`
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_ACCESS_TOKEN`
- `STRAVA_REFRESH_TOKEN`
- `STRAVA_EXPIRES_AT`

**Secrets location:**
- Local development token file: `.env` in the repo root, documented by `README.md` and present in the checkout. Contents are secret material and are not read.
- Docker token file: `/opt/docker/mcp-strava/.env`, documented by `README.md`.
- Optional Docker operator overlay: `/opt/docker/mcp-strava/live.env`, documented by `README.md` and verified by `tests/test_docker_runtime.py`.

## Webhooks & Callbacks

**Incoming:**
- OAuth browser callback - `README.md` uses `http://localhost/exchange_token` as the Strava authorization redirect URI for manual code extraction; no local callback server is detected in scoped files.
- MCP HTTP endpoint - product tools are served at `/mcp`; `tests/test_mcp_surface.py` verifies the exact read-only tool allowlist: `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, `project_fitness_state`, and `get_training_aggregates`.
- Webhooks: None detected.

**Outgoing:**
- Strava OAuth/token refresh and API reads - `tests/test_strava_adapter.py` verifies outgoing HTTP behavior, rate-limit parsing, retries, 401 refresh handling, and token redaction.
- Docker Compose commands - `Justfile` invokes local Docker Compose for build, service startup, smoke tests, and MCP client calls.
- Webhooks: None detected.

---

*Integration audit: 2026-05-26*
