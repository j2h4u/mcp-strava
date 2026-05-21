---
phase: 02-sqlite-safety-repository-layer
plan: 01
subsystem: database
tags: [sqlite, migrations, backup, preflight, parity, safety]
requires:
  - phase: 01-package-foundation-settings
    provides: package-entrypoint-and-typed-settings
provides:
  - Fail-closed expected SQLite mirror open policy
  - Explicit preflight/backup/migration/post-check safety gate
  - Hermetic migration safety tests with deterministic parity checks
affects: [phase-02-plan-02, phase-02-plan-03, phase-02-plan-04]
tech-stack:
  added: []
  patterns: [explicit-migration-gate, fail-closed-db-open, sqlite-backup-api]
key-files:
  created:
    - src/mcp_strava/adapters/sqlite/connection.py
    - src/mcp_strava/adapters/sqlite/schema.py
    - src/mcp_strava/adapters/sqlite/backup.py
    - src/mcp_strava/adapters/sqlite/migrations.py
    - tests/test_sqlite_safety.py
  modified:
    - src/mcp_strava/db.py
    - tests/test_phase01_validation.py
key-decisions:
  - "Runtime paths must never execute schema-changing DDL; preflight/migration gate owns all schema changes."
  - "Expected mirror open is fail-closed (URI mode=rw) while fixture creation remains explicit."
patterns-established:
  - "SQLite safety path: preflight -> backup -> migrate -> post-check -> parity"
  - "Migration tests are hermetic and operate only on temp fixtures"
requirements-completed: [SAFE-01, SAFE-02, SAFE-03, SAFE-04, TEST-01]
duration: 35min
completed: 2026-05-21
---

# Phase 2 Plan 1: SQLite Safety Gate Summary

**Fail-closed SQLite mirror open, explicit migration safety gate, and hermetic parity tests for preflight/backup/user_version control.**

## Performance

- **Duration:** 35 min
- **Started:** 2026-05-21T15:40:00Z
- **Completed:** 2026-05-21T16:15:00Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Added RED/green TDD coverage for fail-closed open, preflight, backup, retention, baseline migration, and synthetic parity drift detection.
- Introduced `src/mcp_strava/adapters/sqlite/*` with connection policy, schema inventory/preflight, timestamped backups, and migration orchestration.
- Removed implicit runtime schema DDL from `db.py::init_db`; runtime now enforces preflight instead of mutating schema.

## Task Commits

1. **Task 1: Write failing SQLite safety tests** - `7612f83` (test)
2. **Task 2: Implement fail-closed connection, preflight, backup, and explicit migration gate** - `7c38eff` (feat)

## Files Created/Modified
- `src/mcp_strava/adapters/sqlite/connection.py` - Fail-closed expected DB open and centralized WAL/busy-timeout policy.
- `src/mcp_strava/adapters/sqlite/schema.py` - Required schema inventory, integrity checks, user_version, and row-count preflight data.
- `src/mcp_strava/adapters/sqlite/backup.py` - Timestamped backups via SQLite backup API and retention policy (default keep=5).
- `src/mcp_strava/adapters/sqlite/migrations.py` - Explicit preflight/backup/migrate flow and parity comparator primitives.
- `src/mcp_strava/db.py` - `DbConn` delegates to adapter and `init_db` is now assertion-only (no CREATE/ALTER DDL).
- `tests/test_sqlite_safety.py` - Hermetic migration safety test suite with deterministic `as_of` parity checks.
- `tests/test_phase01_validation.py` - Updated expectations for fail-closed expected DB behavior and explicit fixture creation.

## Decisions Made
- Enforced fail-closed behavior in runtime `DbConn` using SQLite URI `mode=rw`.
- Kept baseline migration at `PRAGMA user_version=1` idempotent and non-destructive.
- Kept parity checks focused on deterministic row-count and load-signal invariants, not report text snapshots.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Initial RED test run failed with `ModuleNotFoundError` for `mcp_strava.adapters`, which was expected before implementation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 02 Plan 02 can now build repository contracts on top of the adapter safety boundary.
- Migration gate primitives are available for future operator commands without live Strava network calls.

## Self-Check: PASSED

- Verified summary key files exist.
- Verified task commit hashes exist in git history.
- Verified plan-level checks passed: `python3 -m pytest tests/test_sqlite_safety.py -q` and `just test`.

---
*Phase: 02-sqlite-safety-repository-layer*
*Completed: 2026-05-21*
