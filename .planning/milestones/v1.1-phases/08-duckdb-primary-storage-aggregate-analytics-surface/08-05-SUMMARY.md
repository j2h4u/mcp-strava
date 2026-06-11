---
phase: 08-duckdb-primary-storage-aggregate-analytics-surface
plan: 08-05
subsystem: analytics
tags: [metric-registry, aggregates, duckdb, mcp, pytest]
requires:
  - phase: 08-duckdb-primary-storage-aggregate-analytics-surface
    plan: 08-01
    provides: DuckDB dependency baseline and Phase 8 runtime direction
provides:
  - MetricDefinition aggregate metadata fields
  - registry-owned aggregate modes, buckets, scopes, rolling windows, and bundles
  - denominator, weight, quantile, sample-size, and metric-version metadata for aggregate metrics
  - drift-tested aggregate metric documentation
affects: [aggregate-query-layer, get-training-aggregates, compare-periods, duckdb-queries]
tech-stack:
  added: []
  patterns: [registry-owned-aggregate-semantics, bundle-driven-metric-selection, factual-aggregate-docs]
key-files:
  created:
    - .planning/phases/08-duckdb-primary-storage-aggregate-analytics-surface/08-05-SUMMARY.md
  modified:
    - src/mcp_strava/types.py
    - src/mcp_strava/application/metric_registry.py
    - tests/test_metric_registry.py
    - docs/metrics.md
key-decisions:
  - "Aggregate semantics stay in `metric_registry.py` through typed metadata instead of alternate pseudo metric ids."
  - "Metric bundles are scenario-oriented registry data and do not change the existing five-tool MCP allowlist."
  - "Weighted heart-rate aggregate metadata requires explicit denominator and weight columns."
patterns-established:
  - "Aggregate metrics declare mode, source grain, denominator/weight columns, supported buckets/scopes, sample-size provenance, quantiles, bundles, and metric-version policy."
  - "Aggregate docs are drift-tested against registry constants and bundle membership."
requirements-completed: [P8-SC-03, P8-SC-04, P8-D-ALL]
duration: 10 min
completed: 2026-05-25
---

# Phase 8 Plan 5: Aggregate Metric Registry Summary

**Registry-owned aggregate semantics with typed denominators, bundles, quantiles, and drift-tested metric documentation**

## Performance

- **Duration:** 10 min
- **Started:** 2026-05-25T16:55:24Z
- **Completed:** 2026-05-25T17:04:54Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Added RED tests for aggregate modes, supported buckets/scopes, rolling windows, bundle resolution, weighted HR metadata, quantiles, kudos behavior, and pseudo metric-id rejection.
- Extended `MetricDefinition` and the metric registry with aggregate metadata needed by future DuckDB aggregate query builders.
- Defined registry bundles for `daily_brief`, `weekly_digest`, `monthly_digest`, `period_comparison`, `sport_efficiency`, and `historical_facts`.
- Documented aggregate modes, denominators, quantiles, scopes, bundle membership, Monday week buckets, and half-open date ranges in `docs/metrics.md`.

## Task Commits

1. **Task 1: Add failing aggregate registry contract tests** - `4c21883` (`test`)
2. **Task 2: Implement aggregate metadata in registry types and definitions** - `85bb4b4` (`feat`)
3. **Task 3: Document aggregate semantics from registry metadata** - `283757b` (`docs`)

_TDD gate:_ RED commit `4c21883` failed with the expected missing aggregate registry API import; GREEN commit `85bb4b4` made the targeted registry/service tests pass.

## Verification

- `uv run pytest -q tests/test_metric_registry.py` - passed, 19 tests.
- `uv run pytest -q tests/test_metric_registry.py tests/test_metric_services.py` - passed, 29 tests.
- `uv run pytest -q` - passed, 281 tests and 1 skipped.

## Files Created/Modified

- `src/mcp_strava/types.py` - added aggregate metadata fields to `MetricDefinition`.
- `src/mcp_strava/application/metric_registry.py` - added aggregate modes, buckets, scopes, rolling windows, bundle definitions, aggregate metadata application, and bundle lookup.
- `tests/test_metric_registry.py` - added semantic RED tests and docs drift checks for aggregate metadata.
- `docs/metrics.md` - documented the aggregate registry contract and bundle membership.
- `.planning/phases/08-duckdb-primary-storage-aggregate-analytics-surface/08-05-SUMMARY.md` - plan execution summary.

## Decisions Made

- Aggregate behavior is metadata on existing metric ids, preserving current metric ids and avoiding duplicate pseudo metrics for alternate math.
- `get_training_aggregates` bundle definitions are registry data only in this plan; the MCP HTTP allowlist remains unchanged until the later handler plan.
- Gear and equipment are absent from aggregate scopes, filters, and bundles.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `gsd-sdk query requirements.mark-complete P8-SC-03 P8-SC-04 P8-D-ALL` returned `not_found` for all three IDs because those Phase 8 planning IDs are not present in `.planning/REQUIREMENTS.md`. No requirements file changes were made.

## Known Stubs

None. Stub scan found only pre-existing explanatory text and placeholder-test guard terms, not runtime placeholders or unwired UI data.

## User Setup Required

None.

## Next Phase Readiness

Ready for the downstream DuckDB aggregate query layer and `get_training_aggregates` service/handler work. The registry now supplies aggregate modes, denominators, quantiles, supported scopes/buckets, bundles, and metric-version policy.

## TDD Gate Compliance

- RED gate commit present: `4c21883`
- GREEN gate commit present after RED: `85bb4b4`
- Refactor gate: not needed; no behavior-neutral cleanup commit was made.

## Self-Check: PASSED

- Verified key files exist on disk.
- Verified task commits `4c21883`, `85bb4b4`, and `283757b` exist in git history.
- Verified plan-level targeted and full pytest commands passed.

---
*Phase: 08-duckdb-primary-storage-aggregate-analytics-surface*
*Completed: 2026-05-25*
