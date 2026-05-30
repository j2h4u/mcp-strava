# Roadmap: mcp-strava

## Overview

This roadmap refactors the current CLI-first codebase into a layered service architecture while preserving the existing Strava mirror. The first milestone established package/settings, repository, Strava adapter, application/CLI, MCP, and Docker boundaries. The v1.1 milestone added a full-fidelity mirror layer, DuckDB primary runtime storage, materialized derived metrics, aggregate analytics, and factual product bundles so MCP and CLI reads consume prepared facts instead of recomputing expensive stream-derived metrics on request.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Package Foundation & Settings** - Establish installable package/runtime configuration and keep smoke testing operational. (completed 2026-05-20)
- [x] **Phase 2: SQLite Safety & Repository Layer** - Add migration safety rails and move persistence access behind repository boundaries. (completed 2026-05-21)
- [x] **Phase 3: Strava Adapter & Refresh Runtime** - Isolate Strava transport/token logic and implement resilient policy-driven mirror refresh behavior. (completed 2026-05-21)
- [x] **Phase 4: Application Services & CLI Refit** - Move user-facing analytics/reporting workflows into application services and route CLI through them. (completed 2026-05-21)
- [x] **Phase 5: MCP HTTP Surface & Docker Hardening** - Expose read-only MCP tools and finalize local-safe container/runtime boundaries. (completed 2026-05-22)
- [x] **Phase 6: Full-Fidelity Strava Mirror** - Preserve Strava stream data in lossless normalized SQLite structures, generalize stream ingestion, unify GPS storage, and backfill missing stream channels safely. (completed 2026-05-24)
- [x] **Phase 7: Materialized Metrics Read Model** - Persist derived activity, daily load, model, and rolling-window facts beside the Strava mirror so MCP tools aggregate prepared facts under sub-500ms latency targets. (completed 2026-05-24)
- [ ] **Phase 8: DuckDB Primary Storage & Aggregate Analytics Surface** - Migrate the primary local mirror from SQLite to DuckDB and expose bucketed aggregate analytics for MCP period and metric queries.
- [x] **Phase 9: Product factual bundles and CLI read-model consolidation** - Expose factual daily, weekly, historical, status, kudos, and supported gear facts through shared read-model application services for MCP and CLI. (completed 2026-05-26)

## Phase Details

### Phase 1: Package Foundation & Settings

**Goal**: Developers can install and run the refactored service via a package entrypoint with one typed configuration system, while preserving testability through `just test`.
**Depends on**: Nothing (first phase)
**Requirements**: FOUND-01, FOUND-02, FOUND-03
**Success Criteria** (what must be TRUE):

  1. Operator can install and run the project as a Python package without relying on ad hoc `scripts/` path hacks.
  2. Operator can set DB path, token path, runtime mode, bind settings, and freshness thresholds from one typed settings surface.
  3. `just test` runs successfully after packaging changes and still validates baseline smoke behavior.

**Plans**:

  - [x] `01-01` Package Manifest & Source Layout - Wave 1
  - [x] `01-02` Typed Settings Boundary - Wave 2 *(blocked on Wave 1 completion)*
  - [x] `01-03` Pytest Smoke Workflow - Wave 3 *(blocked on Wave 2 completion)*

### Phase 2: SQLite Safety & Repository Layer

**Goal**: Data is preserved through controlled schema evolution, and application data access is isolated behind a SQLite repository interface.
**Depends on**: Phase 1
**Requirements**: SAFE-01, SAFE-02, SAFE-03, SAFE-04, REPO-01, REPO-02, REPO-03, TEST-01
**Success Criteria** (what must be TRUE):

  1. Before schema-altering changes, operator can run preflight checks confirming schema version, required tables, row counts, and DB readability.
  2. Schema-changing migrations create timestamped `data/strava.db` backups and verify post-migration parity for row counts and key report outputs.
  3. If the expected mirror DB is missing or invalid, service startup fails closed instead of silently creating an empty replacement.
  4. Services can read/write activities, streams, zones, kudos, and sync metadata only through repository methods with WAL/busy-timeout-safe behavior, and missing-HR/stream sessions remain explicit unknowns rather than rest days.

**Plans**:

  - [ ] `02-01` SQLite Safety Gate - Wave 1
  - [ ] `02-02` Repository Contracts & Adapter Methods - Wave 2 *(blocked on Wave 1 completion)*
  - [ ] `02-03` Repository Read Adoption & Load Statuses - Wave 2 *(blocked on Wave 1 completion and repository contracts)*
  - [ ] `02-04` Operator Controls & Boundary Enforcement - Wave 3 *(blocked on Wave 2 completion)*

