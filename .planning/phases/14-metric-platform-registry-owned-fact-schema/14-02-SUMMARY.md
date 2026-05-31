---
phase: "14"
plan: "02"
subsystem: "duckdb-schema"
tags: ["duckdb", "metric-registry", "schema-generation", "migration"]
dependency_graph:
  requires:
    - "14-01"
  provides:
    - "activity_metric_facts table creation generated from metric registry metadata"
    - "Late activity fact additive migration SQL generated from the registry"
  affects: ["14-03", "duckdb-repository", "read-model-materialization"]
tech_stack:
  added: []
  patterns:
    - "schema.py keeps migration policy while metric_registry.py renders activity fact DDL"
key_files:
  created: []
  modified:
    - "src/mcp_strava/adapters/duckdb/schema.py"
    - "tests/test_metric_registry.py"
    - "tests/test_duckdb_repository.py"
decisions:
  - "Only activity_metric_facts table DDL moved to registry generation; other fact tables, indexes, and views remain in schema.py."
  - "Late-column additive migration scope remains an explicit schema.py allowlist."
requirements-completed:
  - "Metric platform maintainability / registry source-of-truth"
metrics:
  duration: "10 min"
  completed: "2026-05-31"
  tasks_completed: 3
  files_modified: 3
---

# Phase 14 Plan 02: Registry-Generated Activity Fact Schema Summary

**DuckDB activity_metric_facts creation and late-column migration SQL now render from registry-owned fact metadata.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-05-31T11:55:00Z
- **Completed:** 2026-05-31T12:05:03Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Added temp-DuckDB tests for registry order, representative types/nullability/defaults, primary key columns, expected tables, expected views, and the activity metric index.
- Replaced the duplicated inline `activity_metric_facts` DDL in `schema.py` with `activity_metric_facts_table_sql()`.
- Replaced hand-written late-column `ALTER TABLE` SQL with registry-rendered SQL while keeping the existing late-column allowlist explicit.
- Added an old-temp-fixture migration test proving `ensure_provenance_columns()` adds the current late columns with registry-owned types.

## Task Commits

1. **Task 1: Strengthen schema parity tests before runtime cutover** - `38e660d` (`test(14-02)`)
2. **Task 2: Generate activity_metric_facts table DDL from the registry** - `5b0d94b` (`feat(14-02)`)
3. **Task 3: Generate additive activity fact migrations from registry metadata** - `fafd29d` (`feat(14-02)`)

## Files Created/Modified

- `tests/test_metric_registry.py` - Adds temp-DuckDB parity, broad schema smoke, and source-level cutover assertions.
- `tests/test_duckdb_repository.py` - Adds old-style fixture coverage for registry-owned late-column migration SQL.
- `src/mcp_strava/adapters/duckdb/schema.py` - Imports registry DDL helpers, generates activity fact table DDL, and renders late-column ALTER SQL from the registry.

## Decisions Made

- The runtime cutover is intentionally scoped to `activity_metric_facts`; later metric-platform slices still own source grammar, computed metric DAGs, and rematerialization flows.
- The late-column allowlist stays in `schema.py` as migration policy so registry metadata does not become a generic migration engine.

## Verification Results

| Command | Result |
|---|---|
| `uv run python -c "... create_schema ... count activity_metric_facts columns ..."` | `44` |
| `uv run python -c "... DUCKDB_TABLES ... create_schema ..."` | `schema smoke ok` |
| `uv run pytest tests/test_metric_registry.py -q -x` | `28 passed in 0.97s` |
| `uv run pytest tests/test_metric_registry.py tests/test_duckdb_repository.py -q -x` | `36 passed in 1.15s` |
| `uv run pytest tests/test_read_model_materialization.py tests/test_training_aggregates.py -q -x` | `27 passed in 23.11s` |

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope expansion.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 14-03 can run `just check`, `just test`, and the scope-fence scan against the registry-generated activity fact schema cutover.

## Self-Check: PASSED

- `schema.py` uses `activity_metric_facts_table_sql()` for table creation.
- `ensure_provenance_columns()` uses registry-generated ADD COLUMN SQL for the current late activity fact columns.
- Temp DuckDB schema tests verify names, representative types, nullability, defaults, and primary key.
- Repository initialization compatibility tests still pass.
- No live DB mutation was required.

---
*Phase: 14-metric-platform-registry-owned-fact-schema*
*Completed: 2026-05-31*
