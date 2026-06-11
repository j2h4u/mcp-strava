---
phase: "16"
plan: "06"
subsystem: storage-cleanup
status: complete
tags: [duckdb, schema-views, stream-coverage, cast-removal, json-predicate]
dependency_graph:
  requires: ["16-05"]
  provides: ["views without redundant CAST(x AS DATE)", "SQL json_extract_string existence predicate"]
  affects:
    - schema_views
    - stream_coverage_queries
    - test_metric_registry
    - 16-VALIDATION.md
tech_stack:
  added: []
  patterns:
    - "Remove no-op CAST(x AS DATE) where source column is already DATE"
    - "json_extract_string(values_json, '$.' || ?) IS NOT NULL as DuckDB existence predicate"
    - "Bound-param path concatenation for JSON key lookup"
key_files:
  created: []
  modified:
    - src/mcp_strava/adapters/duckdb/schema_views.py
    - src/mcp_strava/adapters/duckdb/stream_coverage_queries.py
    - tests/test_metric_registry.py
    - .planning/phases/16-duckdb-native-storage-cleanup/16-VALIDATION.md
decisions:
  - "Remove all 7 CAST(x AS DATE) instances where x is a confirmed DATE column — no-op, never changes behavior"
  - "json_extract_string(values_json, '$.' || ?) IS NOT NULL replaces Python any(channel in json.loads(...)) loop — single SQL existence check, reads at most 1 row"
  - "LIMIT 1 added to the existence query — only need to find one matching stream row per activity+channel"
  - "import json removed from stream_coverage_queries.py — no remaining callers"
  - "Test fixes for Phase 16-05 stale expectations: BOOLEAN now supported (16-04), VARCHAR[] DEFAULT [] replaces VARCHAR DEFAULT '[]' (16-05), information_schema normalises DEFAULT [] to main.list_value()"
metrics:
  duration: "~6 min"
  completed: "2026-06-11"
  tasks: 3
  files: 4
---

# Phase 16 Plan 06: CAST cleanup + json_extract_string predicate Summary

Removed 7 no-op `CAST(x AS DATE)` from aggregate views (where source is already DATE) and replaced the N-row Python `json.loads` loop in stream channel coverage with a single SQL `json_extract_string(values_json, '$.' || ?) IS NOT NULL` existence predicate. Also fixed 3 stale test expectations from Phase 16-05. Full suite: 429 passed.

## What Was Done

### Task 5a: Remove redundant CAST(x AS DATE) from schema_views.py

All 7 occurrences were no-ops (source columns are DATE in schema_tables.py):

- `v_activity_aggregate_facts`: `CAST(f.activity_day AS DATE)` → `f.activity_day`
- `v_daily_aggregate_facts`: `CAST(day AS DATE)` → `day`
- `v_training_model_state_facts`: `CAST(day AS DATE)` → `day`
- `v_historical_context_facts` CTE `days`: `CAST(day AS DATE)` → `day`
- `v_historical_context_facts` CTE `last_hikes`: `MAX(CAST(a.activity_day AS DATE))` → `MAX(a.activity_day)`
- `v_historical_context_facts` WHERE: `CAST(a.activity_day AS DATE) <= d.day` → `a.activity_day <= d.day`
- `v_rolling_aggregate_facts`: `CAST(as_of_day AS DATE)` → `as_of_day`

Commit: `9eab907`

### Task 5b: Replace Python json.loads loop with SQL json_extract_string predicate

In `activities_missing_stream_channels()`, the `{"distance", "watts", "temp"}` channel branch previously fetched all `values_json` rows for an activity and ran `any(channel in json.loads(...) for item in value_rows)` — N Python deserializations.

Replaced with:
```sql
SELECT 1 FROM streams
WHERE activity_id = ?
  AND json_extract_string(values_json, '$.' || ?) IS NOT NULL
LIMIT 1
```

`_fetchall` + Python loop → single `_fetchone`. `import json` removed (no remaining uses).

Commit: `807723d`

### Task 5c: Full phase gate + fix stale test expectations

Three tests in `test_metric_registry.py` were failing since Phase 16-05 (not introduced by this plan):

1. `test_fact_column_sql_metadata_rejects_unsafe_fragments_before_rendering`: `BOOLEAN` became supported in 16-04 — updated to `INTEGER` as the rejection case.
2. `test_activity_metric_facts_generated_sql_matches_current_contract`: hardcoded `VARCHAR NOT NULL DEFAULT '[]'` — updated to `VARCHAR[] NOT NULL DEFAULT []`.
3. `test_activity_metric_fact_schema_matches_registry_metadata`: DuckDB `information_schema` normalises `DEFAULT []` to `main.list_value()` — `missing_reasons_json` now verified for type + nullable only (not repr round-trip).

16-VALIDATION.md: `status: complete`, `wave_0_complete: true`, all task rows → ✅ green.

Full gate: `just check` (ruff + format + basedpyright + import-linter + vulture) + `pytest -n auto` → 429 passed.

Commit: `e0b64d8`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fix 3 stale test expectations from Phase 16-05**
- **Found during:** Task 5c full phase gate
- **Issue:** Phase 16-05 changed `missing_reasons_json` from `VARCHAR/'[]'` to `VARCHAR[]/[]` and Phase 16-04 added `BOOLEAN` to supported types, but tests were not updated
- **Fix:** Updated 3 assertions in `test_metric_registry.py` to match current schema/registry state
- **Files modified:** `tests/test_metric_registry.py`
- **Commit:** `e0b64d8`

## Known Stubs

None.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries. All changes are internal SQL cleanup only. `json_extract_string` uses bound parameters (`?`) — no SQL injection surface as documented in T-16-06-JSON.

## Self-Check: PASSED

- `9eab907` exists: checked via git log
- `807723d` exists: checked via git log
- `e0b64d8` exists: checked via git log
- Zero `CAST.*AS DATE` remaining in schema_views.py: confirmed by grep (no output)
- `json_extract_string` in stream_coverage_queries.py: confirmed
- `import json` removed from stream_coverage_queries.py: confirmed
- 429 passed, `just check` green: confirmed
- 16-VALIDATION.md `wave_0_complete: true`: confirmed