**Cross-cutting constraints:**

  - Preserve `data/strava.db`; default planning/execution tests must use temp or copied DBs.
  - Schema changes go through explicit preflight, backup, migration, post-check, and parity.
  - Direct SQLite access stays inside adapter/migration tooling, the compatibility bridge, local operator SQL, and narrow tests.

### Phase 3: Strava Adapter & Refresh Runtime

**Goal**: Strava API interactions and token persistence are fully isolated in adapter/runtime layers with resilient, policy-driven mirror refresh.
**Depends on**: Phase 2
**Requirements**: STRAVA-01, STRAVA-02, STRAVA-03, REFRESH-01, REFRESH-02, REFRESH-03, TEST-02
**Success Criteria** (what must be TRUE):

  1. OAuth refresh, retry/rate-limit behavior, request execution, and payload parsing run through a dedicated Strava adapter rather than repository/application logic.
  2. Token persistence is atomic and single-writer safe under concurrent refresh attempts.
  3. Incremental sync resumes from checkpoints after 429/network/partial-fetch interruptions without corrupting mirror state.
  4. Mirror refresh runtime supports same-day idempotent refresh when internally requested, and request-time freshness checks can signal/schedule first-use refresh without exposing sync as a user action.

**Plans**: TBD

### Phase 4: Application Services & CLI Refit

**Goal**: User-facing analytics/report capabilities are delivered by application services and consumed by a clean CLI surface.
**Depends on**: Phase 3
**Requirements**: APP-01, APP-02, APP-03, APP-04, CLI-01, CLI-02, CLI-03, TEST-04
**Success Criteria** (what must be TRUE):

  1. Operator can get daily report, weekly summary, recent workouts, and per-workout analytics from local mirror data without live Strava calls at request time.
  2. Returned analytics include freshness/completeness/warning metadata and recommendation rationale.
  3. CLI exposes report/weekly/workouts/freshness plus sync/backfill/sql/raw/debug operations through the new service stack, with documented replacement mapping for retained capabilities.
  4. Freshness logic is enforced in application services (not interface glue), including factual metadata and lazy first-use refresh signaling behavior.

**Plans**: TBD

### Phase 5: MCP HTTP Surface & Docker Hardening

**Goal**: MCP users can access read-only intent-level training tools over a local-safe HTTP server, with container/runtime boundaries ready for local gateway integration.
**Depends on**: Phase 4
**Requirements**: MCP-01, MCP-02, MCP-03, MCP-04, DOCKER-01, DOCKER-02, DOCKER-03, TEST-03
**Success Criteria** (what must be TRUE):

  1. MCP HTTP server exposes only read-only training tools for workouts/reports/load/readiness/recommendations.
  2. MCP surface does not include sync/backfill/raw/sql/token/admin/sync-log operations, and allowlist tests prove these tools are absent.
  3. MCP responses include freshness and completeness metadata when analytics may be stale or partial.
  4. Container runtime uses a persistent `data/` volume, fails startup on missing/unreadable expected mirror DB, runs non-root by default, and keeps local-safe bind defaults.

**Plans**:

  - [ ] `05-01` Metric Registry & Synthetic Metric Inventory - Wave 1
  - [ ] `05-02` Fitness & Workout Metric Services - Wave 2 *(blocked on Wave 1 completion)*
  - [ ] `05-03` Period Comparison & Fitness Projection Services - Wave 3 *(blocked on Wave 2 completion)*
  - [ ] `05-04` MCP HTTP Server & Tool Allowlist - Wave 4 *(blocked on Wave 3 completion)*
  - [ ] `05-05` Container Runtime & Data Hardening - Wave 5 *(blocked on Wave 4 completion)*
  - [ ] `05-06` Live Gateway Integration & Rollback Smoke - Wave 6 *(blocked on Wave 5 completion)*

### Phase 6: Full-Fidelity Strava Mirror

