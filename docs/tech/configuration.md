# mcp-strava Configuration

Server configuration is read from environment variables (or a `.env` file in the
project root / the path given by `MCP_STRAVA_TOKEN_PATH`). Every variable below
has a sensible default — a local run needs none of them except your athlete
resting heart rate.

Only the variables that genuinely differ between users or deployments are listed
here. Internal tuning values (batch sizes, freshness thresholds, refresh-worker
poll/health timings) are deliberately **not** configuration: they are fixed
constants in the code, because no operator needs to tune them.

Strava credentials (`STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, tokens) are not
env vars — they live in the token file. See the README's *First-Time Strava
Setup*.

## Athlete

| Variable | Default | Notes |
|---|---|---|
| `MCP_STRAVA_HR_REST` | _(unset)_ | Resting heart rate. Required for HR-derived metrics (TRIMP, zones); valid range 20–120. Computations that need it fail fast when unset. |
| `MCP_STRAVA_HR_ZONE_MODEL` | `karvonen_hrr` | Heart-rate zone model identifier. |

## Deployment

| Variable | Default | Notes |
|---|---|---|
| `MCP_STRAVA_RUNTIME_PROFILE` | `local` | `local` or `docker`. Selects path defaults and bind behavior. |
| `MCP_STRAVA_TOKEN_PATH` | `<project root>/.env` | Path to the Strava credentials/token file. |
| `MCP_STRAVA_DB_PATH` | `<project root>/data/strava.duckdb` (`/runtime/data/strava.duckdb` under the docker profile) | DuckDB mirror location. |
| `MCP_STRAVA_HTTP_HOST` | `127.0.0.1` | Interface the MCP server binds to. |
| `MCP_STRAVA_HTTP_PORT` | `8000` | Port the MCP server binds to. |

## Network & Security (advanced)

| Variable | Default | Notes |
|---|---|---|
| `MCP_STRAVA_ALLOWED_HOSTS` | `127.0.0.1,localhost,mcp-strava` | DNS-rebinding host allowlist (comma-separated). Adjust only if you front the server with a different hostname. |
| `MCP_STRAVA_ALLOWED_ORIGINS` | `http://127.0.0.1,http://localhost,http://[::1]` | Allowed request origins (comma-separated). |
| `MCP_STRAVA_ALLOW_CONTAINER_BIND` | `false` | Permit binding a non-loopback host (needed inside a container). |

## Sync

| Variable | Default | Notes |
|---|---|---|
| `MCP_STRAVA_REFRESH_WORKER_ENABLED` | `true` | Run the background mirror-refresh worker. Set false for a read-only deployment or when syncing out of band. |
| `MCP_STRAVA_REFRESH_INTERVAL_SECONDS` | `3600` | Seconds between refresh cycles (minimum 60). |

## Prompts

| Variable | Default | Notes |
|---|---|---|
| `MCP_STRAVA_PROMPT_LANGUAGE` | `en` | Language of the served MCP prompts: `en` or `ru`. |
