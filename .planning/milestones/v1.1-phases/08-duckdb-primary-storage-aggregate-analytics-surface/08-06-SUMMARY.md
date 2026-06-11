---
phase: 08-duckdb-primary-storage-aggregate-analytics-surface
plan: 08-06
subsystem: analytics
tags: [duckdb, aggregates, metric-registry, service-envelope, tdd]
requires:
  - phase: 08-duckdb-primary-storage-aggregate-analytics-surface/08-03
    provides: DuckDBRepository primary runtime storage and read-model fact APIs
  - phase: 08-duckdb-primary-storage-aggregate-analytics-surface/08-05
    provides: registry-owned aggregate modes, bundles, denominators, buckets, and rolling windows
provides:
  - DuckDB aggregate-ready views over prepared activity, daily, model, and rolling facts
  - whitelisted aggregate query builders for bucketed and rolling registry metrics
  - product-level aggregate service returning ServiceEnvelope rows with freshness and provenance metadata
affects: [phase-08-07, phase-08-08, get-training-aggregates, compare-periods, mcp-surface]
tech-stack:
  added: []
  patterns:
    - registry-driven aggregate query templates
    - aggregate service validation before query execution
    - D-42 row metadata carried in every aggregate payload row
key-files:
  created:
    - src/mcp_strava/adapters/duckdb/aggregate_queries.py
    - src/mcp_strava/application/aggregate_services.py
    - tests/test_training_aggregates.py
  modified:
    - src/mcp_strava/adapters/duckdb/schema.py
    - tests/test_read_model_queries.py
key-decisions:
  - "Aggregate queries use DuckDB views and whitelisted registry metadata, not caller-supplied storage names or SQL."
  - "All-time buckets keep caller bounds when supplied and otherwise default start to the earliest local activity before the exclusive end."
  - "Aggregate service validation happens before opening or executing query work for invalid product parameters."
patterns-established:
  - "Aggregate rows include bucket bounds, unit, calculation, aggregation mode, denominator, value/distribution/quantiles, samples, completeness, missing reasons, metric-version status, materialized timestamp, and freshness fields."
  - "Missing weighted denominators make rows unavailable or partial instead of falling back to naive averages."
  - "Rolling aggregates use as_of_day plus the registry window allowlist: 7, 14, 28, 42, 90."
requirements-completed: [P8-SC-03, P8-D-ALL]
duration: 39min
completed: 2026-05-25
---

# Phase 08 Plan 06: DuckDB Aggregate Query Service Summary

**DuckDB bucket and rolling aggregate service over prepared metric facts with registry-owned math, validated product parameters, and factual D-42 metadata**

## Performance

- **Duration:** 39 min
- **Started:** 2026-05-25T20:25:00Z
- **Completed:** 2026-05-25T21:04:10Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Added RED tests for day/week/month/year/all_time buckets, Monday week starts, half-open ranges, bounded all_time behavior, exact rolling windows, aggregate modes, bundles, sport filters, empty buckets, denominator handling, mixed metric versions, and forbidden product parameters.
- Added DuckDB aggregate views over prepared fact tables: activity aggregate facts, daily aggregate facts, training model state facts, rolling aggregate facts, and metric version status.
- Added `aggregate_queries.py` with validated `AggregateRequest`, whitelisted registry-driven query templates, all_time and rolling range handling, and D-42 aggregate row metadata.
- Added `aggregate_services.py` with `AggregateServiceRequest` and `get_training_aggregates_service(...)`, returning `ServiceEnvelope` payloads with row-level mirror freshness and read-model freshness.
- Extended query-shape guards so aggregate request paths do not scan prepared raw stream rows and do not introduce physical period aggregate tables.

## Task Commits

1. **Task 1: Add failing training aggregate behavior tests** - `9197b9b` (`test`)
2. **Task 2: Implement aggregate-ready views and query builders** - `9aae375` (`feat`)
3. **Task 3 RED: Add failing aggregate service tests** - `9937349` (`test`)
4. **Task 3 GREEN: Implement product-level aggregate application service** - `59cdece` (`feat`)

## Verification

