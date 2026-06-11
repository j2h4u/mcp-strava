---
phase: "16"
plan: "04"
subsystem: storage-cleanup
status: complete
tags: [duckdb, schema, boolean, streams, cardiac-drift]
dependency_graph:
  requires: ["16-02"]
  provides: ["streams.is_moving BOOLEAN", "cardiac_drift_significant BOOLEAN"]
  affects: ["schema_tables", "stream_write_repository", "read_model_activity_facts", "status_fact_queries", "metric_registry_fact_column_sql"]
tech_stack:
  added: []
  patterns: ["bool() coercion at write site", "= TRUE literal predicate", "allowlist-first registry expansion"]
key_files:
  created: []
  modified:
    - src/mcp_strava/adapters/duckdb/schema_tables.py
    - src/mcp_strava/adapters/duckdb/stream_write_repository.py
    - src/mcp_strava/metric_registry_fact_column_sql.py
    - src/mcp_strava/adapters/duckdb/read_model_activity_facts.py
    - src/mcp_strava/adapters/duckdb/status_fact_queries.py
    - tests/test_duckdb_repository.py
    - tests/test_read_model_queries.py
decisions:
  - "BOOLEAN added to _SUPPORTED_FACT_SQL_TYPES before changing cardiac_drift_significant metadata (allowlist-first order per T-16-04-ORDER)"
  - "default_sql='0' kept for cardiac_drift_significant — DuckDB coerces 0→FALSE on BOOLEAN columns"
  - "status_fact_queries uses = TRUE literal (no bound param) — explicit, no injection surface"
metrics:
  duration: "~2 min"
  completed: "2026-06-11"
  tasks: 2
  files: 7
---

# Phase 16 Plan 04: BOOLEAN Column Conversion Summary

Two BIGINT-as-boolean columns converted to native DuckDB BOOLEAN: `streams.is_moving` and `activity_metric_facts.cardiac_drift_significant`.

## What Was Done

### Task 3a: streams.is_moving BIGINT → BOOLEAN

- **schema_tables.py**: `is_moving BIGINT` → `is_moving BOOLEAN` in streams DDL
- **stream_write_repository.py**: bind site now does `bool(row["is_moving"]) if row.get("is_moving") is not None else None` — explicit Python bool, None passthrough preserved for nullable column
- **tests/test_duckdb_repository.py**: stream fixture uses `"is_moving": True` (not `1`)

Commit: `aefc49f`

### Task 3b: cardiac_drift_significant BIGINT → BOOLEAN (registry-owned)

Order was mandatory — validator `_validate_fact_column_sql_metadata()` runs at import time:

1. **metric_registry_fact_column_sql.py**: added `"BOOLEAN"` to `_SUPPORTED_FACT_SQL_TYPES` first
2. **metric_registry_fact_column_sql.py**: `cardiac_drift_significant` metadata changed to `_sql("BOOLEAN", nullable=False, default_sql="0")`
3. **read_model_activity_facts.py**: both write sites (single path line ~184, batched path line ~323) changed to `bool(drift and drift.is_significant)`
4. **status_fact_queries.py**: predicate changed from `cardiac_drift_significant >= ?` to `cardiac_drift_significant = TRUE`; corresponding bound param removed
5. **tests/test_read_model_queries.py**: fixture uses `"cardiac_drift_significant": False` (not `0`)

Commit: `20282c0`

## Deviations from Plan

None — plan executed exactly as written.

## Fingerprint Note

Changing `metric_registry_fact_column_sql.py` (a `COMPUTE_SOURCE_MODULES` member) will flip `compute_logic_fingerprint()` on next startup. This triggers `_seed_logic_version()` to bump `metric_version` and mass-enqueue rematerialization. This is expected and correct — not a regression.

## Known Stubs

None.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries beyond what the plan documented.

## Self-Check: PASSED

- `aefc49f` exists: `git log --oneline | grep aefc49f` ✓
- `20282c0` exists: `git log --oneline | grep 20282c0` ✓
- `is_moving BOOLEAN` in schema_tables.py ✓
- `_SUPPORTED_FACT_SQL_TYPES` includes BOOLEAN ✓
- `just check` green ✓
- `tests/test_read_model_queries.py tests/test_logic_fingerprint.py` 14 passed ✓
- `tests/test_duckdb_repository.py -k stream` 1 passed ✓
