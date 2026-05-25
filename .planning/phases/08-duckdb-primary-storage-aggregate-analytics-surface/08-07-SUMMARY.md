---
phase: 08-duckdb-primary-storage-aggregate-analytics-surface
plan: 08-07
subsystem: mcp
tags: [mcp, duckdb, aggregates, metric-registry, tdd]

requires:
  - phase: 08-06
    provides: DuckDB aggregate query/service layer and scenario metric bundles
provides:
  - get_training_aggregates MCP product tool
  - compare_periods formatting over bounded all_time aggregate requests
  - six-tool MCP allowlist and client smoke coverage
affects: [phase-08, mcp-surface, aggregate-analytics, period-comparison]

tech-stack:
  added: []
  patterns:
    - MCP handlers delegate product parameters to application services without SQL construction
    - Period comparison uses aggregate service envelopes instead of separate row scanning
    - Aggregate registry metadata drives MCP exposure for aggregate metrics

key-files:
  created:
    - .planning/phases/08-duckdb-primary-storage-aggregate-analytics-surface/08-07-SUMMARY.md
  modified:
    - src/mcp_strava/interfaces/mcp_http.py
    - src/mcp_strava/devtools/mcp_client/client.py
    - src/mcp_strava/application/metric_services.py
    - src/mcp_strava/application/metric_registry.py
    - src/mcp_strava/adapters/duckdb/aggregate_queries.py
    - tests/test_mcp_surface.py
    - tests/test_mcp_test_client.py
    - tests/test_metric_registry.py
    - tests/test_metric_services.py

key-decisions:
  - "Expose get_training_aggregates as the sixth and only new product MCP tool."
  - "Format compare_periods from two bounded period_comparison aggregate requests with bucket=all_time."
  - "Use aggregate scope=both internally for comparison bundles so global and per-sport rows share aggregate semantics."

patterns-established:
  - "MCP aggregate tool schemas stay product-level: dates, bucket, metric ids/bundles, scope, sports, and rolling window controls only."
  - "Comparison response metadata is derived from aggregate rows: sample size, activity count, missing reasons, coverage, and metric-version status."

requirements-completed: [P8-SC-04, P8-SC-03, P8-D-ALL]

duration: 12min
completed: 2026-05-25
---

# Phase 08 Plan 08-07: Aggregate MCP Surface Summary

**Six-tool MCP surface with get_training_aggregates and aggregate-backed period comparison over bounded all-time buckets**

## Performance

- **Duration:** 12 min
- **Started:** 2026-05-25T21:22:06Z
- **Completed:** 2026-05-25T21:33:37Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- Added `get_training_aggregates` as the only new MCP product tool, preserving the exact six-tool allowlist and read-only annotations.
- Wired MCP/client smoke paths to exercise the aggregate tool through a weekly digest bundle request.
- Rewrote `compare_periods_service` to call `get_training_aggregates_service` twice with `bucket="all_time"` and explicit exclusive period bounds.
- Aligned compare-period metric exposure with the `period_comparison` aggregate bundle and preserved factual metadata fields in the comparison response.

## Task Commits

1. **Task 1: Add failing MCP aggregate surface and compare delegation tests** - `cd20613` (test)
2. **Task 2: Register get_training_aggregates in MCP and client smoke paths** - `1c82927` (feat)
3. **Task 3 RED: Require aggregate-backed period comparison** - `cc47fbb` (test)
4. **Task 3 GREEN: Rewrite compare_periods over aggregate service** - `ed41b9a` (feat)

## Files Created/Modified

