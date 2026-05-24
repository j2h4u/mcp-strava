---
phase: 06-full-fidelity-strava-mirror
plan: 03
subsystem: database
tags: [sqlite, migration, gps, repository, refresh]
requires:
  - phase: 06-full-fidelity-strava-mirror
    provides: all-channel stream parsing/projection and atomic row+metadata replacement
provides:
  - v4 migration that canonicalizes GPS to streams.lat/lng and removes streams.latlng
  - migration post-check counters for malformed/conflicting latlng payloads
  - runtime stream read/write paths that no longer depend on streams.latlng
affects: [phase-06-04, refresh-runtime, analytics]
tech-stack:
  added: []
  patterns: [transactional sqlite table rebuild migration, canonical scalar gps persistence]
key-files:
  created: []
  modified:
    - src/mcp_strava/adapters/sqlite/migrations.py
    - src/mcp_strava/adapters/sqlite/repository.py
    - src/mcp_strava/refresh/_sync_ops.py
    - tests/test_full_fidelity_mirror.py
    - tests/test_sqlite_safety.py
    - tests/test_repository_boundary.py
    - tests/test_application_reports.py
    - tests/test_application_workouts.py
key-decisions:
  - "Phase 6 canonical runtime schema is v4 with lat/lng + values_json and no streams.latlng."
  - "Migration reports conflict/malformed counters from pre-migration scan while preserving scalar GPS values."
patterns-established:
  - "Repository stream writes are schema-aware for values_json but not latlng-dependent."
requirements-completed: [GPS-01, GPS-02, STREAM-03, TEST-05]
duration: 74min
completed: 2026-05-24
---

# Phase 6 Plan 3: Canonical GPS Migration Summary

**SQLite migration v4 now rebuilds streams to canonical `lat`/`lng`, removes `latlng`, and keeps analytics/runtime parity without Strava API calls.**

## Performance

- **Duration:** 74 min
- **Started:** 2026-05-24T12:47:00Z
- **Completed:** 2026-05-24T14:01:00Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- Added RED tests for v4 migration contract, idempotency, malformed/conflict handling, and temp-fixture-only execution.
- Implemented `MIGRATIONS[4]` with transactional `streams_new` rebuild, scalar-vs-`latlng` precedence, and v4 post-check diagnostics.
- Removed runtime `streams.latlng` dependency from repository writes/reads and refresh stream payload persistence.
- Updated application/report fixtures and boundary guards to validate v4-only runtime behavior.

## Task Commits

1. **Task 1: Add failing canonical GPS migration tests** - `1b2102b` (`test`)
2. **Task 2: Implement backup-protected GPS canonicalization migration** - `fb48629` (`feat`)
3. **Task 3: Remove post-migration latlng reads and writes** - `4bfbd47` (`feat`)

## Files Created/Modified

- `src/mcp_strava/adapters/sqlite/migrations.py` - added v4 GPS migration, pre/post snapshots, and post-check counters.
- `src/mcp_strava/adapters/sqlite/repository.py` - canonicalized stream SQL to lat/lng + values_json paths.
- `src/mcp_strava/refresh/_sync_ops.py` - stopped emitting `latlng` persistence field in stream rows.
- `tests/test_full_fidelity_mirror.py` - v4 contract coverage and migration counter assertions.
- `tests/test_sqlite_safety.py` - updated migration version expectations and temp-path safety assertion.
- `tests/test_repository_boundary.py` - added guard against runtime `streams.latlng` column dependency.
- `tests/test_application_reports.py` - updated stream fixture inserts for v4 schema.
- `tests/test_application_workouts.py` - updated stream fixture inserts for v4 schema.

## Decisions Made

- Kept `latlng` parsing only as inbound stream-channel handling in refresh, not as persisted runtime schema.
- Preserved scalar `lat`/`lng` on conflicts and reported counts instead of mutating scalar values from disagreeing JSON pairs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Repository stream inserts failed immediately on v4 schema**
- **Found during:** Task 2 verification
- **Issue:** Repository SQL still inserted `streams.latlng`, causing migration-path tests to fail on v4 databases.
- **Fix:** Made stream read/write SQL canonical to `lat`/`lng` and schema-aware only for `values_json`.
- **Files modified:** `src/mcp_strava/adapters/sqlite/repository.py`
- **Verification:** `python3 -m pytest tests/test_full_fidelity_mirror.py tests/test_sqlite_safety.py -q`
- **Committed in:** `fb48629`

**2. [Rule 1 - Bug] Application fixtures inserted removed `latlng` column**
- **Found during:** Plan-level verification
- **Issue:** report/workout tests still inserted into `streams.latlng` after v4 removal.
- **Fix:** Updated fixture insert SQL and values to v4 stream columns.
- **Files modified:** `tests/test_application_reports.py`, `tests/test_application_workouts.py`
- **Verification:** `python3 -m pytest tests/test_application_reports.py tests/test_application_workouts.py -q`
- **Committed in:** `4bfbd47`

---

**Total deviations:** 2 auto-fixed (1 rule-3 blocking, 1 rule-1 bug)
**Impact on plan:** Both fixes were required for v4 correctness and full verification completion.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Plan 06-04 channel/backfill follow-ups on top of canonical v4 GPS storage.
- Runtime/tests now assume canonical lat/lng persistence; no `streams.latlng` compatibility path remains.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: migration-surface | src/mcp_strava/adapters/sqlite/migrations.py | Added v4 table-rebuild migration path and post-check diagnostics at schema trust boundary. |

## Self-Check: PASSED
