---
phase: 10-materialize-unwired-training-metrics-and-enforce-core-domain
plan: "03"
subsystem: metrics-materialization
tags: [materialization, pure-functions, tdd, bug-fix, hr-recovery, vertical-speed, cardiac-drift, hrr]
dependency_graph:
  requires: [10-01]
  provides: [wired-metric-columns, populated-activity-metric-facts]
  affects:
    - src/mcp_strava/adapters/duckdb/read_model_materializer.py
    - tests/test_read_model_materialization.py
tech_stack:
  added: []
  patterns: [pure-function-wiring, tdd-red-green, none-safe-access]
key_files:
  created: []
  modified:
    - src/mcp_strava/adapters/duckdb/read_model_materializer.py
    - tests/test_read_model_materialization.py
decisions:
  - "metric_version is NOT bumped — column set and formula identities are unchanged; only defaults are replaced with computed values"
  - "hrr_pct uses hr_max_observed already in scope in _activity_fact, not repo.max_heartrate()"
  - "cardiac_drift_significant collapses insufficient-data and computed-but-not-significant into 0 — pre-existing design, carried over unchanged"
metrics:
  duration: "~10 min"
  completed: "2026-05-29"
  tasks_completed: 2
  files_changed: 2
---

# Phase 10 Plan 03: Wire Pure Metric Functions into Materializer Summary

All 14 previously-hardcoded default columns in `_activity_fact` now call the pure functions from plan 10-01: `calc_hr_recovery`, `calc_vertical_speed`, `calc_cardiac_drift`, and `calc_hrr_pct`. The registered, exposed metrics stop returning null/0.

## What Was Built

**`src/mcp_strava/adapters/duckdb/read_model_materializer.py`**
- Added import: `from mcp_strava.metrics import calc_hr_recovery, calc_vertical_speed, calc_cardiac_drift, calc_hrr_pct`
- In `_activity_fact`, before building the return dict: fetches `hr_rows`, `alt_rows`, `drift_rows`, `median_hr` via repo; calls the four pure functions; replaces all 14 hardcoded defaults with None-safe access from the results
- Full column mapping wired (all 14 per PLAN.md mapping table)
- `hrr_pct` uses `hr_max_observed` already computed in `_activity_fact` — does NOT call `repo.max_heartrate()`
- `metric_version` unchanged (explicit decision — see below)

**`tests/test_read_model_materialization.py`**
- `test_duckdb_materializer_populates_metric_columns_not_defaults` — asserts `vertical_speed_vmh > 0`, `cardiac_drift_quality not None`, `hrr_pct not None`, `trimp > 0` (regression)
- `test_duckdb_materializer_pause_inclusive_hr_recovery` — pause-inclusive fixture (33 rows at velocity=0.0 with 1s intervals), asserts `hr_recovery_median_rate not None` and `hr_recovery_pause_count >= 1`
- `test_duckdb_materializer_rolling_median_populates` — asserts `rolling["median_hr_recovery"] is not None`, proving `_materialize_rolling_facts` SELECTs the matching source column name
- `test_duckdb_materializer_no_hr_columns_stay_at_defaults` — no-HR activity, asserts 7 HR-derived columns stay at defaults without raising; does NOT assert `vertical_speed_*` (altitude-derived, independent of HR)

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | RED — add failing tests for 14 metric columns | 5cd3db9 | tests/test_read_model_materialization.py |
| 2 | GREEN — wire pure functions, fix pause fixture | 4281b67 | src/mcp_strava/adapters/duckdb/read_model_materializer.py, tests/test_read_model_materialization.py |

## Verification Results

- `uv run python -m pytest tests/test_read_model_materialization.py -k "populates_metric_columns or pause or rolling_median or no_hr" -v` — 4 passed
- `uv run python -m pytest tests/test_read_model_materialization.py tests/test_metric_registry.py -q` — 29 passed
- Full suite: 319 passed, 0 failed
- `from mcp_strava.adapters.duckdb.read_model_materializer import materialize_read_model` — import OK
- `_activity_fact` imports and calls all four pure functions; uses `hr_max_observed` for `hrr_pct`; all 14 columns populated; `metric_version` unchanged

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pause fixture used 10s intervals, calc_hr_recovery gap-break rejected each row**
- **Found during:** Task 2 GREEN (pause test still failing after wiring)
- **Issue:** `calc_hr_recovery` breaks a pause segment when consecutive data points are > 3 seconds apart. The fixture used `time_offset = idx * 10` (10s intervals), so every pair of rows triggered the gap break, producing 0-duration "pauses" that were all rejected as < MIN_PAUSE_SEC=30.
- **Fix:** Changed the pause fixture to use `time_offset = idx` (1-second intervals). 33 consecutive stopped rows now form a 33s pause >= MIN_PAUSE_SEC=30. Added a comment explaining the requirement in the fixture docstring.
- **Files modified:** tests/test_read_model_materialization.py
- **Commit:** 4281b67

## TDD Gate Compliance

- RED gate: commit 5cd3db9 `test(10-03): RED — add failing tests for 14 metric columns (RED)` — 3 of 4 new tests failed (no-HR test correctly passes at RED, asserting defaults that already hold)
- GREEN gate: commit 4281b67 `feat(10-03): GREEN — wire pure metric functions into _activity_fact (GREEN)` — all 4 new tests pass, full suite 319 passed

## Known Stubs

None — all 14 columns now compute from real stream data via the pure functions. No hardcoded placeholders remain in the metric columns block.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. All row fetches use existing parameterized repo methods (T-10-IV: accept).

## Self-Check: PASSED

- src/mcp_strava/adapters/duckdb/read_model_materializer.py: FOUND
- tests/test_read_model_materialization.py: FOUND
- commit 5cd3db9 (RED): FOUND
- commit 4281b67 (GREEN): FOUND
