---
phase: 09-product-factual-bundles-and-cli-read-model-consolidation
plan: 09-01
subsystem: analytics
tags: [duckdb, metric-registry, factual-bundles, status-facts, tdd]
requires:
  - phase: 08-duckdb-primary-storage-aggregate-analytics-surface
    provides: DuckDB aggregate query/service layer, scenario bundles, and aggregate-backed compare_periods
provides:
  - Bundle-safe daily_brief, weekly_digest, and historical_facts aggregate queries
  - Registry-backed status fact definitions and DuckDB evidence queries
  - Historical activity/rest streak and last-hike context facts from DuckDB views
  - Factual kudos and gear context boundaries without aggregate gear filters
affects: [phase-09-02, phase-09-03, phase-09-04, aggregate-queries, metric-registry, workout-detail]
tech-stack:
  added: []
  patterns:
    - registry-backed status fact definitions
    - DuckDB view-derived historical context facts
    - detail-only gear facts outside aggregate filters and bundles
key-files:
  created:
    - .planning/phases/09-product-factual-bundles-and-cli-read-model-consolidation/09-01-SUMMARY.md
  modified:
    - src/mcp_strava/types.py
    - src/mcp_strava/application/metric_registry.py
    - src/mcp_strava/adapters/duckdb/schema.py
    - src/mcp_strava/adapters/duckdb/aggregate_queries.py
    - src/mcp_strava/application/metric_services.py
    - src/mcp_strava/adapters/sqlite/repository.py
    - src/mcp_strava/adapters/duckdb/repository.py
    - tests/test_metric_registry.py
    - tests/test_training_aggregates.py
    - docs/metrics.md
key-decisions:
  - "Status facts are registry-backed factual threshold/category records with code, threshold, window, evidence, completeness, calculation, and materialized source metadata."
  - "Historical streak and last-hike facts are derived from DuckDB read-model/activity facts through `v_historical_context_facts`, not absent `training_model_daily` columns."
  - "Gear facts are detail-only product context; aggregate gear/equipment filters, scopes, grouping, and bundles remain absent."
patterns-established:
  - "Scenario bundles can be called with mixed global/per-sport semantics by splitting supported metric scopes internally."
  - "Status fact evidence queries return unavailable only with explicit missing reasons."
requirements-completed: [APP-01, APP-02, MCP-01, MCP-03, READMODEL-01, READMODEL-04, TEST-03, TEST-06]
duration: 14 min
completed: 2026-05-26
---

# Phase 09 Plan 09-01: Product Factual Bundle Registry Summary

**Registry-backed daily, weekly, historical, status, kudos, and gear facts over DuckDB read-model aggregates**

## Performance

- **Duration:** 14 min
- **Started:** 2026-05-26T13:08:14Z
- **Completed:** 2026-05-26T13:22:33Z
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments

- Added RED tests for mixed-scope bundles, historical context facts, status fact contracts/evidence, kudos aggregation, and gear filter rejection.
- Implemented `StatusFactDefinition`/`StatusFact`, `STATUS_FACT_REGISTRY`, `query_status_facts`, and DuckDB evidence queries for D-08/D-09 status facts.
- Added `v_historical_context_facts` so `activity_streak_days`, `rest_streak_days`, and `last_hike_days_ago` are derived facts rather than missing training-model columns.
- Registered gear facts as workout-detail context and kept aggregate request dataclasses rejecting `gear_id` and gear/equipment scopes.
- Updated registry docs for bundles, status facts, kudos behavior, and gear context.

## Task Commits

1. **Task 1: Add failing bundle and registry contract tests** - `9b64841` (`test`)
2. **Task 2: Implement registry-backed bundle-safe aggregate facts** - `02baf22` (`feat`)
3. **Task 3: Update registry-derived metrics documentation** - `13c46ec` (`docs`)
4. **Auto-fix: Emit registered gear detail facts** - `88f9fe3` (`fix`)

## Verification

