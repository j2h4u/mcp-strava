---
phase: 08-duckdb-primary-storage-aggregate-analytics-surface
plan: 08-03
subsystem: database
tags: [duckdb, repository, read-model, refresh, tdd]

requires:
  - phase: 08-duckdb-primary-storage-aggregate-analytics-surface/08-02
    provides: DuckDB schema, migration, and cutover file guarantees
  - phase: 07-materialized-metrics-read-model
    provides: transactional dirty queue and read-model materialization semantics
provides:
  - DuckDBRepository for runtime source, refresh, dirty queue, fact, lease, and query APIs
  - DuckDB read-model materializer with transactional fact writes and dirty-row clearing
  - Runtime routing from MCP_STRAVA_DB_PATH to DuckDB primary storage
  - Guard coverage preventing accidental runtime SQLite writes and generic raw SQL exposure
affects: [phase-08, duckdb-primary-storage, refresh-runtime, read-model, repository-boundary]

tech-stack:
  added: []
  patterns:
    - DuckDB repository parity with focused methods and no public raw SQL surface
    - Explicit SQLite compatibility only for rollback, migration, and fixture paths
    - Runtime refresh materialization imports DuckDB directly after cutover

key-files:
  created:
    - src/mcp_strava/adapters/duckdb/repository.py
    - src/mcp_strava/adapters/duckdb/read_model_materializer.py
    - tests/test_duckdb_repository.py
  modified:
    - src/mcp_strava/adapters/duckdb/__init__.py
    - src/mcp_strava/db.py
    - src/mcp_strava/settings.py
    - src/mcp_strava/sync.py
    - src/mcp_strava/refresh/_sync_ops.py
    - tests/test_read_model_materialization.py
    - tests/test_repository_boundary.py
    - tests/test_security_guards.py
    - tests/test_settings.py
    - tests/test_smoke.py

key-decisions:
  - DuckDBRepository is the primary runtime repository for DuckDB MCP_STRAVA_DB_PATH values.
  - Explicit SQLite paths remain reachable only as rollback, migration, and test-fixture compatibility.
  - Refresh materialization statically routes live DuckDB repositories to the DuckDB materializer.

patterns-established:
  - Repository factory methods choose storage by explicit database path or connection type.
  - DuckDB materialization clears dirty rows in the same successful transaction as fact writes and refresh-run audit records.
  - Security guards enforce static import boundaries while allowing dynamic SQLite compatibility for explicit non-runtime paths.

requirements-completed: [P8-SC-02, P8-D-ALL]

duration: 20min
completed: 2026-05-25
---

# Phase 08 Plan 03: DuckDB Primary Repository Summary

**DuckDB primary runtime repository with transactional read-model materialization and SQLite limited to explicit rollback compatibility paths**

## Performance

- **Duration:** 20 min
- **Started:** 2026-05-25T20:02:54Z
- **Completed:** 2026-05-25T20:23:13Z
- **Tasks:** 3
- **Files modified:** 13

## Accomplishments

- Added `DuckDBRepository` with source mirror writes, refresh leases, dirty queue, read-model fact APIs, query helpers, sync log, streams, zones, kudos, and refresh-request methods.
- Added DuckDB read-model materialization for activity, daily load, training model, and rolling-period facts, with rollback-on-failure and audit-run records.
- Routed runtime `DbConn`, repository factories, legacy sync wrappers, and refresh materialization to DuckDB primary storage while keeping `MCP_STRAVA_DB_PATH` as the single storage path setting.
- Pinned live/container runtime defaults to `/runtime/data/strava.duckdb`.
- Added static guards and targeted tests for runtime SQLite exclusion, no generic raw SQL repository surface, expected-mirror fail-closed opens, and DuckDB fact/materializer behavior.

## Task Commits

1. **Task 1: Add failing DuckDB repository and boundary tests** - `f839c0c` (test)
2. **Task 2: Implement DuckDBRepository API parity and materializer refit** - `594d95c` (feat)
3. **Task 3: Route runtime connection and compatibility paths to DuckDB primary** - `e79237a` (feat)
4. **Task 3 follow-up: Preserve SQLite rollback compatibility paths** - `b981bd7` (fix)

## Files Created/Modified

