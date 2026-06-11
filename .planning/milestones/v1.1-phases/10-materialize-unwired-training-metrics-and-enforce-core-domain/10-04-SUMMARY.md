---
phase: 10-materialize-unwired-training-metrics-and-enforce-core-domain
plan: "04"
subsystem: cleanup
tags: [dead-code-removal, test-repair, domain-separation]
dependency_graph:
  requires: ["10-01", "10-03"]
  provides: ["clean-db-module", "honest-test-suite"]
  affects: ["src/mcp_strava/db.py", "tests/test_smoke.py", "tests/test_metric_services.py", "tests/test_security_guards.py"]
tech_stack:
  added: []
  patterns: ["dead-code removal", "import cleanup", "test suite honesty"]
key_files:
  created: []
  modified:
    - src/mcp_strava/db.py
    - tests/test_smoke.py
    - tests/test_metric_services.py
    - tests/test_security_guards.py
decisions:
  - "timedelta removed from db.py imports — only used by the deleted function; datetime stays for _RealClock and get_zones"
  - "DecouplingResult dropped from smoke test import — unused after plan 10-01 cleanup; dataclass stays defined in mcp_strava.types"
  - "legacy_db_imports cli.py guard (get_daily_trimp_history, api_request) left intact — correctly forbids re-importing deleted/restricted symbols into cli.py"
metrics:
  duration: "2 min"
  completed: "2026-05-29"
  tasks: 3
  files: 4
---

# Phase 10 Plan 04: Dead Code Cleanup and Test Suite Repair Summary

Deleted `get_daily_trimp_history` from db.py (zero src importers per RESEARCH.md), dropped its dangling import from test_smoke.py in the same wave, removed `DecouplingResult` from the smoke import tidy, and purged all stale `enrich_activity` references from test_metric_services.py and test_security_guards.py (CONTEXT.md scope item 5).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Delete dead db.py::get_daily_trimp_history | ba0639b | src/mcp_strava/db.py |
| 2 | Repair test_smoke.py — drop get_daily_trimp_history + DecouplingResult import | d94bd78 | tests/test_smoke.py |
| 3 | Remove stale enrich_activity refs from test_metric_services.py and test_security_guards.py | a28e8b7 | tests/test_metric_services.py, tests/test_security_guards.py |

## Verification Results

- `grep -c 'def get_daily_trimp_history' src/mcp_strava/db.py` → 0
- `grep -c get_daily_trimp_history tests/test_smoke.py` → 0
- `grep -c enrich_activity tests/test_metric_services.py tests/test_security_guards.py` → 0 for both
- `PYTHONPATH=src uv run python -m pytest tests/test_smoke.py tests/test_security_guards.py tests/test_metric_services.py -q` → **43 passed**
- Legacy cli.py import guard (`tests/test_security_guards.py -k legacy`) → **3 passed**

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

One observation: `timedelta` (removed alongside the deleted function) was the only caller; `datetime` was retained as it is used by `_RealClock.now()` and `get_zones()`. This was anticipated in the plan's action description.

## Known Stubs

None.

## Threat Flags

None — this plan only removes dead code and stale test references; no new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Self-Check: PASSED

- ba0639b exists: confirmed
- d94bd78 exists: confirmed
- a28e8b7 exists: confirmed
- src/mcp_strava/db.py modified: confirmed (no get_daily_trimp_history)
- tests/test_smoke.py modified: confirmed (no get_daily_trimp_history, no DecouplingResult)
- tests/test_metric_services.py modified: confirmed (no enrich_activity)
- tests/test_security_guards.py modified: confirmed (no enrich_activity in target sets)