**Goal**: The SQLite mirror preserves Strava stream channel values and metadata in lossless normalized form before deriving analytics projections, without deleting existing data or forcing a full resync.
**Depends on**: Phase 5
**Requirements**: MIRROR-01, MIRROR-02, STREAM-01, STREAM-02, STREAM-03, GPS-01, GPS-02, COVERAGE-01, BACKFILL-01, TEST-05
**Success Criteria** (what must be TRUE):

  1. Strava activity summaries/details, stream channel values, and stream channel metadata are stored in queryable SQLite structures before projection code filters or transforms them.
  2. Stream ingestion handles every channel returned by Strava, including unknown channel names and channel metadata, while still producing the current analytics columns.
  3. Existing mixed GPS storage is migrated into one canonical representation with backup, preflight, post-check, row-count parity, GPS coverage parity, and analytics parity.
  4. Operator can inspect stream channel, channel metadata, and GPS coverage from Docker/runtime-safe tooling without exposing secrets or broad mirror internals through MCP.
  5. Missing stream channels and channel metadata can be backfilled incrementally and resumably under Strava rate limits without deleting current normalized rows.

**Plans**:

  - [ ] `06-01` Lossless Stream Store & Coverage Inventory - Wave 1
  - [ ] `06-02` Generalized Stream Ingest & Projection - Wave 2 *(blocked on Wave 1 completion)*
  - [ ] `06-03` Canonical GPS Migration - Wave 3 *(blocked on Wave 2 projection contract)*
  - [ ] `06-04` Stream Backfill Runtime & Docker Verification - Wave 4 *(blocked on Wave 3 migration safety)*

**Cross-cutting constraints:**

  - Do not run full Strava resync unless explicitly approved during execution.
  - Back up and verify the live mirror before any schema or data migration.
  - Keep mirror coverage/backfill surfaces out of MCP; MCP remains read-only training metrics only.
  - Keep SQLite as the primary mirror; DuckDB is deferred as a possible future analytics/read-model layer.
  - Prefer lossless normalized stream storage plus derived projections over lossy replacement of the existing `streams` table.

### Phase 7: Materialized Metrics Read Model

**Goal**: Derived training metrics are persisted as versioned SQLite read-model facts and recomputed only when source mirror data or metric algorithms change.
**Depends on**: Phase 6
**Requirements**: READMODEL-01, READMODEL-02, READMODEL-03, READMODEL-04, PERF-01, TEST-06
**Success Criteria** (what must be TRUE):

  1. Activity-level derived metrics such as TRIMP, HR zones, HR recovery, vertical speed, cardiac cost, cardiac drift, HRR, Z5 seconds, and anomaly counts are stored with source provenance and metric-version metadata.
  2. Source mirror writes mark affected activities/days dirty through a durable invalidation contract using `source_hash`, `source_revision`, `metric_version`, and transaction-safe dirty queue semantics.
  3. Refresh runtime materializes activity facts, daily load facts, training model daily state, and rolling period facts after source sync/backfill without exposing recompute/admin controls through MCP.
  4. MCP tools read materialized facts and never scan raw stream rows or recompute Jenks/cardio stream metrics during request handling.
  5. Any single MCP tool completes under a 500 ms p95 target on the current local mirror, with tests and live smoke measuring tool latency.

**Cross-cutting constraints:**

  - Raw Strava mirror remains the source of truth; materialized facts are replaceable derived read models.
  - Migration must back up and parity-check existing DB before adding read-model tables or backfilling facts.
  - Materialized facts must be idempotently recomputable after algorithm-version changes.
  - Missing/stale facts must surface as completeness metadata, not request-time stream recomputation in MCP.
  - `just test` remains a fast Docker MCP transport smoke; full performance E2E is a separate explicit gate until read-model work lands.

**Plans:** 6/6 plans complete
Plans:

  - [x] `07-01-PLAN.md` — SQLite v5 read-model schema, indexes, migration safety, and pinned pre-Phase-7 backup
  - [x] `07-02-PLAN.md` — Atomic source-state hashing and dirty queue invalidation for source writes
  - [x] `07-03-PLAN.md` — Materialized activity, daily, training-model, and rolling-window fact pipeline
  - [x] `07-04-PLAN.md` — Refresh/backfill materialization stage, admin command, and MCP boundary preservation
  - [x] `07-05-PLAN.md` — MCP service cutover to fact-only read-model queries with read-model metadata
  - [x] `07-06-PLAN.md` — Query-plan, Docker-first, and warm p95 performance validation gates

### Phase 8: DuckDB Primary Storage & Aggregate Analytics Surface

