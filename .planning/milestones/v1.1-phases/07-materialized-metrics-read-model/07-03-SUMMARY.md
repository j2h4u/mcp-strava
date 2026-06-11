---
phase: 07-materialized-metrics-read-model
plan: 03
subsystem: database
tags: [sqlite, materializer, read-model, metrics, training-model]
requires:
  - phase: 07-materialized-metrics-read-model
    provides: repository-owned dirty queue and source-state invalidation
provides:
  - offline read-model materializer for dirty activity rows
  - activity, daily, training-model, and rolling fact upserts
  - failure-safe dirty row clearing and run audit records
affects: [phase-07-04, phase-07-05, refresh-runtime, mcp-read-paths]
tech-stack:
  added: []
  patterns: [offline materialization pipeline, metric-versioned fact rows, transactional dirty clearing]
key-files:
  created:
    - src/mcp_strava/adapters/sqlite/read_model_materializer.py
  modified:
    - src/mcp_strava/adapters/sqlite/repository.py
    - tests/test_read_model_materialization.py
key-decisions:
  - "Materializer runs below MCP and writes metric-versioned SQLite facts from repository dirty rows."
  - "Dirty rows clear only in the same successful transaction as facts and run audit."
patterns-established:
  - "Materialization failures roll back fact writes and leave dirty rows retryable."
  - "Metric-version recompute writes new versioned facts without deleting prior version facts."
requirements-completed: [READMODEL-01, READMODEL-03, TEST-06]
duration: 8min
completed: 2026-05-24
---

# Phase 7 Plan 3: Read-Model Materializer Summary

**Offline materializer persists activity, daily, training-model, and rolling facts from dirty source rows**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-24T16:30:00+05:00
- **Completed:** 2026-05-24T16:38:00+05:00
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added materializer behavior tests for all four fact tiers, dirty clearing, idempotency, metric-version history, and rollback-on-failure.
- Created `read_model_materializer.py` with `materialize_read_model(...)` using existing local metric/training formulas below the MCP boundary.
- Added repository APIs for fetching dirty rows, upserting fact tables, clearing processed dirty rows, and recording `read_model_refresh_runs`.
- Ensured failures roll back partial fact writes and leave dirty rows available for retry.

## Task Commits

1. **Task 1: Add failing materializer behavior tests** - `f00ef60` (`test`)
2. **Task 2: Implement read-model materializer and fact repository APIs** - `f00ef60` (`feat`)

## Verification

- `uv run pytest -q tests/test_read_model_materialization.py tests/test_metric_services.py` - passed, 23 tests
- `uv run pytest -q tests/test_refresh_runtime.py` - passed, 23 tests
- `uv run pytest -q` - passed, 237 passed, 1 skipped
- `just test` - passed, Docker MCP smoke-basic returned status ok

## Files Created/Modified

- `src/mcp_strava/adapters/sqlite/read_model_materializer.py` - offline materialization pipeline and fact aggregation helpers.
- `src/mcp_strava/adapters/sqlite/repository.py` - read-model fact upsert, dirty fetch/clear, and run-audit methods.
- `tests/test_read_model_materialization.py` - materializer fact-tier, idempotency, versioning, and failure tests.

## Decisions Made

- Kept current numeric metric-version convention from v5 dirty queue instead of introducing a string version while the schema is integer-based.
- Materialized one `all/all` scope for daily/model/rolling facts first; later plans can add per-sport scope rows if MCP read paths need them.
- `read_model_refresh_runs` records success in the same transaction as facts and dirty clearing; failed runs are recorded best-effort after rollback.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Scope Control] Kept metric version numeric**
- **Found during:** Task 2 implementation
- **Issue:** Plan text suggested a string `CURRENT_METRIC_VERSION`, but the Phase 7 v5 schema and dirty queue already use integer `metric_version`.
- **Fix:** Reused the repository `CURRENT_METRIC_VERSION = 1` integer convention.
- **Files modified:** `src/mcp_strava/adapters/sqlite/read_model_materializer.py`
- **Verification:** metric-version tests prove versions `1` and `2` coexist.
- **Committed in:** `f00ef60`

---

**Total deviations:** 1 auto-fixed scope-control adjustment.
**Impact on plan:** Preserves the actual v5 schema contract and avoids a needless migration mismatch.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for Plan 07-04: wire materialization into refresh/backfill/admin flows while preserving the MCP boundary.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: materializer-commit | src/mcp_strava/adapters/sqlite/read_model_materializer.py | Dirty rows are cleared only after fact writes and audit insertion in one transaction. |

## Self-Check: PASSED
