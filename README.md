# mcp-strava

Give an AI agent a coach's view of your training — over your own Strava data, even on a free Strava account.

`mcp-strava` connects your Strava account to an AI agent so it can act as your coach and sports physiologist: it reads your real training history and answers questions like "am I overtraining?", "how does this month compare to last?", or "what should this week look like?" — grounded in your actual workouts, not guesses.

It works with any Strava account, including the free tier. You bring your own Strava API credentials, so you don't need a paid Strava subscription to give an agent full read access to your training history.

## What You Can Use It For

- **Daily training brief:** current fitness state, recent workouts, load, form, freshness, and notable data gaps.
- **Weekly digest:** weekly load, volume, efficiency, sport breakdowns, current-week workouts, and current-vs-previous week trends.
- **Period comparison:** compare two arbitrary date ranges across distance, training impulse (TRIMP), time, elevation, HR, cardiac cost, drift, recovery, and model-state metrics.
- **Training aggregates:** query prepared metrics by day, week, month, year, all-time, globally or per sport.
- **Workout analysis:** inspect one workout with factual intensity, heart-rate, drift, recovery, elevation, kudos, and gear facts when available.
- **Fitness projection:** simulate named load scenarios to see projected fitness, fatigue, and form through a target date.

## Why Local

Instead of proxying every question to Strava on demand, `mcp-strava` builds a full local mirror of your Strava history and serves the agent from that. Once your supported history is mirrored, your training facts are queryable on your machine, repeatable across runs, and available for custom analysis without spending API quota on every prompt.

That choice gives you:

- A durable local copy of activities, streams, kudos, gear facts, and derived read-model facts.
- Fast historical questions, including daily, weekly, monthly, all-time, and per-sport aggregates.
- Reproducible metrics such as training impulse (TRIMP), fitness, fatigue, form, acute:chronic workload ratio (ACWR), cardiac drift, recovery, and sport-efficiency summaries.
- Evidence metadata with freshness, completeness, warnings, and rationale, so agents can say what is known and what is missing.
- A read-only MCP surface that never exposes sync, raw SQL, token refresh, or admin controls.

**How it compares to the official connector.** Strava [announced an official MCP connector for Claude](https://press.strava.com/articles/strava-launches-mcp-connector) on June 1, 2026, providing read-only access to training history, streams, GPS, power, clubs, and events — but it is rolling out to Strava *subscribers*. `mcp-strava` is the self-hosted alternative: it works on any account including the free tier, keeps a local mirror on your machine, and adds prepared aggregate bundles and CLI reports on top.

## MCP Tools

| Tool | Use it for |
|---|---|
| `get_fitness_state` | Current load, fitness, fatigue, form, acute:chronic workload ratio (ACWR), freshness, and model context. |
| `list_workouts` | Recent or filtered workouts with factual volume and intensity metrics. |
| `get_workout_detail` | Detailed metrics for a specific workout id. |
| `compare_periods` | Side-by-side date-range comparison, optionally filtered by sport. |
| `project_fitness_state` | Forward fitness-state projections for training-load scenarios. |
| `get_training_aggregates` | Bucketed aggregate facts for dashboards, digests, and custom analysis. |

## Ready-Made Reports

| Surface | Command or prompt | What it returns |
|---|---|---|
| CLI daily brief | `uv run python -m mcp_strava report daily` | Daily facts for current state, recent workouts, 14-day load, sport mix, freshness, and read-model status. |
| CLI weekly digest | `uv run python -m mcp_strava weekly` | Weekly load, volume, efficiency, sport breakdowns, current-week activities, and week-over-week trends. |
| MCP daily prompt | `strava_daily_training_brief` | A daily Russian brief scenario backed only by factual MCP metrics. |
| MCP weekly prompt | `strava_weekly_training_digest` | A weekly Russian digest scenario using period-comparison metrics. |
| MCP shoe watchdog | `strava_shoe_mileage_watchdog` | Shoe and gear mileage facts for replacement review. |

## Aggregate Bundles

`get_training_aggregates` can query individual metrics, or use prepared bundles:

| Bundle | Focus |
|---|---|
| `daily_brief` | Fitness, fatigue, form, ACWR, weekly load, active/rest days, recent efficiency, and kudos. |
| `weekly_digest` | TRIMP, distance, calories, time, elevation, active days, HR, cardiac cost, drift, and recovery. |
| `monthly_digest` | Monthly volume, 28/90-day load context, and model-state metrics. |
| `period_comparison` | Metrics selected for current-vs-previous or arbitrary period comparisons. |
| `sport_efficiency` | HR, recovery, vertical speed, cardiac cost, drift, and efficiency by sport. |
| `historical_facts` | Calendar context, streaks, zone labels, kudos, and long-horizon factual context. |

## How It Works

- Mirrors Strava activities, streams, kudos, and gear facts into DuckDB.
- Materializes read-model facts for fast MCP tool calls.
- Keeps sync, backfill, SQL, token refresh, and deployment operations below the MCP surface.
- Returns freshness, completeness, warnings, and rationale with product responses so agents know what evidence they are using.

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

After the token file exists, routine token refresh and Strava rate-limit handling are automatic.

## Local Docker Usage

```bash
just test
```

This builds the image, starts the `mcp-strava` container, waits for health, and runs a direct MCP smoke test against the product server at `http://127.0.0.1:8080/mcp`.

## Useful Commands

```bash
# Daily training brief
uv run python -m mcp_strava report daily

# Weekly digest
uv run python -m mcp_strava weekly

# Recent workouts
uv run python -m mcp_strava workouts recent --limit 10

# Analyze the latest workout
uv run python -m mcp_strava workout analyze latest

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

## MCP Boundary

The MCP server is read-only and factual. It does not expose sync, admin, debug, raw SQL, token, or raw Strava API tools. Agents receive metrics and freshness facts, then perform their own interpretation.

## License

Copyright (c) 2026 Maksim Brashchenko.

This project is available for noncommercial use under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). Commercial use requires a separate written commercial license; see [COMMERCIAL.md](COMMERCIAL.md).
