---
analysis_date: 2026-06-01
last_mapped_commit: d16b5fd
scope: full-repo
---
# External Integrations

**Analysis Date:** 2026-06-01

## APIs & External Services

**Strava API:**
- Strava REST API v3 - source of all activity/workout data
  - Base URL: `https://www.strava.com/api/v3` (configurable via `StravaTransport.base_url`)
  - Client: custom `StravaTransport` in `src/mcp_strava/adapters/strava/transport.py`
  - Auth: Bearer token via `FileTokenProvider` (`src/mcp_strava/adapters/strava/token_provider.py`)
  - Rate limiting: `RateLimitPolicy` in `src/mcp_strava/adapters/strava/rate_limit.py` — tracks 15-min and daily windows, respects `Retry-After` headers
  - Retry: 3 attempts with exponential backoff (1s, 5s, 30s) for network errors; separate retry chain for OAuth refresh (2s, 8s, 30s)
  - No third-party SDK — uses `urllib.request` only

**Strava OAuth:**
- OAuth 2.0 token refresh (not full authorization flow — tokens obtained externally and stored in token file)
  - Endpoint: `https://www.strava.com/oauth/token` (POST, `grant_type=refresh_token`)
  - Client: `TokenRefreshTransport` in `src/mcp_strava/adapters/strava/token_refresh.py`
  - Credentials required: `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`
  - Token storage: atomic file write with `fcntl.flock` exclusive lock, `os.replace`, `chmod 0o600`
    (`src/mcp_strava/adapters/strava/token_provider.py`)

**MCP Gateway (context-gateway):**
- Registration script: `deploy/gateway_register.py`
- Registers the service into `/opt/docker/mcp-gateway/catalog.yaml` and `compose.yaml`
- Service URL within the `mcp-backends` Docker network: `http://mcp-strava:8080/mcp`
- Uses `PyYAML` for catalog manipulation

## Data Storage

**Databases:**
- DuckDB (embedded, file-based) — local mirror of all Strava activity data
  - File path: `/runtime/data/strava.duckdb` (container) / `data/strava.duckdb` (local dev)
  - Config: `MCP_STRAVA_DB_PATH`
  - Client: `duckdb` Python package, accessed via `src/mcp_strava/adapters/duckdb/connection.py`
  - Connection patterns:
    - `MirrorConn` — write/admin connections, opens fresh per operation (fail-closed: raises if DB absent)
    - `ReadConn` — thread-local reused read connections (avoids ~25ms catalog attach cost per request)
    - `open_fixture_db` — used in tests to create temporary DBs
  - Schema: `src/mcp_strava/adapters/duckdb/schema.py`
  - Repository: `src/mcp_strava/adapters/duckdb/repository.py`
  - Read model materializer: `src/mcp_strava/adapters/duckdb/read_model_materializer.py`
  - DuckDB holds an exclusive file lock when writing; admin commands require stopping the container (`just admin`)

**File Storage:**
- Token/credential file at `MCP_STRAVA_TOKEN_PATH` (default project-root `.env`; compose sets `/runtime/.env` in the container)
  - Contains `STRAVA_*` OAuth tokens; written atomically on each refresh
  - `.env.lock` sidecar file used for `fcntl` cross-process serialization

**Caching:**
- In-process tool response cache in `src/mcp_strava/interfaces/mcp_http.py`
  - TTL: 30 seconds, max 32 entries (LRU eviction)
  - Applies only to `compare_periods` and `get_training_aggregates` tools
  - Not persistent — cleared on process restart

## Authentication & Identity

**Auth Provider:**
- Strava OAuth 2.0 (custom, no library)
  - Implementation: `FileTokenProvider` manages token lifecycle; `TokenRefreshTransport` handles the actual POST
  - Access tokens auto-refresh when within 60 seconds of expiry (`_is_fresh` check)
  - Client credentials (`STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`) read from token file only via `required_strava_client_creds()` in `src/mcp_strava/settings.py` — never from env vars, never in `load_settings()`
  - No user-facing auth flow — single-athlete deployment

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry or equivalent)

**Logs:**
- Structured JSON to stderr — all MCP tool calls emit `mcp_tool_call_started` / `mcp_tool_call_finished` / `mcp_tool_call_failed` events
  - Fields include: `tool`, `duration_ms`, `warnings_count`, `warning_codes`, `data_shape`, `cached`
  - Implementation: `_emit_log()` in `src/mcp_strava/interfaces/mcp_http.py`
- Container healthcheck: `python -m mcp_strava.deploy.healthcheck` (every 30s, collected by Docker)
- Grafana Alloy on the host scrapes Docker container logs (host-level, not application-configured)

## CI/CD & Deployment

**Hosting:**
- Docker container on server `senbonzakura`
- Project: `deploy/` directory (compose in repo, runtime data at `/opt/docker/mcp-strava/`)
- Docker network: `mcp-backends` (external, pre-existing)

**CI Pipeline:**
- None (no GitHub Actions or equivalent configured in this repo)
- Local validation via `just check` (lint + typecheck) and `just test` (pytest + docker build + smoke)

## Environment Configuration

**Required env vars / token file keys:**
- `MCP_STRAVA_DB_PATH` - DuckDB file path
- `MCP_STRAVA_TOKEN_PATH` - token file path
- `MCP_STRAVA_RUNTIME_PROFILE` - `local` | `container`
- `MCP_STRAVA_HTTP_HOST` / `MCP_STRAVA_HTTP_PORT` - bind address
- `MCP_STRAVA_ALLOW_CONTAINER_BIND` - must be `1` to allow `0.0.0.0` bind in container profile
- `MCP_STRAVA_ALLOWED_HOSTS` / `MCP_STRAVA_ALLOWED_ORIGINS` - DNS rebinding protection lists
- `MCP_STRAVA_HR_REST` - resting heart rate (operator physiology; kept out of git)
- `MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS` / `MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS` - stale-data warning and maximum-age thresholds
- `MCP_STRAVA_REFRESH_WORKER_ENABLED` / `MCP_STRAVA_REFRESH_POLL_SECONDS` / `MCP_STRAVA_REFRESH_INTERVAL_SECONDS`
- In token file: `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_ACCESS_TOKEN`, `STRAVA_REFRESH_TOKEN`, `STRAVA_EXPIRES_AT`

**Secrets location:**
- Token file at `/opt/docker/mcp-strava/.env` (bind-mounted to `/runtime/.env` in container)
- Not stored in `~/.secrets/` (exception to server convention — token file doubles as runtime config)

## Webhooks & Callbacks

**Incoming:**
- None — no Strava webhook receiver; data is pulled via polling sync worker

**Outgoing:**
- None — MCP server is read-only; all writes are to local DuckDB mirror

---

*Integration audit: 2026-06-01*
