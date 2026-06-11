---
phase: 16-duckdb-native-storage-cleanup
plan: "03"
subsystem: duckdb-adapter
tags: [duckdb, schema, refresh-requests, date-column, type-annotation]

requires:
  - phase: 16-duckdb-native-storage-cleanup
    plan: "02"
    provides: activities.date VARCHAR removed; activity_day DATE in place

provides:
  - refresh_requests.requested_for_day as native DATE column in DDL
  - enqueue_refresh_request accepting datetime.date parameter
  - both callers passing datetime.date (not ISO strings)
  - pending_refresh_requests returning "YYYY-MM-DD" string via str(datetime.date)

affects:
  - 16-04 and beyond (refresh_requests table now fully native-typed)

tech-stack:
  added: []
  patterns:
    - "import datetime at module level + from datetime import date,datetime for conflict-free named imports"
    - "fromisoformat guard in enqueue_refresh_request_if_stale for str callers"
    - "today_date = now.date() separate binding alongside today str for _refreshed_today"
    - "str(datetime.date) == 'YYYY-MM-DD' preserves RefreshRequestRow.requested_for_day: str contract"

key-files:
  created: []
  modified:
    - src/mcp_strava/adapters/duckdb/schema_tables.py
    - src/mcp_strava/adapters/duckdb/refresh_state_store.py
    - src/mcp_strava/refresh/freshness.py
    - src/mcp_strava/application/freshness.py

key-decisions:
  - "pending_refresh_requests str(row['requested_for_day']) left unchanged — DuckDB returns datetime.date from DATE column; str() yields identical YYYY-MM-DD preserving RefreshRequestRow contract"
  - "freshness.py uses from datetime import date,datetime (named imports) not import datetime module — avoids F811 name-shadowing ruff error"
  - "today str kept in application/freshness.py for _refreshed_today comparison; today_date introduced as separate binding for enqueue call"

duration: 2 min
completed: 2026-06-11
status: complete
---

# Phase 16 Plan 03: Convert refresh_requests.requested_for_day to Native DATE Summary

**Convert `refresh_requests.requested_for_day` from VARCHAR to native DATE; update `enqueue_refresh_request` signature and both callers to pass `datetime.date` objects directly.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-06-11T09:12:57Z
- **Completed:** 2026-06-11T09:15:03Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

### Task 1 — Change DDL and enqueue_refresh_request to native DATE (commit `92b6e71`)

- `schema_tables.py`: `requested_for_day VARCHAR NOT NULL` → `requested_for_day DATE NOT NULL` in `refresh_requests` DDL
- `refresh_state_store.py`: added `import datetime`; `enqueue_refresh_request` parameter type `str` → `datetime.date`
- `pending_refresh_requests()` body unchanged — `str(row["requested_for_day"])` now receives `datetime.date` from DuckDB and produces identical `"YYYY-MM-DD"` output

### Task 2 — Update callers to pass datetime.date objects (commit `d1cf79a`)

- `refresh/freshness.py`: replaced `import datetime` + `from datetime import datetime` (F811 conflict) with `from datetime import date, datetime`; updated `enqueue_refresh_request_if_stale` parameter to `date | str | None` with `fromisoformat` guard for string callers; passes `now.date()` directly
- `application/freshness.py`: introduced `today_date = now.date()` for the enqueue call; `today` string variable retained for `_refreshed_today` string comparison
- `refresh_state_store.py`: ruff format fix for long method signature line (auto-fix)

## Task Commits

1. **Task 1: Change DDL and enqueue_refresh_request to native DATE** — `92b6e71`
2. **Task 2: Update callers to pass datetime.date** — `d1cf79a`

## Files Created/Modified

- `src/mcp_strava/adapters/duckdb/schema_tables.py` — DDL with DATE column
- `src/mcp_strava/adapters/duckdb/refresh_state_store.py` — datetime.date param + ruff format
- `src/mcp_strava/refresh/freshness.py` — named date import, fromisoformat guard
- `src/mcp_strava/application/freshness.py` — today_date binding for enqueue

## Decisions Made

- `str(row["requested_for_day"])` in `pending_refresh_requests` unchanged — DuckDB returns `datetime.date` from a DATE column, and `str(datetime.date(2026, 6, 11))` == `"2026-06-11"`, preserving the `RefreshRequestRow.requested_for_day: str` contract byte-for-byte (confirmed in RESEARCH.md)
- Named imports (`from datetime import date, datetime`) preferred over module alias (`import datetime`) to avoid the ruff F811 shadowing error that arises when both the module and the class share the same name
- `today` string in `application/freshness.py` is needed by `_refreshed_today(state.last_success_at, today)` — a separate `today_date` binding introduced rather than converting `today` to avoid touching unrelated logic

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ruff F811 name-shadowing: `import datetime` conflicted with `from datetime import datetime`**
- **Found during:** Task 2 `just check` run
- **Issue:** `freshness.py` had both `import datetime` (module) and `from datetime import datetime` (class) — ruff F811 redefinition error
- **Fix:** Collapsed to `from datetime import date, datetime`; updated all `datetime.date` references to bare `date`
- **Files modified:** `src/mcp_strava/refresh/freshness.py`
- **Commit:** `d1cf79a`

**2. [Rule 1 - Bug] ruff format: refresh_state_store.py long signature line**
- **Found during:** Task 2 `just check` run (after Task 1 commit)
- **Issue:** Long `enqueue_refresh_request` signature needed formatter pass
- **Fix:** `uv run ruff format src/mcp_strava/adapters/duckdb/refresh_state_store.py`
- **Files modified:** `src/mcp_strava/adapters/duckdb/refresh_state_store.py`
- **Commit:** `d1cf79a`

## Known Stubs

None. All data flows fully wired.

## Threat Flags

None. Internal DDL type upgrade only; no new external surface.

## Self-Check: PASSED
