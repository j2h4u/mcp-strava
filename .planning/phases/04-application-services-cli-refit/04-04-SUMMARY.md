---
phase: 04-application-services-cli-refit
plan: 04
subsystem: cli
tags: [python, cli, application-services, service-envelope, tdd]
requires:
  - phase: 04-application-services-cli-refit
    provides: 04-01 through 04-03 application services
provides:
  - Product/admin CLI split
  - Product commands backed by application services
  - Admin command namespace for local operator workflows
  - CLI replacement mapping documentation
affects: [cli, mcp-surface, docs]
tech-stack:
  added: []
  patterns: [product-admin-split, envelope-json-output, fixture-backed-cli-e2e]
key-files:
  created:
    - docs/cli.md
    - tests/test_cli_surface.py
    - tests/test_phase4_e2e.py
  modified:
    - src/mcp_strava/cli.py
    - tests/test_security_guards.py
    - tests/test_smoke.py
key-decisions:
  - "Product CLI commands call application services and emit full ServiceEnvelope JSON with --json."
  - "Admin/debug commands are namespaced under admin and stay outside PRODUCT_SERVICES."
patterns-established:
  - "CLI product handlers render human-readable sections while preserving factual freshness/completeness metadata."
  - "CLI replacement docs account for each old top-level command key."
requirements-completed: [APP-01, APP-02, APP-03, APP-04, CLI-01, CLI-02, CLI-03, TEST-04]
duration: 11min
completed: 2026-05-21
---

# Phase 04-04: CLI Product/Admin Refit Summary

**CLI now routes product commands through application services and isolates local operator commands under `admin`**

## Performance

- **Duration:** 11 min
- **Completed:** 2026-05-21
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Added product commands:
  - `report daily [--json]`
  - `weekly [--json]`
  - `workouts recent [--limit N] [--json]`
  - `workout analyze <id|latest> [--json]`
  - `freshness [--json]`
- Added `admin` namespace for mirror refresh, token refresh, backfill, SQL, raw, log, and DB safety commands.
- Added full JSON envelope output for product commands.
- Added human-readable product renderers with freshness, completeness, warnings, and rationale sections.
- Added fixture-backed CLI E2E test using a temporary SQLite DB.
- Added `docs/cli.md` replacement mapping for all old top-level command keys.

## Task Commits

1. **Task 1: Add CLI product/admin contract tests** - `9e4a9b6` (test)
2. **Task 2-3: Refit CLI and document replacement mapping** - `8c327e1` (feat)

## Files Created/Modified

- `src/mcp_strava/cli.py` - Product/admin command dispatcher and renderers.
- `docs/cli.md` - Old-to-new CLI replacement mapping.
- `tests/test_cli_surface.py` - CLI surface and rendering tests.
- `tests/test_phase4_e2e.py` - Fixture-backed CLI-to-service-to-repository test.
- `tests/test_security_guards.py` - Product/admin registry and CLI guard updates.
- `tests/test_smoke.py` - Application service import smoke coverage.

## Decisions Made

- Old top-level admin/debug aliases are not kept as hidden compatibility paths.
- `refresh` is now `admin token-refresh`; mirror refresh is `admin mirror-refresh`.
- Removed/deferred old workflows are documented rather than silently exposed.

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

None.

## Verification

- `PYTHONPATH=src python3 -m pytest tests/test_cli_surface.py tests/test_phase4_e2e.py tests/test_security_guards.py tests/test_smoke.py -q` - 44 passed.
- `PYTHONPATH=src python3 -m mcp_strava freshness --json` - printed a full service envelope from the local mirror without Strava API calls.
- `just test` - 123 passed.

## User Setup Required

None.

## Next Phase Readiness

Phase 5 can build the MCP HTTP surface against `PRODUCT_SERVICES` without discovering admin/debug commands.

---
*Phase: 04-application-services-cli-refit*
*Completed: 2026-05-21*
