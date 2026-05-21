# Phase 2: SQLite Safety & Repository Layer - Research

**Researched:** 2026-05-21
**Status:** Ready for planning
**Scope:** Plan migration safety, SQLite repository boundaries, explicit missing-data semantics, and hermetic tests without mutating `data/strava.db`.

## User Constraints

### Locked Decisions
- **D-01:** Use a strict in-repo SQLite migration gate for Phase 2. Do not introduce Alembic, SQLAlchemy, or a broad ORM/tooling jump in this phase.
- **D-02:** Schema changes must go through an explicit migration path: preflight, timestamped backup, migration, post-check, and parity verification. Runtime read/report paths must not perform schema-altering `CREATE` or `ALTER` work implicitly.
- **D-03:** The migration gate must check database readability, required tables/columns, application schema version, row counts for preserved tables, and SQLite integrity before applying DDL.
- **D-04:** Backups must be timestamped under the data area, openable as SQLite databases, non-empty, and protected with local-user-only permissions where supported. Backup retention should be count-based rather than unbounded.
- **D-05:** Startup/opening of an expected mirror database must fail closed if the DB is missing, unreadable, corrupt, or structurally invalid. Silent creation of an empty replacement DB is not acceptable outside explicit test/dev fixture creation.
- **D-06:** The Phase 2 migration parity gate protects data and lower-level analytical signals, not exact end-user report wording.
- **D-07:** Required parity checks include row-count parity for preserved tables and deterministic numeric/load invariants such as observed TRIMP history, Banister/form/load signals, and key aggregates where source data is observed.
- **D-08:** Full daily/weekly report exact-match is not a Phase 2 migration gate. Recommendation text, warnings, and confidence wording may change later when missing/partial data is represented more honestly.
- **D-09:** Introduce a SQLite adapter package with a shared unit-of-work/connection boundary and focused repository ports for activities, streams/load data, zones/kudos, and sync metadata.
- **D-10:** Direct `sqlite3` access is allowed only inside SQLite adapter/migration tooling and narrowly allowed tests. Application/core/interface modules must use repository methods rather than raw connections.
- **D-11:** The existing local arbitrary SQL capability can remain an operator-only CLI escape hatch for now, but it must stay isolated from application services and must not become a reusable service/MCP capability.
- **D-12:** Repository connections must centrally enforce WAL, busy timeout, and short transaction discipline. Long ingest writes should be chunked deliberately rather than relying on WAL alone.
- **D-13:** Missing HR/stream data must be represented explicitly and must not be treated as a rest day.
- **D-14:** Add a repository-level daily load contract with statuses such as `REST`, `UNKNOWN`, `PARTIAL`, and `OBSERVED`.
- **D-15:** The contract should separate observed load from effective numeric input used by existing training math. This lets Phase 2 preserve current calculations where data is observed while surfacing uncertainty for later application/report/MCP layers.
- **D-16:** `just test` should cover fast hermetic SQLite fixtures and copied DB scenarios only; it must not mutate the real `data/strava.db`.
- **D-17:** Tests must prove backup creation, preflight failure on invalid/missing DBs, post-migration row parity, no live Strava network calls, WAL/busy-timeout settings, direct-`sqlite3` boundary enforcement, and missing-data semantics.
- **D-18:** Heavy verification against the real mirror belongs in an explicit operator preflight/check command, not in default tests.

### Agent Discretion
- Exact module names may be chosen by the planner, but the target shape should be close to `src/mcp_strava/adapters/sqlite/*` plus repository contracts.
- Exact schema-version storage mechanics may be chosen by the planner, provided it uses application-owned versioning and avoids SQLite internal `schema_version` misuse.
- Exact fixture-building strategy may be chosen by the planner, provided tests are deterministic, fast, and never write to the real mirror.

### Deferred Ideas
- Strava OAuth/token/HTTP adapter isolation remains Phase 3.
- Automatic refresh scheduling and request-time freshness policy remain Phase 3.
- Application service and clean CLI refit remain Phase 4.
- MCP HTTP tool surface and Docker/runtime hardening remain Phase 5.

