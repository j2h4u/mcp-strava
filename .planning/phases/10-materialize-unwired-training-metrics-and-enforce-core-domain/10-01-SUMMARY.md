---
phase: 10-materialize-unwired-training-metrics-and-enforce-core-domain
plan: "01"
subsystem: metrics
tags: [pure-functions, domain-separation, tdd, refactor]
dependency_graph:
  requires: []
  provides: [pure-metric-functions, import-clean-metrics-module]
  affects: [src/mcp_strava/metrics.py, tests/test_metrics_pure.py, tests/test_smoke.py]
tech_stack:
  added: []
  patterns: [pure-function-extraction, conn-coupled-to-plain-data, tdd-red-green]
key_files:
  created:
    - tests/test_metrics_pure.py
  modified:
    - src/mcp_strava/metrics.py
    - tests/test_smoke.py
decisions:
  - "Keep calc_hrr_pct as a top-level pure function alongside the other three — no storage access, inline formula, testable in isolation"
  - "Remove _decoupling_invalid and calc_decoupling in the same commit as the smoke test repair (Task 3) — they were kept in the Task 2 draft then removed atomically with their tests"
metrics:
  duration: "~8 min"
  completed: "2026-05-29"
  tasks_completed: 3
  files_changed: 3
---

# Phase 10 Plan 01: Pure Metric Functions in metrics.py Summary

Pure domain extraction: four metric functions now take plain dict rows and return dataclasses with no storage import, closing the core/domain-separation violation and unblocking plan 10-03 materialization.

## What Was Built

- `calc_hr_recovery(rows)` — takes `{time_offset, heartrate, velocity}` rows, detects rest pauses >= MIN_PAUSE_SEC, returns HrRecovery or None
- `calc_vertical_speed(rows)` — takes `{time_offset, altitude}` rows, computes ascent speed in m/h, returns VerticalSpeed or None
- `calc_cardiac_drift(rows, sport_type=None)` — takes `{heartrate, velocity}` rows, uses Jenks clustering, returns CardiacDriftResult or None
- `calc_hrr_pct(median_hr, hr_rest, hr_max)` — pure formula function, `calc_hrr_pct(150, 50, 200) == 66.7`
- `from mcp_strava.db import repository_from_connection` removed from metrics.py
- Dead conn-coupled functions removed: `enrich_activity`, `calc_decoupling_with_gate`, `_fetch_decoupling_rows`, `calc_efficiency_factor`, `_decoupling_invalid`, `calc_decoupling`
- `tests/test_metrics_pure.py` — 4 unit tests over plain dict rows, no DB
- `tests/test_smoke.py` — removed references to deleted symbols so full suite remains collectable

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | RED — failing pure-function tests | 32c8d70 | tests/test_metrics_pure.py |
| 2 | GREEN — extract pure functions, drop db import | 807ec53 | src/mcp_strava/metrics.py |
| 3 | Repair test_smoke.py for deleted symbols | c0cfe43 | tests/test_smoke.py, src/mcp_strava/metrics.py |

## Verification Results

- `uv run python -m pytest tests/test_metrics_pure.py -x -q` — 4 passed
- `uv run python -c "import mcp_strava.metrics"` — exits 0
- `grep -c "from mcp_strava.db import" src/mcp_strava/metrics.py` — 0
- `calc_hrr_pct(150, 50, 200) == 66.7` — confirmed
- `uv run python -m pytest --collect-only -q` — 315 tests collected, no ImportError

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] _decoupling_invalid and calc_decoupling not removed in Task 2 draft**
- **Found during:** Task 3 review
- **Issue:** Plan's Task 2 action listed `_decoupling_invalid` and `calc_decoupling` in the delete list, but my initial Task 2 commit kept them (they were still referenced by smoke tests at that point). The plan intends both the deletions and the smoke repairs to happen atomically in wave 1.
- **Fix:** Removed both functions from metrics.py in the same commit as Task 3's smoke test repair (c0cfe43), maintaining the wave-1 atomicity guarantee.
- **Files modified:** src/mcp_strava/metrics.py, tests/test_smoke.py
- **Commit:** c0cfe43

## TDD Gate Compliance

- RED gate: commit 32c8d70 `test(10-01): add failing tests for pure metric functions (RED)` — tests failed at collection due to ImportError chain (db import → duckdb not available in system Python; correct RED failure)
- GREEN gate: commit 807ec53 `feat(10-01): extract pure functions, drop db import and dead code (GREEN)` — 4 tests passed via `uv run`
- REFACTOR: commit c0cfe43 removed residual functions and repaired smoke tests — suite still green

## Known Stubs

None — all four pure functions compute from real data, no hardcoded placeholders.

## Threat Flags

None — the one threat from the plan (T-10-01: `mcp_strava.db` import surface) is now resolved. `grep -c "from mcp_strava.db import" src/mcp_strava/metrics.py` returns 0.

## Self-Check: PASSED

- tests/test_metrics_pure.py: FOUND
- src/mcp_strava/metrics.py: FOUND
- commit 32c8d70 (RED): FOUND
- commit 807ec53 (GREEN): FOUND
- commit c0cfe43 (Task 3): FOUND
