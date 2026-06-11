---
phase: 05-mcp-http-surface-docker-hardening
plan: 05-03
subsystem: api
tags: [mcp, metrics, comparison, projection, pytest]
requires:
  - phase: 05-01
    provides: metric registry contract and exclusions
  - phase: 05-02
    provides: fitness/workout metric service baselines
provides:
  - compare_periods_service with global/per-sport factual metric deltas
  - project_fitness_state_service with rest/easy/maintain/custom simulations
  - explicit custom scenario validation and no-coaching output guarantees
affects: [phase-05-mcp-surface, compare-periods, project-fitness-state]
tech-stack:
  added: []
  patterns: [registry-driven-comparison, scenario-simulation-with-validation]
key-files:
  created: []
  modified:
    - src/mcp_strava/application/metric_services.py
    - src/mcp_strava/application/__init__.py
    - tests/test_metric_services.py
    - tests/test_metric_registry.py
decisions:
  - "compare_periods exposes factual records with period_a/period_b, delta, delta_pct, trend_direction, sample_size, coverage, missing_reasons."
  - "projection scenarios are facts-only and never rank or recommend scenarios."
metrics:
  duration: "completed in-session"
  completed: 2026-05-22
---

# Phase 05 Plan 03: Comparison And Projection Services Summary

Implemented registry-driven period comparison and fitness projection services, preserving synthetic metric coverage and non-prescriptive contracts for MCP tools.

## Task Commits

1. `faa312c` — `test(05-03): add failing coverage for compare_periods metric service`
2. `1c9034e` — `feat(05-03): implement registry-driven compare_periods service`
3. `94cd44d` — `test(05-03): add failing projection scenario and validation tests`
4. `8606650` — `feat(05-03): implement projection scenarios and custom validation`

## Verification

- `python3 -m pytest tests/test_metric_services.py tests/test_metric_registry.py -q` ✅
- `just test` ✅ (139 passed)

## Deviations from Plan

### Auto-fixed Issues

1. **[Rule 1 - Bug] Enriched activity has no `cc_adj` attribute**
- **Found during:** Task 2 verification
- **Issue:** `cardiac_cost_adjusted` aggregation referenced a missing field and failed comparison tests.
- **Fix:** Switched adjusted-cost extraction to available enriched cardiac-cost value for comparison records.
- **Files modified:** `src/mcp_strava/application/metric_services.py`
- **Commit:** `1c9034e`

## Authentication Gates

None.

## Known Stubs

None.

## Self-Check: PASSED