- `src/mcp_strava/interfaces/mcp_http.py` - Registers the sixth MCP tool and delegates to `get_training_aggregates_service`.
- `src/mcp_strava/devtools/mcp_client/client.py` - Adds aggregate tool expectations, latency order, default warm calls, and live smoke calls.
- `src/mcp_strava/application/metric_services.py` - Formats `compare_periods` from aggregate service rows instead of separate row-scanning comparison maps.
- `src/mcp_strava/application/metric_registry.py` - Adds aggregate MCP exposure and constrains compare-period metrics to the `period_comparison` bundle.
- `src/mcp_strava/adapters/duckdb/aggregate_queries.py` - Adds internal aggregate `scope="both"` expansion and HR-zone distribution aggregation.
- `tests/test_mcp_surface.py` - Covers exact six-tool MCP surface, forbidden parameters, annotations, and structured output.
- `tests/test_mcp_test_client.py` - Covers aggregate default warm calls and smoke call wiring.
- `tests/test_metric_registry.py` - Verifies compare-period registry exposure resolves through aggregate metadata.
- `tests/test_metric_services.py` - Verifies bounded aggregate delegation and compare response metadata.

## Decisions Made

- `get_training_aggregates` is the sixth MCP tool and the only new product surface in this plan.
- `compare_periods` now uses the `period_comparison` aggregate bundle through two bounded `all_time` aggregate service calls.
- Aggregate comparison uses internal `scope="both"` expansion to get global and per-sport rows without adding separate public MCP parameters.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Added aggregate scope expansion and HR-zone distribution support**
- **Found during:** Task 3 (Rewrite compare_periods over aggregate service)
- **Issue:** The `period_comparison` aggregate bundle includes metrics that need both global/per-sport rows and HR-zone distribution rows, but the aggregate query layer only accepted one scope at a time and did not materialize HR-zone distribution buckets.
- **Fix:** Added internal `scope="both"` validation/expansion and a DuckDB aggregate query for `time_in_hr_zones_min` zone-minute distributions.
- **Files modified:** `src/mcp_strava/adapters/duckdb/aggregate_queries.py`
- **Verification:** `uv run pytest -q tests/test_metric_services.py tests/test_metric_registry.py tests/test_training_aggregates.py tests/test_security_guards.py`
- **Committed in:** `ed41b9a`

---

**Total deviations:** 1 auto-fixed (Rule 2)
**Impact on plan:** Required for correctness of the planned aggregate-backed comparison path; no additional MCP/admin surface was introduced.

## Issues Encountered

- Test fixture imports needed to follow the new aggregate envelope shape (`CompletenessMetadata`, `ServiceRationale`). Fixed before the Task 3 GREEN commit.
- A local `read_model` variable was missing after the compare formatter rewrite. Fixed before the Task 3 GREEN commit.
- `gsd-sdk query requirements.mark-complete P8-SC-04 P8-SC-03 P8-D-ALL` returned `not_found` for all three IDs because the current `.planning/REQUIREMENTS.md` does not contain those Phase 8 decision IDs as requirement checkboxes/table rows.

## TDD Gate Compliance

- RED gate: `cd20613` added failing MCP aggregate surface/client/compare-delegation tests.
- GREEN gate: `1c82927` implemented the aggregate MCP tool and client smoke wiring.
- RED gate: `cc47fbb` added failing aggregate-backed period comparison and registry tests.
- GREEN gate: `ed41b9a` rewrote compare-periods over aggregate service rows.

## Verification

- `uv run pytest -q tests/test_mcp_surface.py tests/test_metric_services.py tests/test_mcp_test_client.py tests/test_training_aggregates.py tests/test_security_guards.py` - 64 passed in 7.01s.
- `uv run pytest -q tests/test_metric_services.py tests/test_metric_registry.py tests/test_training_aggregates.py tests/test_security_guards.py` - 69 passed in 6.14s.
- `uv run pytest -q` - 320 passed, 1 skipped in 15.08s.

## Known Stubs

None. Stub-pattern scan found only the existing registry test that rejects placeholder metric ids, not runtime placeholders or unwired UI/data stubs.

## Auth Gates

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 08-08 can validate latency and self-UAT against a six-tool MCP surface. The `all_time` compare-period key-link is now green because period comparison delegates through bounded aggregate requests.

## Self-Check: PASSED

- Verified all created/modified files listed in this summary exist.
- Verified task commits `cd20613`, `1c82927`, `cc47fbb`, and `ed41b9a` exist in git history.

---
*Phase: 08-duckdb-primary-storage-aggregate-analytics-surface*
*Completed: 2026-05-25*
