# mcp-strava

Local Strava mirror and MCP training-metrics server.

`mcp-strava` keeps Strava activities, streams, kudos, and derived training metrics in a local DuckDB database, then exposes read-only MCP tools for agents that need workout facts, period comparisons, and fitness-state projections.

## What It Does

- Mirrors Strava activities and sensor streams into DuckDB.
- Materializes read-model facts for fast MCP tool calls.
- Exposes factual MCP tools only: workouts, workout detail, period comparison, current fitness state, fitness-state projection, and prepared training aggregates.
- Keeps sync, backfill, SQL, token refresh, and deployment operations below the MCP surface.

## Requirements

- Python 3.14+
- `uv`
- Docker with Compose
- `just`
- A Strava API application for OAuth credentials

## First-Time Strava Setup

This project stores Strava credentials in a local env file, not in a keychain. Treat this file as secret material and keep it outside git.

### 1. Create A Strava Application

Open `https://www.strava.com/settings/api` and create an application:

| Field | Value |
|---|---|
| Application Name | Any local name, for example `mcp-strava` |
| Category | Any suitable category |
| Website | `http://localhost` |
| Authorization Callback Domain | `localhost` |

Copy the generated `Client ID` and `Client Secret`.

### 2. Authorize The Application

Open this URL in a browser after replacing `CLIENT_ID`:

```text
https://www.strava.com/oauth/authorize?client_id=CLIENT_ID&redirect_uri=http://localhost/exchange_token&response_type=code&approval_prompt=force&scope=read,activity:read_all,profile:read_all
```

After approval, Strava redirects to a localhost URL. The page may fail to load; that is fine. Copy the `code` query parameter from the browser address bar.

### 3. Exchange The Code For Tokens

```bash
curl -s -X POST https://www.strava.com/oauth/token \
  -d client_id=CLIENT_ID \
  -d client_secret=CLIENT_SECRET \
  -d code=AUTHORIZATION_CODE \
  -d grant_type=authorization_code
```

The response contains `access_token`, `refresh_token`, and `expires_at`.

### 4. Write The Token File

For local development, create `.env` in the repo root:

```bash
cat > .env <<'EOF'
STRAVA_CLIENT_ID=...
STRAVA_CLIENT_SECRET=...
STRAVA_ACCESS_TOKEN=...
STRAVA_REFRESH_TOKEN=...
STRAVA_EXPIRES_AT=...
EOF
chmod 600 .env
```

For the Docker runtime, the canonical token file is `/opt/docker/mcp-strava/.env`:

```bash
install -d -m 750 /opt/docker/mcp-strava
install -m 600 .env /opt/docker/mcp-strava/.env
```

Tokens refresh automatically. To verify credentials manually:

```bash
MCP_STRAVA_TOKEN_PATH=.env uv run python -m mcp_strava admin token-refresh
```

## Local Docker Usage

```bash
just test
```

This builds the image, starts the `mcp-strava` container, waits for health, and runs a direct MCP smoke test against the product server at `http://127.0.0.1:8080/mcp`.

## Useful Commands

```bash
# Full local validation: pytest, Docker build/start, MCP smoke
just test

# Full MCP smoke
just mcp-smoke-full

# Read-model latency gate
just mcp-read-model-perf

# List exposed MCP tools
just mcp-list-tools

# Run all Python tests
uv run pytest -q
```

## Runtime State

Live Docker state is expected under `/opt/docker/mcp-strava`:

| Path | Purpose |
|---|---|
| `/opt/docker/mcp-strava/data/strava.duckdb` | DuckDB mirror and read-model facts |
| `/opt/docker/mcp-strava/.env` | Strava OAuth credentials |

## Strava Notes

- Access tokens expire after roughly six hours; the refresh token is used automatically.
- Strava rate limits are enforced by Strava and surfaced through response headers. Avoid full backfills unless needed.
- If Strava returns `429`, wait for the current rate-limit window before retrying.

## MCP Boundary

The MCP server is read-only and factual. It does not expose sync, admin, debug, raw SQL, token, or raw Strava API tools. Agents receive metrics and freshness facts, then perform their own interpretation.

## License

Copyright (c) 2026 Maksim Brashchenko.

This project is available for noncommercial use under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). Commercial use requires a separate written commercial license; see [COMMERCIAL.md](COMMERCIAL.md).
