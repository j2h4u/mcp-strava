---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Full-Fidelity Strava Mirror
status: executing
last_updated: "2026-05-25T16:51:05.824Z"
last_activity: 2026-05-25
progress:
  total_phases: 8
  completed_phases: 7
  total_plans: 39
  completed_plans: 33
  percent: 85
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-24)

**Core value:** Preserve the local Strava mirror and keep trusted training analytics working while the service is refactored into clean core, repository, adapter, CLI, and MCP boundaries.
**Current focus:** Phase 08 — duckdb-primary-storage-aggregate-analytics-surface

## Current Position

Phase: 08 (duckdb-primary-storage-aggregate-analytics-surface) — EXECUTING
Plan: 3 of 8
Status: Ready to execute
Last activity: 2026-05-25

## Performance Metrics

**Velocity:**

- Total plans completed: 31
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
| 07 | 6 | 247min | 41min |

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
| Phase 07 P07-03 | 8min | 2 tasks | 3 files |
| Phase 07 P07-04 | 78min | 4 tasks | 12 files |
| Phase 07 P07-05 | 45min | 2 tasks | 7 files |
| Phase 07 P07-06 | 62min | 3 tasks | 10 files |
| Phase 08 P08-01 | 7min | 2 tasks | 3 files |
| Phase 08-duckdb-primary-storage-aggregate-analytics-surface P08-02 | 12 min | 3 tasks | 10 files |

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
- [Phase 07]: Materializer runs below MCP and writes metric-versioned SQLite facts from repository dirty rows.
- [Phase 07]: Dirty rows clear only in the same successful transaction as facts and run audit.
- [Phase 07]: Refresh, legacy backfill, and stream-channel backfill now call the same read-model materialization stage below MCP.
- [Phase 07]: Read-model materialization lease renewal must not commit an already-active materializer transaction.
- [Phase 07]: Read-model materialization remains runtime-owned automation only; MCP enforces the exact five product tools rather than a redundant forbidden-name list.
- [Phase 07]: Phase 7 self-UAT passed against Docker MCP with live v5 read-model facts and sub-500ms p95 for all product tools.
- [Quick 260524-v31]: Docker/runtime Python baseline is Python 3.14.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Use admin duckdb-cutover as the local admin storage migration command. — Keeps migration local-admin only and gives later plans a stable command name.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Create the final DuckDB runtime file only after backup, lease, cast, and parity gates pass. — Protects local data and avoids failed cutovers mutating the canonical target path.
- [Phase 08-duckdb-primary-storage-aggregate-analytics-surface]: Allow direct SQLite access outside the SQLite adapter only in the migration-only DuckDB cutover module. — Preserves direct-SQLite guard coverage while allowing stopped-source backup and parity migration reads.

### Roadmap Evolution

- Phase 8 planned: DuckDB Primary Storage & Aggregate Analytics Surface

### Pending Todos

None yet.

### Blockers/Concerns

None currently.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-05-25T16:50:37.390Z
Stopped at: Completed 08-02-PLAN.md
Resume file: None

## Quick Tasks Completed

| Quick Task | Date | Summary |
|------------|------|---------|
| 260522-ra3 set default Strava mirror refresh cadence to one hour | 2026-05-22 | `.planning/quick/260522-ra3-set-default-strava-mirror-refresh-cadenc/260522-ra3-SUMMARY.md` |
| 260524-kiy add persistent MCP test client and tool-call logging | 2026-05-24 | `.planning/quick/260524-kiy-add-persistent-mcp-test-client-tool-call/260524-kiy-SUMMARY.md` |
| 260524-p6j remove read-model materialization admin surface | 2026-05-24 | `.planning/quick/260524-p6j-remove-read-model-materialization-admin-/260524-p6j-SUMMARY.md` |
| 260524-u5f live Phase 7 DB cutover | 2026-05-24 | `.planning/quick/260524-u5f-live-phase-7-db-cutover-backup-opt-docke/SUMMARY.md` |
| 260524-v31 bump Docker/runtime Python baseline to 3.14 | 2026-05-24 | `.planning/quick/260524-v31-bump-docker-runtime-python-baseline-to-3/260524-v31-SUMMARY.md` |
| 260524-xa9 add metric registry calculation descriptions | 2026-05-25 | `.planning/quick/260524-xa9-add-metric-registry-calculation-descript/260524-xa9-SUMMARY.md` |
| 260525-ng3 Hermes prompts and metric polish | 2026-05-25 | `.planning/quick/260525-ng3-hermes-prompts-metric-polish/260525-ng3-SUMMARY.md` |
