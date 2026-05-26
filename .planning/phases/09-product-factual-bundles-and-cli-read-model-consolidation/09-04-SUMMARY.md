---
phase: 09-product-factual-bundles-and-cli-read-model-consolidation
plan: 09-04
subsystem: testing
tags: [mcp, product-bundles, smoke, security-guards, docs]
requires:
  - phase: 09-02
    provides: Shared product factual bundle services with explicit completeness contracts
  - phase: 09-03
    provides: CLI product reads consolidated on product fact and metric services
provides:
  - Direct MCP bundle smoke coverage for daily_brief, weekly_digest, and historical_facts
  - Final MCP six-tool allowlist, payload, cache identity, and no-advice/no-admin assertions
  - Final product boundary AST guards for product bundle services and CLI read paths
  - Phase 9 deployment verification sequence and phase9-bundle-smoke recipe
affects: [phase-09-closeout, mcp-direct-smoke, product-boundary-guards, deployment-runbook]
tech-stack:
  added: []
  patterns:
    - direct MCP server smoke through the existing six-tool surface
    - AST import/call guards for product/admin boundary preservation
    - fixture-backed non-Docker p95 fallback documentation
key-files:
  created:
    - .planning/phases/09-product-factual-bundles-and-cli-read-model-consolidation/09-04-SUMMARY.md
  modified:
    - Justfile
    - src/mcp_strava/devtools/mcp_client/client.py
    - tests/test_mcp_surface.py
    - tests/test_mcp_test_client.py
    - tests/test_security_guards.py
    - docs/deployment.md
key-decisions:
  - "Direct MCP bundle smoke exercises daily_brief, weekly_digest, and historical_facts through get_training_aggregates rather than adding any MCP tool."
  - "Scenario bundle smoke uses bounded start/end dates only; explicit as_of_day/window_days cache identity remains unit-tested because mixed bundles contain heterogeneous rolling-window metrics."
  - "Phase 9 verification excludes gateway smoke and keeps sync/admin/raw/debug/recompute commands below the product MCP boundary."
patterns-established:
  - "MCP smoke payload assertions require rows, bundle sections, bundle_completeness, read-model metadata, freshness/completeness metadata, and caller-visible reason_code values."
  - "Product bundle and CLI boundary guards inspect AST imports and calls rather than fragile grep-only checks."
requirements-completed: [MCP-01, MCP-02, MCP-03, PERF-01, TEST-03, TEST-04, TEST-06]
duration: 15 min
completed: 2026-05-26
---

# Phase 09 Plan 09-04: MCP Bundle Smoke and Boundary Guard Summary

**Direct MCP product bundle smoke, six-tool boundary guards, and Phase 9 verification docs for factual read-model-backed product surfaces**

## Performance

- **Duration:** 15 min
- **Started:** 2026-05-26T14:36:21Z
- **Completed:** 2026-05-26T14:50:53Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added TDD RED tests for final MCP bundle payload contracts, daily-brief composition, cache identity, and direct smoke coverage for all three product bundles.
- Extended the MCP test client so full direct live smoke calls `daily_brief`, `weekly_digest`, and `historical_facts` through the existing `get_training_aggregates` tool.
- Added security guards proving product bundle services and CLI product commands do not call or import admin, raw, sync, Strava adapter, token refresh, legacy report/workout, or request-time recompute paths.
- Added `just phase9-bundle-smoke` and documented the Phase 9 targeted tests, direct server smoke, Docker p95 gate, and non-Docker fixture fallback.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Add final MCP bundle smoke and allowlist tests** - `9cf028d` (`test`)
2. **Task 1 GREEN: Cover product bundles in MCP direct smoke** - `54a34d0` (`feat`)
3. **Auto-fix: Keep bundle smoke requests validator-compatible** - `2c2285b` (`fix`)
4. **Task 2: Add final boundary guards and verification docs** - `510bbd2` (`test`)

**Plan metadata:** recorded in the final docs commit for this summary.

## Verification

- `uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py` - RED failed as expected before implementation with 17 passed and 2 failures: default warm calls only covered `weekly_digest`, and `run_live_smoke()` did not accept a deterministic `today`.
- `uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py` - passed, 19 tests.
- `uv run pytest -q tests/test_security_guards.py tests/test_mcp_surface.py tests/test_mcp_test_client.py` - passed, 49 tests.
- `just phase9-bundle-smoke` - passed. Direct live smoke called `get_training_aggregates:daily_brief`, `get_training_aggregates:weekly_digest`, and `get_training_aggregates:historical_facts` against `http://127.0.0.1:8080/mcp`.
- `just test` - passed. Docker build/recreate succeeded and smoke-basic verified the exact six product MCP tools directly against the local server.

