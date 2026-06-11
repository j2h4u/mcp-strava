---
phase: 16-duckdb-native-storage-cleanup
plan: "02"
subsystem: duckdb-adapter
tags: [duckdb, schema, kudos, date-column, rename, fixture-cleanup]

requires:
  - phase: 16-duckdb-native-storage-cleanup
    plan: "01"
    provides: xfail window_days regression guard

provides:
  - activities table without date VARCHAR column
  - kudos_store window_days branch using native DuckDB INTERVAL arithmetic
  - RepositoryActivityRow.activity_day (renamed from .date)
  - all a.date SQL references migrated to a.activity_day
  - test_activities_missing_kudos_with_window_days passing without xfail

affects:
  - 16-03 and beyond (schema is now cleaner; no date VARCHAR dead weight)

tech-stack:
  added: []
  patterns:
    - "CURRENT_DATE - (? * INTERVAL '1 day') with plain int param for DuckDB window filter"
    - "a.activity_day AS activity_date alias preserves byte-identical MCP payload key"
    - "str(datetime.date) == 'YYYY-MM-DD' — same format as old date VARCHAR"

key-files:
  created: []
  modified:
    - src/mcp_strava/adapters/duckdb/schema_tables.py
    - src/mcp_strava/adapters/duckdb/repository.py
    - src/mcp_strava/adapters/duckdb/kudos_store.py
    - src/mcp_strava/adapters/duckdb/activity_lookup_queries.py
    - src/mcp_strava/adapters/duckdb/activity_selectors.py
    - src/mcp_strava/adapters/duckdb/stream_coverage_queries.py
    - src/mcp_strava/adapters/duckdb/read_model_repository.py
    - src/mcp_strava/adapters/duckdb/read_model_source_repository.py
    - src/mcp_strava/types_repository.py
    - src/mcp_strava/adapters/duckdb/activity_rows.py
    - tests/test_duckdb_repository.py
    - tests/test_application_services.py
    - tests/_fixtures_duckdb.py
    - tests/test_phase4_e2e.py
    - tests/test_read_model_queries.py
    - tests/test_hr_zones.py
    - tests/test_training_aggregates.py
    - tests/test_load_status.py
    - tests/test_metric_services.py

key-decisions:
  - "projection_services.py row.date left unchanged — that is SimDay.date, not RepositoryActivityRow.date"
  - "last_activity_at now returns YYYY-MM-DD (from DATE column) not YYYY-MM-DDTHH:MM:SS — test assertions updated accordingly"
  - "read_model_source_repository.py was not in plan file_list but contained a stale date column SELECT — fixed as Rule 1"

duration: 12 min
completed: 2026-06-11
status: complete
---

# Phase 16 Plan 02: Drop date VARCHAR and Activate kudos Window Filter Summary

**Remove `activities.date VARCHAR` (SQLite dead weight), rewrite kudos `window_days` branch to native DuckDB `CURRENT_DATE - INTERVAL` arithmetic, rename `RepositoryActivityRow.date` → `activity_day`; xfail test from 16-01 now passes.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-11T09:57:04Z
- **Completed:** 2026-06-11T10:09:00Z
- **Tasks:** 3 (+ Rule 1 auto-fixes in 6 additional files)
- **Files modified:** 19

## Accomplishments

### Task 1 — Drop date column from schema DDL and upsert_activity_summary (commit `71e6ee5`)
- Removed `date VARCHAR,` from `DUCKDB_SCHEMA_SQL` activities DDL
- Removed `date` from `upsert_activity_summary` INSERT column list and VALUES binding
- Removed `date=excluded.date` from ON CONFLICT UPDATE SET
- Method signature param `date: str` stays (still used to compute `activity_day` via `date[:10]`)

### Task 2 — Replace all a.date SQL references and rewrite kudos window_days (commit `6009ff0`)
- `kudos_store.py`: `date('now', ?)` → `CURRENT_DATE - (? * INTERVAL '1 day')` with plain int param; `ORDER BY a.date DESC` → `ORDER BY a.activity_day DESC`
- `activity_lookup_queries.py`: three SELECTs use `activity_day`; `MAX(date)` → `MAX(activity_day)` in `latest_activity_at`
- `activity_selectors.py`: both `activities_missing_streams` and `activities_missing_details` SELECT lists and GROUP BY updated
- `stream_coverage_queries.py`: `SELECT a.id, a.date` → `SELECT a.id` (date was unused downstream)
- `read_model_repository.py`: `a.date AS activity_date` → `a.activity_day AS activity_date` at both alias sites

### Task 3 — Rename RepositoryActivityRow.date → activity_day, remove xfail (commit `66b01e9`)
- `types_repository.py`: `RepositoryActivityRow.date: str` → `activity_day: str`
- `activity_rows.py`: `date=str(row["date"])` → `activity_day=str(row["activity_day"])`
- `test_duckdb_repository.py`: removed `@pytest.mark.xfail` decorator — `test_activities_missing_kudos_with_window_days` passes cleanly
- All 8 test fixture files updated (date param removed from INSERT INTO activities)
- `test_application_services.py`: `last_activity_at` assertions updated to `"YYYY-MM-DD"` format (now DATE not datetime string)

