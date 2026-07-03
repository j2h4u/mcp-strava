---
phase: 260702-strava-bronze-migration-design
reviewed: 2026-07-03T10:42:01Z
depth: deep
files_reviewed: 19
files_reviewed_list:
  - src/mcp_strava/adapters/duckdb/activity_lookup_queries.py
  - src/mcp_strava/adapters/duckdb/activity_selectors.py
  - src/mcp_strava/adapters/duckdb/hydrated_activity_sql.py
  - src/mcp_strava/adapters/duckdb/kudos_store.py
  - src/mcp_strava/adapters/duckdb/read_model_repository.py
  - src/mcp_strava/adapters/duckdb/read_model_source_repository.py
  - src/mcp_strava/adapters/duckdb/repository.py
  - src/mcp_strava/adapters/duckdb/repository_models.py
  - src/mcp_strava/adapters/duckdb/schema_tables.py
  - src/mcp_strava/adapters/duckdb/schema_views.py
  - src/mcp_strava/adapters/duckdb/source_hashing.py
  - src/mcp_strava/metric_registry.py
  - src/mcp_strava/refresh/_sync_ops.py
  - src/mcp_strava/refresh/runtime.py
  - tests/test_duckdb_repository.py
  - tests/test_read_model_queries.py
  - tests/test_refresh_runtime.py
  - tests/test_repository_boundary.py
  - tests/test_source_hashing.py
findings:
  critical: 2
  warning: 1
  info: 0
  total: 3
status: issues_found
---

# Phase 260702-strava-bronze-migration-design: Code Review Report

**Reviewed:** 2026-07-03T10:42:01Z
**Depth:** deep
**Files Reviewed:** 19
**Status:** issues_found

## Summary

Reviewed the uncommitted bronze-migration WIP across repository, refresh runtime, hydrated read paths, and the touched tests. The main regressions are in backfill invalidation/materialization and in propagation of summary date edits through source-state and read-model facts. I also found an upgrade-path gap where the new legacy bronze backfill is not consumable by `schema_validate`.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Details-only catchup stores bronze detail payloads but never invalidates or materializes them

**File:** `src/mcp_strava/refresh/runtime.py:163-179`
**Issue:** `run_catchup()` now runs `sync_details()` and then jumps straight to `materialize_read_model_stage()`, but `sync_details()` no longer updates `activities.detail_json` or enqueues dirty rows. Unlike the daily path, the backfill path never calls `schema_validate()` after detail ingestion, so a details-only backfill can finish `ok` with the new bronze detail payload persisted and zero dirty rows/materialized facts. I reproduced this on the current tree with an activity that already had streams: `run_catchup()` returned `ok`, `bronze.latest_activity_payloads` contained the detail JSON, and `activity_metric_facts` still had no row for that activity.
**Fix:**
```python
if start_index <= _backfill_stage_index(Stage.DETAILS_BACKFILL):
    refresh_store.set_checkpoint(Stage.DETAILS_BACKFILL.value, None)
    details_fetched = _sync_ops.sync_details(...)

if start_index <= _backfill_stage_index(Stage.READ_MODEL_MATERIALIZE_BACKFILL):
    refresh_store.set_checkpoint(Stage.READ_MODEL_MATERIALIZE_BACKFILL.value, None)
    _sync_ops.schema_validate(repo)
    _sync_ops.materialize_read_model_stage(...)
```
Prefer a dedicated backfill schema-validation checkpoint if you need crash-safe resume between invalidation and materialization.

### CR-02: Summary date edits never propagate into source state or materialized fact dates

**File:** `src/mcp_strava/adapters/duckdb/read_model_source_repository.py:35-45`, `src/mcp_strava/adapters/duckdb/read_model_source_repository.py:88-95`, `src/mcp_strava/adapters/duckdb/read_model_activity_facts.py:303-312`, `src/mcp_strava/adapters/duckdb/repository.py:509-535`
**Issue:** `schema_validate()` creates a shell only when the activity is missing, but for existing rows it leaves `activities.activity_day` unchanged. `_read_activity_source_components()` then records `activity_day` from the stale silver row instead of the hydrated bronze summary, and materialization writes `activity_metric_facts.activity_day` from the dirty row rather than from `source.activity.activity_day`. Result: if a Strava summary payload moves a workout to a different day, the bronze payload and hydrated name update, but the dirty queue, source state, and fact row stay pinned to the old day. I reproduced this on the current tree: after writing a bronze summary that moved activity `901` from `2026-05-21` to `2026-05-10`, `schema_validate()` enqueued `activity_day='2026-05-21'` and the rematerialized fact still stored `2026-05-21`.
**Fix:**
```python
# read_model_source_repository.py
SELECT
    a.id,
    COALESCE(summary_payload.activity_day, a.activity_day) AS activity_day,
    COALESCE(json_extract_string(summary_payload.payload_json, '$.name'), a.name) AS name,
    ...

# read_model_activity_facts.py
"activity_day": source.activity.activity_day,
```
If the modeled `activities` shell is meant to remain queryable on its own, process-time projection also needs to update the shell's date/name fields from the latest bronze summary instead of leaving them stale forever.

## Warnings

### WR-01: The one-time legacy bronze backfill is not actually consumable by `schema_validate`

**File:** `src/mcp_strava/adapters/duckdb/repository.py:120-193`, `src/mcp_strava/adapters/duckdb/repository.py:497-507`, `src/mcp_strava/refresh/_sync_ops.py:360-370`
**Issue:** the constructor backfills `bronze.activity_payloads` from existing `activities.summary_json/detail_json`, but `schema_validate()` only walks `activity_ids_with_source_bronze_payloads()`, which explicitly excludes `migrated_from_legacy = TRUE`. On an upgraded mirror with preserved legacy rows but no usable `activity_source_state`/dirty queue, the migration seeds bronze data that the processing pipeline will never consume, forcing a future Strava replay to rebuild read-model provenance. I reproduced this on the current tree by creating a DB with only a legacy `activities` row: repo open backfilled bronze rows, `schema_validate()` reported `activities_considered=0`, and the dirty queue stayed empty.
**Fix:**
```python
def schema_validate(repo) -> None:
    activity_ids = repo.activity_ids_needing_bronze_bootstrap()
    ...
```
At minimum, add a one-shot bootstrap path that seeds `activity_source_state`/dirty rows from migrated bronze payloads when no source-state row exists, so upgrade recovery does not depend on a rate-limited full resync.

---

_Reviewed: 2026-07-03T10:42:01Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