## Project Constraints from AGENTS.md

- Preserve existing `data/strava.db`; schema work requires backup, preflight, and verification.
- Avoid full Strava resync and live API calls unless explicitly approved.
- Keep MCP sync/admin/debug capabilities out of the MCP surface.
- Keep request-time freshness checks in core/application logic, not MCP tool design.
- Default serving must remain local/container-network safe.
- Existing behavior must remain verifiable with `just test`; new boundaries need targeted tests.
- Runtime remains Python 3.13 and stdlib-oriented; no new ORM/framework is needed for this phase.

## Standard Stack

- Python `sqlite3` remains the only database runtime dependency. [VERIFIED: codebase]
- Use `sqlite3.connect(..., uri=True)` with `file:{path}?mode=rw` for fail-closed opens of expected mirror databases; Python documents `mode=rw` as raising an operational error when the DB does not exist. [CITED: docs.python.org/3/library/sqlite3.html]
- Use SQLite `PRAGMA user_version` only as an application-owned integer schema marker, not SQLite's internal `schema_version`. [CITED: sqlite.org/pragma.html]
- Use `PRAGMA integrity_check` or `quick_check` during preflight/post-check, with `integrity_check` for the operator migration gate. [CITED: sqlite.org/pragma.html]
- Continue using WAL for normal repository connections and add explicit `PRAGMA busy_timeout`. SQLite documents `busy_timeout` as the pragma equivalent of the busy-timeout API, and WAL supports concurrent readers with a single writer. [CITED: sqlite.org/pragma.html] [CITED: sqlite.org/wal.html]
- For backups, prefer Python's `sqlite3.Connection.backup()` API over copying only the `.db` file; WAL-mode SQLite treats the `-wal` file as part of database state while open. [CITED: docs.python.org/3/library/sqlite3.html] [CITED: sqlite.org/wal.html]

## Architecture Patterns

### Responsibility Map

| Capability | Owner | Notes |
|------------|-------|-------|
| Expected mirror DB open/fail-closed | `adapters/sqlite/connection.py` | Uses typed `Settings.database_path`; explicit fixture/dev creation path stays separate. |
| Schema introspection/preflight/post-check | `adapters/sqlite/schema.py` or `migrations.py` | Checks required tables/columns, `user_version`, row counts, and integrity. |
| Backup and retention | `adapters/sqlite/backup.py` | Uses SQLite backup API and count-based retention under `data/`. |
| Migration orchestration | `adapters/sqlite/migrations.py` | Performs preflight -> backup -> migrate -> post-check -> parity; no implicit DDL from report/read paths. |
| Repository contracts/types | `types.py` and `adapters/sqlite/repository.py` | Follow dataclass patterns already used in `types.py`. |
| CLI operator commands | `cli.py` | May expose migration preflight/check/migrate as local operator commands; arbitrary SQL stays local-only. |
| Runtime analytics | `report.py`, `analytics.py`, `metrics.py`, `trends.py`, `sync.py` | Move toward repository methods without changing Strava adapter yet. |

### Migration Gate Shape

The gate should be a deterministic sequence:

1. Open expected DB fail-closed.
2. Run preflight: readability, required table/column inventory, `PRAGMA user_version`, row counts, `PRAGMA integrity_check`.
3. Create timestamped backup with `Connection.backup()`.
4. Apply explicit migrations only from migration tooling.
5. Run post-check and row-count parity for preserved tables.
6. Run numeric/load parity over observed data: TRIMP history, Banister/form/load invariants, and key aggregates.
7. Report structured status for CLI and tests.

### Repository Boundary Shape

- Create focused repository methods for activities, streams/load data, zones/kudos, and sync metadata.
- Keep row-level parsing close to SQLite adapter, but keep training math in existing core modules.
- Start by introducing repositories and switching the highest-risk paths (`report.py`, `analytics.py`, `trends.py`, `sync.py`) to call repository methods. CLI `sql` remains an explicit operator escape hatch.
- Keep `api_request`, token refresh, and Strava transport in existing modules for now; Phase 3 isolates them.

## Don't Hand-Roll

