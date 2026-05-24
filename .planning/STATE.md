---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Full-Fidelity Strava Mirror
status: executing
last_updated: "2026-05-24T11:30:33.147Z"
last_activity: 2026-05-24 -- Completed 07-02 dirty invalidation
progress:
  total_phases: 7
  completed_phases: 6
  total_plans: 31
  completed_plans: 27
  percent: 86
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-22)

**Core value:** Preserve the local Strava mirror and keep trusted training analytics working while the service is refactored into clean core, repository, adapter, CLI, and MCP boundaries.
**Current focus:** Phase 7 materialized metrics read model

## Current Position

Phase: 07
Plan: 07-03
Status: Ready to execute next plan
Last activity: 2026-05-24 -- Completed 07-02 dirty invalidation

## Performance Metrics

**Velocity:**

- Total plans completed: 26
- Average duration: 0 min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3 | - | - |
| 02 | 4 | - | - |
| 03 | 4 | - | - |
| 04 | 4 | - | - |
| 05 | 6 | - | - |
| 06 | 4 | - | - |
| 07 | 2 | 54min | 27min |

**Recent Trend:**

- Last 5 plans: n/a
- Trend: Stable

*Updated after each plan completion*
| Phase 01 P01 | 6m | 3 tasks | 18 files |
| Phase 01 P02 | 9m | 3 tasks | 4 files |
| Phase 02 P01 | 2100s | 2 tasks | 9 files |
| Phase 02 P02 | 21m | 2 tasks | 4 files |
| Phase 02 P04 | 41min | 3 tasks | 4 files |
| Phase 05-mcp-http-surface-docker-hardening P05-01 | 8 min | 3 tasks | 6 files |
| Phase 05 P05-02 | 3 min | 2 tasks | 6 files |
| Phase 05 P04 | completed in-session | 4 tasks | 11 files |
| Phase 05 P05 | 12 min | 3 tasks | 9 files |
| Phase 05 P06 | completed in-session | 4 tasks | 6 files |
| Phase 06 P01 | 3300 | 3 tasks | 10 files |
| Phase 06 P02 | 35min | 3 tasks | 5 files |
| Phase 06 P03 | 74min | 3 tasks | 8 files |
| Phase 06 P04 | 6 min | 4 tasks | 12 files |
| Phase 07 P07-01 | 44min | 2 tasks | 7 files |
| Phase 07 P07-02 | 10min | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Phase 1: Start with package/settings boundary before deeper adapter/MCP work.
- Phase 2: Treat `data/strava.db` as durable state with mandatory backup/preflight/parity checks.
- Phase 5: Keep MCP read-only and exclude sync/admin/debug capability surface.
- [Phase 01]: Established src/mcp_strava package boundary and module entrypoint via python -m mcp_strava
- [Phase 01]: Deferred console executable remains enforced with no [project.scripts] entry
- [Phase 02]: Runtime paths no longer execute schema-changing DDL; migration gate owns schema changes.
- [Phase 02]: Expected mirror DB open now fails closed with sqlite URI mode=rw.
- [Phase 02]: Repository boundary implemented with focused methods and AST direct-sqlite guard.
- [Phase 02]: Plan 02-04 enforces explicit DB safety commands and repository-backed sync writes.
- [Phase 05-mcp-http-surface-docker-hardening]: Use final MCP tool ids only in metric registry exposure. — Matches D-03 and blocks accidental tool-id drift.
- [Phase 05-mcp-http-surface-docker-hardening]: Exclude interpretation labels and preserve numeric/model metrics only. — Implements D-02 and D-18 by keeping MCP factual.
- [Phase 05]: 05-02 explicit metric projection for get_fitness_state payloads — Avoid serialize-then-filter of report outputs
- [Phase 05]: 05-02 closed safety warning code table — Keep warning contract machine-readable and bounded
- [Phase 05]: MCP HTTP surface restricted to exact five read-only metric tools. — Enforces D-03/D-06 and prevents sync/admin/debug/raw exposure.
- [Phase 05]: just test now runs through uv-managed python3. — Ensures pinned MCP SDK dependency resolves during full test execution.
- [Phase 05]: Docker runtime defaults use expose-only compose networking with no host ports by default.
- [Phase 05]: Container startup now fails closed through deploy preflight before MCP HTTP server exec.
- [Phase 05]: prepare_runtime writes canonical live.env paths under /opt/docker/mcp-strava for live CLI/admin alignment.
- [Phase 05]: Gateway live-path checks allow dry-run but require --apply + --confirm-live-gateway for mutation.
- [Phase 05]: Gateway registration mutates catalog/compose atomically with rollback restart on failure.
- [Milestone v1.1]: Make Strava stream mirroring lossless-normalized; analytics columns become hot-path projections, not the only stored copy.
- [Milestone v1.1]: Unify mixed GPS storage formats locally before relying on track data as a clean mirror surface.
- [Phase 06]: SQLite remains the primary mirror database; DuckDB is deferred as a possible future analytics/read-model layer.
- [Phase 06]: SQLite user_version advanced to 3 with lossless stream inventory — Phase 06-01 requirements MIRROR-01/STREAM-02 require stream metadata and extra channel retention.
- [Phase 06]: Schema inventory is version-aware by PRAGMA user_version — Keeps v3 latlng contract separate from reserved v4 migration scope.
- [Phase 06]: mirror-coverage is admin-only — Operational coverage controls must not cross into product/MCP boundaries.
- [Phase 06]: Use time as canonical point index for all-channel projection and tolerate uneven channel lengths. — Keeps refresh ingest resilient to sparse/uneven channels without dropping activity-level ingestion.
- [Phase 06]: Persist requested-but-absent channels as unavailable metadata rather than failing stream ingestion. — Preserves observability and supports planned backfill/merge flows without destructive replacement behavior.
- [Phase 06]: Phase 06-03 canonical runtime stream schema is v4 with lat/lng plus values_json and no streams.latlng
- [Phase 06]: Migration reports malformed/conflict counts from pre-migration scan while preserving scalar GPS precedence
- [Phase 06]: Stream-channel backfill runs only for activities with existing stream rows and streams endpoint only.
- [Phase 06]: Daily refresh and legacy backfill reject stream-channel backfill checkpoints explicitly.
- [Phase 06]: Runtime preflight accepts v3 intermediate and enforces v4 as final no-latlng schema.
- [Phase 07]: Runtime schema target is now user_version=5 for read-model tables.
- [Phase 07]: Pre-Phase-7 backups use a pinned filename class and are excluded from ordinary retention pruning.
- [Phase 07]: Dirty invalidation is owned by repository source-write methods, not refresh orchestration.
- [Phase 07]: Non-semantic timestamp and batch fields are excluded from source hashes.

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 7 must keep raw Strava mirror as source of truth while materializing derived facts for MCP latency.
- Derived facts require source revision/hash, metric version, dirty queue, and transactional invalidation.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-05-24T11:30:33.135Z
Stopped at: Completed 07-02-PLAN.md
Resume file: None

## Quick Tasks Completed

| Quick Task | Date | Summary |
|------------|------|---------|
| 260522-ra3 set default Strava mirror refresh cadence to one hour | 2026-05-22 | `.planning/quick/260522-ra3-set-default-strava-mirror-refresh-cadenc/260522-ra3-SUMMARY.md` |
| 260524-kiy add persistent MCP test client and tool-call logging | 2026-05-24 | `.planning/quick/260524-kiy-add-persistent-mcp-test-client-tool-call/260524-kiy-SUMMARY.md` |
