# mcp-strava

## What This Is

mcp-strava is a local Strava mirror and training analytics service for one primary user. It now runs as a service-shaped Python codebase with a DuckDB primary runtime store, a Strava API adapter, shared application/read-model services, and separate CLI and HTTP MCP control surfaces.

The runtime shape is a Docker-packaged local MCP server connected to the user's local MCP network. The MCP surface exposes factual workouts, analytics, reports, and prepared metric bundles, not operational sync/admin controls.

## Core Value

Preserve the local Strava mirror and keep trusted training analytics working while the service is refactored into clean core, repository, adapter, CLI, and MCP boundaries.

## Current State

The v1.1 full-fidelity mirror milestone is complete. The current runtime is
DuckDB-only for product and service paths: local Strava activity data, streams,
kudos, refresh state, and prepared read-model facts live in the DuckDB mirror,
and MCP/CLI product reads consume application services over that mirror.

Phase 14 completed the first metric-platform source-of-truth slice: the
`activity_metric_facts` SQL schema metadata is owned by the metric registry,
DuckDB table DDL is generated from the registry, and late additive activity fact
migrations use registry-rendered SQL behind explicit safety checks.

**Current validated capabilities:**
- DuckDB is the primary runtime mirror and analytical store.
- The single-owner Docker service runs MCP HTTP plus the in-process refresh worker.
- MCP exposes exactly six read-only factual product tools, plus prompt templates.
- CLI product commands route through application services; operational sync/admin/debug stays below MCP.
- Derived activity, daily, model, rolling, aggregate, status, and product bundle facts are prepared in the read model rather than recomputed from raw streams at request time.
- Metric-domain functions are pure and storage-free; repository and adapter boundaries own persistence and Strava I/O.
- `activity_metric_facts` schema generation now comes from the metric registry instead of duplicated hand-written SQL.

## Requirements

### Validated

- [x] Local DuckDB mirror stores Strava activities, streams, athlete zones, sync history, kudos, refresh state, and read-model facts in `data/strava.duckdb` / `/runtime/data/strava.duckdb` — validated through Phases 8-9
- [x] Strava OAuth refresh-token flow and direct API fetching support activity summaries, details, streams, zones, athlete stats, gear, and kudos — existing
- [x] Incremental sync and backfill can populate local Strava data while respecting API rate limits — existing
- [x] Daily report computes recent activity panorama, Banister form, ACWR, progressive signal, weekly plan, recommendations, and safety warnings — existing
- [x] Weekly analytics and trend views compute rolling load, efficiency, sport summaries, and form trends — existing
- [x] CLI commands provide current access to report, weekly digest, workouts, freshness, and namespaced local admin workflows including catchup, compact, SQL, raw Strava calls, logs, and DB checks — validated through Phases 4, 8, and 9
- [x] Smoke tests run through `just test` and cover pytest, Docker build, container health, and MCP product smoke — current full run: 357 passed plus Docker/MCP smoke after Phase 14 UAT
- [x] Refactored runtime is installable as a Python package with `python -m mcp_strava`, `src/mcp_strava` package imports, typed settings for DB/token/runtime/HTTP/freshness, and pytest-backed `just test` — validated in Phase 1
- [x] Historical SQLite migration safety was validated in Phase 2; current DuckDB runtime opens fail-closed through preflight/health checks and keeps all runtime persistence behind the DuckDB adapter
- [x] Strava API adapter owns OAuth refresh, request execution, rate-limit handling, retries, and payload parsing, with refresh runtime checkpoints/backoff/leases — validated in Phase 3
- [x] Lazy first-use mirror freshness policy is represented in application metadata and internal refresh requests without exposing sync as a product/MCP action — validated in Phase 4
- [x] Application services return daily report, weekly summary, recent workouts, per-workout analytics, and freshness envelopes from the local mirror with factual freshness/completeness/warnings/rationale — validated in Phase 4
- [x] CLI has product commands over application services and namespaced local admin/debug workflows with documented replacement mapping — validated in Phase 4
- [x] HTTP MCP server exposes the read-only factual product surface with freshness/completeness metadata, forbidden admin/sync/raw/sql surface tests, and no coaching interpretation — validated in Phase 5 and expanded to the exact six-tool surface by Phase 9
- [x] Docker runtime and gateway integration tooling provide non-root container startup, fail-closed DB preflight, dry-run gateway registration, rollback, and explicit operator confirmation for live gateway mutation — validated in Phase 5
- [x] Strava stream data is preserved in lossless normalized mirror structures before analytics projections are derived — validated in Phase 6 and carried through the DuckDB cutover in Phase 8
- [x] Stream ingestion stores all returned channels, unknown channel values, and channel metadata without a fixed analytics-only allowlist — validated in Phase 6
- [x] Mixed GPS stream storage is migrated into canonical `lat`/`lng` columns with backup, preflight, post-check, row-count parity, GPS parity, and analytics parity — validated in Phase 6
- [x] Local admin tooling reports stream/channel/GPS coverage and supports resumable, rate-limit-aware stream-channel backfill without exposing those controls through MCP — validated in Phase 6
- [x] Derived activity, daily load, training-model, and rolling-window facts are persisted as versioned DuckDB read-model data with source provenance — validated in Phase 7 and carried through the DuckDB cutover in Phase 8
- [x] Source mirror writes invalidate derived metrics through durable `source_hash`, `source_revision`, `metric_version`, and dirty-queue semantics — validated in Phase 7
- [x] Refresh and backfill runtime materializes read-model facts below the MCP boundary without exposing recompute/admin tools — validated in Phase 7
- [x] MCP metric tools read prepared facts and pass the sub-500 ms warm p95 target on the live Docker runtime — validated in Phase 7
- [x] DuckDB is the primary runtime storage for MCP/CLI aggregate analytics, with cutover/parity checks, single-owner Docker runtime behavior, and read-model-backed aggregate queries — validated in Phase 8
- [x] MCP and CLI product reads expose factual daily, weekly, historical, status, kudos, and supported gear facts from shared DuckDB/read-model application services, while MCP remains the exact six-tool product surface — validated in Phase 9
- [x] Separate core/domain training logic from SQLite, Strava HTTP calls, CLI formatting, and MCP transport concerns — validated in Phase 10 (`metrics.py` is a pure domain module with an AST import-boundary guard; the previously-unwired metrics now materialize from real streams)
- [x] Metric-platform fact schema metadata for `activity_metric_facts` is registry-owned, runtime DuckDB DDL is generated from the registry, and late additive activity fact migrations use registry-rendered SQL with safety guards — validated in Phase 14

