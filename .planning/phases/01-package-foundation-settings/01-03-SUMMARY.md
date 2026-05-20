---
phase: 01-package-foundation-settings
plan: 03
subsystem: testing
tags: [pytest, justfile, smoke-tests, package-imports]
requires: [FOUND-01, FOUND-02]
provides:
  - Pytest-native smoke execution for packaged mcp_strava modules.
  - `just test` routed to `python3 -m pytest` as primary workflow.
  - Removal of legacy `scripts/run_tests.py` from active test path.
affects: [FOUND-03, test-workflow, smoke-coverage]
tech-stack:
  added: []
  patterns: [pytest-discovery, package-qualified-imports, fail-closed-smoke-skip]
key-files:
  created: [.planning/phases/01-package-foundation-settings/01-03-SUMMARY.md]
  modified: [tests/test_smoke.py, Justfile, src/mcp_strava/cli.py, src/mcp_strava/strava_api_reference.py]
  deleted: [scripts/run_tests.py]
decisions:
  - Keep smoke coverage function set unchanged while migrating imports to `mcp_strava.*`.
  - Treat absent or schema-incomplete local DB as explicit pytest skip in smoke path.
metrics:
  duration: 29min
  completed: 2026-05-20
  tasks_completed: 3
---

# Phase 01 Plan 03: Pytest Workflow Summary

Converted baseline smoke verification to pytest over the packaged code and made `just test` the single primary test command.

## Task Commits

1. `bf1d141` — test(01-package-foundation-settings-03): migrate smoke tests to mcp_strava pytest imports
2. `4a21c5d` — chore(01-package-foundation-settings-03): route just test to pytest
3. `f74d972` — chore(01-package-foundation-settings-03): retire legacy custom smoke runner
4. `ff36929` — fix(01-package-foundation-settings-03): remove stale strava_lib source references

## Verification Results

- `python3 -m pytest tests/test_smoke.py` -> 12 passed
- `just test` -> 21 passed
- `python3 -m pytest` -> 21 passed
- `rg "strava_lib|scripts/run_tests.py" tests Justfile pyproject.toml src` -> no matches
- `PYTHONPATH=src python3 -m mcp_strava` -> usage output shown
- `python3 -m pytest tests/test_smoke.py -q` -> 12 passed
- `test -f data/strava.db` -> pass

## Deviations from Plan

### Auto-fixed Issues

1. [Rule 1 - Bug] Fixed smoke instability caused by cached settings leaking from `tests/test_settings.py` into DB-backed smoke
- Found during: Task 2 verification (`just test`)
- Issue: `daily_report()` opened a temporary DB path cached by previous settings tests and failed with `no such table: activities`.
- Fix: Reset settings cache before `daily_report()` in `test_daily_report`.
- Files modified: `tests/test_smoke.py`
- Commit: `4a21c5d`

2. [Rule 1 - Bug] Removed stale `strava_lib` references in package source to satisfy no-primary-path-reference gate
- Found during: Final verification grep
- Issue: `src/mcp_strava/cli.py` and `src/mcp_strava/strava_api_reference.py` still contained `strava_lib` text.
- Fix: Updated both references to `mcp_strava`.
- Files modified: `src/mcp_strava/cli.py`, `src/mcp_strava/strava_api_reference.py`
- Commit: `ff36929`

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED

- FOUND: `.planning/phases/01-package-foundation-settings/01-03-SUMMARY.md`
- FOUND: commits `bf1d141`, `4a21c5d`, `f74d972`, `ff36929`
