---
phase: 02-sqlite-safety-repository-layer
plan: 03
subsystem: database
tags: [sqlite, repository, load-status, analytics, metrics, parity]
requires:
  - phase: 02-sqlite-safety-repository-layer
    provides: sqlite-repository-contracts-and-safety-gate
provides:
  - Daily load status contract with REST/UNKNOWN/PARTIAL/OBSERVED semantics
  - Repository-backed read paths for report, weekly analytics, trends, and metrics
  - Numeric parity protection for Banister/EWMA/weekly-plan observed-load signals
affects: [phase-02-plan-04, phase-03-strava-adapter-refresh-runtime]
tech-stack:
  added: []
  patterns: [daily-load-contract, repository-only-stream-reads, observed-vs-effective-load]
key-files:
  created:
    - tests/test_load_status.py
  modified:
    - src/mcp_strava/adapters/sqlite/repository.py
    - src/mcp_strava/types.py
    - src/mcp_strava/db.py
    - src/mcp_strava/report.py
    - src/mcp_strava/analytics.py
    - src/mcp_strava/trends.py
    - src/mcp_strava/metrics.py
    - tests/test_repository_boundary.py
key-decisions:
  - "Daily load contract keeps uncertainty explicit with status + observed/effective split while retaining Phase 2 numeric parity."
  - "All activity/stream SQL in report/analytics/trends/metrics moved behind repository helper methods."
patterns-established:
  - "training.py continues consuming deterministic {date: effective_trimp} mappings derived from repository status points."
  - "Read-path parity checks focus on numeric/load invariants, not report wording snapshots."
requirements-completed: [SAFE-03, REPO-01, REPO-03, TEST-01]
duration: 67min
completed: 2026-05-21
---

# Phase 2 Plan 3: Repository Read Adoption & Load Statuses Summary

**Repository daily-load contract now exposes REST/UNKNOWN/PARTIAL/OBSERVED while report/analytics/trends/metrics consume repository methods and keep observed training-load parity.**

## Performance

- **Duration:** 67 min
- **Started:** 2026-05-21T11:48:00Z
- **Completed:** 2026-05-21T12:55:00Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Added RED tests for missing-data semantics and effective-vs-observed TRIMP parity with frozen `today_str`.
- Implemented `DailyLoadPoint` contract and repository helpers for status windows, effective history, observed history, and metric-specific stream/activity reads.
- Migrated `db.py`, `report.py`, `analytics.py`, `trends.py`, and `metrics.py` read paths to repository delegation, eliminating direct activity/stream SQL from those modules.

## Task Commits

1. **Task 1: Write failing missing-data and observed-load parity tests** - `a9d6c2e` (test)
2. **Task 2: Implement daily load status contract and migrate read paths** - `c98b052` (feat)

## Files Created/Modified
- `tests/test_load_status.py` - Hermetic status semantics and training parity checks.
- `tests/test_repository_boundary.py` - Added AST guard for raw activity/stream SQL in load/metrics paths.
- `src/mcp_strava/types.py` - Added `DailyLoadPoint` and `DailyLoadStatus`.
- `src/mcp_strava/adapters/sqlite/repository.py` - Added status-window/effective-history methods and metric query helpers.
- `src/mcp_strava/db.py` - `get_daily_trimp_history` now delegates to repository observed history.
- `src/mcp_strava/report.py` - Daily report load history and volume reads now repository-backed.
- `src/mcp_strava/analytics.py` - Weekly digest and efficiency reads now repository-backed.
- `src/mcp_strava/trends.py` - Trend load history now repository-backed.
- `src/mcp_strava/metrics.py` - All activity/stream metric fetches now repository-backed.

## Decisions Made
- Kept Phase 2 semantics strict: `REST`, `UNKNOWN`, `PARTIAL` map to `effective_trimp=0.0` and `observed_trimp=None`; `OBSERVED` maps `observed_trimp == effective_trimp`.
- Preserved deterministic training outputs by comparing Banister/EWMA/weekly-plan numeric signals at fixed `today_str`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Adapted `enrich_activity()` to repository dataclass rows**
- **Found during:** Task 2 verification (`just test`)
- **Issue:** `report.daily_report()` passed `RepositoryActivityRow` objects, while `metrics.enrich_activity()` still indexed rows as dicts.
- **Fix:** Added field-access compatibility for dataclass-or-dict rows in `enrich_activity`.
- **Files modified:** `src/mcp_strava/metrics.py`
- **Verification:** `just test` (47 passed)
- **Committed in:** `c98b052`

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** No scope creep; fix was required for runtime correctness after repository read migration.

## Issues Encountered

- RED test fixture initially triggered a non-contract failure (`row_factory` mismatch) and was corrected so failures reflected missing implementation only.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 02-04 can now enforce remaining boundary constraints using repository methods already in place.
- REPO-03 status contract and numeric parity gates are now test-covered for future adapter/service work.

## Self-Check: PASSED

- Verified summary file exists: `.planning/phases/02-sqlite-safety-repository-layer/02-03-SUMMARY.md`
- Verified task commits exist: `a9d6c2e`, `c98b052`
- Verified checks pass: `python3 -m pytest tests/test_load_status.py tests/test_repository_boundary.py -q` and `just test`

---
*Phase: 02-sqlite-safety-repository-layer*
*Completed: 2026-05-21*
