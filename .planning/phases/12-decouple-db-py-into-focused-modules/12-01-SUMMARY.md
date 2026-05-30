---
phase: 12-decouple-db-py-into-focused-modules
plan: "01"
subsystem: adapters/duckdb
tags: [duckdb, connection, refactor, additive]
dependency_graph:
  requires: []
  provides: [MirrorConn, ReadConn, reset_thread_connections, _db_path in adapters/duckdb/connection]
  affects: []
tech_stack:
  added: []
  patterns: [thread-local read-connection pool, context-manager connection lifetime]
key_files:
  created: []
  modified:
    - src/mcp_strava/adapters/duckdb/connection.py
decisions:
  - "MirrorConn opens via open_expected_mirror_db(_db_path()) — collapses the _open_storage_connection indirection from db.py since it was a one-liner alias"
  - "The dict[str, object] pyright error on reset_thread_connections is pre-existing (mirrors db.py L91); not introduced by this plan"
  - "init_db NOT relocated — dead code (RI-03), deleted with db.py in 12-05"
metrics:
  duration: 6 min
  completed: "2026-05-30"
  tasks_completed: 2
  files_modified: 1
---

# Phase 12 Plan 01: Add MirrorConn/ReadConn/thread-pool to adapters/duckdb/connection Summary

**One-liner:** DuckDB connection-lifetime helpers (MirrorConn, ReadConn, thread-local read pool, reset_thread_connections, _db_path) added verbatim into adapters/duckdb/connection.py beside open_expected_mirror_db as the D-01/D-02/D-03 additive step.

## What Was Built

Added to `src/mcp_strava/adapters/duckdb/connection.py`:

- `_db_path() -> str` — returns `str(get_settings().database_path)`
- `class MirrorConn` — context manager renamed from `DbConn`; `__enter__` calls `open_expected_mirror_db(_db_path())` directly (collapsed `_open_storage_connection` alias)
- `_thread_state = threading.local()` — shared thread-local for read pool
- `_thread_read_connections()` — lazy-init dict accessor on `_thread_state`
- `class ReadConn` — thread-local reused read connection with evict-on-error `__exit__` (verbatim from db.py)
- `reset_thread_connections()` — closes and clears the per-thread pool (tests + shutdown)

`db.py` is untouched. `init_db` is NOT relocated (dead code per RI-03, will be deleted with db.py in 12-05). This is a pure additive step in the D-10 hard-cut migration order.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Move MirrorConn + ReadConn + thread-local pool into connection.py | 47f63ed | src/mcp_strava/adapters/duckdb/connection.py |
| 2 | Lint/typecheck and suite verification | b0abf4b | (verification only, no code changes) |

## Verification

- `uv run python -c "from mcp_strava.adapters.duckdb.connection import MirrorConn, ReadConn, reset_thread_connections, _db_path; print('ok')"` → `ok`
- `init_db` absent from connection.py (grep count: 0)
- `uv run ruff check src/mcp_strava/adapters/duckdb/connection.py` → All checks passed
- `uv run ruff format --check src/mcp_strava/adapters/duckdb/connection.py` → already formatted
- `uv run pyright src` → 360 errors before and after (no new errors; line 113 mirrors pre-existing db.py L91 pattern)
- `uv run pytest -q` → **323 passed** (additive change broke nothing)

## Deviations from Plan

None — plan executed exactly as written.

The `_open_storage_connection` indirection in db.py (L28-29) is a one-liner alias for `open_expected_mirror_db` — collapsed to a direct call in MirrorConn and ReadConn per the plan's action note ("collapse to a direct call"). This is not a deviation; the plan explicitly calls for it.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. Relocation only.

## Self-Check: PASSED

- `src/mcp_strava/adapters/duckdb/connection.py` exists and contains MirrorConn, ReadConn, reset_thread_connections, _db_path
- Commits 47f63ed and b0abf4b verified in git log
- 323 tests green
