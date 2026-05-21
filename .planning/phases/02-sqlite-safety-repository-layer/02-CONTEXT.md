# Phase 2: SQLite Safety & Repository Layer - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 protects the existing SQLite Strava mirror during schema evolution and moves application data access behind a SQLite repository boundary. It must introduce preflight, backup, migration, parity, fail-closed, and repository contracts for activities, streams, zones, kudos, and sync metadata.

This phase must not build the Strava adapter, automatic refresh runtime, application service layer, MCP HTTP surface, or Docker runtime. Those remain later phases. The existing `data/strava.db` is durable mirror state, not a disposable cache.

</domain>

<decisions>
## Implementation Decisions

### Migration Safety
- **D-01:** Use a strict in-repo SQLite migration gate for Phase 2. Do not introduce Alembic, SQLAlchemy, or a broad ORM/tooling jump in this phase.
- **D-02:** Schema changes must go through an explicit migration path: preflight, timestamped backup, migration, post-check, and parity verification. Runtime read/report paths must not perform schema-altering `CREATE` or `ALTER` work implicitly.
- **D-03:** The migration gate must check database readability, required tables/columns, application schema version, row counts for preserved tables, and SQLite integrity before applying DDL.
- **D-04:** Backups must be timestamped under the data area, openable as SQLite databases, non-empty, and protected with local-user-only permissions where supported. Backup retention should be count-based rather than unbounded.
- **D-05:** Startup/opening of an expected mirror database must fail closed if the DB is missing, unreadable, corrupt, or structurally invalid. Silent creation of an empty replacement DB is not acceptable outside explicit test/dev fixture creation.

### Parity Gate
- **D-06:** The Phase 2 migration parity gate protects data and lower-level analytical signals, not exact end-user report wording.
- **D-07:** Required parity checks include row-count parity for preserved tables and deterministic numeric/load invariants such as observed TRIMP history, Banister/form/load signals, and key aggregates where source data is observed.
- **D-08:** Full daily/weekly report exact-match is not a Phase 2 migration gate. Recommendation text, warnings, and confidence wording may change later when missing/partial data is represented more honestly.

### Repository Boundary
- **D-09:** Introduce a SQLite adapter package with a shared unit-of-work/connection boundary and focused repository ports for activities, streams/load data, zones/kudos, and sync metadata.
- **D-10:** Direct `sqlite3` access is allowed only inside SQLite adapter/migration tooling and narrowly allowed tests. Application/core/interface modules must use repository methods rather than raw connections.
- **D-11:** The existing local arbitrary SQL capability can remain an operator-only CLI escape hatch for now, but it must stay isolated from application services and must not become a reusable service/MCP capability.
- **D-12:** Repository connections must centrally enforce WAL, busy timeout, and short transaction discipline. Long ingest writes should be chunked deliberately rather than relying on WAL alone.

### Missing And Partial Data
- **D-13:** Missing HR/stream data must be represented explicitly and must not be treated as a rest day.
- **D-14:** Add a repository-level daily load contract with statuses such as `REST`, `UNKNOWN`, `PARTIAL`, and `OBSERVED`.
- **D-15:** The contract should separate observed load from effective numeric input used by existing training math. This lets Phase 2 preserve current calculations where data is observed while surfacing uncertainty for later application/report/MCP layers.

### Verification
- **D-16:** `just test` should cover fast hermetic SQLite fixtures and copied DB scenarios only; it must not mutate the real `data/strava.db`.
- **D-17:** Tests must prove backup creation, preflight failure on invalid/missing DBs, post-migration row parity, no live Strava network calls, WAL/busy-timeout settings, direct-`sqlite3` boundary enforcement, and missing-data semantics.
- **D-18:** Heavy verification against the real mirror belongs in an explicit operator preflight/check command, not in default tests.

### Agent Discretion
- Planner may decide exact module names, but the target shape should be close to `src/mcp_strava/adapters/sqlite/*` plus repository contracts rather than adding a new framework.
- Planner may choose the exact schema-version storage mechanics, provided it uses application-owned versioning and avoids SQLite internal `schema_version` misuse.
- Planner may choose the exact fixture-building strategy, provided tests are deterministic, fast, and never write to the real mirror.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope
- `.planning/PROJECT.md` — project value, data-preservation constraints, and MCP/sync boundaries.
- `.planning/REQUIREMENTS.md` — Phase 2 maps to `SAFE-01`, `SAFE-02`, `SAFE-03`, `SAFE-04`, `REPO-01`, `REPO-02`, `REPO-03`, and `TEST-01`.
- `.planning/ROADMAP.md` — Phase 2 goal, success criteria, dependencies, and later-phase boundaries.
- `.planning/STATE.md` — current workflow position and carried-forward decisions.

