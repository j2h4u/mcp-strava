---
phase: 02-sqlite-safety-repository-layer
plan: 04
subsystem: database
tags: [sqlite, repository, sync, cli, safety-guards, migration-gate]
requires:
  - phase: 02-sqlite-safety-repository-layer
    provides: sqlite-safety-gate-and-repository-read-adoption
provides:
  - Explicit local DB safety CLI commands (`db-preflight`, `db-check`, `db-migrate`)
  - Sync/backfill persistence routed through repository write methods
  - Integrated source guards for sqlite boundary, operator-only SQL, and no implicit runtime DDL
affects: [phase-03-strava-adapter-refresh-runtime, phase-04-application-services-cli-refit]
tech-stack:
  added: []
  patterns: [operator-db-safety-commands, repository-write-boundary, hermetic-real-db-non-mutation-check]
key-files:
  created: []
  modified:
    - tests/test_security_guards.py
    - src/mcp_strava/cli.py
    - src/mcp_strava/sync.py
    - src/mcp_strava/adapters/sqlite/repository.py
key-decisions:
  - "Keep arbitrary SQL as local CLI-only `cmd_sql`; prohibit service/MCP reuse paths."
  - "Require sync/backfill to assert schema with preflight and write through repository methods."
patterns-established:
  - "Operator safety workflow: explicit preflight/check/migrate commands with JSON output."
  - "Phase verification includes before/after metadata invariance for real mirror DB sidecars."
requirements-completed: [SAFE-01, SAFE-02, SAFE-03, SAFE-04, REPO-01, REPO-02, REPO-03, TEST-01]
duration: 41min
completed: 2026-05-21
---

# Phase 2 Plan 4: Operator Wiring & Repository Boundary Enforcement Summary

**CLI now exposes explicit DB safety commands while sync/backfill writes are repository-backed and full verification proves no real mirror mutation.**

## Performance

- **Duration:** 41 min
- **Started:** 2026-05-21T10:29:00Z
- **Completed:** 2026-05-21T11:10:42Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Added integrated boundary guards that enforce explicit DB safety commands, operator-only SQL scope, no sync `init_db()` usage, and no schema DDL in runtime `init_db`.
- Wired CLI commands `db-preflight`, `db-check`, and `db-migrate` to migration-gate APIs with structured JSON status output.
- Refactored sync/backfill persistence paths to repository methods for activity upserts, stream writes, detail updates, kudos writes, and sync-log writes.
- Verified full suite (`just test`) with before/after metadata parity for `data/strava.db`, `data/strava.db-wal`, and `data/strava.db-shm`.

## Task Commits

1. **Task 1: Add operator command and boundary guard tests** - `a7e541d` (test)
2. **Task 2: Wire CLI migration commands and repository-backed sync writes** - `202ec3f` (feat)
3. **Task 3: Run full verification and real-mirror non-mutation check** - `ca30748` (test)

## Files Created/Modified

- `tests/test_security_guards.py` - Added AST/source guards for sqlite boundary, CLI DB command registration, operator-only SQL isolation, and sync/schema enforcement.
- `src/mcp_strava/cli.py` - Added `db-preflight`, `db-check`, and `db-migrate` commands with JSON output.
- `src/mcp_strava/sync.py` - Removed `init_db` calls; routed persistence writes through `SQLiteRepository`; added preflight assertions.
- `src/mcp_strava/adapters/sqlite/repository.py` - Added `delete_stream_rows_for_activity` helper used by backfill stream refresh.

## Decisions Made

- Kept arbitrary SQL command unchanged and local-only in CLI per D-11.
- Used migration preflight assertion at sync/backfill entry instead of schema mutation bootstrap.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- RED baseline initially passed for Task 1; added stricter guards to enforce missing CLI DB commands and sync `init_db` prohibition before implementation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 2 safety/repository boundary objectives are now enforced by tests and command wiring.
- Phase 3 can focus on Strava adapter/token/runtime isolation without reopening SQLite boundary concerns.

## Self-Check: PASSED

- Verified summary file exists.
- Verified task commit hashes exist in git history: `a7e541d`, `202ec3f`, `ca30748`.
- Verified focused and full checks passed:
  - `python3 -m pytest tests/test_sqlite_safety.py tests/test_repository_boundary.py tests/test_security_guards.py -q`
  - `just test`
- Verified real mirror metadata invariance:
  - `data/strava.db`: unchanged inode/size/mtime_ns
  - `data/strava.db-wal`: missing before and after
  - `data/strava.db-shm`: missing before and after

---
*Phase: 02-sqlite-safety-repository-layer*
*Completed: 2026-05-21*
