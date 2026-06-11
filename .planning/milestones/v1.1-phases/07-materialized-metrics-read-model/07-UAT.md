---
status: complete
phase: 07-materialized-metrics-read-model
source:
  - .planning/phases/07-materialized-metrics-read-model/07-01-SUMMARY.md
  - .planning/phases/07-materialized-metrics-read-model/07-02-SUMMARY.md
  - .planning/phases/07-materialized-metrics-read-model/07-03-SUMMARY.md
  - .planning/phases/07-materialized-metrics-read-model/07-04-SUMMARY.md
  - .planning/phases/07-materialized-metrics-read-model/07-05-SUMMARY.md
  - .planning/phases/07-materialized-metrics-read-model/07-06-SUMMARY.md
started: 2026-05-24T22:52:38+05:00
updated: 2026-05-24T22:57:50+05:00
---

## Current Test

[testing complete]

## Tests

### 1. Docker MCP Cold Start Smoke
expected: Rebuilding and recreating the Docker MCP service boots a healthy Python 3.14 container. A basic MCP smoke call lists exactly the product tools and can call `list_workouts` successfully against the live read-model database.
result: pass

### 2. MCP Tool Surface Is Product-Only
expected: Listing MCP tools shows only `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, and `project_fitness_state`; there are no sync, backfill, SQL, raw, materialize, dirty, or admin tools.
result: pass

### 3. Read-Model Data Is Current
expected: MCP responses include read-model metadata showing facts are available/current, `dirty_count` is zero, metric versions are present, and the live database remains `user_version=5` with integrity `ok`.
result: pass

### 4. Workout List And Detail Use Materialized Facts
expected: `list_workouts` returns workout rows with factual volume/intensity fields, and `get_workout_detail` returns prepared synthetic metrics and completeness metadata without slow raw-stream recompute.
result: pass

### 5. Period Comparison Exposes Trends Without Interpretation
expected: `compare_periods` returns factual period A/B values, deltas, sample/coverage metadata, global/per-sport sections, and metric-version status while avoiding coaching or medical interpretation.
result: pass

### 6. Fitness Projection Uses Read-Model Baseline
expected: `project_fitness_state` returns scenario projections from materialized baseline model facts, includes read-model metadata, and keeps projection bounded without triggering sync or recompute controls.
result: pass

### 7. Warm MCP Calls Meet p95 Target
expected: Running the explicit read-model performance gate reports p95 below 500 ms for every MCP product tool, with startup measured separately from warm tool-call latency.
result: pass

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[]