### Active

- None — all milestone v1.1 requirements validated.

### Out of Scope

- Preserving old CLI command names or exact JSON response shapes — there are no external compatibility obligations
- Exposing `sync`, `backfill`, `raw`, `sql`, or sync-log tools through MCP — MCP should expose user-facing training capabilities only
- Treating the DuckDB database as disposable cache — it is the local Strava mirror and must be preserved through refactors and migrations
- Public multi-user SaaS, account management, or hosted internet exposure — this is a local service for one primary user
- Replacing Strava as the source of truth for activity data — the local database mirrors Strava for analytics and resilience
- Reworking the training model itself before architecture boundaries are clean — model improvements can follow once the service is structured

## Context

The current codebase lives under `src/mcp_strava/` and uses a standard-library-oriented Python runtime. The active architecture is a CLI dispatcher and MCP HTTP interface over application services, a DuckDB adapter/repository/materializer, a Strava adapter, refresh runtime modules, pure metric/training modules, and shared dataclass contracts.

The existing DuckDB database at `data/strava.duckdb` locally and `/runtime/data/strava.duckdb` in the container is valuable. It contains data that took a long time to fetch under Strava rate limits, so schema work must remain conservative. DuckDB preflight, health checks, admin wrappers, and compaction tooling protect the single-owner runtime.

The desired architecture is not an API wrapper over Strava. It is a local mirror plus analytics core. Sync is infrastructure and policy, not an agent-facing action. MCP clients should ask questions about training and analytics; the core/application layer decides whether the mirror is fresh enough and returns freshness/completeness metadata while refresh work stays below MCP.

The v1.1 milestone tightened the mirror contract. Strava stream data is now retained in lossless normalized form, DuckDB is the primary runtime store, and derived training metrics are materialized into versioned read-model facts so MCP and CLI product reads can consume prepared factual data instead of recomputing expensive stream-derived metrics on request.

Existing codebase concerns that should shape the next roadmap:

- `src/mcp_strava/adapters/duckdb/repository.py` remains the largest module and owns many query/write concerns.
- `src/mcp_strava/metric_registry.py` is intentionally central but large; future metric-platform work should split source-of-truth concerns carefully only after registry ownership is stable.
- `src/mcp_strava/sync.py` remains a compatibility/public refresh API around newer refresh runtime modules.
- `.env` is a mutable plaintext token/config store and must not leak into logs, docs, summaries, or chat output.
- `cmd_sql` is intentionally local-only and must not become remote/MCP-accessible.
- MCP HTTP currently relies on local/container network boundaries rather than per-request authentication.

