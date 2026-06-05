---
status: planned
mode: quick-full
quick_id: 260605-mna
date: 2026-06-05
must_haves:
  truths:
    - Preserve Phase 10 pure metric contract: do not port hr_recovery or cardiac_drift to SQL in this slice.
    - Do not touch or resync runtime DuckDB data.
    - Batched path must preserve byte-identical materialized facts.
    - Running max HR must remain day-inclusive, not activity-row-order dependent.
  artifacts:
    - src/mcp_strava/adapters/duckdb/repository.py
    - src/mcp_strava/adapters/duckdb/read_model_materializer.py
    - tests/test_read_model_materialization.py
    - .planning/quick/260605-mna-implement-phase-3-activity-fact-duckdb-b/260605-mna-SUMMARY.md
    - .planning/quick/260605-mna-implement-phase-3-activity-fact-duckdb-b/260605-mna-VERIFICATION.md
  key_links:
    - .planning/quick/260605-gsd-phase-3-duckdb-compute-pushdown-panel/EXPERT-PANEL.md
    - .planning/PROJECT.md
---

# Quick Task 260605-mna: Phase 3 _activity_fact DuckDB Batch Reads

## Objective

Implement the first Phase 3 read-model materializer performance slice from the accepted expert-panel design: remove the per-activity scalar read fan-out around `_activity_fact` by adding parity-gated batched DuckDB reads and wiring the materializer to use them, while keeping the complex pure metric functions canonical.

## Task 1: RED/Parity Scaffolding

**files**

- `tests/test_read_model_materialization.py`

**action**

Add focused tests that prove the future batched path preserves current behavior:

- Batch scalar repository reads match existing per-activity methods for a multi-day, multi-activity fixture.
- Running max HR by date matches `repo.max_heartrate_to_date(day)` and is day-inclusive for same-day activities.
- Batched `_activity_fact` output matches the current sequential `_activity_fact` output exactly.
- Statement-count evidence shows the batched materialization avoids O(N) scalar reads for N dirty activities.

Keep test fixtures local to this test module and avoid runtime DB data.

**verify**

- Run targeted pytest for the new tests and confirm they fail before implementation for missing batch methods/path.

**done**

- Tests define the expected behavior and cover parity plus statement-count reduction.

## Task 2: Batched Repository Read Methods

**files**

- `src/mcp_strava/adapters/duckdb/repository.py`
- `tests/test_read_model_materialization.py`

**action**

Add typed repository methods for the materializer's batch inputs:

- Source/activity lookup for a list of activity ids.
- Stream scalar aggregates grouped by `activity_id` for counts, HR min/max, median HR, and cardiac cost.
- Day-level running max HR for a list/range of dirty activity days.
- Bounds-driven grouped zone/TRIMP query that uses Python-computed bounds.
- Bulk stream row reads grouped/partitioned by `activity_id` while preserving current filters/order for pure metric calls.

Use Python rounding where current code does. Keep SQL identifiers/params safe and avoid adding storage imports to domain modules.

**verify**

- New method-level parity tests pass against the existing per-activity methods.

**done**

- Batch methods provide enough data for `_activity_fact` without per-activity scalar queries.

## Task 3: Materializer Wiring And Validation

**files**

- `src/mcp_strava/adapters/duckdb/read_model_materializer.py`
- `tests/test_read_model_materialization.py`
- `.planning/STATE.md`

**action**

Refactor the materializer so the dirty-row loop consumes preloaded batch maps instead of issuing scalar repository reads per activity.

Keep:

- `calc_hr_recovery`, `calc_vertical_speed`, `calc_cardiac_drift`, and `calc_hrr_pct` as the canonical metric implementations.
- `_detail_calories()` and `_start_time_local()` in Python.
- The existing transaction boundary, dirty-row clearing, failed-run behavior, and whole-day limit behavior.

Add the small independent improvement after parity is green: hoist `repo.training_model_row(as_of_day, metric_version)` out of the `ROLLING_WINDOWS` loop.

**verify**

- Targeted materializer tests pass.
- `ruff check`, `ruff format --check`, `pyright`, `vulture`, and `pytest` are clean or any failure is documented.

**done**

- Materializer uses batched reads, preserves output parity, reduces statement-count shape, and leaves MCP/runtime surfaces unchanged.
