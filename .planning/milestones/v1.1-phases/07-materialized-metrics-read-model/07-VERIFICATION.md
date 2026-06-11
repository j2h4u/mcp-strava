---
status: passed
phase: 07-materialized-metrics-read-model
verified: 2026-06-11T11:10:00Z
method: retrospective synthesis (UAT + VALIDATION + SECURITY already verified; VERIFICATION.md backfilled)
must_haves_verified: 5
must_haves_total: 5
score: 5/5
source_artifacts:
  - 07-UAT.md (status: complete, 7/7 passed, 0 issues)
  - 07-VALIDATION.md (status: verified)
  - 07-SECURITY.md (status: verified, threats_open: 0)
---

# Phase 7: Verification Report — Materialized Metrics Read Model

**Goal:** Derived training metrics are persisted as versioned read-model facts and
recomputed only when source mirror data or metric algorithms change.

**Verdict:** PASSED (5/5 success criteria verified). This VERIFICATION.md is a
retrospective backfill: the phase was closed 2026-05-24 via the UAT + validate +
secure path (all three artifacts verified) before VERIFICATION.md was a standard
execute-phase output. No re-testing was required — the existing artifacts already
establish goal achievement, and the full suite remains green at HEAD.

## Success Criteria

| # | Criterion | Evidence | Status |
|---|-----------|----------|--------|
| 1 | Activity-level derived metrics (TRIMP, HR zones, HR recovery, vertical speed, cardiac cost/drift, HRR, Z5 sec, anomaly counts) stored with source provenance + metric-version metadata | UAT #4 (workout list/detail use materialized facts); fact tables carry `source_hash`/`source_revision`/`metric_version` | ✅ |
| 2 | Source writes mark activities/days dirty via durable invalidation (`source_hash`, `source_revision`, `metric_version`, transaction-safe dirty queue) | UAT #3 (`dirty_count` zero after materialize, versions present); 07-02 dirty-queue plan | ✅ |
| 3 | Refresh runtime materializes activity/daily/model/rolling facts after sync/backfill without MCP recompute/admin controls | UAT #2 (MCP surface is product-only — no sync/backfill/materialize/admin tools); 07-04 | ✅ |
| 4 | MCP tools read materialized facts, never scan raw streams / recompute at request time | UAT #4, #5, #6 (list/detail/compare/project use prepared facts + completeness metadata) | ✅ |
| 5 | Any MCP tool under 500 ms p95 on local mirror, with tests + live smoke | UAT #7 (read-model perf gate: p95 < 500 ms all product tools; startup measured separately) | ✅ |

## Cross-Cutting Constraints

- Raw mirror remains source of truth; facts are replaceable derived read models — UAT #3/#4.
- Idempotent recompute after algorithm-version changes — verified by VALIDATION.md and
  later reinforced by Phase 15's source-fingerprint auto-recompute.
- Missing/stale facts surface as completeness metadata, not request-time recompute — UAT #5/#6.

## Security

07-SECURITY.md: `status: verified`, `threats_open: 0`, ASVS level 1.

## Note on Storage Evolution

The goal text says "SQLite read-model facts" (accurate at authoring time). Phase 8
migrated primary storage to DuckDB and Phase 16 made the read-model columns
DuckDB-native; the read-model *contract* verified here (versioned facts, dirty-queue
invalidation, fact-only MCP reads, p95 target) holds unchanged on the current DuckDB
backend, exercised by the green test suite at HEAD.
