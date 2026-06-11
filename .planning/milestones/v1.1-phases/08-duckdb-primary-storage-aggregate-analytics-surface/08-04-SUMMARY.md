---
phase: 08-duckdb-primary-storage-aggregate-analytics-surface
plan: 08-04
subsystem: deploy-refresh-runtime
tags: [duckdb, docker, healthcheck, refresh, tdd]
requires:
  - phase: 08-duckdb-primary-storage-aggregate-analytics-surface/08-03
    provides: DuckDBRepository runtime routing and DuckDB read-model materializer
  - phase: 08-duckdb-primary-storage-aggregate-analytics-surface/08-02
    provides: DuckDB schema and active refresh lease cutover gate
provides:
  - Single DuckDB owner-process Docker runtime topology
  - Owner/HTTP healthcheck path without live DuckDB read-write opens
  - DuckDB startup preflight with active refresh lease blocking
  - In-process refresh scheduling through storage-neutral repository factories
affects: [phase-08, docker-runtime, refresh-runtime, duckdb-primary-storage, healthcheck]
tech-stack:
  added: []
  patterns:
    - owner-process DuckDB runtime
    - healthcheck via owner-process state plus HTTP readiness
    - per-thread DuckDB connection policy for in-process refresh
key-files:
  created:
    - tests/test_duckdb_concurrency_guards.py
  modified:
    - deploy/Dockerfile
    - deploy/docker-compose.yml
    - src/mcp_strava/deploy/entrypoint.py
    - src/mcp_strava/deploy/healthcheck.py
    - src/mcp_strava/deploy/preflight.py
    - src/mcp_strava/deploy/service.py
    - src/mcp_strava/refresh/_sync_ops.py
    - src/mcp_strava/refresh/bootstrap.py
    - src/mcp_strava/refresh/runtime.py
    - src/mcp_strava/refresh/worker.py
    - tests/test_docker_runtime.py
    - tests/test_refresh_runtime.py
    - .planning/codebase/ARCHITECTURE.md
    - .planning/codebase/INTEGRATIONS.md
key-decisions:
  - "DuckDB container runtime uses one owner process with in-process refresh scheduling and per-thread DuckDB connections."
  - "Docker healthcheck validates owner-process state and HTTP readiness instead of opening the live DuckDB file."
  - "Standalone `refresh.worker` refuses live DuckDB container mode; refresh runs through the owner process."
patterns-established:
  - "Startup preflight may open the DuckDB file before ownership starts; healthcheck must not open the live DB."
  - "Refresh worker code uses `repository_from_connection` and `_sync_ops.materialize_read_model_stage` rather than SQLite-only imports."
requirements-completed: [P8-SC-02, P8-D-ALL]
duration: 9min
completed: 2026-05-25
---

# Phase 8 Plan 4: DuckDB Owner Runtime Summary

**DuckDB runtime now starts as one owner process with in-process refresh scheduling, offline startup preflight, and HTTP/owner health checks**

## Performance

- **Duration:** 9 min
- **Started:** 2026-05-25T20:34:01Z
- **Completed:** 2026-05-25T20:43:08Z
- **Tasks:** 3
- **Files modified:** 15

## Accomplishments

- Added RED coverage for DuckDB single-owner topology, healthcheck safety, active lease startup blocking, canonical Docker DB path, and refresh repository/materializer routing.
- Refit Docker service startup so DuckDB mode runs MCP HTTP plus refresh scheduling inside one owner process.
- Refit healthcheck to validate owner-process state and HTTP readiness without opening the live DuckDB file.
- Refit startup preflight to validate DuckDB structure and block active refresh leases before ownership begins.
- Refit refresh worker/bootstrap paths to use storage-neutral repository factories and the DuckDB-aware materialization stage.

## Task Commits

1. **Task 1: Add failing single-owner runtime and healthcheck tests** - `9c6264f` (`test`)
2. **Task 2: Implement owner-process service and healthcheck path** - `a635f21` (`feat`)
3. **Task 3: Refit refresh scheduling for owner-process DuckDB access** - `91dd033` (`feat`)

## Verification

- `uv run pytest -q tests/test_duckdb_concurrency_guards.py tests/test_refresh_runtime.py tests/test_docker_runtime.py tests/test_mcp_surface.py` - passed, 65 tests.
- `uv run pytest -q` - passed, 299 tests and 1 skipped.

## Files Created/Modified

- `tests/test_duckdb_concurrency_guards.py` - DuckDB owner-process, healthcheck, and standalone refresh worker guards.
- `src/mcp_strava/deploy/service.py` - Single owner-process DuckDB runtime with in-process refresh thread and owner state file.
- `src/mcp_strava/deploy/healthcheck.py` - Owner state and HTTP readiness healthcheck without live DB opens.
- `src/mcp_strava/deploy/preflight.py` - DuckDB startup validation, required table checks, read-model metadata, and active lease blocking.
- `src/mcp_strava/deploy/entrypoint.py` - Skips SQLite migration checks for DuckDB files and relies on startup preflight.
- `deploy/Dockerfile` and `deploy/docker-compose.yml` - Canonical `/runtime/data/strava.duckdb` runtime DB path.
- `src/mcp_strava/refresh/bootstrap.py` and `src/mcp_strava/refresh/worker.py` - Storage-neutral repository access for refresh failure recording and worker scheduling.
- `src/mcp_strava/refresh/_sync_ops.py` and `src/mcp_strava/refresh/runtime.py` - DuckDB materialization routing and limit-aware materialization stage calls.
- `tests/test_refresh_runtime.py` and `tests/test_docker_runtime.py` - Updated refresh and Docker runtime contracts.
- `.planning/codebase/ARCHITECTURE.md` and `.planning/codebase/INTEGRATIONS.md` - Updated structural runtime map for DuckDB owner-process health and storage.

## Decisions Made

- DuckDB runtime ownership belongs to the deploy service process; refresh runs as an in-process scheduler instead of a separate read-write child process.
- Healthcheck is an owner/HTTP probe only. Direct DuckDB file validation remains an offline startup preflight concern.
- Refresh worker standalone mode is rejected for live DuckDB container/runtime profiles to avoid a second write owner.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- One new RED test initially omitted the DuckDB path environment when asserting owner state; it was corrected before the Task 2 commit.
- Existing worker tests still patched the old `run_preflight` symbol after refresh scheduling moved to `ensure_runtime_refresh_schema`; tests were updated to the new storage-neutral boundary.
- Requirement marking reported `P8-SC-02` and `P8-D-ALL` as not present in `.planning/REQUIREMENTS.md`, matching prior Phase 08 plan behavior; no requirement rows were changed.

## Known Stubs

None. Stub scan found only typed optional defaults and empty test fixture containers, not runtime placeholders or unwired data sources.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for later Phase 08 aggregate query and MCP surface work. Docker/runtime defaults now point at DuckDB primary, and refresh remains automatic below MCP without sync/admin/debug tool exposure.

## TDD Gate Compliance

- RED gate: `9c6264f` added failing single-owner/runtime tests before implementation.
- GREEN gate: `a635f21` and `91dd033` implemented owner-process startup and refresh scheduling until targeted and full tests passed.
- Refactor gate: not needed; no behavior-neutral cleanup commit was made.

## Self-Check: PASSED

- Summary file exists.
- Created guard test file exists.
- Task commits are present in git history: `9c6264f`, `a635f21`, `91dd033`.
- Verification commands passed after final task commit.

---
*Phase: 08-duckdb-primary-storage-aggregate-analytics-surface*
*Completed: 2026-05-25*
