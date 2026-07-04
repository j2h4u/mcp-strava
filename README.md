# Coach's view of your training

Give an AI agent a coach's view of your training over your own Strava data, using a local mirror and your active Strava API access.

`mcp-strava` connects your Strava account to an AI agent so it can act as your coach and sports physiologist: it reads your real training history and answers questions like "am I overtraining?", "how does this month compare to last?", or "what should this week look like?" — grounded in your actual workouts, not guesses.

`mcp-strava` uses Strava's public API through your own API application. As of Strava's June 2026 developer-program changes, Standard Tier API access requires an active Strava subscription or a Strava-provided grace period; Extended Access Tier applications are handled separately by Strava. A free Strava account alone is no longer enough for API refresh.

## What You Can Use It For

- **Daily training brief:** current fitness state, recent workouts, load, form, freshness, and notable data gaps.
- **Weekly digest:** weekly load, volume, efficiency, sport breakdowns, current-week workouts, and current-vs-previous week trends.
- **Period comparison:** compare two arbitrary date ranges across distance, training impulse (TRIMP), time, elevation, HR, cardiac cost, drift, recovery, and model-state metrics.
- **Training trends:** see how your training evolves over time — by day, week, month, year, or all-time, overall or per sport.
- **Workout analysis:** inspect one workout with factual intensity, heart-rate, drift, recovery, elevation, kudos, and gear facts when available.
- **Fitness projection:** simulate named load scenarios to see projected fitness, fatigue, and form through a target date.

## Why Local

Instead of proxying every question to Strava on demand, `mcp-strava` builds a full local mirror of your Strava history and serves the agent from that. Once your supported history is mirrored, your training facts are queryable on your machine, repeatable across runs, and available for custom analysis without spending API quota on every prompt.

That choice gives you:

- A durable local copy of activities, streams, kudos, gear facts, and derived read-model facts.
- Fast historical questions, including daily, weekly, monthly, all-time, and per-sport aggregates.
- Reproducible metrics such as training impulse (TRIMP), fitness, fatigue, form, acute:chronic workload ratio (ACWR), cardiac drift, recovery, and sport-efficiency summaries.

