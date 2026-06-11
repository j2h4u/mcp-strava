---
phase: 04-application-services-cli-refit
plan: 03
subsystem: application
tags: [python, workouts, analytics, service-envelope, tdd]
requires:
  - phase: 04-application-services-cli-refit
    provides: 04-01 service envelope and freshness metadata
provides:
  - Recent workouts application service returning ServiceEnvelope
  - Per-workout analytics application service returning ServiceEnvelope
  - Product service registry wiring for workout services
affects: [cli, mcp-surface, application-services]
tech-stack:
  added: []
  patterns: [connection-injected-service-tests, envelope-wrapped-domain-output]
key-files:
  created:
    - src/mcp_strava/application/workouts.py
    - tests/test_application_workouts.py
  modified:
    - src/mcp_strava/application/__init__.py
    - src/mcp_strava/application/registry.py
key-decisions:
  - "Workout services read only from the local SQLite mirror."
  - "Per-workout analytics reuse existing enrich_activity calculations."
patterns-established:
  - "Workout availability and metric gaps are exposed as factual completeness metadata."
  - "The product service registry now includes report, weekly, workout, and freshness services."
requirements-completed: [APP-03, APP-04, TEST-04]
duration: 4min
completed: 2026-05-21
---

# Phase 04-03: Workout Application Services Summary

**Recent workout and per-workout analytics now run through the application service envelope**

## Performance

- **Duration:** 4 min
- **Completed:** 2026-05-21
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added `get_recent_workouts_service()` for compact local mirror workout lists.
- Added `get_workout_analytics_service()` for existing enriched workout metrics.
- Added support for `activity_id="latest"`.
- Added factual missing-data metadata for missing HR, missing streams, unavailable metrics, and not-found workouts.
- Registered workout services in `PRODUCT_SERVICES`.

## Task Commits

1. **Task 1: Add workout service contract tests** - `5851c1b` (test)
2. **Task 2: Implement workout application services** - `d48c89f` (feat)

## Files Created/Modified

- `src/mcp_strava/application/workouts.py` - Recent workouts and workout analytics services.
- `src/mcp_strava/application/__init__.py` - Public application exports.
- `src/mcp_strava/application/registry.py` - Product service registry wiring.
- `tests/test_application_workouts.py` - Fixture-backed workout service contract tests.

## Decisions Made

- Compact recent workouts preserve the existing local fields: id, date, name, sport, distance, moving time, TRIMP, average HR, and max HR.
- Per-workout analytics uses `enrich_activity()` instead of reimplementing formulas.
- Missing data remains factual metadata; services do not add coaching interpretation.

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

None.

## Verification

- `PYTHONPATH=src python3 -m pytest tests/test_application_workouts.py tests/test_application_services.py tests/test_security_guards.py -q` - 27 passed.
- `just test` - 108 passed.

## User Setup Required

None.

## Next Phase Readiness

CLI refit can route product commands through the completed application service registry.

---
*Phase: 04-application-services-cli-refit*
*Completed: 2026-05-21*
