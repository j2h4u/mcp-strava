---
phase: 03-strava-adapter-refresh-runtime
plan: 03-04
subsystem: integration
tags: [refresh-runtime, cli, sync-shim, db-shim, boundary-guards]
requires:
  - phase: 03-01
    provides: Strava adapter package and token refresh transport
  - phase: 03-02
    provides: Refresh runtime run_once and run_backfill
  - phase: 03-03
    provides: SQLite refresh-state repository methods
provides:
  - Legacy sync entrypoints routed through refresh runtime
  - Legacy db auth/API shims routed through Strava adapter
  - Operator-only db-refresh command with force mode
  - Boundary tests for urllib containment, read-path isolation, and sync helper removal
affects: [phase-04-application-services, phase-05-mcp]
tech-stack:
  added: []
  patterns: [thin-compatibility-shim, operator-refresh-command, source-boundary-guards]
key-files:
  created: []
  modified:
    - src/mcp_strava/sync.py
    - src/mcp_strava/db.py
    - src/mcp_strava/cli.py
    - tests/test_security_guards.py
    - tests/test_smoke.py
key-decisions:
  - "sync_activities and backfill_activities are compatibility wrappers over refresh.runtime."
  - "db.py no longer owns OAuth URLs, API base URLs, urllib calls, or rate-limit parsing."
  - "db-refresh is an operator CLI command only; MCP remains unaware of sync controls."
patterns-established:
  - "Production refresh collaborators are built in one sync module factory and reused by CLI."
  - "Read/analytics modules are guarded from importing Strava adapter or refresh runtime."
requirements-completed: [STRAVA-01, STRAVA-03, REFRESH-01, REFRESH-02, TEST-02]
duration: 10min
completed: 2026-05-21
---

# Phase 3: Strava Adapter & Refresh Runtime Summary

**Production wiring now routes legacy sync/db/CLI entrypoints through the new adapter and refresh-runtime boundaries**

## Performance

- **Duration:** 10 min
- **Started:** 2026-05-21T15:43:45Z
- **Completed:** 2026-05-21T15:53:29Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Replaced legacy `sync.py` internals with thin wrappers over `refresh.runtime.run_once()` and `run_backfill()`.
- Removed inline OAuth/API/urllib/rate-limit logic from `db.py`; `refresh_token()` and `api_request()` now delegate through the Strava adapter.
- Added `db-refresh [--force]` as the explicit operator CLI path for manual refresh.
- Added source-level guard tests for read-module isolation, urllib containment, refresh import direction, and deleted sync helpers.

## Task Commits

1. **Task 1: Refactor sync.py and db.py to thin adapter-backed compatibility layers** - `e3afa20` (refactor)
2. **Task 2: Wire db-refresh CLI command and extend security boundary tests** - `5f1e6ae` (feat)

**Plan metadata:** this summary

## Files Created/Modified

- `src/mcp_strava/sync.py` - Compatibility factory plus `sync_activities()` and `backfill_activities()` wrappers over refresh runtime.
- `src/mcp_strava/db.py` - Adapter-backed `refresh_token()` and `api_request()` shims; Phase 4 note for zone writes.
- `src/mcp_strava/cli.py` - `db-refresh [--force]` command and backfill `since` pass-through.
- `tests/test_security_guards.py` - Boundary tests for CLI wiring and import containment.
- `tests/test_smoke.py` - Updated sync imports after `RateLimiter` removal.

## Decisions Made

- Kept old public `sync_activities`, `backfill_activities`, `refresh_token`, and `api_request` names as compatibility shims, but removed their legacy implementation ownership.
- Used `PYTHONPATH=src` for direct module help checks because this repo uses a src layout and is not installed into the active interpreter by default.

## Deviations from Plan

- Updated `tests/test_smoke.py` with Task 1 production changes so the intermediate sync refactor remains import-clean after deleting `RateLimiter`.

## Issues Encountered

- `python3 -m mcp_strava db-refresh --help` without `PYTHONPATH=src` cannot find the package in this src-layout checkout. The source-tree equivalent succeeds.

## Verification

- `python3 -m pytest tests/test_security_guards.py tests/test_smoke.py -q` -> 27 passed.
- `just test` -> 90 passed.
- Grep guards confirmed `sync.py` no longer defines `RateLimiter`, `_fetch_with_retry`, moved sync helpers, or urllib imports.
- Grep guard confirmed `db.py` no longer contains Strava OAuth/API URL literals.
- `PYTHONPATH=src python3 -m mcp_strava db-refresh --help` shows `--force`.

## User Setup Required

None - no live Strava call was made during execution.

## Next Phase Readiness

Phase 3 production wiring is ready for phase-level closeout and follow-up security/validation gates. Phase 4 can build application services on top of repository and refresh boundaries without MCP knowing about sync internals.

---
*Phase: 03-strava-adapter-refresh-runtime*
*Completed: 2026-05-21*
