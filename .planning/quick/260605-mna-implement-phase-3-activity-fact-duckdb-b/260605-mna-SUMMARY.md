---
status: complete
quick_id: 260605-mna
date: 2026-06-05
commit: 4e45c2c, 1d80139
---

# Quick Task 260605-mna Summary

## Goal

Implement the first Phase 3 `_activity_fact` DuckDB batch-read performance slice from the accepted expert-panel design.

## Completed

- Added batched materializer repository contracts:
  - `activity_materialization_sources`
  - `activity_stream_scalars_for_materialization`
  - `max_heartrate_to_dates`
  - `activity_zone_trimp_for_bounds`
  - bulk stream-row reads for HR recovery, vertical speed, and cardiac drift inputs
- Added `_activity_facts_batched` in the read-model materializer.
- Wired `materialize_read_model` to use the batched path while keeping `_activity_fact` as the sequential parity reference.
- Preserved Phase 10 pure metric semantics: `calc_hr_recovery`, `calc_vertical_speed`, `calc_cardiac_drift`, and `calc_hrr_pct` remain canonical Python functions.
- Preserved day-inclusive running max HR and per-activity observed max for `%HRR`.
- Hoisted `repo.training_model_row(as_of_day, metric_version)` out of the rolling-window loop.
- Optimized batch running-max HR lookup to pre-aggregate per-day HR before applying a running window.
- Moved batch activity-fact reads and pure computations before the write transaction so cold-start MCP reads are not blocked by long materialization compute.
- Added tests for:
  - batch repository reads vs existing per-activity methods
  - batched activity facts vs sequential `_activity_fact`
  - no per-activity scalar read fanout during materialization
  - batch reads run before the materializer write transaction

## Verification

- `uv run pytest tests/test_read_model_materialization.py -q` -> 17 passed in 26.84s
- `just check` -> passed
  - ruff format check
  - ruff check
  - basedpyright
  - import contracts
  - compileall
  - vulture
- `time -p just test` -> passed
  - pytest phase: 395 passed in 64.44s
  - Docker build/start/health: passed
  - MCP smoke-basic: passed
  - wall-clock: real 120.56s

## Notes

- No runtime DuckDB data was touched or resynced.
- MCP and CLI surfaces were unchanged.
- The complex SQL-port question remains deferred behind a future explicit parity-gated decision.
