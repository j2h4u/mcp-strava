---
phase: 12-decouple-db-py-into-focused-modules
plan: "04"
subsystem: cli-migration
tags: [db-decoupling, cli, tests, security-guards]
dependency_graph:
  requires: ["12-03"]
  provides: ["12-05"]
  affects: [cli, tests]
tech_stack:
  added: []
  patterns: [module-facade, direct-repository-factory]
key_files:
  modified:
    - src/mcp_strava/cli.py
    - src/mcp_strava/refresh/bootstrap.py
    - src/mcp_strava/sync.py
    - tests/test_cli_surface.py
    - tests/test_repository_boundary.py
    - tests/test_smoke.py
    - tests/test_phase01_validation.py
    - tests/test_security_guards.py
decisions:
  - "RealClock/RealSleeper wave-3 compat aliases removed from bootstrap and sync once cli.py migrated to SystemClock/SystemSleeper"
  - "StravaClient.api_request/refresh_token used directly in cli.py (D-08) — no token= param"
  - "init_db DDL guard helper removed; test retargeted/removed since init_db deleted in 12-05"
metrics:
  duration: "9 min"
  completed: "2026-05-30"
  tasks: 3
  files: 8
---

# Phase 12 Plan 04: cli.py + test migration to new module homes Summary

Migrated the last consumers of `mcp_strava.db` in cli.py and the test suite. After this plan, nothing outside of `db.py` itself imports `mcp_strava.db`, clearing the path for deletion in 12-05.

## What Was Built

**Task 1 — cli.py migration + alias cleanup:**
- Replaced `from mcp_strava.db import DbConn, refresh_token, repository_from_connection, repository_from_path` with `MirrorConn` (adapters/duckdb/connection), `DuckDBRepository` (adapters/duckdb/repository), `StravaClient` (adapters/strava/client), `SystemClock/SystemSleeper` (adapters/strava/clock).
- `cmd_refresh` now calls `StravaClient().refresh_token()` (D-08).
- `cmd_strava_raw` now calls `StravaClient().api_request(path)` — no token= param (GP-02).
- `cmd_catchup` dry/live paths use `MirrorConn` + `DuckDBRepository.from_connection/from_path`.
- `cmd_sql`, `cmd_log` use `MirrorConn`.
- `cmd_mirror_coverage` uses `DuckDBRepository.from_path`.
- Removed `RealClock`/`RealSleeper` aliases from `bootstrap.py` (wave-3 compat no longer needed).
- Removed `RealClock`/`RealSleeper` from `sync.py` imports, re-exports, and `__all__`.

**Task 2 — CLI-scoped test monkeypatch retargets:**
- `test_cli_surface.py`: `cli.api_request` guard (raising=False) → `cli.StravaClient` (no raising=False); `cli.DbConn` → `cli.MirrorConn` (no raising=False).
- `test_repository_boundary.py`: `legacy_db.api_request/refresh_token` → `StravaClient.api_request/.refresh_token` on concrete class so the "repository must never touch Strava" invariant cannot pass vacuously; `DbConn`→`MirrorConn` + `repository_from_connection`→`DuckDBRepository.from_connection`.
- `test_smoke.py` and `test_phase01_validation.py`: `from mcp_strava.db import DbConn` → `from mcp_strava.adapters.duckdb.connection import MirrorConn`.

**Task 3 — Security guard literals + init_db guard removal:**
- Negative-import set literals updated from `mcp_strava.db.api_request`/`refresh_token` to `mcp_strava.adapters.strava.client.StravaClient`/`.api_request`.
- `test_metric_services` guard tuple updated from `mcp_strava.db.*` prefixes to `mcp_strava.adapters.strava.client`.
- Removed `_assert_no_schema_ddl_in_init_db` helper (references `db.py:init_db` which is deleted in 12-05).
- Removed `test_sync_never_calls_init_db_and_db_init_db_has_no_ddl` test (references dead symbol).

## Verification

Full suite: **328 passed** (0 failures, 0 errors).

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced.

## Self-Check: PASSED

- `src/mcp_strava/cli.py` — no `mcp_strava.db` import remains
- `src/mcp_strava/refresh/bootstrap.py` — RealClock/RealSleeper aliases removed
- `src/mcp_strava/sync.py` — RealClock/RealSleeper removed from imports/__all__
- Commits: 411bd81, 52a58b7, 006c5b4
- 328 tests passed