## Files Created/Modified

- `src/mcp_strava/devtools/mcp_client/client.py` - Adds product bundle smoke call construction and reports aggregate bundle coverage from full direct live smoke.
- `tests/test_mcp_surface.py` - Asserts MCP bundle payload rows, sections, completeness reason codes, freshness/completeness/read-model metadata, no advice/admin/raw leakage, daily-brief composition, and cache identity.
- `tests/test_mcp_test_client.py` - Covers scripted/default/live smoke calls for daily, weekly, and historical bundles through `get_training_aggregates`.
- `tests/test_security_guards.py` - Adds product bundle and CLI product AST guards against admin/raw/sync/token/legacy/recompute paths and retired legacy modules.
- `Justfile` - Adds `phase9-bundle-smoke` for targeted tests plus direct full MCP smoke.
- `docs/deployment.md` - Documents Phase 9 targeted, CLI/security, direct smoke, Docker p95, and non-Docker fixture fallback verification.

## Decisions Made

- Direct bundle smoke uses the current six-tool MCP surface and does not add tool ids, prompts, gateway calls, or admin controls.
- Mixed scenario bundle smoke omits `as_of_day` and `window_days` because daily/weekly/historical bundles include metrics with different registered rolling windows; explicit cache identity for those fields is covered separately.
- Phase 9 verification is direct-server-first: gateway registration and gateway catalog mutation remain deployment operations, not product verification.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed invalid mixed-bundle as-of/window smoke arguments**
- **Found during:** Task 2 (`just phase9-bundle-smoke`)
- **Issue:** The first implementation passed a single `as_of_day`/`window_days` pair to mixed scenario bundles. Live MCP validation rejected this because bundle metrics such as `daily_avg_trimp_7d`, `volume_7d`, and historical facts have heterogeneous rolling-window requirements.
- **Fix:** Kept scripted bundle smoke bounded by start/end dates and bundle ids, while preserving a separate cache identity test that proves explicit `as_of_day` and `window_days` are part of cache identity when supplied.
- **Files modified:** `src/mcp_strava/devtools/mcp_client/client.py`, `tests/test_mcp_test_client.py`
- **Verification:** `uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py`; `just phase9-bundle-smoke`; `just test`
- **Committed in:** `2c2285b`

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug)
**Impact on plan:** Preserves the intended direct MCP bundle smoke without weakening cache-key coverage or adding any MCP/admin/sync surface.

## Issues Encountered

- `just phase9-bundle-smoke` initially failed until the smoke request shape was corrected for mixed scenario bundles. No package, auth, or gateway blocker occurred.
- `gsd-sdk query state.update-progress` returned `Progress field not found in STATE.md`; `state.advance-plan`, `state.record-metric`, `state.add-decision`, `state.record-session`, `roadmap.update-plan-progress`, and `requirements.mark-complete` completed. The roadmap and state plan counts were updated.

## Known Stubs

None. Stub-pattern scan found type annotations, test fixture collections, and local timing variables only; no runtime placeholder data source or UI-facing stub was introduced.

## Authentication Gates

None.

## Threat Flags

None. The changes add tests, direct smoke tooling, and documentation only. No new network endpoint, auth path, file access pattern, schema boundary, or MCP tool surface was introduced beyond the plan threat model.

## TDD Gate Compliance

- RED gate: `9cf028d` added failing MCP bundle smoke, payload, composition, and cache identity tests.
- GREEN gate: `54a34d0` implemented direct smoke bundle coverage until targeted tests passed.
- Refactor gate: no behavior-neutral refactor commit was needed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 9 is complete. MCP and CLI product reads remain factual, read-model-backed, product-only, smoke-testable, and guarded against sync/admin/raw/debug/recompute leakage.

## Self-Check: PASSED

- Verified summary and all modified files exist on disk.
- Verified task commits `9cf028d`, `54a34d0`, `2c2285b`, and `510bbd2` exist in git history.
- Verified targeted tests, direct bundle smoke, and Docker smoke passed.

---
*Phase: 09-product-factual-bundles-and-cli-read-model-consolidation*
*Completed: 2026-05-26*