- `uv run pytest -q tests/test_metric_registry.py tests/test_training_aggregates.py` - passed, 42 tests.
- `uv run pytest -q tests/test_metric_registry.py tests/test_training_aggregates.py tests/test_metric_services.py::test_tool_metric_payloads_match_registry_exposure` - passed, 43 tests.
- `uv run pytest -q` - passed, 336 tests and 1 skipped.
- Boundary scan found no new MCP tools, Strava network calls, sync/admin/debug exposure, raw SQL request parameters, or aggregate gear filters. `gear_id` appears only as workout-detail output and as an aggregate rejection test.

## Files Created/Modified

- `src/mcp_strava/types.py` - Added typed status fact contracts.
- `src/mcp_strava/application/metric_registry.py` - Added status registry, gear metrics, historical projection allowlist entries, and catalog output.
- `src/mcp_strava/adapters/duckdb/schema.py` - Added `v_historical_context_facts`.
- `src/mcp_strava/adapters/duckdb/aggregate_queries.py` - Added status fact queries and routed historical facts through the derived view.
- `src/mcp_strava/application/metric_services.py` - Emits registered gear facts only for workout detail payloads.
- `src/mcp_strava/adapters/sqlite/repository.py` - Includes `detail_json` in activity fact rows for detail context.
- `src/mcp_strava/adapters/duckdb/repository.py` - Includes `detail_json` in activity fact rows for detail context.
- `tests/test_metric_registry.py` - Covers status and gear registry contracts.
- `tests/test_training_aggregates.py` - Covers mixed-scope bundles, historical facts, and status evidence fixtures.
- `docs/metrics.md` - Documents bundles, status facts, kudos, and gear boundaries.

## Decisions Made

- Status fact thresholds and evidence keys live in `STATUS_FACT_REGISTRY`, not private query literals.
- Historical context facts are view-derived from local read-model/activity facts and remain registry allowlisted.
- Gear facts are exposed as detail context only; aggregate requests still reject gear/equipment filters.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Emitted registered gear facts from workout detail**
- **Found during:** Final full-suite verification after Task 3
- **Issue:** Gear metrics were correctly registered for `get_workout_detail`, but the workout detail service did not emit those registered keys, causing registry exposure parity to fail.
- **Fix:** Added detail-only gear payload fields and included `detail_json` in SQLite/DuckDB activity fact repository rows.
- **Files modified:** `src/mcp_strava/application/metric_services.py`, `src/mcp_strava/adapters/sqlite/repository.py`, `src/mcp_strava/adapters/duckdb/repository.py`
- **Verification:** `uv run pytest -q tests/test_metric_services.py::test_tool_metric_payloads_match_registry_exposure`; `uv run pytest -q`
- **Committed in:** `88f9fe3`

---

**Total deviations:** 1 auto-fixed (Rule 2)
**Impact on plan:** Required to keep registry metadata truthful. No new MCP/admin/sync/raw surface was added.

## Issues Encountered

- The docs drift guard required new gear metric rows in `docs/metrics.md` before the Task 2 GREEN gate could pass. The broader status/bundle docs were completed in Task 3.

## Known Stubs

None. Stub-pattern scan found only test fixture empty lists, SQL placeholder variable names, and existing optional empty payload defaults; no runtime placeholder data source was introduced.

## Authentication Gates

None.

## Threat Flags

None. The new query/status surfaces are the registry-to-DuckDB and read-model-to-product boundaries described in the plan threat model, and remain parameterized/allowlisted.

## TDD Gate Compliance

- RED gate: `9b64841` added failing bundle, status, and gear contract tests.
- GREEN gate: `02baf22` implemented registry-backed bundle and status support until targeted tests passed.
- Refactor gate: no behavior-neutral refactor commit was needed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for Plan 09-02. Product bundle services can now consume registry-backed aggregate rows, status facts, historical context, kudos counts, and detail-only gear facts without adding MCP tools or admin controls.

## Self-Check: PASSED

- Verified modified files exist on disk.
- Verified task commits `9b64841`, `02baf22`, `13c46ec`, and `88f9fe3` exist in git history.
- Verified targeted and full pytest commands passed.

---
*Phase: 09-product-factual-bundles-and-cli-read-model-consolidation*
*Completed: 2026-05-26*
