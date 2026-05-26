---
phase: 09-product-factual-bundles-and-cli-read-model-consolidation
plan: 09-02
subsystem: analytics
tags: [product-facts, aggregate-services, read-model, bundle-completeness, tdd]
requires:
  - phase: 09-01
    provides: Registry-backed aggregate bundles, status fact queries, historical context facts, kudos, and detail-only gear boundaries
provides:
  - Shared daily_brief, weekly_digest, and historical_facts product fact services
  - Explicit bundle_completeness contract for bundle and section payloads
  - Aggregate service bundle payloads for registered product scenario bundles while preserving rows
  - Status fact evidence normalization and mirrored gear fact handling
affects: [phase-09-03, phase-09-04, cli-product-read-model, mcp-aggregate-bundles]
tech-stack:
  added: []
  patterns:
    - application-layer product fact bundle services
    - explicit bundle completeness accounting
    - aggregate row contract plus optional product bundle shaping
key-files:
  created:
    - src/mcp_strava/application/product_facts.py
    - tests/test_product_fact_bundles.py
    - .planning/phases/09-product-factual-bundles-and-cli-read-model-consolidation/09-02-SUMMARY.md
  modified:
    - src/mcp_strava/application/aggregate_services.py
    - tests/test_training_aggregates.py
key-decisions:
  - "Product fact bundles are assembled in application services from existing aggregate, metric, status, and workout-detail services."
  - "Aggregate service responses preserve the rows contract and add bundle payloads only for daily_brief, weekly_digest, and historical_facts scenario bundle requests."
  - "Supported gear facts are detail-only mirrored facts; missing mirrored gear is explicit as gear_data_not_mirrored."
patterns-established:
  - "Every bundle and bundle section reports requested, included, unavailable, skipped, and scope-incompatible metrics."
  - "Status facts remain machine-readable threshold facts, with product-facing evidence aliases added outside the registry query layer."
requirements-completed: [APP-01, APP-02, APP-03, APP-04, MCP-01, MCP-03, READMODEL-04, TEST-04, TEST-06]
duration: 12 min
completed: 2026-05-26
---

# Phase 09 Plan 09-02: Product Factual Bundle Services Summary

**Daily, weekly, historical, status, kudos, and mirrored gear fact bundles with explicit completeness contracts over prepared read-model data**

## Performance

- **Duration:** 12 min
- **Started:** 2026-05-26T13:27:01Z
- **Completed:** 2026-05-26T13:39:17Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added RED tests for daily, weekly, historical, status, completeness, kudos, mirrored gear, and aggregate scenario bundle behavior.
- Implemented `product_facts.py` with shared application services returning `ServiceEnvelope` payloads for `daily_brief`, `weekly_digest`, and `historical_facts`.
- Added aggregate service shaping so registered product scenario bundle calls keep `rows` and also expose a structured `bundle` payload with per-section completeness.
- Kept product bundles factual and local: no new MCP tools, no sync/admin/debug/raw surface, and no Strava live calls.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add failing product fact bundle service tests** - `0e445bd` (test)
2. **Task 2: Implement factual bundle services and aggregate response shaping** - `dad7e38` (feat)

**Plan metadata:** `cb72b72` (`docs`)

## Verification

- `uv run pytest -q tests/test_product_fact_bundles.py tests/test_training_aggregates.py` - RED failed as expected before implementation: missing `product_facts` module and missing aggregate `bundle` payload.
- `uv run pytest -q tests/test_product_fact_bundles.py tests/test_training_aggregates.py tests/test_metric_services.py` - passed, 35 tests.
- `uv run pytest -q` - passed, 342 tests and 1 skipped.
- Boundary scan found no new MCP tool, sync/admin/debug/raw endpoint, Strava network call, or aggregate gear filter. Matches were existing MCP prompt text and the new application-layer product fact module.

## Files Created/Modified

