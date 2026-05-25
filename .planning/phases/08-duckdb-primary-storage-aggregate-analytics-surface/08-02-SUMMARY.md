---
phase: 08-duckdb-primary-storage-aggregate-analytics-surface
plan: 08-02
subsystem: database
tags: [duckdb, sqlite, migration, backup, admin-cli, parity]
requires:
  - phase: 08-duckdb-primary-storage-aggregate-analytics-surface
    provides: DuckDB dependency baseline from 08-01
provides:
  - Typed DuckDB schema inventory for source mirror and read-model fact tables
  - One-shot SQLite backup-to-DuckDB cutover migration with parity and cast checks
  - Admin-only `duckdb-cutover` CLI command
affects: [phase-08-03, phase-08-04, phase-08-08, storage-runtime, deploy-preflight]
tech-stack:
  added: []
  patterns:
    - temp DuckDB migration target promoted only after parity success
    - migration-only SQLite extension attach
    - structured cutover report with rollback metadata
key-files:
  created:
    - src/mcp_strava/adapters/duckdb/__init__.py
    - src/mcp_strava/adapters/duckdb/connection.py
    - src/mcp_strava/adapters/duckdb/schema.py
    - src/mcp_strava/adapters/duckdb/migrations.py
    - tests/test_duckdb_migration.py
  modified:
    - src/mcp_strava/adapters/sqlite/backup.py
    - src/mcp_strava/cli.py
    - tests/test_cli_surface.py
    - tests/test_repository_boundary.py
    - tests/test_security_guards.py
key-decisions:
  - "Use `admin duckdb-cutover` as the local admin storage migration command."
  - "Create the final DuckDB runtime file only after backup, lease, cast, and parity gates pass."
  - "Allow direct SQLite access outside the SQLite adapter only in the migration-only DuckDB cutover module."
patterns-established:
  - "Pre-Phase-8 backups use `strava-pre-phase-8-*.db` and are pinned outside ordinary retention."
  - "DuckDB migration reports expose counts, cast failures, refresh lease state, and rollback paths without raw payloads or Strava calls."
requirements-completed: [P8-SC-01, P8-SC-02, P8-D-ALL]
duration: 12 min
completed: 2026-05-25
---

# Phase 08 Plan 02: DuckDB Migration Foundation Summary

**One-shot SQLite backup-to-DuckDB cutover with typed tables, parity checks, active-lease blocking, and admin-only CLI control**

## Performance

- **Duration:** 12 min
- **Started:** 2026-05-25T16:36:00Z
- **Completed:** 2026-05-25T16:48:47Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments

- Added RED/GREEN coverage for temp-only DuckDB migration fixtures, row-count parity, DATE casts, active refresh lease blocking, pre-Phase-8 pinned backups, and local-admin CLI exposure.
- Created the DuckDB adapter package with fail-closed expected DB opens, typed physical tables for D-08 entities, migration-only SQLite extension attach, cast-failure reporting, and structured rollback metadata.
- Wired `admin duckdb-cutover` as an admin-only command with explicit path arguments and live-target confirmation, while keeping migration controls out of product and MCP surfaces.

## Task Commits

1. **Task 1: Add failing DuckDB migration and cutover command tests** - `cfe8a6d` (`test`)
2. **Task 2: Implement typed DuckDB schema and one-shot migration** - `7df1f7d` (`feat`)
3. **Task 3: Wire local admin cutover command** - `4f6dad5` (`feat`)
4. **Auto-fix: satisfy full-suite guard tests** - `76dd93a` (`fix`)

## Verification

- `uv run pytest -q tests/test_duckdb_migration.py tests/test_cli_surface.py` - RED failed as expected before implementation: 9 failed, 16 passed.
- `uv run pytest -q tests/test_duckdb_migration.py` - passed, 6 tests.
- `uv run pytest -q tests/test_duckdb_migration.py tests/test_cli_surface.py tests/test_mcp_surface.py` - passed, 31 tests.
- `uv run pytest -q tests/test_docker_runtime.py::test_runtime_path_references_stay_in_deploy_surface tests/test_repository_boundary.py::test_ast_guard_blocks_direct_sqlite_outside_allowlist tests/test_security_guards.py::test_direct_sqlite_access_stays_inside_allowed_boundaries` - passed, 3 tests.
- `uv run pytest -q` - passed, 272 passed, 1 skipped.

