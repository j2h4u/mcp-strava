---
status: complete
phase: 14-metric-platform-registry-owned-fact-schema
source:
  - 14-01-SUMMARY.md
  - 14-02-SUMMARY.md
  - 14-03-SUMMARY.md
started: 2026-05-31T18:18:03+05:00
updated: 2026-05-31T18:32:24+05:00
---

## Current Test

[testing complete]

## Tests

### 1. Existing MCP Product Surface Still Works
expected: The service still exposes the same six read-only product MCP tools after the registry-owned `activity_metric_facts` schema cutover, and a basic `list_workouts` smoke call returns `status: ok` with no warnings.
result: pass
evidence: `just test` completed Docker build, container health, and MCP smoke; smoke returned `status: ok`, tools `compare_periods`, `get_fitness_state`, `get_training_aggregates`, `get_workout_detail`, `list_workouts`, `project_fitness_state`, and no `list_workouts` warnings.

### 2. Existing Analytics Queries Still Work
expected: Materialized read-model and training aggregate queries still run against the DuckDB schema after `activity_metric_facts` table creation and late-column migration SQL are generated from the metric registry.
result: pass
evidence: Focused phase suite passed with `65 passed in 23.77s`; full `just test` passed with `357 passed in 137.70s`.

### 3. No New User-Facing Capabilities Were Introduced
expected: Phase 14 remains an internal maintainability slice: there is no new rematerialize command, source grammar, computed-metric DAG, or MCP/CLI payload behavior for the user to learn or operate.
result: pass
evidence: Scope scan `rg -n "source=.*detail_json|rematerialize|computed:|ACTIVITY_SCALAR_FACTS" src/mcp_strava tests` returned only two pre-existing `ACTIVITY_SCALAR_FACTS` references in `src/mcp_strava/application/metric_services.py`, which Phase 14 did not modify.

## Summary

total: 3
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[]
