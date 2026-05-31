---
phase: "14"
plan: "01"
subsystem: "metric-registry"
tags: ["duckdb", "metric-registry", "schema-generation", "tdd"]
dependency_graph:
  requires: []
  provides:
    - "Registry-owned SQL metadata for materialized fact columns"
    - "Generated activity_metric_facts table and ADD COLUMN SQL helpers"
  affects: ["14-02", "duckdb-schema"]
tech_stack:
  added: []
  patterns:
    - "Materialized fact schema metadata lives in metric_registry.py and is import-time validated"
key_files:
  created: []
  modified:
    - "src/mcp_strava/metric_registry.py"
    - "tests/test_metric_registry.py"
decisions:
  - "Keep Phase 14-01 limited to registry metadata and helper rendering; schema.py remains unchanged until 14-02."
requirements-completed:
  - "Metric platform maintainability / registry source-of-truth"
metrics:
  duration: "12 min"
  completed: "2026-05-31"
  tasks_completed: 2
  files_modified: 2
---

# Phase 14 Plan 01: Registry-Owned Fact Schema Metadata Summary

**Registry-owned SQL metadata and deterministic activity_metric_facts DDL helpers without runtime schema changes.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-05-31T11:43:00Z
- **Completed:** 2026-05-31T11:55:44Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added TDD coverage requiring SQL metadata on every materialized fact registry column.
- Populated `FactColumnDefinition` with DuckDB type, nullability, and default metadata for current materialized fact tables.
- Added import-time validation for identifiers, supported DuckDB type tokens, and the deliberately small default expression set.
- Added generated `activity_metric_facts` table SQL and generated activity fact `ADD COLUMN` SQL helpers.

## Task Commits

1. **Task 1: Add failing registry schema-metadata tests** - `d2ad419` (`test(14-01)`)
2. **Task 2: Add FactColumnDefinition SQL metadata and activity DDL helpers** - `d2a16ed` (`feat(14-01)`)

## Files Created/Modified

- `tests/test_metric_registry.py` - Adds registry SQL metadata and generated activity fact DDL contract tests.
- `src/mcp_strava/metric_registry.py` - Adds SQL metadata fields, metadata population, validation, and activity fact SQL render helpers.

## Decisions Made

- The registry now owns materialized fact SQL metadata, while `schema.py` remains untouched for this setup plan.
- Allowed SQL defaults are intentionally narrow: `0`, `0.0`, and `'[]'`, matching the current materialized fact schema.

## Verification Results

| Command | Result |
|---|---|
| `uv run pytest tests/test_metric_registry.py -q -x` | `25 passed in 0.80s` |
| `uv run python -c "from mcp_strava.metric_registry import activity_metric_facts_table_sql; print(activity_metric_facts_table_sql())"` | Printed `CREATE TABLE activity_metric_facts (` with current columns and primary key |

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope expansion.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 14-02 can now cut `schema.py` over to `activity_metric_facts_table_sql()` and registry-generated additive `ALTER TABLE` SQL.

## Self-Check: PASSED

- Registry SQL metadata exists for all materialized fact columns.
- `activity_metric_facts_table_sql()` generates the current activity fact table DDL.
- `activity_metric_fact_add_column_sql()` generates ADD COLUMN statements from registry metadata.
- Targeted registry tests pass.
- `schema.py` was not changed in this plan.

---
*Phase: 14-metric-platform-registry-owned-fact-schema*
*Completed: 2026-05-31*