## Files Created/Modified

- `tests/test_duckdb_migration.py` - Temp-fixture migration, cast, lease, backup, rollback, and canonical path coverage.
- `src/mcp_strava/adapters/duckdb/__init__.py` - DuckDB adapter exports.
- `src/mcp_strava/adapters/duckdb/connection.py` - Fail-closed expected DuckDB open and fixture open helper.
- `src/mcp_strava/adapters/duckdb/schema.py` - Physical DuckDB D-08 table inventory with DATE day columns.
- `src/mcp_strava/adapters/duckdb/migrations.py` - Pinned-backup cutover, SQLite extension check, controlled date casts, parity report, and rollback metadata.
- `src/mcp_strava/adapters/sqlite/backup.py` - Pre-Phase-8 pinned backup support and generalized pinned retention.
- `src/mcp_strava/cli.py` - `admin duckdb-cutover` command.
- `tests/test_cli_surface.py` - Admin-only cutover command and no-MCP/product exposure tests.
- `tests/test_repository_boundary.py` - Exact migration-only direct SQLite boundary allowance.
- `tests/test_security_guards.py` - Matching security guard allowance for the DuckDB migration module.

## Decisions Made

- Chose `admin duckdb-cutover` over `admin storage-migrate-duckdb` to keep the command short and aligned with the plan’s `run_duckdb_cutover` naming.
- Used a temporary DuckDB file and atomic replace so the final target path is not created on active lease, cast failure, or parity failure.
- Kept direct `sqlite3` reads restricted to migration-only lease/count checks and backup parity reporting; all runtime paths remain behind repositories.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Regression] Full-suite boundary guards needed exact DuckDB migration allowances**
- **Found during:** Plan-level full pytest.
- **Issue:** New migration-only SQLite reads correctly belonged outside the SQLite adapter, but existing repository/security AST guards flagged all direct `sqlite3.connect` calls outside `adapters/sqlite/`.
- **Fix:** Added an exact allowlist for `src/mcp_strava/adapters/duckdb/migrations.py` only, preserving the guard for all other runtime paths.
- **Files modified:** `tests/test_repository_boundary.py`, `tests/test_security_guards.py`
- **Verification:** Targeted guard tests and full `uv run pytest -q` passed.
- **Committed in:** `76dd93a`

**2. [Rule 1 - Regression] CLI embedded a deploy host path literal outside deploy code**
- **Found during:** Plan-level full pytest.
- **Issue:** The live-target guard in `cli.py` included `/opt/docker/mcp-strava`, which violated the existing deploy-surface path-literal guard.
- **Fix:** Restricted CLI live-target detection to `/runtime/` paths and the canonical `/runtime/data/strava.duckdb` target.
- **Files modified:** `src/mcp_strava/cli.py`
- **Verification:** `test_runtime_path_references_stay_in_deploy_surface` and full `uv run pytest -q` passed.
- **Committed in:** `76dd93a`

---

**Total deviations:** 2 auto-fixed regressions.
**Impact on plan:** Both fixes tightened existing safety boundaries without expanding runtime or MCP scope.

## Issues Encountered

Initial full-suite verification failed on existing safety guards after the planned migration module was added. The failures were fixed with exact allowlists and removal of the host deployment path from CLI code.

## Known Stubs

None. Stub scan findings were test-only fixture placeholders or empty fixture containers and do not flow to runtime output.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for Plan 08-03. DuckDB schema and migration foundation exist, but runtime repository, refresh, deploy preflight, and Docker paths are still handled by later plans before live cutover.

## Self-Check: PASSED

- Created files exist.
- Task commits are present in git history: `cfe8a6d`, `7df1f7d`, `4f6dad5`, `76dd93a`.
- Verification commands passed after final commits.

---
*Phase: 08-duckdb-primary-storage-aggregate-analytics-surface*
*Completed: 2026-05-25*
