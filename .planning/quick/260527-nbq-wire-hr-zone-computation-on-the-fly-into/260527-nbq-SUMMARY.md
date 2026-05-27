---
quick_id: 260527-nbq
phase: quick
plan: 260527-nbq
subsystem: metrics/materializer
tags: [hr-zones, trimp, duckdb, settings, refactor]
dependency_graph:
  requires: [hr_zones.py stage-1, settings.py stage-2]
  provides: [on-the-fly zone computation, provenance persistence, Config.Athlete removal]
  affects: [read_model_materializer, repository, metrics, aggregate_queries, db]
tech_stack:
  added: []
  patterns: [strategy pattern for HR zone model, explicit bounds threading, fail-fast on missing env]
key_files:
  created:
    - tests/conftest.py
  modified:
    - src/mcp_strava/adapters/duckdb/schema.py
    - src/mcp_strava/adapters/duckdb/repository.py
    - src/mcp_strava/adapters/duckdb/read_model_materializer.py
    - src/mcp_strava/adapters/duckdb/aggregate_queries.py
    - src/mcp_strava/application/metric_registry.py
    - src/mcp_strava/constants.py
    - src/mcp_strava/metrics.py
    - src/mcp_strava/db.py
    - tests/test_hr_zones.py
    - tests/test_load_status.py
    - docs/metrics.md
decisions:
  - "Thread explicit bounds through daily_load_points_between and effective_trimp_history rather than making them compute bounds internally — keeps the parameter boundary explicit at all call sites"
  - "Use global max-heartrate-to-date for session_bounds in _materialize_daily_facts (daily aggregation), while per-activity _activity_fact uses running max-to-date per activity day"
  - "When max_heartrate() is None in aggregate_queries z5 fallback, use 300 (ZONE_CAP_BPM) as unreachable threshold — returns 0 Z5 events, which is correct"
metrics:
  duration: ~25 minutes
  completed: "2026-05-27"
  tasks_completed: 4
  files_modified: 11
---

# Phase quick Plan 260527-nbq: Wire HR Zone Computation On-the-fly into TRIMP Materialization — Summary

## One-liner

Replaced all hardcoded Config.Athlete/Config.Zones.BOUNDS/Config.SQL constants with on-the-fly Karvonen HRR zone bounds computed from running max-HR-to-date and MCP_STRAVA_HR_REST, persisting provenance on every activity fact.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Schema provenance columns | fdeaf35 | schema.py, repository.py |
| 2 | build_trimp_sql helpers + constants cleanup | e84a5f1 | repository.py, constants.py, test_hr_zones.py |
| 3 | Wire bounds into materializer + running hr_max query | bf8732e | read_model_materializer.py, repository.py, db.py, test_load_status.py |
| 4 | Rewire remaining consumers + conftest + descriptions | 59db9fd | metrics.py, aggregate_queries.py, metric_registry.py, docs/metrics.md, conftest.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing functionality] Thread bounds through daily_load_points_between and effective_trimp_history**
- Found during: Task 3
- Issue: observed_trimp_history now requires explicit bounds, but daily_load_points_between and effective_trimp_history called it without bounds
- Fix: Added `bounds: list[int]` parameter to both methods; updated all call sites (materializer, test_load_status.py)
- Files modified: repository.py, read_model_materializer.py, tests/test_load_status.py

**2. [Rule 2 - Missing functionality] metric_registry column registry missing 5 new provenance columns**
- Found during: Task 4 (test run)
- Issue: test_metric_registry.py::test_materialized_fact_column_registry_matches_duckdb_schema failed because MATERIALIZED_FACT_COLUMN_REGISTRY didn't include the new columns
- Fix: Added 5 provenance column entries to activity_metric_facts in the registry
- Files modified: metric_registry.py

**3. [Rule 2 - Missing functionality] docs/metrics.md calculation strings needed updating**
- Found during: Task 4 (test run)
- Issue: test_docs_metrics_md_stays_in_sync_with_registry verified that registry calculation strings appear verbatim in docs/metrics.md; trimp and hrr_pct strings were stale
- Fix: Updated both rows in docs/metrics.md
- Files modified: docs/metrics.md

## TRIMP Regression Result

```
tests/test_hr_zones.py::test_karvonen_reproduces_historical_bounds PASSED
tests/test_hr_zones.py::test_trimp_regression PASSED
zone_bounds(191, 53) == [122, 136, 150, 163, 177, 300]  ✓
```

KarvonenHRR at hr_rest=53/hr_max=191 reproduces the historical bounds byte-identically. The TRIMP regression test confirms that 10 HR=160 stream rows (z4, coeff=3) produce TRIMP=0.5 exactly.

## Full Suite Result

300 passed in ~164s (0 failures, 0 errors)

## Config.* Symbols Removed

| Symbol | Location | Status |
|--------|----------|--------|
| Config.Athlete | constants.py | Deleted |
| Config.Zones.BOUNDS | constants.py | Deleted |
| Config.SQL (TRIMP/ZONES/TRIMP_S/ZONES_S) | constants.py | Deleted |
| _build_trimp_cases | constants.py | Deleted |

Replacement: `build_trimp_sql(bounds, alias)` and `build_zones_sql(bounds, alias)` in repository.py, which take precomputed integer bounds from `zone_bounds(hr_max, hr_rest)`.

## Provenance Columns Added

`activity_metric_facts` gains five new columns:
- `observed_min_hr` — min stream HR for the activity
- `observed_max_hr` — max stream HR for the activity
- `hr_zone_model` — zone model identifier used (e.g. "karvonen_hrr")
- `hr_max_used` — running max-HR-to-date used as hr_max
- `hr_rest_used` — athlete hr_rest from MCP_STRAVA_HR_REST

Added to DUCKDB_SCHEMA_SQL for fresh DBs and via `ensure_provenance_columns()` (ALTER TABLE IF NOT EXISTS) for existing DBs.

## Known Stubs

None — all provenance fields are populated from live data during materialization.

## Self-Check: PASSED

- tests/conftest.py: FOUND
- tests/test_hr_zones.py (extended): FOUND
- src/mcp_strava/adapters/duckdb/schema.py (provenance columns): FOUND
- src/mcp_strava/adapters/duckdb/read_model_materializer.py (on-the-fly bounds): FOUND
- Commits fdeaf35, e84a5f1, bf8732e, 59db9fd: all present in git log
- grep Config.Athlete/Config.Zones.BOUNDS/Config.SQL in src/: CLEAN