## Constraints

- **Data preservation**: The DuckDB mirror `data/strava.duckdb` / `/runtime/data/strava.duckdb` must not be deleted or overwritten during refactor; schema work requires backup/preflight/verification.
- **Rate limits**: Strava API calls are expensive and rate-limited; avoid plans that require full resync unless explicitly approved.
- **MCP boundary**: MCP exposes factual workouts, analytics, reports, projections, and prepared aggregates only; operational sync/admin/debug capabilities stay below the MCP surface.
- **Sync policy**: The local mirror refreshes through internal runtime policy and currently defaults to a fixed hourly cadence; MCP clients must remain unaware of sync controls.
- **Deployment target**: Runtime fits Docker and the local MCP gateway/network; default serving should remain local/container-network safe.
- **Local-first security**: Default HTTP serving must be local/container-network safe and avoid public unauthenticated exposure.
- **Testing**: Existing behavior must remain verifiable with `just test`; new boundaries need targeted tests for repositories, migrations, freshness, and MCP tools.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Refactor first for v1 | Clean boundaries prevent CLI/MCP surfaces from cementing the current coupling | Validated through Phase 4 package, repository, adapter, application-service, and CLI boundaries |
| v1 includes CLI parity at capability level plus MCP HTTP skeleton | Gives a vertical proof of the new architecture without forcing full MCP coverage immediately | CLI capability parity validated in Phase 4; MCP HTTP surface and Docker/gateway boundaries validated in Phase 5 |
| Do not preserve exact old CLI names or JSON formats | The project has no external compatibility obligations, so cleanup is allowed | Validated in Phase 4 with product/admin CLI split and replacement mapping |
| Preserve existing Strava data as durable mirror state | Refetching is slow and rate-limited; data loss would be costly | Validated in Phase 2 with fail-closed open, preflight, backup, migration, and parity gates |
| MCP must not expose sync/admin/debug tools | Agents should consume training insight, not operate infrastructure controls | Product registry excludes admin/debug commands in Phase 4; MCP allowlist and forbidden-tool tests validated in Phase 5 |
| Sync is internal core/runtime policy | The local mirror refreshes through internal runtime policy; MCP still must not expose sync controls | Validated in Phase 4 freshness metadata and reinforced by the runtime refresh worker |
| Prefer development efficiency over intermediate operability | The service does not need to stay fully usable during refactor; it only needs to be operational after the milestone is complete | Validated through Phase 4 refactor sequencing |
| Lossless normalized mirror for v1.1 | The local database should preserve Strava stream information in structured queryable form without making permanent raw JSON retention the main contract | Planned for v1.1 Full-Fidelity Strava Mirror |
| Materialized read model below MCP | MCP tools should remain factual/product-only while refresh/backfill automation owns recomputation and invalidation | Validated in Phase 7 with v5 read-model tables, dirty queue, runtime materialization, and live Docker p95 smoke |
| Performance gates are explicit | Normal Docker smoke should stay fast, while the full warm p95 check remains available as a deliberate acceptance gate | Validated in Phase 7 through `just mcp-read-model-perf` |
| DuckDB primary runtime store | Aggregate analytics and time-bucket style product reads fit DuckDB better than SQLite row scans | Validated in Phase 8 with DuckDB cutover, runtime routing, Docker ownership, aggregate queries, and parity checks |
| Product factual bundles stay inside existing MCP surface | Agents need richer prepared facts, but not additional admin/debug/sync tools or coaching interpretation from this service | Validated in Phase 9 through shared bundle services, six-tool MCP allowlist, direct bundle smoke, and CLI read-model consolidation |
| Domain metric math is pure and storage-free | Keeping training-metric functions free of storage/HTTP imports completes core/domain separation and makes the metrics unit-testable without a DB | Validated in Phase 10 — `metrics.py` imports only constants/types/cardiac_drift, an AST guard forbids storage imports, and the four pure functions now feed the read-model materializer |
| Activity fact schema metadata is registry-owned | Duplicated hand-written `activity_metric_facts` SQL would drift from metric registry semantics; registry SQL metadata now renders table DDL and late-column ADD COLUMN SQL while schema.py keeps explicit migration policy | Validated in Phase 14 with generated DDL, generated additive migration SQL, safety guards, temp-DuckDB parity tests, and full `just test` Docker smoke |

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
*Last updated: 2026-06-01 after documentation audit — current state refreshed after Phase 14 UAT*
*Completion updated: 2026-05-31 after Phase 14 UAT — registry-owned `activity_metric_facts` schema slice validated*
