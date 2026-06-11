---
phase: "16"
plan: "05"
subsystem: storage-cleanup
status: complete
tags: [duckdb, schema, varchar-array, missing-reasons, aggregate]
dependency_graph:
  requires: ["16-03", "16-04"]
  provides: ["missing_reasons_json VARCHAR[]", "list_distinct(flatten(...)) aggregation", "json-free decode"]
  affects:
    - metric_registry_fact_column_sql
    - schema_tables
    - read_model_materializer_utils
    - read_model_period_facts
    - aggregate_queries
    - aggregate_rows
tech_stack:
  added: []
  patterns:
    - "allowlist-first registry expansion (VARCHAR[] before metadata change)"
    - "DuckDB list_distinct(flatten(list(col))) for nested array aggregation"
    - "Python list[str] binds natively to VARCHAR[] column"
decisions:
  - "VARCHAR[] added to _SUPPORTED_FACT_SQL_TYPES BEFORE updating missing_reasons_json metadata entries (T-16-05-ORDER)"
  - "[] bare array literal added to _SUPPORTED_FACT_DEFAULT_SQL; old '[]' string default retained until fully superseded"
  - "list_distinct(flatten(list(col))) collapses list[list[str]] to flat list[str] in SQL — no Python json.loads needed"
  - "_missing_reasons returns flat list[str] directly (payloads is already the flat list post-flatten)"
  - "import json removed from both read_model_materializer_utils and aggregate_rows (no remaining uses)"
  - "import cast removed from aggregate_rows (no remaining uses after _missing_reasons refactor)"
key_files:
  created: []
  modified:
    - src/mcp_strava/metric_registry_fact_column_sql.py
    - src/mcp_strava/adapters/duckdb/schema_tables.py
    - src/mcp_strava/adapters/duckdb/read_model_materializer_utils.py
    - src/mcp_strava/adapters/duckdb/read_model_period_facts.py
    - src/mcp_strava/adapters/duckdb/aggregate_queries.py
    - src/mcp_strava/adapters/duckdb/aggregate_rows.py
metrics:
  duration: "~3 min"
  completed: "2026-06-11"
  tasks: 3
  files: 6
---

# Phase 16 Plan 05: VARCHAR[] missing_reasons_json Conversion Summary

Converted `missing_reasons_json VARCHAR` to `VARCHAR[]` end-to-end across all four fact tables, eliminated Python JSON serialization in the write path, replaced `list(col)` SQL with `list_distinct(flatten(list(col)))` in three aggregate queries, and removed `json.loads` from the decode path.

## What Was Done

### Task 4a: Expand allowlists and update registry metadata

Order was mandatory — `_validate_fact_column_sql_metadata()` runs at import time:

1. **metric_registry_fact_column_sql.py**: added `"VARCHAR[]"` to `_SUPPORTED_FACT_SQL_TYPES`
2. **metric_registry_fact_column_sql.py**: added `"[]"` to `_SUPPORTED_FACT_DEFAULT_SQL`
3. Import check passed before any metadata change
4. All four `missing_reasons_json` entries changed from `_sql("VARCHAR", ..., default_sql="'[]'")` to `_sql("VARCHAR[]", ..., default_sql="[]")`
5. **schema_tables.py**: three direct DDL tables (`daily_load_facts`, `training_model_daily`, `rolling_period_facts`) changed from `VARCHAR NOT NULL DEFAULT '[]'` to `VARCHAR[] NOT NULL DEFAULT []`

Commit: `556c0a8`

### Task 4b: Update write paths

- **read_model_materializer_utils.py**: `_json_list` return type changed from `str` to `list[str]`; now returns `sorted(set(values))` instead of `json.dumps(...)`; `import json` removed (sole use was `_json_list`)
- **read_model_period_facts.py**: two hardcoded `"missing_reasons_json": "[]"` literals changed to `"missing_reasons_json": []` (Python empty list binds natively to VARCHAR[])

Commit: `53c0f71`

### Task 4c: Update aggregate SQL and remove json.loads decode

- **aggregate_queries.py**: all three occurrences of `list(missing_reasons_json) AS missing_reason_payloads` changed to `list_distinct(flatten(list(missing_reasons_json))) AS missing_reason_payloads`
- **aggregate_rows.py**: `_missing_reasons` replaced with json-free version — `payloads` is now the flat `list[str]` returned by `list_distinct(flatten(...))`, so the function simply filters None items
- **aggregate_rows.py**: `import json` removed (no remaining uses); `from typing import cast` removed (only use was the now-deleted `json.loads` call)

Commit: `51692fb`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Remove unused `cast` import from aggregate_rows.py**
- **Found during:** Task 4c — `just check` reported `F401 cast imported but unused`
- **Issue:** After removing `_missing_reasons`'s `json.loads` path, `cast` had no remaining callers
- **Fix:** Removed `from typing import cast` import
- **Files modified:** `src/mcp_strava/adapters/duckdb/aggregate_rows.py`
- **Commit:** `51692fb`

**2. [Rule 3 - Blocking] Fix import group separator after cast removal**
- **Found during:** Task 4c — ruff `I001` "Organize imports" after cast removal left stdlib and project imports adjacent
- **Fix:** Added blank line between `from datetime import ...` and project imports
- **Files modified:** `src/mcp_strava/adapters/duckdb/aggregate_rows.py`
- **Commit:** `51692fb`

## Fingerprint Note

Changing `metric_registry_fact_column_sql.py` (a `COMPUTE_SOURCE_MODULES` member) will flip `compute_logic_fingerprint()` on next startup. This triggers `_seed_logic_version()` to bump `metric_version` and mass-enqueue rematerialization. Expected and correct.

## Known Stubs

None.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries beyond what the plan documented. All changes are internal storage representation only.

## Self-Check: PASSED

- `556c0a8` exists: ✓
- `53c0f71` exists: ✓
- `51692fb` exists: ✓
- `VARCHAR[]` in schema_tables.py DDL: ✓
- `_SUPPORTED_FACT_SQL_TYPES` includes `VARCHAR[]`: ✓
- `_SUPPORTED_FACT_DEFAULT_SQL` includes `[]`: ✓
- `_json_list` returns `list[str]`: ✓
- Three `list_distinct(flatten(...))` in aggregate_queries.py: ✓
- No `json.loads` in aggregate_rows.py: ✓
- `import json` removed from aggregate_rows.py: ✓
- 21 passed (test_read_model_materialization + test_read_model_queries): ✓
- `just check` green: ✓
