# Roadmap: mcp-strava

## Overview

This roadmap refactors the current CLI-first codebase into a layered service architecture while preserving the existing `data/strava.db` mirror. The first milestone established package/settings, repository, Strava adapter, application/CLI, MCP, and Docker boundaries. The v1.1 milestone adds a full-fidelity mirror layer so raw Strava payloads are retained before analytics projections are derived.

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
- [ ] **Phase 6: Full-Fidelity Strava Mirror** - Preserve raw Strava activity and stream payloads, generalize stream ingestion, unify GPS storage, and backfill missing raw stream data safely.

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
**Goal**: The SQLite mirror preserves raw Strava payloads before deriving normalized analytics projections, without deleting existing data or forcing a full resync.
**Depends on**: Phase 5
**Requirements**: MIRROR-01, MIRROR-02, STREAM-01, STREAM-02, STREAM-03, GPS-01, GPS-02, COVERAGE-01, BACKFILL-01, TEST-05
**Success Criteria** (what must be TRUE):
  1. Raw Strava summary/detail/stream payloads are stored with endpoint, request, fetch, hash, and schema metadata before projection code filters or transforms them.
  2. Stream ingestion handles every channel returned by Strava, including unknown channel names and channel metadata, while still producing the current analytics columns.
  3. Existing mixed GPS storage is migrated into one canonical representation with backup, preflight, post-check, row-count parity, GPS coverage parity, and analytics parity.
  4. Operator can inspect raw payload, stream channel, and GPS coverage from Docker/runtime-safe tooling without exposing secrets or broad raw data through MCP.
  5. Missing raw stream payloads can be backfilled incrementally and resumably under Strava rate limits without deleting current normalized rows.
**Plans**:
  - [ ] `06-01` Raw Payload Store & Coverage Inventory - Wave 1
  - [ ] `06-02` Generalized Stream Ingest & Projection - Wave 2 *(blocked on Wave 1 completion)*
  - [ ] `06-03` Canonical GPS Migration - Wave 3 *(blocked on Wave 2 projection contract)*
  - [ ] `06-04` Raw Backfill Runtime & Docker Verification - Wave 4 *(blocked on Wave 3 migration safety)*

**Cross-cutting constraints:**
  - Do not run full Strava resync unless explicitly approved during execution.
  - Back up and verify the live mirror before any schema or data migration.
  - Keep raw mirror/audit surfaces out of MCP; MCP remains read-only training metrics only.
  - Prefer raw retention plus derived projections over lossy replacement of the existing `streams` table.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Package Foundation & Settings | 3/3 | Complete    | 2026-05-20 |
| 2. SQLite Safety & Repository Layer | 4/4 | Complete    | 2026-05-21 |
| 3. Strava Adapter & Refresh Runtime | 4/4 | Complete    | 2026-05-21 |
| 4. Application Services & CLI Refit | 4/4 | Complete    | 2026-05-21 |
| 5. MCP HTTP Surface & Docker Hardening | 6/6 | Complete    | 2026-05-22 |
| 6. Full-Fidelity Strava Mirror | 0/4 | Planned | |
