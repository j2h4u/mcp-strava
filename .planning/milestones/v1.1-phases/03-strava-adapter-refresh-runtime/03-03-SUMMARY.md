---
phase: 03-strava-adapter-refresh-runtime
plan: 03-03
subsystem: database
tags: [sqlite, migration, repository, refresh-state, leases, checkpoints]
requires:
  - phase: 02-sqlite-safety-repository-layer
    provides: SQLite safety gate, repository boundary, and migration parity checks
provides:
  - Schema v2 refresh_state and refresh_requests inventory
  - Migration registry with v2 refresh control-plane tables
  - Repository methods for leases, checkpoints, refresh failures, and request dedupe
  - Typed RefreshStateRow and RefreshRequestRow contracts
affects: [phase-03-refresh-runtime, phase-04-application-services, phase-05-mcp]
tech-stack:
  added: []
  patterns: [sqlite-control-plane, partial-unique-dedupe, repository-only-refresh-state]
key-files:
  created: []
  modified:
    - src/mcp_strava/adapters/sqlite/schema.py
    - src/mcp_strava/adapters/sqlite/migrations.py
    - src/mcp_strava/adapters/sqlite/repository.py
    - src/mcp_strava/types.py
    - tests/test_sqlite_safety.py
    - tests/test_repository_boundary.py
key-decisions:
  - "refresh_requests dedupe uses a partial unique index over pending rows."
  - "mark_refresh_requests_consumed consumes all pending requests in one parameterized UPDATE."
  - "refresh_state is the singleton source of truth for lease, backoff, checkpoints, and last refresh outcome."
patterns-established:
  - "Schema additions remain behind explicit migration/preflight/post-check flow."
  - "Refresh runtime state is exposed only through SQLiteRepository methods."
requirements-completed: [REFRESH-02, REFRESH-03, STRAVA-03]
duration: 19min
completed: 2026-05-21
---

# Phase 3: Strava Adapter & Refresh Runtime Summary

**SQLite refresh control-plane with v2 migration, lease/checkpoint repository methods, and pending refresh-request dedupe**

## Performance

- **Duration:** 19 min
- **Started:** 2026-05-21T15:20:20Z
- **Completed:** 2026-05-21T15:39:11Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added schema v2 inventory for `refresh_state` and `refresh_requests`.
- Added migration v2 that creates refresh metadata tables, seeds `refresh_state(id=1)`, and creates `idx_refresh_requests_dedupe`.
- Added repository methods for refresh lease ownership, checkpointing, attempts, success/failure states, pending request enqueue/consume, and backfill target selection.
- Added product-safe refresh reason code whitelist.
- Extended migration/repository tests while preserving Phase 2 safety and parity checks.

## Task Commits

1. **Task 1: Extend SQLite safety and repository boundary tests** - `b4ec9b6` (test)
2. **Task 2: Implement schema v2 and refresh repository methods** - `5411d02` (feat)

**Plan metadata:** this summary

## Files Created/Modified

- `tests/test_sqlite_safety.py` - v2 migration, preflight, and partial-index coverage.
- `tests/test_repository_boundary.py` - refresh repository method, lease, dedupe, reason-code, and backfill helper coverage.
- `src/mcp_strava/adapters/sqlite/schema.py` - v2 inventory and index validation.
- `src/mcp_strava/adapters/sqlite/migrations.py` - migration registry and v2 DDL.
- `src/mcp_strava/adapters/sqlite/repository.py` - refresh state/request repository methods.
- `src/mcp_strava/types.py` - refresh state/request dataclasses and allowed reason codes.

## Decisions Made

- Kept preflight compatible with pre-v2 fixture databases while recognizing v2 inventory after migration.
- Used repository-level reason-code validation so token values or stack traces cannot land in `refresh_state.last_error_code`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Verification

- `python3 -m pytest tests/test_sqlite_safety.py tests/test_repository_boundary.py -q` -> 26 passed.
- `just test` -> 74 passed.
- `PYTHONPATH=src python3` signature check confirmed `mark_refresh_requests_consumed(self, consumed_at: str) -> int`.
- DDL grep confirmed no invalid `UNIQUE(reason, requested_for_day, consumed_at_is_null)` literal.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The refresh runtime can now rely on SQLiteRepository for lease acquisition, checkpoint persistence, failure backoff state, and first-use refresh request dedupe. Plan 03-02 can build runtime orchestration on these methods.

---
*Phase: 03-strava-adapter-refresh-runtime*
*Completed: 2026-05-21*