- Do not hand-roll SQLite file copying while the DB may be in WAL mode; use SQLite backup API or a checkpointed/open connection path. [CITED: sqlite.org/wal.html]
- Do not add SQLAlchemy/Alembic or an ORM in this phase; context explicitly rejects a broad tooling jump.
- Do not expose migration/sync/admin controls through MCP.
- Do not make tests touch `data/strava.db`; fixtures must use temp DBs or copied DB files.

## Common Pitfalls

- `sqlite3.connect(path)` silently creates a missing DB; use URI `mode=rw` for expected mirror opens. [CITED: docs.python.org/3/library/sqlite3.html]
- WAL mode keeps persistent state in `-wal` while connections are open; backing up only the main file can lose committed transactions. [CITED: sqlite.org/wal.html]
- `get_daily_trimp_history()` currently filters out missing-HR activities, which hides activity presence and creates false rest-day semantics. [VERIFIED: `src/mcp_strava/db.py`]
- Current `init_db()` performs implicit `CREATE TABLE` and `ALTER TABLE` work in runtime sync paths; this contradicts D-02 and must be isolated behind explicit migration tooling. [VERIFIED: `src/mcp_strava/db.py`]
- Current codebase maps in `.planning/codebase/*` still mention old `scripts/` paths; map them to current `src/mcp_strava/*` before implementation. [VERIFIED: codebase]

## Code Examples

Use existing local idioms:

- Dataclass contracts: `src/mcp_strava/types.py` (`StravaActivity`, `DailyReport`, `WeeklyDigest`).
- Settings access: `src/mcp_strava/settings.py` (`Settings.database_path`, `get_settings()`, cache reset for tests).
- Connection policy: current `src/mcp_strava/db.py::DbConn`, but replace silent directory creation and missing DB creation for expected mirrors with fail-closed open.
- Sync batch writes: `src/mcp_strava/sync.py::_insert_streams()` commits per batch; repository methods should preserve deliberate chunking.
- Pytest fixture style: existing tests use `tmp_path`, `monkeypatch`, subprocess, and direct assertions.

## Validation Architecture

Use pytest through `just test` for all default verification. Every test uses temp files or explicit copied fixtures:

- `tests/test_sqlite_safety.py`: migration preflight, backup creation/openability, retention, post-check parity, fail-closed opens.
- `tests/test_repository_boundary.py`: repository connection PRAGMAs, focused read/write methods, direct-`sqlite3` boundary guard, no live Strava network calls.
- `tests/test_load_status.py`: `REST`, `UNKNOWN`, `PARTIAL`, `OBSERVED` status semantics and observed numeric input parity.
- Existing smoke tests remain green.

Feedback target: `python3 -m pytest tests/test_sqlite_safety.py tests/test_repository_boundary.py tests/test_load_status.py -q` for focused runs; `just test` for the full suite.

## Open Questions (RESOLVED)

1. **Should Phase 2 add an ORM?** RESOLVED: No; D-01 requires an in-repo SQLite gate.
2. **Should parity assert exact report JSON?** RESOLVED: No; D-06 through D-08 limit parity to data and numeric/load invariants.
3. **Should default tests use the real mirror?** RESOLVED: No; D-16 and D-18 require hermetic defaults and explicit operator checks for real mirror validation.

## Package Legitimacy Audit

No package-manager installs are planned for Phase 2.

## Source Coverage Targets

- **GOAL:** Controlled schema evolution and repository isolation.
- **REQ:** SAFE-01, SAFE-02, SAFE-03, SAFE-04, REPO-01, REPO-02, REPO-03, TEST-01.
- **CONTEXT:** D-01 through D-18 must be referenced in plan actions or must-haves.
- **RESEARCH:** Migration gate, fail-closed opens, backup API, WAL/busy-timeout policy, repository methods, load statuses, hermetic tests.

## References

- SQLite PRAGMA documentation: https://www.sqlite.org/pragma.html
- SQLite WAL documentation: https://www.sqlite.org/wal.html
- Python sqlite3 documentation: https://docs.python.org/3/library/sqlite3.html
