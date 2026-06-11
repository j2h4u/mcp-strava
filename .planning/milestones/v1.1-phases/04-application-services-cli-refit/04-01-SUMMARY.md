---
phase: 04-application-services-cli-refit
plan: 01
subsystem: application
tags: [python, sqlite, freshness, service-envelope, tdd]
requires:
  - phase: 03-strava-adapter-refresh-runtime
    provides: refresh_state, refresh_requests, RefreshPolicy
provides:
  - Shared ServiceEnvelope/FreshnessMetadata/CompletenessMetadata contracts
  - Application freshness service with lazy first-use refresh signaling
  - Product service registry skeleton for future MCP allowlist
  - Repository helpers for latest activity timestamp/id
affects: [phase-04, phase-05-mcp, cli, application-services]
tech-stack:
  added: []
  patterns: [application-service-envelope, product-service-registry, fixture-sqlite-tests]
key-files:
  created:
    - src/mcp_strava/application/__init__.py
    - src/mcp_strava/application/freshness.py
    - src/mcp_strava/application/registry.py
    - tests/test_application_services.py
  modified:
    - src/mcp_strava/types.py
    - src/mcp_strava/adapters/sqlite/repository.py
    - tests/test_security_guards.py
key-decisions:
  - "First-use refresh uses local-day comparison, not age-based stale thresholds."
  - "Product application package is guarded from Strava/sync/runtime imports."
patterns-established:
  - "Application services return ServiceEnvelope with data, freshness, completeness, warnings, and rationale."
  - "Freshness metadata separates last_successful_refresh_at from last_activity_at."
requirements-completed: [APP-04, TEST-04]
duration: 19min
completed: 2026-05-21
---

# Phase 04-01: Application Freshness Contract Summary

**Shared product service envelope and local freshness metadata with idempotent first-use refresh signaling**

## Performance

- **Duration:** 19 min
- **Started:** 2026-05-21T22:14:00+05:00
- **Completed:** 2026-05-21T22:33:18+05:00
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Added service envelope dataclasses for Phase 4 product services.
- Added `build_freshness_metadata()` and `get_freshness_service()` over local SQLite state only.
- Added `latest_activity_at()` and `latest_activity_id()` repository helpers.
- Added AST guard proving product application services do not import Strava, sync, or refresh runtime execution.

## Task Commits

1. **Task 1: Add failing envelope and freshness metadata tests** - `c8f3e8d` (test)
2. **Task 2: Implement service envelope, freshness metadata, and product registry skeleton** - `dcc7b75` (feat)

## Files Created/Modified

- `src/mcp_strava/types.py` - Service envelope, freshness, completeness, warning, and rationale dataclasses.
- `src/mcp_strava/application/freshness.py` - Factual freshness metadata builder and freshness service.
- `src/mcp_strava/application/registry.py` - Product service allowlist skeleton.
- `src/mcp_strava/adapters/sqlite/repository.py` - Latest activity helpers.
- `tests/test_application_services.py` - Fixture-backed freshness contract tests.
- `tests/test_security_guards.py` - Product application import boundary guard.

## Decisions Made

- First-use refresh is signaled when no successful refresh happened on the current local day, even if the mirror is still age-fresh.
- `get_freshness_service()` returns freshness metadata as both `data` and envelope `freshness` for the product `freshness` command.

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

- The first fixture schema missed `idx_streams_act`; fixed before committing RED so failures targeted the missing application layer.

## Verification

- `PYTHONPATH=src python3 -m pytest tests/test_application_services.py tests/test_security_guards.py -q` — 22 passed.
- `just test` — 100 passed.

## User Setup Required

None.

## Next Phase Readiness

Report, weekly, and workout services can now wrap existing analytics in the shared envelope and reuse the local freshness metadata.

---
*Phase: 04-application-services-cli-refit*
*Completed: 2026-05-21*
