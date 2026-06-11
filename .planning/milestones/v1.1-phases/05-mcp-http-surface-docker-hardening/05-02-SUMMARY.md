---
phase: 05-mcp-http-surface-docker-hardening
plan: 05-02
subsystem: api
tags: [mcp, metrics, services, sqlite, pytest]
requires:
  - phase: 05-01
    provides: metric registry contract and exclusion map
provides:
  - metric service backends for get_fitness_state/list_workouts/get_workout_detail
  - explicit registry-driven fitness projection with safety warning code contract
  - repository-backed workout filtering by date/sport for MCP read surface
affects: [phase-05-mcp-surface, compare-periods, project-fitness-state]
tech-stack:
  added: []
  patterns: [explicit-metric-projection, closed-warning-codes, repository-filtered-read-service]
key-files:
  created:
    - src/mcp_strava/application/metric_services.py
    - tests/test_metric_services.py
  modified:
    - src/mcp_strava/types.py
    - src/mcp_strava/application/__init__.py
    - src/mcp_strava/adapters/sqlite/repository.py
    - tests/test_security_guards.py
key-decisions:
  - "Fitness-state service builds metrics via explicit projection and never serializes report objects for filtering."
  - "Safety warnings use closed codes with optional numeric evidence payloads."
patterns-established:
  - "ServiceEnvelope data payloads for MCP backends carry only metric IDs plus freshness/completeness metadata."
  - "Workout list filters are executed in repository SQL with explicit start/end/sport parameters."
requirements-completed: [MCP-01, MCP-03, TEST-03]
duration: 3 min
completed: 2026-05-22
---

# Phase 05 Plan 02: Metric Service Backends Summary

**Registry-aligned metric services for fitness state, workout list, and workout detail with factual metadata and closed safety warning codes**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-22T15:19:59+05:00
- **Completed:** 2026-05-22T10:23:22Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Added RED tests for metric-service envelopes, no-coaching/no-admin payload constraints, warning-code contract, and source guards.
- Implemented `get_fitness_state_service`, `list_workouts_service`, and `get_workout_detail_service` in `metric_services.py` with explicit metric projection and repository-backed filtering.
- Extended repository with parameterized `list_activities()` filter support and exported new metric services through `application.__init__`.

## Task Commits

1. **Task 1: Add failing service tests for fitness and workout metric bundles** - `c9528ef` (test)
2. **Task 2: Implement fitness state and workout metric services** - `e896f7a` (feat)

## Files Created/Modified
- `src/mcp_strava/application/metric_services.py` - three MCP-target metric services, explicit projection, and structured warning code mapping.
- `src/mcp_strava/adapters/sqlite/repository.py` - `list_activities()` with `start_date/end_date/sport/limit/cursor` filtering and desc ordering.
- `src/mcp_strava/types.py` - `ServiceWarning.evidence` support for numeric warning context.
- `src/mcp_strava/application/__init__.py` - exports for new metric services and safety warning code set.
- `tests/test_metric_services.py` - service envelope and metric contract tests (RED/GREEN).
- `tests/test_security_guards.py` - metric-services import guard against strava/sync/runtime/token surfaces.

## Decisions Made
- `get_fitness_state_service` data payload is built with `_project_fitness_state_metrics` field-by-field mapping from model/analytics facts.
- Safety warning outputs are normalized to closed code values (`SAFETY_WARNING_CODES`) and keep evidence fields factual.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 05 now has service backends for 3/5 MCP tools with strict no-coaching/no-admin data boundaries.
- Ready for next plan to implement comparison/projection tool backends and MCP transport wiring.

## Self-Check: PASSED

---
*Phase: 05-mcp-http-surface-docker-hardening*
*Completed: 2026-05-22*