**How it compares to the official connector.** Strava [announced an official MCP connector for Claude](https://press.strava.com/articles/strava-launches-mcp-connector) on June 1, 2026, providing read-only access to training history, streams, GPS, power, clubs, and events for Strava subscribers. `mcp-strava` is the self-hosted alternative: it keeps a local mirror on your machine, uses your own API application, and adds prepared aggregate bundles and CLI reports on top. It still depends on whatever Strava API access your account and application tier currently have.

## MCP Tools

| Tool | Use it for |
|---|---|
| `get_fitness_state` | Current load, fitness, fatigue, form, acute:chronic workload ratio (ACWR), freshness, and model context. |
| `list_workouts` | Recent or filtered workouts with factual volume and intensity metrics. |
| `get_workout_detail` | Detailed metrics for a specific workout id. |
| `compare_periods` | Side-by-side date-range comparison, optionally filtered by sport. |
| `project_fitness_state` | Forward fitness-state projections for training-load scenarios. |
| `get_training_aggregates` | Bucketed aggregate facts for dashboards, digests, and custom analysis. Ships prepared metric bundles for common views (daily brief, weekly digest, sport efficiency, and more). |

## Ready-Made Reports

| Surface | Command or prompt | What it returns |
|---|---|---|
| CLI daily brief | `uv run python -m mcp_strava report daily` | Daily facts for current state, recent workouts, 14-day load, sport mix, freshness, and read-model status. |
| CLI weekly digest | `uv run python -m mcp_strava weekly` | Weekly load, volume, efficiency, sport breakdowns, current-week activities, and week-over-week trends. |
| MCP daily prompt | `strava_daily_training_brief` | A daily brief scenario backed only by factual MCP metrics. |
| MCP weekly prompt | `strava_weekly_training_digest` | A weekly digest scenario using period-comparison metrics. |
| MCP shoe watchdog | `strava_shoe_mileage_watchdog` | Shoe and gear mileage facts for replacement review. |

## How It Works

- Mirrors Strava activities, streams, kudos, and gear facts into DuckDB.
- Materializes read-model facts for fast MCP tool calls.
- Returns freshness, completeness, warnings, and rationale with product responses so agents know what evidence they are using.

## Requirements

- Python 3.14+
- `uv`
- Docker with Compose
- `just`
- Active Strava API access and a Strava API application for OAuth credentials

## First-Time Strava Setup

This project stores Strava credentials in a local env file, not in a keychain. Treat this file as secret material and keep it outside git.

Strava's current Developer Program requires a subscription for Standard Tier API access. If the Docker healthcheck reports `strava_application_inactive`, verify the application tier and subscription/grace status in the [Strava API settings dashboard](https://www.strava.com/settings/api).

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

For local development, copy the tracked template and fill the values in `.env`:

```bash
cp .env.example .env
$EDITOR .env
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

## Strava API Access Notes

`mcp-strava` currently syncs through these public Strava API surfaces: athlete activities, activity details, activity streams, and activity kudos. It does not use the Club endpoints or Segment Explore endpoint that Strava scheduled for September 1, 2026 deprecation.

Strava has announced a future API base-URL migration from `https://www.strava.com/api/v3` to `https://api-v3.strava.com`. Their changelog says the new base URL becomes available on January 4, 2027, and the old base URL is due for retirement on June 1, 2027. Until the new host is live, keep using the current base URL. `mcp-strava` already sends data API access tokens in the `Authorization: Bearer ...` header.

Live refresh is API-only. If Strava disables API access for the configured application, the existing local DuckDB mirror remains usable for read-only analytics, but this project does not document or support a non-API refresh path.

## Local Docker Usage

```bash
just runtime
```

This builds the image, starts the `mcp-strava` container, waits for health, and runs a direct MCP smoke test against the product server at `http://127.0.0.1:8080/mcp`.

## Configuration

A local run needs no configuration beyond your Strava credentials and resting heart rate. Server settings (paths, host/port, prompt language, refresh behavior, security allowlists) are environment variables with sensible defaults — see [docs/tech/configuration.md](docs/tech/configuration.md).

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

# Static quality gate: format, lint, types, imports, workflows, compile, dead code
just check

# Unit tests only
just unit

# Opt-in debt gate: type-check tests without making verify depend on it yet
just typecheck-tests

# Runtime validation: Docker build/start, MCP smoke
just runtime

# Full local validation before claiming completion
just verify

# Full MCP smoke against the running Docker service
just mcp-smoke-full

# Read-model latency gate
just mcp-read-model-perf

# List exposed MCP tools
just mcp-list-tools
```

## Runtime State

Live Docker state is split — the DuckDB mirror lives under `/srv` (data separated from the deploy dir), the secret env stays beside the compose under `/opt/docker`:

| Path | Purpose |
|---|---|
| `/srv/mcp-strava/data/strava.duckdb` | DuckDB mirror and read-model facts |
| `/opt/docker/mcp-strava/.env` | Strava OAuth credentials + resting-HR (mounted with `.env.lock`) |

The mirror path is instance config, not source: override it with `MCP_STRAVA_DATA_DIR` in an untracked `deploy/.env` (default `/srv/mcp-strava/data`).

## MCP Boundary

The MCP server is read-only and factual. It does not expose sync, admin, debug, raw SQL, token, or raw Strava API tools. Agents receive metrics and freshness facts, then perform their own interpretation.

## Documentation

**Agent startup**
- [Agent & project notes](AGENTS.md) — read this first for repo constraints, planning route, and verification gates.
- [.planning/PROJECT.md](.planning/PROJECT.md) — current milestone/project status and active constraints.
- [.planning/STATE.md](.planning/STATE.md) — current state ledger.
- [.planning/codebase/ARCHITECTURE.md](.planning/codebase/ARCHITECTURE.md) — current architecture map.
- [.planning/codebase/CONCERNS.md](.planning/codebase/CONCERNS.md) — current open concerns and closed items.
- [.planning/milestones/](.planning/milestones/) — milestone archive and completed phase history.
- [.planning/research/SUMMARY.md](.planning/research/SUMMARY.md) — historical research summary; useful context, not the current stack contract.

**Usage**
- [Configuration](docs/tech/configuration.md) — server environment variables and their defaults.
- [Strava API access notes](docs/tech/strava-api-access.md) — subscription/tier requirements, endpoint impact, and the 2027 base-URL migration.

**Operations**
- [Deployment runbook](docs/tech/deployment.md) — gateway registration, DuckDB compaction, rollback, secret handling.

**Reference**
- [Strava Kudos API field notes](docs/tech/kudos-api.md) — endpoint behavior for kudos data.

**Sport science & methodology** — cardiac cost and cardiac drift are different metrics, tracked independently; see each file's scope note.
- [Cardiac cost: cross-activity normalization research](docs/sport/cardiac-cost-normalization-research.md) — why cardiac cost is tracked per sport, not normalized across activities.
- [Cardiac drift: steady-state requirement](docs/sport/cardiac-drift-steady-state.md) — why decoupling needs a constant pace to be meaningful.

**Project**
- [Contributing](CONTRIBUTING.md) — contribution workflow.
- [Commercial licensing](COMMERCIAL.md) — terms for commercial use.

**Development**
- [Strava MCP skill definition](skills/SKILL.md) — agent-facing pointer map for the local Strava skill.
- [Expert panel pattern](skills/expert-panel-pattern.md) — multi-expert review process used in this repo.

## License

Copyright (c) 2026 Maksim Brashchenko.

This project is available for noncommercial use under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). Commercial use requires a separate written commercial license; see [COMMERCIAL.md](COMMERCIAL.md).
