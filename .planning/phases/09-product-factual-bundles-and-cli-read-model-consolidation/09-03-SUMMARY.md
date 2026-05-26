---
phase: 09-product-factual-bundles-and-cli-read-model-consolidation
plan: 09-03
subsystem: cli
tags: [cli, product-facts, read-model, boundary-guards, tdd]
requires:
  - phase: 09-02
    provides: Shared daily_brief, weekly_digest, and historical_facts product fact services over aggregate/read-model data
provides:
  - Thin product CLI commands backed by product fact and metric services
  - Retired legacy report/workout application modules and dead CLI handlers
  - Tested replacement paths for former activities, gear, stats, trend, and kudos commands
  - Product service registry aligned with Phase 9 factual bundle services
affects: [phase-09-04, cli-product-read-model, product-service-registry, mcp-boundary]
tech-stack:
  added: []
  patterns:
    - CLI product commands delegate to the same application services as MCP-facing code
    - Local admin commands remain explicit under ADMIN_COMMANDS
    - Legacy module retirement is guarded by AST tests instead of text grep
key-files:
  created:
    - .planning/phases/09-product-factual-bundles-and-cli-read-model-consolidation/09-03-SUMMARY.md
  modified:
    - src/mcp_strava/cli.py
    - src/mcp_strava/application/registry.py
    - tests/test_cli_surface.py
    - tests/test_security_guards.py
    - tests/test_application_reports.py
    - tests/test_application_workouts.py
    - tests/test_smoke.py
    - docs/cli.md
  deleted:
    - src/mcp_strava/application/reports.py
    - src/mcp_strava/application/workouts.py
key-decisions:
  - "CLI daily and weekly product reads now call product fact bundle services instead of legacy report recomputation."
  - "CLI workout list/detail reads now call metric_services read-model services, including filter forwarding and detail-only kudos/gear facts."
  - "Legacy application.reports and application.workouts modules were retired rather than retained as compatibility aliases."
patterns-established:
  - "CLI replacement-path tests use service spies plus AST guards to prove product/admin boundary routing."
  - "Docs preserve capability mapping without promising old command names or JSON shapes."
requirements-completed: [CLI-01, CLI-02, CLI-03, APP-01, APP-02, APP-03, APP-04, MCP-02, TEST-03, TEST-04]
duration: 10 min
completed: 2026-05-26
---

# Phase 09 Plan 09-03: CLI Read-Model Consolidation Summary

**Product CLI daily, weekly, workout, and freshness reads now share read-model-backed application services with MCP-facing code**

## Performance

- **Duration:** 10 min
- **Started:** 2026-05-26T14:22:54Z
- **Completed:** 2026-05-26T14:31:56Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments

- Added RED tests proving product CLI commands must delegate to product fact bundles and metric services, not legacy report/workout modules.
- Rewired `report daily`, `weekly`, `workouts recent`, `workout analyze`, and `freshness` to thin application-service calls.
- Added `workouts recent` filter forwarding for `--limit`, `--start-date`, `--end-date`, and `--sport`.
- Removed dead legacy CLI handlers for activities, gear, stats, sync, backtest, trend, and kudos paths.
- Deleted legacy `application.reports` and `application.workouts` modules after replacing their product surface with `product_facts` and `metric_services`.
- Updated CLI docs with current replacement rows for activities, gear, stats, backtest, trend, and kudos without preserving old command aliases.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add failing CLI consolidation and dead-handler tests** - `d960b22` (`test`)
2. **Task 2: Rewire CLI to product facts and remove dead legacy handlers** - `3d6a42f` (`feat`)

## Verification

- `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` - RED failed before implementation with 15 expected failures against legacy CLI routing and docs/registry gaps.
- `uv run pytest -q tests/test_cli_surface.py tests/test_security_guards.py` - passed, 48 tests.
- `uv run pytest -q tests/test_application_reports.py tests/test_application_workouts.py tests/test_smoke.py` - passed, 16 tests and 1 skipped.
- `uv run pytest -q` - passed, 343 tests and 1 skipped.
- `PYTHONPATH=src uv run python -m mcp_strava` - usage lists only `report`, `weekly`, `workouts`, `workout`, `freshness`, and `admin`.
- Product/MCP boundary check confirmed `sync`, `backfill`, `raw`, `sql`, `token`, `migration`, `log`, and `duckdb-cutover` are absent from `PRODUCT_SERVICES` and `MCP_TOOL_NAMES`.
- AST check confirmed `cmd_activities`, `cmd_gear`, `cmd_stats`, `cmd_backtest`, `cmd_trend`, and `cmd_kudos` are absent.

