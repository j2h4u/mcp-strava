---
phase: 07-materialized-metrics-read-model
plan: 01
subsystem: database
tags: [sqlite, migration, read-model, backup, tests]
requires:
  - phase: 06-full-fidelity-strava-mirror
    provides: canonical v4 SQLite mirror with full-fidelity stream storage
provides:
  - SQLite user_version=5 read-model schema foundation
  - pinned pre-Phase-7 backup support preserved outside normal retention
  - schema inventory and row-count reporting for read-model tables
affects: [phase-07-02, phase-07-03, refresh-runtime, mcp-read-paths]
tech-stack:
  added: []
  patterns: [idempotent sqlite ddl, pinned migration backup, wide fact table inventory]
key-files:
  created:
    - tests/test_read_model_materialization.py
  modified:
    - src/mcp_strava/adapters/sqlite/backup.py
    - src/mcp_strava/adapters/sqlite/migrations.py
    - src/mcp_strava/adapters/sqlite/schema.py
    - src/mcp_strava/types.py
    - tests/test_full_fidelity_mirror.py
    - tests/test_sqlite_safety.py
key-decisions:
  - "Runtime schema target is now user_version=5 for Phase 7 read-model tables."
  - "Pre-Phase-7 backups use a pinned filename class and are excluded from ordinary retention pruning."
patterns-established:
  - "Read-model tables are rebuildable SQLite projections beside the source mirror, not source-of-truth replacements."
  - "Hot MCP facts use explicit wide tables with scope/sport/version indexes."
requirements-completed: [READMODEL-01, READMODEL-02, TEST-06]
duration: 44min
completed: 2026-05-24
---

# Phase 7 Plan 1: SQLite Read-Model Schema Summary

**SQLite v5 read-model inventory with pinned migration backup and wide fact-table contracts**

## Performance

- **Duration:** 44 min
- **Started:** 2026-05-24T15:36:00+05:00
- **Completed:** 2026-05-24T16:20:00+05:00
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Added RED/GREEN coverage for v5 read-model tables, exact required columns, exact required indexes, row-count inventory, idempotency, and source row-count parity.
- Added `MIGRATIONS[5]` with idempotent DDL for `activity_source_state`, `metric_dirty_activities`, `activity_metric_facts`, `daily_load_facts`, `training_model_daily`, `rolling_period_facts`, and `read_model_refresh_runs`.
- Added pinned pre-Phase-7 backup support that retention preserves while continuing to prune normal backups.
- Added typed read-model dataclass contracts in `src/mcp_strava/types.py`.

## Task Commits

1. **Task 1: Add failing v5 read-model schema and backup tests** - `02be2f2` (`test`)
2. **Task 2: Implement v5 schema inventory, migration, and pinned backup support** - `02be2f2` (`feat`)

## Verification

- `uv run pytest -q tests/test_sqlite_safety.py tests/test_read_model_materialization.py` - passed, 18 tests
- `uv run pytest -q tests/test_full_fidelity_mirror.py tests/test_repository_boundary.py tests/test_sqlite_safety.py tests/test_read_model_materialization.py` - passed, 44 tests
- `uv run pytest -q` - passed, 226 passed, 1 skipped

## Files Created/Modified

- `tests/test_read_model_materialization.py` - v5 schema, index, inventory, parity, and idempotency tests.
- `src/mcp_strava/adapters/sqlite/backup.py` - pinned pre-Phase-7 backup creation and retention preservation.
- `src/mcp_strava/adapters/sqlite/migrations.py` - v5 read-model migration and pinned backup before applying Phase 7 DDL.
- `src/mcp_strava/adapters/sqlite/schema.py` - v5 required table/column/index inventory and row-count reporting.
- `src/mcp_strava/types.py` - read-model dataclass contracts.
- `tests/test_sqlite_safety.py` - v5 migration expectations and pinned backup retention test.
- `tests/test_full_fidelity_mirror.py` - updated migration expectations from v4 final to v5 final.

## Decisions Made

- Kept SQLite as the Phase 7 primary read-model store.
- Added one wide fact table per grain instead of split per-scope tables.
- Pinned backup recognition is filename-based (`strava-pre-phase-7-*.db`) so it works without sidecar metadata.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Regression] Existing migration tests still expected v4 as the terminal schema**
- **Found during:** plan-level regression verification
- **Issue:** Phase 6 tests asserted `run_migrations()` ended at user_version=4.
- **Fix:** Updated those assertions to user_version=5 while preserving their v3/v4 stream-inventory checks.
- **Files modified:** `tests/test_full_fidelity_mirror.py`, `tests/test_sqlite_safety.py`
- **Verification:** `uv run pytest -q tests/test_full_fidelity_mirror.py tests/test_repository_boundary.py tests/test_sqlite_safety.py tests/test_read_model_materialization.py`
- **Committed in:** `02be2f2`

---

**Total deviations:** 1 auto-fixed regression update.
**Impact on plan:** Required for the new schema target; no scope expansion beyond Plan 07-01.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for Plan 07-02: source writes can now target the v5 provenance and dirty-queue tables.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: migration-surface | src/mcp_strava/adapters/sqlite/migrations.py | Added v5 DDL and backup-protected schema transition. |
| threat_flag: backup-retention | src/mcp_strava/adapters/sqlite/backup.py | Added pinned backup class excluded from normal retention pruning. |

## Self-Check: PASSED