**Goal**: The local Strava mirror uses DuckDB as the primary runtime database, preserving mirrored data and derived metric facts while enabling native time-bucket, median/quantile, weighted-average, and period aggregation queries for MCP tools.
**Depends on**: Phase 7
**Requirements**: TBD
**Success Criteria** (what must be TRUE):

  1. Existing live SQLite mirror data is backed up, migrated into a DuckDB database, and parity-checked for source rows, stream coverage, kudos, refresh state, and derived metric facts.
  2. Runtime repository, refresh, migration, preflight, healthcheck, Docker, and CLI paths use DuckDB as primary storage rather than SQLite, with SQLite retained only as migration input/backup.
  3. Aggregate analytics can answer day/week/month/year/all-time bucketed metric queries using DuckDB-native SQL primitives such as time buckets, medians/quantiles, weighted averages, and grouped distributions.
  4. `compare_periods` is implemented over the same aggregate query layer as the general aggregate MCP tool, preserving freshness/completeness metadata and avoiding raw SQL exposure through MCP.
  5. Python runtime remains on Python 3.14 and uses the current stable 3.14 patch in Docker where available.

**Cross-cutting constraints:**

  - Preserve the current live data before migration; no Strava full resync is allowed as a substitute for local migration.
  - MCP remains a read-only factual metrics surface; no raw SQL/admin/debug/storage migration tools cross into MCP.
  - Domain-specific metrics such as TRIMP, cardiac cost, drift, HR recovery, fitness, fatigue, and form remain explicit metric facts; DuckDB handles aggregation, not domain interpretation.
  - Avoid a permanent SQLite + DuckDB dual-primary design; any SQLite bridge is transitional migration tooling only.

**Plans:** 7/8 plans executed

Plans:

  - [x] `08-01-PLAN.md` — DuckDB package legitimacy gate and dependency baseline
  - [x] `08-02-PLAN.md` — One-shot SQLite-to-DuckDB migration, pinned backup, parity, and admin cutover command
  - [x] `08-03-PLAN.md` — DuckDB primary repository, read-model materializer, and runtime connection cutover
  - [x] `08-04-PLAN.md` — Single-owner DuckDB runtime topology, healthcheck, refresh, and `/runtime/data/strava.duckdb` Docker path refit
  - [x] `08-05-PLAN.md` — Metric registry aggregate semantics, bundles, denominators, and docs
  - [x] `08-06-PLAN.md` — DuckDB aggregate views/query builders and aggregate application service
  - [x] `08-07-PLAN.md` — `get_training_aggregates` MCP tool and `compare_periods` aggregate-layer rewrite
  - [ ] `08-08-PLAN.md` — Docker-first smoke, MCP smoke, 100 ms p95, live cutover, rollback image tag, and rollback validation

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Package Foundation & Settings | 3/3 | Complete    | 2026-05-20 |
| 2. SQLite Safety & Repository Layer | 4/4 | Complete    | 2026-05-21 |
| 3. Strava Adapter & Refresh Runtime | 4/4 | Complete    | 2026-05-21 |
| 4. Application Services & CLI Refit | 4/4 | Complete    | 2026-05-21 |
| 5. MCP HTTP Surface & Docker Hardening | 6/6 | Complete    | 2026-05-22 |
| 6. Full-Fidelity Strava Mirror | 4/4 | Complete    | 2026-05-24 |
| 7. Materialized Metrics Read Model | 6/6 | Complete    | 2026-05-24 |
| 8. DuckDB Primary Storage & Aggregate Analytics Surface | 7/8 | In Progress|  |
| 9. Product factual bundles and CLI read-model consolidation | 4/4 | Complete    | 2026-05-26 |

### Phase 9: Product factual bundles and CLI read-model consolidation

**Goal:** MCP and CLI product reads expose factual daily, weekly, historical, status, kudos, and supported gear facts from the DuckDB/read-model application layer without adding MCP tools or reviving legacy CLI/recompute paths.
**Requirements**: APP-01, APP-02, APP-03, APP-04, CLI-01, CLI-02, CLI-03, MCP-01, MCP-02, MCP-03, READMODEL-01, READMODEL-04, PERF-01, TEST-03, TEST-04, TEST-06
**Depends on:** Phase 8
**Plans:** 4/4 plans complete

Plans:

- [x] `09-01-PLAN.md` — Windowed historical/status fact contracts and bundle-safe registry queries
- [x] `09-02-PLAN.md` — Shared product factual bundle services with explicit completeness contracts
- [x] `09-03-PLAN.md` — CLI read-model consolidation, replacement paths, and legacy service retirement
- [x] `09-04-PLAN.md` — MCP bundle/completeness smoke, boundary guards, and verification docs

