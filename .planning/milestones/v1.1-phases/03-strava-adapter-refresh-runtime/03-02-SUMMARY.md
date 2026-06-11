---
phase: 03-strava-adapter-refresh-runtime
plan: 03-02
subsystem: runtime
tags: [refresh-runtime, checkpoints, freshness, lease, backfill, sqlite]
requires:
  - phase: 03-01
    provides: Strava adapter ports and typed StravaUnavailable reasons
  - phase: 03-03
    provides: SQLite refresh_state, refresh_requests, lease, checkpoint, and request methods
provides:
  - Refresh runtime package with run_once and run_backfill
  - Checkpoint stage enum and daily/backfill transitions
  - Pure freshness evaluator and stale-request enqueue helper
  - Private sync operation helpers moved toward refresh ownership
affects: [phase-03-integration, phase-04-application-services, phase-05-mcp]
tech-stack:
  added: []
  patterns: [runtime-orchestration, freshness-state-machine, private-sync-ops]
key-files:
  created:
    - src/mcp_strava/refresh/__init__.py
    - src/mcp_strava/refresh/policy.py
    - src/mcp_strava/refresh/checkpoints.py
    - src/mcp_strava/refresh/freshness.py
    - src/mcp_strava/refresh/runtime.py
    - src/mcp_strava/refresh/_sync_ops.py
    - tests/test_refresh_runtime.py
  modified: []
key-decisions:
  - "run_once owns daily refresh orchestration and honors lease/backoff even when force=True."
  - "run_backfill is a separate sibling entrypoint that skips summaries and kudos."
  - "freshness evaluation is pure over refresh_state plus policy and does not call Strava."
patterns-established:
  - "Refresh runtime accepts repo, transport, policy, clock, and sleeper collaborators."
  - "refresh/_sync_ops.py is private and refresh modules do not import mcp_strava.sync."
requirements-completed: [STRAVA-03, REFRESH-01, REFRESH-02, REFRESH-03, TEST-02]
duration: 23min
completed: 2026-05-21
---

# Phase 3: Strava Adapter & Refresh Runtime Summary

**Lease-backed refresh runtime with daily idempotency, force refresh, backfill stages, freshness states, and hermetic orchestration tests**

## Performance

- **Duration:** 23 min
- **Started:** 2026-05-21T15:20:40Z
- **Completed:** 2026-05-21T15:43:43Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Added `run_once()` daily refresh orchestration over injected repository, transport, policy, clock, and sleeper collaborators.
- Added `run_backfill()` as a separate backfill path that does not run summaries/schema/kudos.
- Added checkpoint stages for daily and backfill flows.
- Added pure freshness state evaluation with `fresh`, `aging`, `stale`, `refresh_in_progress`, `refresh_failed`, and `refresh_delayed`.
- Added `enqueue_refresh_request_if_stale()` for idempotent SQLite refresh signals from read-runtime.
- Added hermetic runtime tests with fake Strava transport and live-network guard.

## Task Commits

1. **Task 1: Write failing refresh-runtime tests** - `6445edf` (test)
2. **Task 2: Implement refresh runtime** - `3cea43a` (feat)

**Plan metadata:** this summary

## Files Created/Modified

- `tests/test_refresh_runtime.py` - Runtime tests for daily completion, force, lease/backoff, backfill subset, freshness, request enqueue, and import direction.
- `src/mcp_strava/refresh/checkpoints.py` - Daily and backfill stage enum/transition helpers.
- `src/mcp_strava/refresh/policy.py` - Runtime policy defaults and settings factory.
- `src/mcp_strava/refresh/freshness.py` - Pure freshness evaluator and request enqueue helper.
- `src/mcp_strava/refresh/_sync_ops.py` - Private sync helpers owned by refresh runtime.
- `src/mcp_strava/refresh/runtime.py` - `run_once`, `run_backfill`, result/skip types, and failure handling.
- `src/mcp_strava/refresh/__init__.py` - Public refresh runtime exports.

## Decisions Made

- Kept `_sync_ops` private and out of `refresh.__all__`, preserving the public runtime surface.
- Kept daily refresh success tied to `record_refresh_success`; backfill writes sync audit metadata but does not satisfy daily freshness.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Verification

- `python3 -m pytest tests/test_refresh_runtime.py -q` -> 8 passed.
- `just test` -> 82 passed.
- Grep guards confirmed no `sqlite3`, `urllib`, or `mcp_strava.sync` imports under `src/mcp_strava/refresh/`.
- Grep guard confirmed `_sync_ops` is not re-exported from `refresh/__init__.py`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The refresh runtime is ready for production entrypoint integration. Plan 03-04 can now make `sync.py`, `db.py`, and `cli.py` route through adapter/runtime boundaries and add source-level guardrails.

---
*Phase: 03-strava-adapter-refresh-runtime*
*Completed: 2026-05-21*
