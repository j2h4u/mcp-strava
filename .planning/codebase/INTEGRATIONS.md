---
analysis_date: 2026-05-22
last_mapped_commit: b207e64f8293ddb0b3432562705b96a0a0264082
---
# External Integrations

**Analysis Date:** 2026-05-22

## APIs & External Services

**Strava API:**
- `https://www.strava.com/oauth/token` and `https://www.strava.com/api/v3` - OAuth token refresh and activity/athlete fetches in `src/mcp_strava/adapters/strava/token_refresh.py` and `src/mcp_strava/adapters/strava/transport.py`.
  - SDK/Client: stdlib `urllib.request` wrappers, not a third-party HTTP client.
  - Auth: `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`, `STRAVA_ACCESS_TOKEN`, and `STRAVA_EXPIRES_AT` from the token file path selected by `MCP_STRAVA_TOKEN_PATH`.

**Local MCP gateway:**
- `http://mcp-strava:8080/mcp` - The service URL registered by `deploy/gateway_register.py` into `/opt/docker/mcp-gateway/catalog.yaml` and `/opt/docker/mcp-gateway/compose.yaml`.
  - SDK/Client: `PyYAML` for catalog/compose edits and `docker compose` for validation/restart.
  - Auth: Not applicable; the integration is local network routing, not user auth.

## Data Storage

**Databases:**
- DuckDB - Primary mirror storage in `data/strava.duckdb` and, in container mode, `/runtime/data/strava.duckdb` via the `/opt/docker/mcp-strava` runtime mount.
  - Connection: `src/mcp_strava/adapters/duckdb/connection.py` opens the expected mirror fail-closed.
  - Client: `src/mcp_strava/adapters/duckdb/repository.py`, `src/mcp_strava/db.py`, `src/mcp_strava/deploy/preflight.py`, and the owner-process refresh runtime.
- SQLite - Compatibility input for rollback, migration, and historical test fixtures only.

**File Storage:**
- Local filesystem only - Token files, backups, and runtime state live on disk under `.env`, `data/`, and `/opt/docker/mcp-strava/`.

**Caching:**
- DuckDB is the durable local mirror/read-model store - There is no separate Redis or remote cache layer.
- Token refresh writes back to the local token file - `src/mcp_strava/adapters/strava/token_provider.py`.

## Authentication & Identity

**Auth Provider:**
- Strava OAuth 2.0 - Implemented in `src/mcp_strava/adapters/strava/token_refresh.py` and wrapped by `src/mcp_strava/adapters/strava/token_provider.py`.
  - Implementation: refresh-token flow with file-backed token rotation and atomic writes.
- MCP HTTP access control - `src/mcp_strava/interfaces/mcp_http.py` enforces safe hosts, allowed origins, and DNS rebinding protection for the streamable HTTP endpoint.

## Monitoring & Observability

**Error Tracking:**
- None detected - No external error-tracking service is wired in.

**Logs:**
- Process stderr/stdout and DuckDB audit rows - Sync/runtime failures are printed locally and recorded in `sync_log` via `src/mcp_strava/db.py` and related refresh code.
- Container health - `deploy/Dockerfile` uses a `HEALTHCHECK` that runs `python -m mcp_strava.deploy.healthcheck`, which checks owner-process state and HTTP readiness without directly opening the live DuckDB file.

## CI/CD & Deployment

**Hosting:**
- Docker - Container image build and runtime in `deploy/Dockerfile`.
- Local MCP network - `deploy/docker-compose.yml` attaches the service to the external `mcp-backends` network.

**CI Pipeline:**
- None detected - No hosted CI configuration is present in the scoped files.

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
- `MCP_STRAVA_PROJECT_ROOT`
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REFRESH_TOKEN`
- `STRAVA_ACCESS_TOKEN`
- `STRAVA_EXPIRES_AT`

**Secrets location:**
- `.env` in the repo root for local development, and `/opt/docker/mcp-strava/.env` in container deployment as wired by `deploy/docker-compose.yml` and `deploy/prepare_runtime.py`.

## Webhooks & Callbacks

**Incoming:**
- None detected - `src/mcp_strava/interfaces/mcp_http.py` exposes only the read-only MCP `streamable-http` endpoint at `/mcp`; no webhook routes are defined.

**Outgoing:**
- None detected - The code only calls Strava OAuth/API endpoints and the local MCP gateway registration path; no webhook callbacks are emitted.

---

*Integration audit: 2026-05-22*
