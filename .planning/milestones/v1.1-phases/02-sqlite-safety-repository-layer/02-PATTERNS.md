# Phase 2: SQLite Safety & Repository Layer - Pattern Map

**Mapped:** 2026-05-21
**Files analyzed:** 13 planned new/modified files
**Analogs found:** 13 / 13

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/mcp_strava/adapters/__init__.py` | package marker | import boundary | `src/mcp_strava/__init__.py` | exact |
| `src/mcp_strava/adapters/sqlite/__init__.py` | package marker | import boundary | `src/mcp_strava/__init__.py` | exact |
| `src/mcp_strava/adapters/sqlite/connection.py` | adapter | SQLite connection | `src/mcp_strava/db.py` | role-match |
| `src/mcp_strava/adapters/sqlite/schema.py` | adapter | schema introspection | `src/mcp_strava/db.py` | role-match |
| `src/mcp_strava/adapters/sqlite/backup.py` | adapter | file/SQLite backup | `src/mcp_strava/db.py` | partial |
| `src/mcp_strava/adapters/sqlite/migrations.py` | adapter | migration orchestration | `src/mcp_strava/db.py` | role-match |
| `src/mcp_strava/adapters/sqlite/repository.py` | repository | CRUD/query | `src/mcp_strava/sync.py`, `src/mcp_strava/db.py` | role-match |
| `src/mcp_strava/types.py` | contract | dataclass serialization | `src/mcp_strava/types.py` | exact |
| `src/mcp_strava/db.py` | legacy bridge | connection/auth/query split | `src/mcp_strava/db.py` | exact |
| `src/mcp_strava/sync.py` | writer orchestration | batch ingest | `src/mcp_strava/sync.py` | exact |
| `src/mcp_strava/report.py` | analytics orchestration | read queries | `src/mcp_strava/report.py` | exact |
| `src/mcp_strava/analytics.py` | analytics orchestration | read queries | `src/mcp_strava/analytics.py` | exact |
| `src/mcp_strava/cli.py` | CLI dispatcher | operator commands | `src/mcp_strava/cli.py` | exact |
| `tests/test_sqlite_safety.py` | test | temp SQLite fixtures | `tests/test_phase01_validation.py` | role-match |
| `tests/test_repository_boundary.py` | test | source/runtime guard | `tests/test_security_guards.py` | role-match |
| `tests/test_load_status.py` | test | pure/fixture behavior | `tests/test_smoke.py` | role-match |

## Pattern Assignments

### `src/mcp_strava/adapters/sqlite/connection.py`

**Analog:** `src/mcp_strava/db.py`

**Current pattern to preserve:** `DbConn` sets `row_factory`, WAL, and autocheckpoint in one boundary. Phase 2 should move this policy into the adapter and add `PRAGMA busy_timeout`.

**Required deviation:** current `DbConn.__enter__` creates the data directory and uses plain `sqlite3.connect(path)`, which can create a missing expected mirror. New expected-mirror open must use fail-closed URI mode and keep explicit fixture/dev creation separate.

### `src/mcp_strava/adapters/sqlite/schema.py`

**Analog:** `src/mcp_strava/db.py`

**Current pattern to extract:** required table definitions and column checks currently live in `init_db()`. The new schema module should encode required tables/columns as data and expose preflight/post-check functions instead of applying DDL from runtime read paths.

### `src/mcp_strava/adapters/sqlite/backup.py`

**Analog:** `src/mcp_strava/db.py` connection lifecycle and Python sqlite3 backup API.

**Pattern:** use a short-lived source connection and destination connection; backup output must be openable, non-empty, timestamped, and chmodded to local-user-only permissions where supported.

### `src/mcp_strava/adapters/sqlite/migrations.py`

**Analog:** `src/mcp_strava/db.py::init_db`

**Pattern:** keep the existing table/column DDL as the first explicit migration baseline, but only run it from migration tooling. Runtime sync/report paths should call an assertion/check path, not `CREATE`/`ALTER`.

### `src/mcp_strava/adapters/sqlite/repository.py`

**Analogs:** `src/mcp_strava/sync.py`, `src/mcp_strava/db.py`, `src/mcp_strava/metrics.py`

**Write pattern:** `_insert_streams()` batches 5000 stream rows and commits deliberately per batch. Repository methods should preserve explicit chunking and parameterized SQL.

**Read pattern:** analytics functions use `sqlite3.Row` key access and return dataclasses or typed primitives. Repository methods should return dataclasses from `types.py` or rows wrapped by adapter-local methods, not raw dict leakage across new boundaries.

### `src/mcp_strava/types.py`

**Analog:** existing dataclasses and `dc_to_dict`.

**Pattern:** add small dataclasses/enums for `DatabasePreflight`, `MigrationBackup`, `MigrationParity`, `DailyLoadPoint`, and load status values. Use simple `str` statuses if that better matches existing JSON serialization.

### `tests/test_sqlite_safety.py`

**Analog:** `tests/test_phase01_validation.py`

**Pattern:** use `tmp_path`, `monkeypatch`, and `reset_settings_cache()` for isolated DB paths. Never point tests at `data/strava.db`.

### `tests/test_repository_boundary.py`

**Analog:** `tests/test_security_guards.py`

**Pattern:** source guard tests may use `git` or path reads for project-level policy checks. Runtime tests should use temp DBs and assert PRAGMA values and repository method behavior.

### `tests/test_load_status.py`

**Analog:** `tests/test_smoke.py`

**Pattern:** direct function tests with small temp SQLite fixtures and explicit assertions. Prefer checking `None`/status outcomes to broad integration snapshots.

## Shared Patterns

### Settings
**Source:** `src/mcp_strava/settings.py`
**Apply to:** connection, migration, backup, CLI operator commands

Use `get_settings().database_path` and `reset_settings_cache()` in tests. Do not introduce a second configuration source.

### Test Command
**Source:** `Justfile`
**Apply to:** every plan

`just test` is the full verification command; focused pytest commands can be used after individual tasks.

### Local-Only Operator Escape Hatch
**Source:** `src/mcp_strava/cli.py::cmd_sql`
**Apply to:** migration/check commands

Keep operator-only commands in CLI. Do not design them as reusable application/MCP service capabilities.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| None | - | - | All planned files have local analogs or direct source patterns. |

## Metadata

**Analog search scope:** `src/mcp_strava/`, `tests/`, `Justfile`, `.planning/codebase/`
**Files scanned:** current source and planning maps through `rg --files` and targeted reads
**Pattern extraction date:** 2026-05-21