- `src/mcp_strava/adapters/duckdb/repository.py` - DuckDB repository API for runtime reads/writes, refresh state, source hashes, dirty queue, fact access, and sync helpers.
- `src/mcp_strava/adapters/duckdb/read_model_materializer.py` - DuckDB fact materializer with explicit transactions and dirty-row clearing.
- `src/mcp_strava/adapters/duckdb/__init__.py` - Exports DuckDB repository and materializer entrypoints.
- `src/mcp_strava/db.py` - Routes runtime DB connections and repository factories to DuckDB, with explicit SQLite compatibility for rollback/test paths.
- `src/mcp_strava/settings.py` - Defaults runtime/container storage to DuckDB while preserving `MCP_STRAVA_DB_PATH`.
- `src/mcp_strava/sync.py` - Uses DuckDBRepository and DuckDB preflight/count paths for legacy sync wrappers.
- `src/mcp_strava/refresh/_sync_ops.py` - Routes live DuckDB materialization to the DuckDB materializer and dynamically falls back only for explicit SQLite repositories.
- `tests/test_duckdb_repository.py` - DuckDB repository parity and boundary tests.
- `tests/test_read_model_materialization.py` - DuckDB materializer transaction, dirty queue, run audit, and idempotency coverage.
- `tests/test_repository_boundary.py` - Repository boundary and generic SQL exposure guards.
- `tests/test_security_guards.py` - Runtime SQLite import/write guards and live DuckDB routing checks.
- `tests/test_settings.py` - Canonical `/runtime/data/strava.duckdb` and storage-neutral path tests.
- `tests/test_smoke.py` - Default test settings updated for DuckDB primary storage.

## Decisions Made

- `MCP_STRAVA_DB_PATH` remains the only primary DB path setting; no `MCP_STRAVA_DUCKDB_PATH` or dual-primary bridge was added.
- Explicit `.db`, `.sqlite`, and `.sqlite3` paths are treated as SQLite compatibility paths for rollback, migration input, and historical fixtures only.
- Runtime refresh materialization imports the DuckDB materializer directly; the SQLite materializer is reached dynamically only when the repository object is not a DuckDBRepository.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Preserved explicit SQLite rollback/test compatibility**
- **Found during:** Full verification after Task 3
- **Issue:** Older fixtures and rollback paths that explicitly pass SQLite connections or `.db` paths were being opened or materialized as DuckDB, breaking full-suite compatibility.
- **Fix:** Added explicit SQLite path/connection detection in `db.py` and dynamic SQLite materializer fallback in `_sync_ops.py` while keeping live DuckDB materialization on the static DuckDB path.
- **Files modified:** `src/mcp_strava/db.py`, `src/mcp_strava/refresh/_sync_ops.py`, `tests/test_smoke.py`
- **Verification:** `uv run pytest -q tests/test_duckdb_repository.py tests/test_read_model_materialization.py tests/test_security_guards.py tests/test_repository_boundary.py tests/test_settings.py`; `uv run pytest -q`
- **Committed in:** `b981bd7`

---

**Total deviations:** 1 auto-fixed (Rule 3)
**Impact on plan:** Correctness-only compatibility fix. DuckDB remains the primary runtime storage path and SQLite remains limited to explicit rollback/migration/test-fixture use.

## Issues Encountered

- Full pytest initially failed on historical SQLite fixture paths after Task 3. The compatibility routing fix above resolved the failures without adding a permanent dual-primary write path.
- Requirement marking was attempted for `P8-SC-02` and `P8-D-ALL`; `gsd-sdk` reported both IDs were not present in `.planning/REQUIREMENTS.md`, so no requirement rows were mutated.

## Known Stubs

None. Stub-pattern scan found typed optional defaults and legitimate nullable fact fields only; no placeholder UI/runtime data source was introduced.

## TDD Gate Compliance

- RED gate: `f839c0c` added failing tests before implementation.
- GREEN gate: `594d95c` and `e79237a` implemented DuckDB repository, materializer, and runtime routing.
- Follow-up fix: `b981bd7` resolved full-suite compatibility failures discovered during verification.

## Verification

- `uv run pytest -q tests/test_duckdb_repository.py tests/test_read_model_materialization.py tests/test_security_guards.py tests/test_repository_boundary.py tests/test_settings.py` - `90 passed in 6.39s`
- `uv run pytest -q` - `290 passed, 1 skipped in 10.37s`

## Self-Check: PASSED

- Found summary file.
- Found DuckDB repository, DuckDB materializer, and DuckDB repository tests.
- Found task commits: `f839c0c`, `594d95c`, `e79237a`, `b981bd7`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for the next incomplete Phase 08 plan. Runtime repository access now uses DuckDB primary storage for DuckDB paths, and guard coverage blocks accidental runtime SQLite writes.

---
*Phase: 08-duckdb-primary-storage-aggregate-analytics-surface*
*Completed: 2026-05-25*