## Task Commits

1. **Task 1: Drop date VARCHAR from schema DDL and upsert** - `71e6ee5`
2. **Task 2: Replace all a.date SQL refs, rewrite kudos window_days** - `6009ff0`
3. **Task 3: Rename RepositoryActivityRow.date, fix callers, remove xfail** - `66b01e9`

## Files Created/Modified

**Source:**
- `src/mcp_strava/adapters/duckdb/schema_tables.py` — DDL without date VARCHAR
- `src/mcp_strava/adapters/duckdb/repository.py` — upsert_activity_summary clean
- `src/mcp_strava/adapters/duckdb/kudos_store.py` — native DuckDB INTERVAL window
- `src/mcp_strava/adapters/duckdb/activity_lookup_queries.py` — activity_day everywhere
- `src/mcp_strava/adapters/duckdb/activity_selectors.py` — activity_day everywhere
- `src/mcp_strava/adapters/duckdb/stream_coverage_queries.py` — SELECT a.id only
- `src/mcp_strava/adapters/duckdb/read_model_repository.py` — activity_day AS activity_date
- `src/mcp_strava/adapters/duckdb/read_model_source_repository.py` — stale date col removed [Rule 1]
- `src/mcp_strava/types_repository.py` — RepositoryActivityRow.activity_day
- `src/mcp_strava/adapters/duckdb/activity_rows.py` — mapper updated

**Tests:**
- `tests/test_duckdb_repository.py` — xfail removed
- `tests/test_application_services.py` — MAX(activity_day), last_activity_at date assertions
- `tests/_fixtures_duckdb.py` — date param removed from fixture INSERT
- `tests/test_phase4_e2e.py` — date param + last_activity_at assertion
- `tests/test_read_model_queries.py` — fixture INSERT
- `tests/test_hr_zones.py` — fixture INSERT (single-line form)
- `tests/test_training_aggregates.py` — fixture INSERT
- `tests/test_load_status.py` — fixture INSERT
- `tests/test_metric_services.py` — fixture INSERT

## Decisions Made

- `projection_services.py` line 197 `row.date` left unchanged — this is `SimDay.date` (training simulation dataclass), not `RepositoryActivityRow.date`; they are different types
- `last_activity_at` return value changed from `"YYYY-MM-DDTHH:MM:SS"` (was pulling from `date VARCHAR` which stored datetime) to `"YYYY-MM-DD"` (DATE column). MCP payload key `activity_date` is unaffected (uses separate alias)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] read_model_source_repository.py not in plan file list but contained stale date column SELECT**
- **Found during:** Task 3 first test run (BinderException: column "date" not found)
- **Issue:** `_read_activity_source_components` selected `id, activity_day, date, name, ...` — date column removed from schema in Task 1
- **Fix:** Changed SELECT to `id, activity_day, name, ...`
- **Files modified:** `src/mcp_strava/adapters/duckdb/read_model_source_repository.py`
- **Commit:** `66b01e9`

**2. [Rule 1 - Bug] 8 test fixture files used raw INSERT with date column**
- **Found during:** Task 3 full test run
- **Issue:** Direct SQL `INSERT INTO activities (id, activity_day, date, ...)` in fixtures across `test_application_services.py`, `_fixtures_duckdb.py`, `test_phase4_e2e.py`, `test_read_model_queries.py`, `test_hr_zones.py`, `test_training_aggregates.py`, `test_load_status.py`, `test_metric_services.py`
- **Fix:** Removed `date` from INSERT column list and corresponding param from VALUES in each file
- **Commit:** `66b01e9`

**3. [Rule 1 - Bug] test_application_services.py asserted last_activity_at as datetime string**
- **Found during:** Task 3 after fixture fixes
- **Issue:** Test expected `"2026-05-18T07:00:00"` / `"2026-05-21T07:00:00"` — old `date VARCHAR` values. Now `latest_activity_at` returns `str(datetime.date)` = `"YYYY-MM-DD"`
- **Fix:** Updated assertions to `"2026-05-18"` / `"2026-05-21"` and adjusted `last_activity_age_seconds` accordingly (266400 → 291600: 7h difference = T07:00:00 vs midnight)
- **Files modified:** `tests/test_application_services.py`, `tests/test_phase4_e2e.py`
- **Commit:** `66b01e9`

---

**Total deviations:** 3 auto-fixed (Rule 1 — stale column refs in files not listed in plan)

## Known Stubs

None. All data flows are fully wired.

## Threat Flags

None. No new external surface introduced; internal DDL cleanup only.

## Self-Check: PASSED
