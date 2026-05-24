---
phase: 07-materialized-metrics-read-model
plan: 02
subsystem: database
tags: [sqlite, repository, dirty-queue, source-hash, transactions]
requires:
  - phase: 07-materialized-metrics-read-model
    provides: user_version=5 read-model schema and pinned backup foundation
provides:
  - semantic source hashing for activity mirror rows
  - transactional source-state updates and dirty queue enqueue
  - metric-version recompute queue API
affects: [phase-07-03, phase-07-04, materialization-pipeline]
tech-stack:
  added: []
  patterns: [semantic hash invalidation, dirty queue dedupe, source write transaction wrapping]
key-files:
  created: []
  modified:
    - src/mcp_strava/adapters/sqlite/repository.py
    - tests/test_read_model_materialization.py
key-decisions:
  - "Dirty invalidation is owned by repository source-write methods, not refresh orchestration."
  - "Non-semantic timestamp and batch fields are excluded from source hashes."
patterns-established:
  - "Source writes update `activity_source_state` and `metric_dirty_activities` in one SQLite transaction."
  - "Dirty queue conflicts reset attempt state only when semantic source content changes."
requirements-completed: [READMODEL-02, TEST-06]
duration: 10min
completed: 2026-05-24
---

# Phase 7 Plan 2: Dirty Invalidation Summary

**Repository source writes now atomically update source provenance and queue read-model recompute work**

## Performance

- **Duration:** 10 min
- **Started:** 2026-05-24T16:20:00+05:00
- **Completed:** 2026-05-24T16:30:00+05:00
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added dirty-invalidation tests for activity summaries, details, stream replacement, stream-channel merge, metadata writes, metric-version recompute, duplicate dirty rows, timestamp-only churn, and rollback failure.
- Implemented semantic source hashing in the SQLite repository while excluding `synced_at`, `fetched_at`, `timestamp`, `updated_at`, `modified_at`, and `batch_id`.
- Wrapped source-changing repository methods so source mutation, source-state update, and dirty queue enqueue commit or roll back together.
- Added dirty queue APIs: `dirty_activity_rows`, `mark_dirty_activity_attempt_failed`, and `enqueue_metric_version_recompute`.

## Task Commits

1. **Task 1: Add failing dirty invalidation tests** - `810939b` (`test`)
2. **Task 2: Implement semantic source state and atomic dirty queue APIs** - `810939b` (`feat`)

## Verification

- `uv run pytest -q tests/test_read_model_materialization.py tests/test_refresh_runtime.py tests/test_full_fidelity_mirror.py` - passed, 42 tests
- `uv run pytest -q tests/test_repository_boundary.py tests/test_security_guards.py` - passed, 38 tests
- `uv run pytest -q` - passed, 233 passed, 1 skipped
- `just test` - passed, Docker MCP smoke-basic returned status ok

## Files Created/Modified

- `src/mcp_strava/adapters/sqlite/repository.py` - semantic hash helpers, source state update, dirty queue APIs, transactional source write wrappers.
- `tests/test_read_model_materialization.py` - dirty invalidation, dedupe, non-semantic hash stability, metric-version recompute, and rollback tests.

## Decisions Made

- Kept dirty enqueue out of `_sync_ops.py`; sync continues to call repository methods and the repository owns invalidation.
- Reset dirty `attempt_count` and `last_error` when a semantic source change re-queues existing dirty work.
- Excluded metadata fetch timestamps and batch ids from source hash so operational fetch churn does not trigger recompute.

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for Plan 07-03: materializer can consume `metric_dirty_activities`, write fact tables, and clear dirty rows only after fact commits.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: dirty-invalidation | src/mcp_strava/adapters/sqlite/repository.py | Source writes now control recompute eligibility and must remain transactionally coupled. |

## Self-Check: PASSED
