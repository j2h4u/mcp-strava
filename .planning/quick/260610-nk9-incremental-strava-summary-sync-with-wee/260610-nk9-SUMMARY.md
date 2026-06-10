---
phase: 260610-nk9
plan: 01
subsystem: refresh
tags: [incremental-sync, strava-api, rate-limiting, duckdb-schema]
status: complete

dependency_graph:
  requires: []
  provides: [incremental-summaries-260610-nk9]
  affects: [refresh/runtime, refresh/_sync_ops, adapters/duckdb/refresh_state_store]

tech_stack:
  added: []
  patterns:
    - ALTER TABLE ADD COLUMN IF NOT EXISTS for live-DB-safe additive schema migration
    - full/incremental gate driven by nullable timestamp marker + configurable interval

key_files:
  created:
    - tests/test_incremental_summary_sync.py
  modified:
    - src/mcp_strava/adapters/duckdb/schema_tables.py
    - src/mcp_strava/adapters/duckdb/refresh_state_store.py
    - src/mcp_strava/settings.py
    - src/mcp_strava/refresh/policy.py
    - src/mcp_strava/refresh/_sync_ops.py
    - src/mcp_strava/refresh/runtime.py
    - tests/test_refresh_runtime.py

decisions:
  - "ALTER TABLE ADD COLUMN IF NOT EXISTS in from_connection rather than a one-time migration — idempotent on every construction, cheap, no migration state to track"
  - "after_epoch derived from MAX(date)[:10] via latest_activity_at — handles both YYYY-MM-DD and YYYY-MM-DDThh:mm:ssZ stored values"
  - "full_resync_interval_seconds added to both RefreshSettings and RefreshPolicy; from_settings wires the value through so policy is the single knob at runtime"

metrics:
  duration: "~25 minutes"
  completed: "2026-06-10T12:18:52Z"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 7
  tests_added: 12
---

# Phase 260610-nk9 Plan 01: Incremental Strava Summary Sync Summary

Hourly SUMMARIES stage is now incremental: passes `&after=<epoch>` to Strava on normal runs (~1 API call), with an automatic weekly full resync as a safety net.

## What Was Built

- `sync_summaries` accepts `after_epoch: int | None` — appends `&after=N` to all `/athlete/activities` page URLs when set
- `run_once` SUMMARIES block: reads `last_full_summary_sync_at` marker, selects full vs. incremental via `refresh_interval_elapsed`, derives `after_epoch` from `latest_activity_at(repo)[:10]`
- `last_full_summary_sync_at VARCHAR` column on `refresh_state` — added to DDL for fresh DBs; `_ensure_column_last_full_summary_sync_at()` runs `ALTER TABLE ADD COLUMN IF NOT EXISTS` in `RefreshStateStore.from_connection` for live DBs
- `get_last_full_summary_sync_at` / `set_last_full_summary_sync_at` methods on `RefreshStateStore`
- `full_resync_interval_seconds: int = 604800` on both `RefreshSettings` and `RefreshPolicy`, parsed from `MCP_STRAVA_REFRESH_FULL_RESYNC_INTERVAL_SECONDS`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `date.fromisoformat` failed on full datetime string**
- **Found during:** Task 2 GREEN phase
- **Issue:** `latest_activity_at` returns `MAX(date)` — fixture stores dates as `"YYYY-MM-DDT..."` strings; `date.fromisoformat` requires exactly `"YYYY-MM-DD"`
- **Fix:** Added `[:10]` slice before `date.fromisoformat`
- **Files modified:** `src/mcp_strava/refresh/runtime.py`
- **Commit:** 7d4173a

**2. [Rule 1 - Bug] `test_run_once_skips_until_refresh_interval_then_re_runs` KeyError on incremental URL**
- **Found during:** Task 2 GREEN — existing test regression
- **Issue:** After first full run writes `last_full_summary_sync_at`, subsequent periodic run uses incremental path generating URL `/athlete/activities?per_page=100&page=1&after=N`. Test used `dict(transport.calls_by_path)["/athlete/activities?per_page=100&page=1"]` which raises `KeyError` when only the `&after=` variant is present
- **Fix:** Changed assertion to `sum(v for k,v in calls.items() if k.startswith("/athlete/activities"))` prefix-sum comparison
- **Files modified:** `tests/test_refresh_runtime.py`
- **Commit:** 7d4173a

**3. [Rule 1 - Bug] Worker test `SimpleNamespace` missing `full_resync_interval_seconds`**
- **Found during:** Task 2 GREEN — existing test regression
- **Issue:** Worker tests mock `settings.refresh` as `SimpleNamespace` without `full_resync_interval_seconds`; `RefreshPolicy.from_settings` now accesses this field
- **Fix:** Added `full_resync_interval_seconds=604800` to all three `SimpleNamespace` refresh settings in worker tests
- **Files modified:** `tests/test_refresh_runtime.py`
- **Commit:** 7d4173a

**4. [Chore] Ruff format + vulture**
- **Found during:** Task 3 quality gate
- **Issue:** 4 files needed reformatting; `lambda *a, **kw:` in test lambdas flagged as unused variables by vulture
- **Fix:** `just fix` for format; renamed to `*_a, **_kw` for vulture
- **Files modified:** `tests/test_incremental_summary_sync.py`, `src/mcp_strava/refresh/runtime.py`, `src/mcp_strava/refresh/_sync_ops.py`, `src/mcp_strava/adapters/duckdb/refresh_state_store.py`
- **Commit:** 611b293

## Known Stubs

None.

## Threat Flags

None. New surface is internal only (ALTER TABLE runs against own DB; `after_epoch` is derived from local activity data, not user input).

## Self-Check: PASSED

- `tests/test_incremental_summary_sync.py` — 12 tests, all pass
- `tests/test_refresh_runtime.py` — all pass (including regressions fixed)
- Commits: b68b783, 5c5a615, 7d4173a, 611b293
- `just verify` exits 0 — Docker container rebuilt, MCP smoke `status: ok`