- `uv run pytest -q tests/test_training_aggregates.py tests/test_read_model_queries.py` - RED failed as expected before implementation with missing `mcp_strava.adapters.duckdb.aggregate_queries`.
- `uv run pytest -q tests/test_training_aggregates.py tests/test_read_model_queries.py` - passed after query layer implementation, 19 tests.
- `uv run pytest -q tests/test_training_aggregates.py tests/test_metric_services.py` - RED failed as expected before service implementation with missing `mcp_strava.application.aggregate_services`.
- `uv run pytest -q tests/test_training_aggregates.py tests/test_metric_services.py` - passed after service implementation, 24 tests.
- `uv run pytest -q tests/test_training_aggregates.py tests/test_read_model_queries.py tests/test_metric_services.py` - passed, 31 tests.
- `uv run pytest -q` - passed, 314 tests and 1 skipped.

## Files Created/Modified

- `src/mcp_strava/adapters/duckdb/aggregate_queries.py` - Whitelisted aggregate request, query, and row contracts plus DuckDB-backed bucket/rolling aggregate builders.
- `src/mcp_strava/application/aggregate_services.py` - Product-level aggregate service that validates parameters and returns factual ServiceEnvelope payloads.
- `tests/test_training_aggregates.py` - Aggregate behavior and service RED/GREEN coverage.
- `src/mcp_strava/adapters/duckdb/schema.py` - Aggregate-ready DuckDB views over prepared fact tables.
- `tests/test_read_model_queries.py` - Query-shape guard for DuckDB aggregate views, no raw stream scans, and no physical period aggregate tables.

## Decisions Made

- Use logical DuckDB views plus query builders for aggregate math; no permanent period aggregate tables were added.
- Keep aggregate query input as product-level request fields only: bucket, date bounds, metric ids or bundle, scope, sport filter, include-empty flag, as_of_day, and window_days.
- Leave gear/equipment out of aggregate filters and request dataclasses.
- Preserve registry-owned semantics for sums, calendar averages, weighted averages, ratio-of-sums, quantiles, last-state, distribution, and kudos count.

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

- DuckDB reports `weighted_avg` as a macro function, so it cannot use `FILTER`. The implementation uses conditional arguments to keep the same weighted average semantics while preserving the `weighted_avg` primitive.
- `gsd-sdk query requirements.mark-complete P8-SC-03 P8-D-ALL` may report these planning IDs as absent from `.planning/REQUIREMENTS.md`, matching prior Phase 08 behavior. No requirements file mutation is required when IDs are not present.

## Known Stubs

None. Stub scan findings were typed optional defaults, local empty accumulators, and empty fixture containers only; no runtime placeholder data source was introduced.

## Authentication Gates

None.

## Threat Flags

None. The new application parameter boundary and query-template boundary are the surfaces described in the plan threat model and are covered by validation tests.

## TDD Gate Compliance

- RED gate: `9197b9b` added aggregate behavior/query-shape tests before implementation.
- GREEN gate: `9aae375` implemented aggregate views and query builders until targeted tests passed.
- RED gate: `9937349` added aggregate service envelope/validation tests before service implementation.
- GREEN gate: `59cdece` implemented the aggregate service until targeted tests passed.
- Refactor gate: not needed; no behavior-neutral cleanup commit was made.

## User Setup Required

None.

## Next Phase Readiness

Ready for Plan 08-07. The aggregate service exists below the MCP boundary; the next plan can expose `get_training_aggregates` through the MCP allowlist without adding sync/admin/debug/raw controls.

## Self-Check: PASSED

- Verified created files exist: `src/mcp_strava/adapters/duckdb/aggregate_queries.py`, `src/mcp_strava/application/aggregate_services.py`, `tests/test_training_aggregates.py`.
- Verified modified files exist: `src/mcp_strava/adapters/duckdb/schema.py`, `tests/test_read_model_queries.py`.
- Verified task commits exist in git history: `9197b9b`, `9aae375`, `9937349`, `59cdece`.
- Verified plan-level targeted and full pytest commands passed after final task commit.

---
*Phase: 08-duckdb-primary-storage-aggregate-analytics-surface*
*Completed: 2026-05-25*
