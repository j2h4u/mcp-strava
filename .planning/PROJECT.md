# mcp-strava

## What This Is

mcp-strava is a local Strava mirror and training analytics service for one primary user. Today it is a Python CLI over a SQLite database populated from Strava; this project refactors it into a service-shaped codebase with core training logic, a SQLite repository, a Strava API adapter, and separate CLI and HTTP MCP control surfaces.

The long-term shape is a Docker-packaged local MCP server connected to the user's local MCP network. The MCP surface should expose workouts, analytics, reports, and recommendations, not operational sync/admin controls.

## Core Value

Preserve the local Strava mirror and keep trusted training analytics working while the service is refactored into clean core, repository, adapter, CLI, and MCP boundaries.

## Requirements

### Validated

- [x] Local SQLite mirror stores Strava activities, streams, athlete zones, sync history, and kudos in `data/strava.db` — existing
- [x] Strava OAuth refresh-token flow and direct API fetching support activity summaries, details, streams, zones, athlete stats, gear, and kudos — existing
- [x] Incremental sync and backfill can populate local Strava data while respecting API rate limits — existing
- [x] Daily report computes recent activity panorama, Banister form, ACWR, progressive signal, weekly plan, recommendations, and safety warnings — existing
- [x] Weekly analytics and trend views compute rolling load, efficiency, sport summaries, and form trends — existing
- [x] CLI commands provide current access to activities, report, weekly digest, trends, sync, backfill, raw Strava calls, SQL, sync logs, and kudos — existing
- [x] Smoke tests run through `just test` and cover imports, pure model functions, daily report, metrics helpers, analytics helpers, and sport registry behavior — existing

### Active

- [ ] Refactor the codebase into an installable Python package with explicit settings for database path, environment, Strava credentials, and runtime mode
- [ ] Separate core/domain training logic from SQLite, Strava HTTP calls, CLI formatting, and MCP transport concerns
- [ ] Introduce a data-preserving SQLite repository layer with schema versioning, migration preflight, and backup safeguards before destructive changes
- [ ] Introduce a Strava API adapter that owns OAuth refresh, request execution, rate-limit handling, retries, and payload parsing
- [ ] Introduce application services/use cases for reports, activity queries, analytics, recommendations, and mirror freshness decisions
- [ ] Replace the current CLI with a clean command surface over application services; command and JSON compatibility with the old CLI is not required
- [ ] Add an HTTP MCP server skeleton using the modern MCP HTTP transport and read-only user-facing tools for workouts, analytics, reports, and recommendations
- [ ] Keep sync, backfill, raw API calls, arbitrary SQL, and sync logs out of the MCP tool surface
- [ ] Define automatic mirror refresh policy: at least once daily, plus staleness checks inside core/application logic when user-facing requests are served
- [ ] Prepare Docker packaging and local MCP-gateway integration boundaries without making container rollout the first milestone

### Out of Scope

- Preserving old CLI command names or exact JSON response shapes — there are no external compatibility obligations
- Exposing `sync`, `backfill`, `raw`, `sql`, or sync-log tools through MCP — MCP should expose user-facing training capabilities only
- Treating the SQLite database as disposable cache — it is a local Strava mirror and must be preserved through refactors and migrations
- Public multi-user SaaS, account management, or hosted internet exposure — this is a local service for one primary user
- Replacing Strava as the source of truth for activity data — the local database mirrors Strava for analytics and resilience
- Reworking the training model itself before architecture boundaries are clean — model improvements can follow once the service is structured

## Context

The current codebase lives under `scripts/` and uses a standard-library-only Python runtime. The existing architecture is a CLI dispatcher in `scripts/cli.py` plus library modules in `scripts/strava_lib/` for sync, SQLite, metrics, training models, daily reports, weekly analytics, trends, and dataclass contracts.

The existing SQLite database at `data/strava.db` is valuable. It contains data that took a long time to fetch under Strava rate limits, so migrations must be conservative: backup first, inspect current schema, migrate incrementally, and verify row counts and core reports after changes.

The desired architecture is not an API wrapper over Strava. It is a local mirror plus analytics core. Sync is infrastructure and policy, not an agent-facing action. MCP clients should ask questions about training and analytics; the core decides whether the mirror is fresh enough and whether background refresh policy needs attention.

Existing codebase concerns that should shape the roadmap:

- `scripts/strava_lib/db.py` mixes SQLite lifecycle, schema migration, `.env` token storage, OAuth refresh, Strava HTTP requests, and TRIMP queries.
- `scripts/strava_lib/sync.py` mixes sync orchestration, API retry/rate-limit behavior, persistence writes, and stderr progress output.
- Schema changes are inline `ALTER TABLE` checks rather than versioned migrations.
- `.env` is a mutable plaintext token store.
- `cmd_sql` is intentionally local-only and must not become remote/MCP-accessible.
- Current tests are smoke-oriented; migration, sync retry, OAuth, freshness policy, and MCP transport need focused coverage as the refactor proceeds.

## Constraints

- **Data preservation**: Existing `data/strava.db` must not be deleted or overwritten during refactor; schema work requires backup/preflight/verification.
- **Rate limits**: Strava API calls are expensive and rate-limited; avoid plans that require full resync unless explicitly approved.
- **MCP boundary**: MCP exposes workouts, analytics, reports, and recommendations only; operational sync/admin/debug capabilities stay below the MCP surface.
- **Sync policy**: The local mirror should refresh automatically at least once per day; request-time freshness checks belong in core/application logic, not in MCP tool design.
- **Deployment target**: Future runtime should fit Docker and the local MCP gateway/network, but the first milestone should establish clean service boundaries before full rollout.
- **Local-first security**: Default HTTP serving must be local/container-network safe and avoid public unauthenticated exposure.
- **Testing**: Existing behavior must remain verifiable with `just test`; new boundaries need targeted tests for repositories, migrations, freshness, and MCP tools.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Refactor first for v1 | Clean boundaries prevent CLI/MCP surfaces from cementing the current coupling | — Pending |
| v1 includes CLI parity at capability level plus MCP HTTP skeleton | Gives a vertical proof of the new architecture without forcing full MCP coverage immediately | — Pending |
| Do not preserve exact old CLI names or JSON formats | The project has no external compatibility obligations, so cleanup is allowed | — Pending |
| Preserve existing Strava data as durable mirror state | Refetching is slow and rate-limited; data loss would be costly | — Pending |
| MCP must not expose sync/admin/debug tools | Agents should consume training insight, not operate infrastructure controls | — Pending |
| Sync is automatic/background/core policy | The local mirror should stay fresh without making sync an MCP user action | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `$gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `$gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-20 after initialization*