### Phase 10: Materialize unwired training metrics and enforce core/domain storage boundary

**Goal:** Finish the deferred 2026-05-25 decision (quick task 260525-jpo): make `metrics.py` a pure domain module and wire its compute into the read-model materializer so the registered-but-empty metrics (hr_recovery, vertical_speed, cardiac_drift, hrr_pct + rolling medians) are actually computed instead of stored as null/0 — closing the last open PROJECT.md requirement (core/domain separation) and fixing a latent product bug. Full context: see this phase's CONTEXT.md.
**Requirements**: Core/domain separation (PROJECT.md Active); fix unmaterialized registered metrics (260525-jpo preserve-and-fix)
**Depends on:** Phase 9
**Plans:** 4/4 plans complete

Plans:

**Wave 1**

- [x] 10-01-PLAN.md — Extract pure metric functions in metrics.py (calc_hr_recovery/vertical_speed/cardiac_drift/hrr_pct), remove the mcp_strava.db import (TDD)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 10-02-PLAN.md — Extend the import-boundary guard to forbid storage/adapter imports from domain modules
- [x] 10-03-PLAN.md — Wire the pure functions into read_model_materializer._activity_fact so the 13 empty columns are computed (TDD)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 10-04-PLAN.md — Delete dead db.py::get_daily_trimp_history and repair stale tests (test_smoke.py)

### Phase 11: Tidy materializer repository access

**Goal:** Replace the 6 inline-SQL `repo._fetchone`/`repo._fetchall` call sites in `src/mcp_strava/adapters/duckdb/read_model_materializer.py` (≈ lines 43, 64, 259, 356, 378, 386) with named methods on `DuckDBRepository`. Intra-adapter cleanup on the storage side — no behavior change, the full `just test` suite must stay green. Closes code-review finding IN-03 from Phase 10.
**Requirements**: Code quality / boundary hygiene (Phase 10 REVIEW IN-03)
**Depends on:** Phase 10
**Plans:** 1/1 plans complete
Plans:

- [x] 11-01-PLAN.md — Add 6 named DuckDBRepository methods + replace all inline call sites in materializer

### Phase 12: Decouple db.py into focused modules

**Goal:** Split `src/mcp_strava/db.py` (237 lines mixing five concerns: connection management `DbConn`/`ReadConn`/thread-local pool, repository factories, token/OAuth `_CompatTokenProvider`/`refresh_token`, Strava HTTP `api_request`/`get_zones`/`_build_transport`, and clock/sleeper) into focused modules — move token/OAuth into a dedicated auth module, route HTTP through `adapters/strava`, fold connection management into `adapters/duckdb/connection` — then migrate all callers. `just test` must stay green. This is the last meaningful coupling hotspot after Phase 10.
**Requirements**: Core/domain separation — residual `db.py` coupling (extends PROJECT.md core/domain goal)
**Depends on:** Phase 10**Plans:** 1/5 plans executed

- [ ] TBD (run /gsd-plan-phase 12 to break down)

### Phase 13: Lint and type-check cleanup (ruff residual + pyright)

**Goal:** Clear the deferred lint/type findings surfaced when ruff + pyright were introduced in Phase 11 side-work (tooling: commit `bcfc0e2`; safe autofixes already applied in `b27a167`; the one real bug — F821 missing `Path` import — fixed in `859859b`). Scope: (1) **ruff F401** unused-import (~40) — separate genuinely-dead imports (remove) from re-exported public names in namespace modules like `constants.py` (protect with `__all__`; do NOT blind-remove — that broke importers in the Phase 11 trial). (2) **~17 manual ruff fixes**: bugbear `B905` (zip `strict=`), `B904` (`raise … from`), `B007`, `B017`; pyupgrade `UP031` (printf→format), `UP035` (deprecated-import). (3) **`E402`** (3 import-not-at-top) — decide `# noqa` vs intentional late imports. (4) **pyright (~359 errors)** — dominated by DuckDB rows typed `object` flowing into `int()`/`float()`; needs a typing strategy first (a typed `Row`/`Mapping` alias or a pyright mode decision), not blind per-error edits. `just test` and `just lint` must end green; `just check` should pass.
**Requirements**: Code quality / tooling hygiene (ruff + pyright introduced in Phase 11 side-work)
**Depends on:** Phase 11
**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 13 to break down)
