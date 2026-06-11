---
phase: 05-mcp-http-surface-docker-hardening
plan: 05-01
subsystem: api
tags: [mcp, metrics, registry, pytest, contracts]
requires:
  - phase: 04-application-services-cli-refit
    provides: application services, freshness/completeness envelope, report/workout facts
provides:
  - complete MCP metric registry contract with metadata
  - explicit interpretation exclusions with preserved numeric/model facts
  - docs and tests that prevent silent registry drift
affects: [phase-05-mcp-surface, compare-periods, project-fitness-state]
tech-stack:
  added: []
  patterns: [registry-as-contract, docs-synced-by-test]
key-files:
  created:
    - src/mcp_strava/application/metric_registry.py
    - tests/test_metric_registry.py
    - docs/metrics.md
  modified:
    - src/mcp_strava/types.py
    - src/mcp_strava/application/__init__.py
    - tests/test_smoke.py
key-decisions:
  - "Use final MCP tool ids only: get_fitness_state, list_workouts, get_workout_detail, compare_periods, project_fitness_state."
  - "Exclude recommendation/weekly-plan/safety language fields from metrics and preserve only numeric/model inputs."
patterns-established:
  - "Metric contract is centralized in METRIC_REGISTRY with required metadata fields."
  - "Documentation drift is blocked by tests asserting docs contain all registry and exclusion keys."
requirements-completed: [MCP-01, MCP-03, TEST-03]
duration: 8 min
completed: 2026-05-22
---

# Phase 05 Plan 01: Metric Registry Contract Summary

**Complete MCP-facing metric registry with comparison metadata, interpretation exclusions, and anti-drift tests/docs coverage**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-22T10:08:00Z
- **Completed:** 2026-05-22T10:16:48Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Added TDD RED coverage for required metric ids, metadata quality, enum/tool-id validity, and interpretation exclusion mapping.
- Implemented `MetricDefinition`/`ExcludedInterpretation` dataclasses plus a full `METRIC_REGISTRY` and helper APIs (`metric_definition`, `metrics_for_tool`, `comparable_metrics`, `metric_catalog_payload`).
- Added synced docs table and exclusions section in `docs/metrics.md`, with tests ensuring docs include all metric ids and exclusion keys.

## Task Commits

1. **Task 1: Add failing metric registry coverage tests** - `f9b7824` (test)
2. **Task 2: Implement registry dataclasses and complete metric catalog** - `e14dd43` (feat)
3. **Task 3: Document the metric registry contract** - `2640a92` (docs)

## Files Created/Modified

- `src/mcp_strava/application/metric_registry.py` - full metric and exclusion registry plus registry query helpers
- `src/mcp_strava/types.py` - new registry dataclasses
- `src/mcp_strava/application/__init__.py` - registry exports
- `tests/test_metric_registry.py` - full registry contract tests and docs sync tests
- `tests/test_smoke.py` - smoke import for metric registry
- `docs/metrics.md` - agent-facing metric catalog and exclusion contract

## Decisions Made

- Final MCP tool ids are the only allowed `exposed_in` values; unknown tool ids are rejected by `metrics_for_tool`.
- Interpretive/coaching fields are explicitly excluded and mapped to preserved numeric/model metric inputs.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Metric contract layer is complete and test-protected.
- Ready for next Phase 05 plan to consume registry definitions in MCP service/tool wiring.

## Self-Check: PASSED

---
*Phase: 05-mcp-http-surface-docker-hardening*
*Completed: 2026-05-22*