### Prior Phase Context
- `.planning/phases/01-package-foundation-settings/01-CONTEXT.md` — Phase 1 decisions: direct package move, no old CLI compatibility obligation, typed settings boundary, preserve `data/strava.db`.

### Codebase Maps
- `.planning/codebase/STACK.md` — original stack and SQLite/stdlib constraints; note that paths were pre-Phase-1 and should be mapped to `src/mcp_strava/*`.
- `.planning/codebase/ARCHITECTURE.md` — original architecture and data flow; use for responsibility mapping, not as current path truth.
- `.planning/codebase/CONCERNS.md` — known risks around inline schema mutation, missing-HR false rest days, arbitrary SQL, and smoke-only coverage.

### Current Implementation
- `src/mcp_strava/db.py` — current `DbConn`, `init_db`, Strava auth/API coupling, inline table creation/migration, and `get_daily_trimp_history`.
- `src/mcp_strava/sync.py` — current ingest writes for activities, streams, details, kudos, and sync log.
- `src/mcp_strava/report.py` — daily report dependency on DB/load history.
- `src/mcp_strava/analytics.py` — weekly digest dependency on DB/load history.
- `src/mcp_strava/metrics.py` — stream-derived metrics and direct SQL stream reads.
- `src/mcp_strava/trends.py` — trend computation over load history.
- `src/mcp_strava/cli.py` — current local CLI including sync/backfill/sql/log command surface.
- `src/mcp_strava/settings.py` — Phase 1 typed DB/token/runtime/freshness settings.
- `tests/test_smoke.py` — current smoke behavior and DB-skip assumptions.
- `tests/test_phase01_validation.py` — existing guard checks around DB path behavior.
- `tests/test_security_guards.py` — existing security guard tests; extend boundary/safety coverage here or adjacent tests.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Settings.database_path` and `MCP_STRAVA_DB_PATH` already provide the configurable DB path needed for fixture DBs, copied DB tests, and operator preflight.
- Existing dataclasses in `src/mcp_strava/types.py` are the local pattern for cross-module contracts; repository return types should follow this style.
- Existing `just test` already points at pytest and should remain the primary developer verification command.

### Established Patterns
- Current runtime is stdlib-oriented Python, so a small in-repo SQLite migration/repository layer fits the existing stack better than adding an ORM in Phase 2.
- Current analytics functions return `None` or omit results for insufficient data rather than inventing defaults. Missing/partial load status should preserve that honesty.
- Current code has short-lived one-shot CLI commands, but future refresh/MCP concurrency requires central connection policy now.

### Integration Points
- `src/mcp_strava/db.py` currently mixes connection lifecycle, schema bootstrap/migration, token store, Strava HTTP, and analytical queries. Phase 2 should split the SQLite responsibilities without solving Strava adapter isolation yet.
- `src/mcp_strava/sync.py` currently owns write SQL for activities, streams, details, kudos, and sync logs. These writes should move behind repository methods while later Strava transport work remains Phase 3.
- `get_daily_trimp_history` currently filters on `s.heartrate IS NOT NULL`, which can make missing-HR activities disappear from history and look like rest days.
- The real mirror currently has tables `activities`, `streams`, `athlete_zones`, `kudos`, and `sync_log`; observed row counts during discussion were 594 activities, 2,641,404 streams, 123 kudos, 4 sync_log rows, and 0 athlete_zones rows.

</code_context>

<specifics>
## Specific Ideas

- The user delegated technical/architecture tradeoffs to an expert panel and wants user questions limited to product/business decisions when possible.
- The expert panel converged on a strict custom migration gate, focused SQLite repository boundary, explicit missing-data statuses, and hermetic tests.
- The user chose lower-level parity as the Phase 2 key report gate: protect data and numeric/load signals, but do not require full end-user report exact-match.
- External SQLite docs consulted during discussion: official SQLite PRAGMA docs for `user_version`, `integrity_check`, and `busy_timeout`; SQLite WAL docs; SQLite backup API docs; Python sqlite URI `mode=rw` docs.

</specifics>

<deferred>
## Deferred Ideas

- Strava OAuth/token/HTTP adapter isolation remains Phase 3.
- Automatic refresh scheduling and request-time freshness policy remain Phase 3.
- Application service and clean CLI refit remain Phase 4.
- MCP HTTP tool surface and Docker/runtime hardening remain Phase 5.

</deferred>

---

*Phase: 2-SQLite Safety & Repository Layer*
*Context gathered: 2026-05-21*
