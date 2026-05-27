---
quick_task: 260526-u2h-remove-obsolete-sqliterepository-runtime
status: complete
completed_at: 2026-05-27
phase: 08-duckdb-primary-storage-aggregate-analytics-surface
---

# Summary: Remove obsolete SQLite/runtime compatibility paths

## Trigger

The user saw `_usage_error("admin db-migrate was removed; DuckDB is the only runtime
storage.")` and objected that a tailored "removed command" message is backward-compatibility
archaeology. The task expanded from deleting one string into removing the whole class of stale
SQLite / cutover / removed-command paths now that the live DuckDB cutover has already happened.

## What changed

Delivered in three atomic commits on `feat/phase-8-duckdb-primary-storage`:

1. `refactor(phase-08)` — source cleanup (`8d5bc98`)
   - Deleted the entire `src/mcp_strava/adapters/sqlite/` tree, the one-shot SQLite→DuckDB
     cutover tooling (`adapters/duckdb/migrations.py`), and the legacy `analytics.py` /
     `report.py` / `trends.py` modules.
   - Removed SQLite repository routing from runtime factories; DuckDB is the only runtime path.
   - Removed `db-migrate` / `duckdb-cutover` special-casing from the CLI (`ADMIN_COMMANDS` no
     longer contains them; removed commands fall through as plain unknown commands).
   - Trimmed `training.py` / `types.py` to the surviving model (Banister/EWMA/forward-sim);
     dropped dead weekly-plan/report dataclasses and helpers.

2. `test(phase-08)` — test suite rewrite (`354b6eb`)
   - Added shared DuckDB fixture `tests/_fixtures_duckdb.py` (`create_fixture_db`,
     `create_empty_fixture_db`).
   - Deleted `test_sqlite_safety.py` and `test_duckdb_migration.py` (tested removed SQLite
     safety + cutover tooling).
   - Rewrote SQLite-fixture tests onto DuckDB: refresh runtime, load status, application
     services, phase-4 e2e, repository boundary, metric services, read-model materialization.
   - **Ported** the lossless stream-channel contract tests (insert/replace/channel-metadata/
     unavailable-status/merge) from `test_full_fidelity_mirror.py` to DuckDB so milestone
     stream coverage survived rather than being dropped.
   - Stripped removed-command / removed-module assertions from smoke, metric registry,
     phase-01, docker runtime, cli surface, and security guards; kept the absence guards.

3. `docs(phase-08)` — docs (`157229a`)
   - Removed `db-migrate` / `duckdb-cutover` from CLI docs, the SQLite Phase 7 read-model
     validation runbook, the Phase 8 cutover runbook, and the Phase 8 SQLite rollback runbook.
   - Pointed canonical/runtime paths and `prepare_runtime` bootstrap at `strava.duckdb`.

Net: 49 files changed, ~775 insertions / ~10,628 deletions vs the paused WIP commit.

## Verification

- Marker scan (`SQLiteRepository|adapters.sqlite|run_migrations|run_duckdb_cutover|db-migrate|
  duckdb-cutover|mcp_strava.analytics|report|trends|…`) clean across `src tests docs README.md
  Justfile` — remaining hits are legitimate absence-guards, AST direct-`sqlite3` detectors,
  `.gitignore` hygiene patterns, and the Strava `gear.retired` field reference.
- Full suite: **291 passed** (`uv run pytest -q`).

## Decisions

- DuckDB is the only runtime storage path; SQLite is not a live adapter.
- No backward-compatibility archaeology: removed commands are unknown commands, no aliases, no
  tailored removal errors, no retired modules, no tests for removed behavior.
- Tests verify current behavior only; behavior that still exists (e.g. lossless streams) was
  rewritten onto DuckDB rather than deleted.

## Not in scope / still open

- Phase 08 plan **08-08** performance acceptance remains open: the 100 ms warm p95 gate
  (`just mcp-read-model-perf 20 2 100`) previously failed. This cleanup was the local
  groundwork; the perf gate is the next milestone-closing task.