## Files Created/Modified

- `src/mcp_strava/cli.py` - Product commands now call product fact and metric services; legacy unregistered handlers were removed; admin commands remain namespaced.
- `src/mcp_strava/application/registry.py` - Product service allowlist now registers daily/weekly/historical fact services and metric read services.
- `src/mcp_strava/application/reports.py` - Deleted legacy report-service module.
- `src/mcp_strava/application/workouts.py` - Deleted legacy workout-service module.
- `tests/test_cli_surface.py` - Covers product-service delegation, replacement paths, filter forwarding, kudos/gear detail facts, and docs mapping.
- `tests/test_security_guards.py` - Adds AST guards for retired CLI handlers/imports and product command service routing.
- `tests/test_application_reports.py` - Tracks legacy report module retirement and current product fact service surface.
- `tests/test_application_workouts.py` - Tracks legacy workout module retirement and current metric service surface.
- `tests/test_smoke.py` - Updates package import smoke to current product fact and metric services.
- `docs/cli.md` - Documents current product/admin commands and replacement mapping.

## Decisions Made

- Daily and weekly CLI JSON now exposes Phase 9 bundle payloads through `get_daily_brief_facts_service` and `get_weekly_digest_facts_service`.
- Workout list/detail CLI commands use `list_workouts_service` and `get_workout_detail_service`, preserving read-model status metadata, kudos counts/names, and mirrored gear facts where available.
- Legacy report/workout service modules were deleted instead of kept as aliases because there is no current runtime compatibility need.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated stale legacy module tests after deleting retired modules**
- **Found during:** Task 2 (GREEN implementation)
- **Issue:** Existing smoke/application tests still imported `mcp_strava.application.reports` and `mcp_strava.application.workouts`, which would block full-suite verification after the planned module retirement.
- **Fix:** Converted those tests to assert module retirement and current product fact/metric service import surfaces.
- **Files modified:** `tests/test_application_reports.py`, `tests/test_application_workouts.py`, `tests/test_smoke.py`
- **Verification:** `uv run pytest -q tests/test_application_reports.py tests/test_application_workouts.py tests/test_smoke.py`; `uv run pytest -q`
- **Committed in:** `3d6a42f`

---

**Total deviations:** 1 auto-fixed (1 Rule 3 blocking issue)
**Impact on plan:** Required to keep the test suite aligned with the planned legacy module deletion. No product/admin/MCP scope expansion.

## Issues Encountered

- No authentication or package-install gates occurred.
- Intentional deletions in Task 2: `src/mcp_strava/application/reports.py` and `src/mcp_strava/application/workouts.py`.

## Known Stubs

None. Stub-pattern scan found only test fixture placeholders, intentional empty fixture lists/dicts, and optional admin-local defaults; no runtime placeholder data source was introduced.

## Authentication Gates

None.

## Threat Flags

None. The changed shell-args-to-CLI and CLI-to-application boundaries are the trust boundaries covered by the plan threat model; admin/raw/sql/token/backfill/cutover paths remain under `admin`, and no MCP tool surface was added.

## TDD Gate Compliance

- RED gate: `d960b22` added failing CLI consolidation, replacement-path, docs, and AST guard tests.
- GREEN gate: `3d6a42f` rewired CLI/registry/docs and retired legacy modules until targeted and full tests passed.
- Refactor gate: no separate behavior-neutral refactor commit was needed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for Plan 09-04. CLI product reads now share the Phase 9 factual bundle/read-model contract, while MCP remains constrained to its existing product tool allowlist for bundle/completeness smoke and verification docs.

## Self-Check: PASSED

- Verified modified files exist on disk and deleted files are absent as intended.
- Verified task commits `d960b22` and `3d6a42f` exist in git history.
- Verified targeted, affected, and full pytest commands passed.
- Verified root CLI usage and product/MCP boundary checks match the implemented surface.

---
*Phase: 09-product-factual-bundles-and-cli-read-model-consolidation*
*Completed: 2026-05-26*
