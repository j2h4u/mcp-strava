---
phase: 16-duckdb-native-storage-cleanup
plan: "01"
subsystem: testing
tags: [duckdb, kudos, pytest, xfail, regression-guard]

requires:
  - phase: 15-self-invalidating-read-model
    provides: DuckDBRepository with from_path, upsert_activity_summary

provides:
  - window_days regression guard for kudos store (xfail test in test_duckdb_repository.py)
  - Assumption A1 confirmed inline: RepositoryActivityRow.date exists at types_repository.py:193

affects:
  - 16-02 (rewrite kudos window_days branch — this test becomes GREEN after that plan)

tech-stack:
  added: []
  patterns:
    - "xfail strict=False marks broken SQLite-compat branch before DuckDB rewrite"
    - "TYPE_CHECKING + from __future__ import annotations for helper function type hints in test modules"

key-files:
  created: []
  modified:
    - tests/test_duckdb_repository.py

key-decisions:
  - "Split window_days coverage into two tests: None-path (passes today) and 7-day window (xfail until 16-02)"
  - "kudos_count=3 in seed (not 0) — activities_missing_kudos filters kudos_count>0; count=0 would return empty"
  - "from __future__ import annotations added to test file to allow TYPE_CHECKING forward reference without quotes"

patterns-established:
  - "Wave-0 guard pattern: xfail strict=False marks broken branch before rewrite; None-path guard verifies working path"

requirements-completed:
  - "Storage-layer modernization to DuckDB-native types (post-v1.1 maintenance)"

duration: 5min
completed: 2026-06-11
status: complete
---

# Phase 16 Plan 01: Window_days Kudos Regression Guard Summary

**xfail regression guard for kudos window_days branch + Assumption A1 confirmation before 16-02 rewrites the dead SQLite date('now', ?) SQL**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-11T08:49:00Z
- **Completed:** 2026-06-11T08:53:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Confirmed Assumption A1: `RepositoryActivityRow.date: str` exists at `types_repository.py:193`; `activity_rows.py:12` constructs it as `date=str(row["date"])`; `projection_services.py:197` reads `row.date`; `repository.py:302` uses `date=excluded.date` in ON CONFLICT UPDATE
- Added `test_activities_missing_kudos_with_window_days_none` — verifies the None-path (no window filter) returns all three seeded activities; passes today
- Added `test_activities_missing_kudos_with_window_days` — `@pytest.mark.xfail(strict=False)` marks the broken SQLite `date('now', ?)` branch; becomes GREEN after Plan 16-02 rewrites to DuckDB interval arithmetic
- Added `_seed_kudos_window_activities` helper seeding activities at day offsets -1, -5, -20 with `kudos_count=3` (non-zero so they appear as "missing kudos" candidates)
- No production code changed

## Task Commits

1. **Task W0-1: Confirm A1 and add window_days kudos test** - `8cde2b5` (test)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `tests/test_duckdb_repository.py` - Added `from __future__ import annotations`, `TYPE_CHECKING` import, helper `_seed_kudos_window_activities`, `test_activities_missing_kudos_with_window_days_none` (passes), `test_activities_missing_kudos_with_window_days` (xfail)

## Decisions Made

- Split into two test functions instead of one: the None-path must pass cleanly today, the window_days=7 path is xfail; combining them would mask the None-path outcome
- Seeded `kudos_count=3` (not 0): the query filters `kudos_count > 0`, so count=0 would have returned empty and made the None-path test vacuously pass against a wrong fixture
- Added `from __future__ import annotations` to satisfy UP037 (remove string quotes from type annotation) while keeping `DuckDBRepository` as a `TYPE_CHECKING`-only import

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed seed: kudos_count was 0, causing None-path test to return empty set**
- **Found during:** Task W0-1 (first test run)
- **Issue:** Plan spec said `kudos_count=0` but `activities_missing_kudos` filters `kudos_count > 0`; all three activities were excluded
- **Fix:** Changed seed to `kudos_count=3` so activities qualify as "missing kudos" candidates
- **Files modified:** tests/test_duckdb_repository.py
- **Verification:** `uv run pytest -k kudos` → 2 passed, 1 xfailed
- **Committed in:** `8cde2b5` (task commit)

**2. [Rule 1 - Bug] Fixed ruff UP037/F821: unquoted DuckDBRepository annotation outside TYPE_CHECKING scope**
- **Found during:** Task W0-1 (ruff check)
- **Issue:** Helper function annotation `"DuckDBRepository"` with quotes triggered UP037; without quotes triggered F821 (undefined name)
- **Fix:** Added `from __future__ import annotations` to defer all annotation evaluation; added `TYPE_CHECKING` block with `DuckDBRepository` import
- **Files modified:** tests/test_duckdb_repository.py
- **Verification:** `ruff check` → all checks passed
- **Committed in:** `8cde2b5` (task commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — bugs in spec/annotation)
**Impact on plan:** Both fixes necessary for test correctness and linter compliance. No scope creep.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## Next Phase Readiness

- Wave-0 guard is in place: `test_activities_missing_kudos_with_window_days` is xfail today
- Plan 16-02 rewrites `kudos_store.py` `window_days` branch to DuckDB-native `CURRENT_DATE - INTERVAL ? DAY` syntax
- After 16-02 the same test flips GREEN (xfail becomes unexpected pass → promoted to pass by strict=False)

## Self-Check: PASSED

---
*Phase: 16-duckdb-native-storage-cleanup*
*Completed: 2026-06-11*
