---
phase: 04-application-services-cli-refit
plan: 02
subsystem: application
tags: [python, reports, weekly-digest, service-envelope, tdd]
requires:
  - phase: 04-application-services-cli-refit
    provides: 04-01 service envelope and freshness metadata
provides:
  - Daily report application service returning ServiceEnvelope
  - Weekly summary application service returning ServiceEnvelope
  - Connection-injected daily report helper for fixture tests
affects: [cli, mcp-surface, application-services]
tech-stack:
  added: []
  patterns: [connection-injected-service-tests, envelope-wrapped-domain-output]
key-files:
  created:
    - src/mcp_strava/application/reports.py
    - tests/test_application_reports.py
  modified:
    - src/mcp_strava/report.py
    - src/mcp_strava/analytics.py
    - src/mcp_strava/application/__init__.py
    - src/mcp_strava/application/registry.py
    - tests/test_smoke.py
key-decisions:
  - "Existing daily and weekly formulas are preserved and wrapped by application services."
  - "Report services accept injected connections so tests do not touch data/strava.db."
patterns-established:
  - "Application services build freshness first, compute domain data, then attach factual completeness/warnings."
  - "Daily report compatibility wrapper remains while service tests use daily_report_from_connection()."
requirements-completed: [APP-01, APP-02, APP-04, TEST-04]
duration: 5min
completed: 2026-05-21
---

# Phase 04-02: Report Application Services Summary

**Daily and weekly training analytics wrapped in shared service envelopes with fixture-backed parity tests**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-21T22:33:30+05:00
- **Completed:** 2026-05-21T22:38:48+05:00
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Added `get_daily_report_service()` and `get_weekly_summary_service()`.
- Refactored daily report calculations into `daily_report_from_connection()` while preserving `daily_report()`.
- Added optional `today` injection to `weekly_digest()` for deterministic service tests.
- Added fixture-backed report service tests and smoke imports.

## Task Commits

1. **Task 1: Add report and weekly service parity tests** - `7321f52` (test)
2. **Task 2: Implement daily and weekly application services** - `70d92c6` (feat)

## Files Created/Modified

- `src/mcp_strava/application/reports.py` - Daily/weekly application services and completeness helpers.
- `src/mcp_strava/report.py` - Connection-injected daily report helper plus compatibility wrapper.
- `src/mcp_strava/analytics.py` - Deterministic `today` injection for weekly digest.
- `tests/test_application_reports.py` - Fixture-backed envelope/parity tests.
- `tests/test_smoke.py` - Imports report services.

## Decisions Made

- Weekly digest keeps its existing calculation path and only receives date injection.
- Completeness uses repository daily load status for partial/unknown days and factual warning codes.

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

None.

## Verification

- `PYTHONPATH=src python3 -m pytest tests/test_application_reports.py tests/test_smoke.py -q` — 15 passed.
- `just test` — 103 passed.

## User Setup Required

None.

## Next Phase Readiness

Workout services can reuse the same envelope/freshness/completeness pattern and registry wiring.

---
*Phase: 04-application-services-cli-refit*
*Completed: 2026-05-21*
