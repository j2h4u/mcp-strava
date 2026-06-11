---
phase: 12-decouple-db-py-into-focused-modules
plan: "03"
subsystem: application/refresh/sync
tags: [migration, db-decoupling, connection-management, repository-factory]
dependency_graph:
  requires: ["12-01", "12-02"]
  provides: ["12-04", "12-05"]
  affects: ["application/*", "refresh/worker", "refresh/bootstrap", "sync"]
tech_stack:
  added: []
  patterns:
    - "DuckDBRepository.from_connection() direct factory replaces repository_from_connection() indirection (D-04)"
    - "MirrorConn replaces DbConn in all non-CLI callers (D-03)"
    - "RealClock/RealSleeper backward-compat aliases in bootstrap.py until cli.py migrates in 12-04"
    - "_build_strava_transport shared helper; bootstrap no longer duplicates token-file parsing (D-05/D-06)"
key_files:
  created: []
  modified:
    - src/mcp_strava/application/aggregate_services.py
    - src/mcp_strava/application/metric_services.py
    - src/mcp_strava/application/product_facts.py
    - src/mcp_strava/application/freshness.py
    - src/mcp_strava/application/mirror_coverage.py
    - src/mcp_strava/sync.py
    - src/mcp_strava/refresh/bootstrap.py
    - src/mcp_strava/refresh/worker.py
    - tests/conftest.py
    - tests/test_metric_services.py
    - tests/test_refresh_runtime.py
    - tests/test_application_services.py
    - tests/test_security_guards.py
decisions:
  - "MirrorConn (not DbConn alias) used in all application/refresh/sync callers — consistent with D-03 rename"
  - "bootstrap.py uses _build_strava_transport shared helper to eliminate duplicate token-wiring chain"
  - "RealClock = SystemClock / RealSleeper = SystemSleeper aliases kept in bootstrap until cli.py migrates"
  - "B904 pre-existing ruff error in worker __main__ fixed as Rule 2 since file was being touched"
metrics:
  duration_minutes: 8
  completed_date: "2026-05-30"
  tasks_completed: 4
  files_modified: 13
---

# Phase 12 Plan 03: Application/Refresh/Sync db.py Migration Summary

Migrated all application/*, refresh/*, and sync.py callers off mcp_strava.db onto the adapter homes established in 12-01/12-02. Concrete: ReadConn/MirrorConn imported from adapters.duckdb.connection, repository_from_connection() calls replaced with DuckDBRepository.from_connection(), bootstrap duplicate token parser removed.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Repoint application/* imports (D-04) | 1a90c8e | 5 application modules |
| 2 | Migrate sync.py + worker.py + bootstrap.py (D-04/D-05/D-06) | 246e5ef | sync.py, worker.py, bootstrap.py |
| 3 | Test monkeypatch retargeting | 6282eb1 | conftest.py + 4 test files |
| 4 | Suite validation + ruff cleanup | 398c21e | 5 files (import sort, B904) |

## Verification

- 329 tests passed (full suite)
- ruff: clean on all modified files
- pyright: 136 pre-existing errors unchanged (same count before and after)
- No db.py imports remain in application/*, refresh/*, or sync.py

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Python 2 bare except syntax in metric_services.py**
- **Found during:** Task 1
- **Issue:** `except TypeError, ValueError:` on lines 167 and 262 — Python 2 syntax, would cause SyntaxError at import
- **Fix:** Changed to `except (TypeError, ValueError):`
- **Files modified:** src/mcp_strava/application/metric_services.py
- **Commit:** 1a90c8e

**2. [Rule 2 - Missing correctness] Fixed pre-existing B904 in worker.py __main__ block**
- **Found during:** Task 4 ruff check
- **Issue:** `raise SystemExit(130)` inside `except KeyboardInterrupt` missing `from None`
- **Fix:** Changed to `raise SystemExit(130) from None`
- **Files modified:** src/mcp_strava/refresh/worker.py
- **Commit:** 398c21e

## Known Stubs

None — all production imports are wired to real adapter implementations.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced. Behavioral migration only.

## Self-Check: PASSED
- All 13 modified files committed
- Commits 1a90c8e, 246e5ef, 6282eb1, 398c21e verified in git log
- No db.py imports in application/*, refresh/*, sync.py (grep confirmed)
- 329 tests green