- `src/mcp_strava/application/product_facts.py` - Shared product fact bundle services, bundle completeness helpers, status evidence normalization, and mirrored gear section support.
- `src/mcp_strava/application/aggregate_services.py` - Adds optional product bundle shaping for registered scenario bundle requests while preserving existing row data.
- `tests/test_product_fact_bundles.py` - Covers daily, weekly, historical, status, completeness, kudos, and supported gear bundle behavior.
- `tests/test_training_aggregates.py` - Covers aggregate service bundle shaping and row-contract preservation.

## Decisions Made

- Product fact bundle services are shared application services, not MCP tool additions.
- Aggregate responses add `data.bundle` only for `daily_brief`, `weekly_digest`, and `historical_facts`; other aggregate bundles stay rows-only.
- Gear facts are emitted only from mirrored summary/detail fields, and missing mirror gear data is represented as `gear_data_not_mirrored`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed daily by-sport aggregate scope handling**
- **Found during:** Task 2 (GREEN verification)
- **Issue:** The first daily by-sport aggregate request used strict `per_sport` scope with `trimp`, which is a global-only aggregate metric.
- **Fix:** Switched that service request to the existing mixed-scope `both` aggregate path so global and per-sport facts are represented without validation failure.
- **Files modified:** `src/mcp_strava/application/product_facts.py`
- **Verification:** `uv run pytest -q tests/test_product_fact_bundles.py tests/test_training_aggregates.py tests/test_metric_services.py`
- **Committed in:** `dad7e38`

**2. [Rule 2 - Missing Critical Functionality] Added bounded mirrored-gear lookup for product bundles**
- **Found during:** Task 2 (GREEN verification)
- **Issue:** The supported gear section initially reused the displayed 14-day recent workout list, which could miss mirrored gear facts just outside that display window.
- **Fix:** Added a bounded 28-day local workout-detail lookup for gear facts, still using mirrored fields only and no Strava calls.
- **Files modified:** `src/mcp_strava/application/product_facts.py`
- **Verification:** `uv run pytest -q tests/test_product_fact_bundles.py tests/test_training_aggregates.py tests/test_metric_services.py`; `uv run pytest -q`
- **Committed in:** `dad7e38`

---

**Total deviations:** 2 auto-fixed (1 Rule 1 bug, 1 Rule 2 missing critical functionality)
**Impact on plan:** Both fixes preserve the planned product/read-model boundary and avoid new MCP/admin/sync surface.

## Issues Encountered

- GREEN implementation required two iterations for aggregate scope compatibility and mirrored gear lookup breadth; both were resolved before the Task 2 commit.
- `gsd-sdk query state.update-progress` reported `Progress field not found in STATE.md`; `state.advance-plan`, `state.record-metric`, `state.add-decision`, `state.record-session`, and `roadmap.update-plan-progress` completed and updated the tracked state/roadmap fields.

## Known Stubs

None. Stub-pattern scan found type hints, helper initializers, and test fixture empty collections only; no runtime placeholder data source was introduced.

## Authentication Gates

None.

## Threat Flags

None. The new product caller, bundle formatter, read-model status, kudos, and gear paths are the surfaces covered by the plan threat model; no extra network, auth, file, admin, or MCP tool surface was introduced.

## TDD Gate Compliance

- RED gate: `0e445bd` added failing product fact bundle and aggregate bundle shaping tests.
- GREEN gate: `dad7e38` implemented product fact services and aggregate response shaping until targeted and full tests passed.
- Refactor gate: no behavior-neutral refactor commit was needed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for Plan 09-03. CLI consolidation can now call shared product factual bundle services and rely on the same completeness/status contract used by aggregate-backed MCP calls.

## Self-Check: PASSED

- Verified created files exist on disk: `src/mcp_strava/application/product_facts.py`, `tests/test_product_fact_bundles.py`, and this summary.
- Verified task commits `0e445bd`, `dad7e38`, and `cb72b72` exist in git history.
- Verified targeted and full pytest commands passed.

---
*Phase: 09-product-factual-bundles-and-cli-read-model-consolidation*
*Completed: 2026-05-26*
