---
phase: 14-metric-platform-registry-owned-fact-schema
reviewed: 2026-05-31T13:06:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - src/mcp_strava/metric_registry.py
  - src/mcp_strava/adapters/duckdb/schema.py
  - tests/test_metric_registry.py
  - tests/test_duckdb_repository.py
findings:
  critical: 0
  warning: 2
  info: 0
  total: 2
status: issues_found
---

# Phase 14: Code Review Report

**Reviewed:** 2026-05-31T13:06:00Z  
**Depth:** standard  
**Files Reviewed:** 4  
**Status:** issues_found

## Summary

Phase 14 successfully centralizes `activity_metric_facts` DDL in the registry and preserves explicit migration policy in `schema.py`. No immediate behavioral regressions or security vulnerabilities were found in the current implementation path. Two robustness/test-reliability warnings should be addressed to prevent future silent breakage.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: Additive migration safety is implicit, not enforced

**Classification:** WARNING  
**File:** `src/mcp_strava/adapters/duckdb/schema.py:518`  
**Issue:** `ensure_provenance_columns()` assumes every column in `ACTIVITY_METRIC_FACT_LATE_COLUMNS` can be safely added to an already-populated table. This is currently true, but there is no guard preventing a future late column from being `NOT NULL` without a `DEFAULT`, which would fail on existing DBs and break startup-time migration.  
**Fix:**
```python
# schema.py
from mcp_strava.metric_registry import _materialized_fact_column_definition  # or a public accessor

for column_name in ACTIVITY_METRIC_FACT_LATE_COLUMNS:
    definition = _materialized_fact_column_definition("activity_metric_facts", column_name)
    if (not definition.nullable) and (definition.default_sql is None):
        raise RuntimeError(
            f"Unsafe additive migration for {column_name}: NOT NULL without DEFAULT"
        )
    conn.execute(activity_metric_fact_add_column_sql(column_name))
```
Add a test that enforces this invariant for all late columns.

### WR-02: Source-level DDL cutover test is brittle

**Classification:** WARNING  
**File:** `tests/test_metric_registry.py:383`  
**Issue:** `assert "CREATE TABLE activity_metric_facts (" not in inspect.getsource(schema)` is a text-fragment assertion. It can false-pass (inline DDL with altered whitespace/casing) or false-fail (the string appears in comments/docs), reducing test reliability.  
**Fix:** Replace string search with a structural assertion (AST or runtime behavior), e.g. assert `DUCKDB_SCHEMA_SQL` includes `{activity_metric_facts_table_sql()}`-derived columns by comparing the executed schema contract only (already mostly done in nearby tests), and remove the raw source-substring check.

---

_Reviewed: 2026-05-31T13:06:00Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: standard_
