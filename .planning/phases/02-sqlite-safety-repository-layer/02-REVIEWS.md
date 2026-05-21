---
phase: 2
reviewers: [opencode, claude]
reviewed_at: 2026-05-21T10:21:36Z
plans_reviewed: [02-01-PLAN.md, 02-02-PLAN.md, 02-03-PLAN.md, 02-04-PLAN.md]
cycle: 1
---

# Cross-AI Plan Review — Phase 2

## Consensus Summary

Both requested reviewers agree that the Phase 2 plan set is structurally sound: the wave order is correct, the data-preservation posture is conservative, and the repository boundary is pointed at the right problems. Both reviewers also found that the phase should not proceed unchanged because several acceptance criteria are still too ambiguous to verify the core safety guarantees.

### Agreed Strengths

- Wave ordering is coherent: SQLite safety gates land before repository contracts, read adoption, and final enforcement.
- Fail-closed SQLite opening, `Connection.backup()`, hermetic tests, and no live Strava calls are the right safety posture for the local mirror.
- The missing-HR/missing-stream load-status model addresses a real analytics bug without redesigning the training model in this phase.
- The MCP boundary is not leaking sync/admin/debug operations into Phase 2.

### Agreed Concerns

- **HIGH: Parity checks are not specific enough.** Both reviewers called out that row-count checks plus broad “TRIMP/load parity” wording may not prove Banister/load/report behavior is preserved. The plan needs exact functions, windows, tolerances, and a synthetic migration or equivalent before parity can be trusted.
- **HIGH: `training.py` is missing from the load-status migration contract.** OpenCode marked this HIGH because `DailyLoadPoint.effective_trimp` feeds Banister math; Claude raised the same area through parity and downstream-load concerns. The plan needs to name how repository daily-load output becomes the series consumed by training calculations.
- **HIGH: `init_db()` implicit DDL retirement is not explicit.** Claude marked this HIGH, and OpenCode also flagged it as a medium concern. The plans must state whether `init_db()` is removed from runtime paths or converted to assertion-only behavior; otherwise D-02 can fail through sync paths.
- **HIGH: `metrics.py` migration and repository-guard scope contradict each other.** Claude marked this HIGH, and OpenCode also flagged the vague metrics scope. The plans must either move all relevant stream queries behind repository methods or explicitly allowlist `metrics.py` for this phase with a follow-up boundary.
- Backup retention, busy timeout defaults, source-guard implementation mechanics, and `effective_trimp` behavior for UNKNOWN/PARTIAL statuses need concrete defaults before or during execution.

### Divergent Views

- Claude rated `init_db()` retirement and `metrics.py` boundary ambiguity as HIGH; OpenCode rated them MEDIUM. For convergence, they are treated as current HIGH concerns because at least one requested reviewer classified each as HIGH and they directly affect phase-exit enforceability.
- OpenCode uniquely raised `training.py` absence as a HIGH. Claude did not name the file as a standalone HIGH, but its parity and load-consumer concerns overlap enough that this should be fixed in the replan.
- Claude uniquely emphasized that Phase 2 may not exercise a real schema migration unless the plan adds a synthetic migration test. OpenCode also raised parity specificity, so the consensus fix should cover both.

## Current HIGH Concerns

- Parity verification is under-specified and may not prove preserved training/load behavior.
- `training.py` is absent from the 02-03 load-status/repository adoption contract despite consuming numeric load inputs.
- `init_db()` implicit schema-changing DDL is not explicitly removed or converted to assertion-only behavior on runtime/sync paths.
- `metrics.py` repository migration scope conflicts with the planned raw-SQL source guard.

## Claude Review

<sef-eval phase="USER-PROMPT">
<task>Produce a cross-AI plan review of Phase 2 plans 02-01 through 02-04 with structured assessment</task>
<skills>gsd-review matches by name (cross-AI plan review) but is itself the dispatcher that asks Claude for this review — invoking it would recurse. gsd-code-review reviews source files, not plans. No other skill matches a "produce reviewer output" task.</skills>
<decision>proceed — produce review output directly as the requested reviewer</decision>
</sef-eval>

# Phase 2 Plan Review — Cycle 1 (Claude)

## Summary

The four Phase 2 plans form a coherent, well-decomposed implementation path that maps cleanly onto locked decisions D-01..D-18 and the SAFE-/REPO-/TEST-01 requirements. Wave structure is correct (safety gate → contracts → adoption → enforcement), TDD scaffolding is in every plan, and threat models are present. The strongest concern is a **coordination gap**: between "delegate `DbConn` connection policy" (02-01) and "sync writes through repository" (02-04), `init_db()`'s implicit `ALTER TABLE` behavior — which directly contradicts D-02 — is never explicitly removed, only routed around. A second tension is the "where practical" hedge in 02-03 for `metrics.py` vs. the strict source guard in 02-04, which will collide at execution time given `metrics.py` has ~10 distinct `conn.execute` call sites. Several smaller gaps (backup location/retention defaults, busy_timeout value, parity snapshotting mechanics, Phase 1 test impact) are recoverable during execution.

## Strengths

- **Decision traceability** is explicit per plan and per task; reviewers can verify each D-XX maps to an artifact and acceptance criterion.
- **Wave ordering** is correct: 02-01 (safety primitives) blocks everything else, 02-02 (contracts) and 02-03 (adoption + load statuses) are correctly parallelizable in Wave 2, and 02-04 (enforcement + integration) gates the phase exit.
- **Hermetic test posture** is consistent: every plan calls out `tmp_path`/copied DB, `reset_settings_cache()`, no live Strava, no mutation of `data/strava.db`, and Plan 02-04 Task 3 verifies the real DB inode/sidecar status before/after `just test`.
- **Backup via `Connection.backup()`** correctly chosen over file copy — addresses the WAL-state pitfall noted in research.
- **DailyLoadPoint contract** (status + `observed_trimp` + `effective_trimp` split per D-15) cleanly preserves Banister/TRIMP math while exposing uncertainty for later phases.
- **Operator escape hatch boundary** (cmd_sql stays, MCP/service SQL forbidden, D-11) is reiterated in tests, not just docs.
- **Threat model in every plan** with explicit T-02-XX IDs cross-referenced in the validation map.

## Concerns

### HIGH

- **`init_db()` implicit DDL never explicitly retired.** D-02 forbids implicit schema-altering work on runtime paths. `sync.py` currently calls `init_db(conn)` at the top of both `sync_activities` and `backfill_activities`, which executes `ALTER TABLE streams ADD COLUMN …` and `ALTER TABLE sync_log ADD COLUMN …` on every sync. Plan 02-01 Task 2 acceptance says "`db.py` no longer owns inline `ALTER TABLE` decisions on normal read/report open paths" — but sync paths are *write* paths, so this wording lets `init_db()` survive. Plan 02-04 Task 2 says sync "calls repository methods for writes" but doesn't say `init_db()` is removed. Either Plan 02-01 must explicitly delete `init_db()`'s `ALTER TABLE` block (replacing it with a preflight assertion) or Plan 02-04 must explicitly do so — currently neither commits. Without this, D-02 fails at phase exit.

- **`metrics.py` repository migration is hedged with "where practical".** Plan 02-03 Task 2 says: "for `metrics.py`, keep per-activity stream metric queries behind repository helpers *where practical* without changing the cardiac drift algorithm." `metrics.py` has at least 10 distinct stream queries (decoupling row fetch, cardiac drift fetch, EF avg HR/velocity, HR recovery scan, vertical speed, CC, median HR via OFFSET, Z5 minute check, HR anomaly scan, and the `_get_hr_max` cache). Plan 02-04 Task 1 then adds a source guard that "rejects new raw `sqlite3` access outside allowed boundaries." If the allowlist excludes `metrics.py`, Plan 02-03's hedge collapses Plan 02-04's guard. Either the guard's allowlist must explicitly include `metrics.py` for Phase 2 (with a Phase 3/4 cleanup note), or 02-03 must commit to moving all stream queries behind repository methods. Currently ambiguous, and execution will hit a contradiction.

- **Migration parity gate is structurally complete but exercises nothing in Phase 2.** Plans 02-01/02-03 require post-migration row-count + observed-TRIMP parity. But Phase 2 introduces no schema-altering migration — the existing live schema becomes "version 1" baseline. The first real migration that exercises parity is Phase 3+. This isn't fatal, but the plans should state that the Phase 2 baseline migration is an idempotent recording (capture `user_version=1`, verify required tables/columns already match), and that parity helpers are tested via a **synthetic test migration** that does change schema, not via a real one. Without that synthetic-migration test, parity infrastructure is unverified. Plan 02-01 Task 1 lists "Migration orchestration preserves row counts… and compares deterministic TRIMP/load parity on observed data" as a behavior, but doesn't say *what migration* the test applies. Risk: parity code ships without ever having run a real before/after comparison.

### MEDIUM

- **Phase 1 test will break under fail-closed open.** `tests/test_phase01_validation.py::test_found02_dbconn_uses_runtime_settings_db_path` (line 40) points `MCP_STRAVA_DB_PATH` at a nonexistent file then enters `DbConn() as conn` and writes. Once `DbConn` delegates to fail-closed `mode=rw`, this test fails because the file doesn't exist. Plans don't list `tests/test_phase01_validation.py` in `files_modified` for 02-01 or 02-04. Either the fail-closed path needs a separate "create-new" entrypoint that this test uses, or the test must be updated and the plan must say so. Currently silent.

- **`Settings.database_path` default still resolves to a path even when the file doesn't exist.** `settings.py:130` defaults to `root / 'data' / 'strava.db'`. Fail-closed semantics need to distinguish "operator expects mirror" (fail closed) from "fresh install / fixture" (explicit create). Plans imply this via "explicit fixture/dev creation stays separate," but the API shape (function name? settings flag? CLI command?) is undefined. Without a named API, callers will default to whichever path is convenient and erode D-05.

- **Backup retention count and location are unspecified.** Plan 02-01 says "count-based retention" and "under the data area" without specifying defaults or whether the count is configurable via `Settings`. Operator with 1 backup/sync over 6 months produces ~180 backup files at >50MB each (current DB has 2.6M stream rows). Suggest: default retention 5, configurable via `MCP_STRAVA_BACKUP_RETENTION`; location `data/backups/`. Otherwise execution agent picks arbitrarily.

- **`PRAGMA busy_timeout` value not specified.** Research mentions adding it but no default. Pragmatic range 5000–30000ms; under single-user load 5000ms is fine. Should be set explicitly in `connection.py` and ideally configurable.

- **`get_daily_trimp_history(conn, ...)` signature compatibility.** Plan 02-03 says `db.py::get_daily_trimp_history` "delegates to the repository for compatibility." Current callers pass an existing `conn`. Does the repository-backed version still accept a connection, or does it open its own? If callers stop passing `conn`, that's a signature change rippling through `report.py`, `analytics.py`, `trends.py`. If it accepts `conn` for compatibility but opens new repository connections internally, you get connection-within-connection patterns. The plan doesn't pick.

- **Parity snapshot mechanics undefined.** Migration parity = compare X before/after. Plan doesn't describe whether parity queries run pre-migration (capture into memory or temp table), nor what happens if the migration takes long enough that fatigue/Banister values "drift" because real wall-clock time has moved. For deterministic parity, use frozen `today_str` or `as_of` parameter. Worth pinning down before execution.

- **`Connection.backup()` and concurrent sync.** SQLite `backup()` works across concurrent readers but interacts with a long-running sync writer. Plan doesn't say whether `db-migrate` is required to fail if a sync is in flight, or if it serializes. With only one operator, this is mostly theoretical, but worth a single sentence: "operator commands acquire an exclusive lock or fail with `BUSY`."

- **Source guard implementation strategy is grep-fragile.** Plan 02-02 Task 1 names the guard but not the mechanism. `grep "sqlite3.connect"` misses `import sqlite3 as _s; _s.connect(...)`. AST-based guard is more robust but heavier. Pick one and document; a brittle regex guard will produce false negatives that won't be caught for months.

- **No test for what happens when `cmd_sql` runs DDL.** D-11 keeps `cmd_sql` as operator escape hatch. But nothing prevents an operator from running `ALTER TABLE` via `cmd_sql`, bypassing the migration gate entirely. Plan accepts this (T-02-08 is "accept"), but a test asserting `cmd_sql` doesn't loop back into migration tooling would close the design.

### LOW

- **Validation strategy frontmatter has `wave_0_complete: false`** but Plan 02-01 Task 1 creates the failing tests inline. Confirm whether `wave_0_complete` flips to `true` after Plan 02-01 Task 1 lands, or whether Wave 0 is meant to be a separate pre-execution step. Likely just a stale flag.

- **`metrics.py::_hr_max_cache` module-global** survives across requests. Phase 4 concern, not Phase 2, but worth noting since 02-03 touches the file.

- **Plan 02-04 Task 3 uses `git status --short`** to verify real DB untouched, but `data/strava.db` is gitignored (per `tests/test_security_guards.py:18`). `git status` won't show changes to gitignored files. Better check: snapshot `(inode, size, mtime)` of `data/strava.db`/`-wal`/`-shm` before `just test` and re-compare after, matching the pattern already in `test_existing_local_mirror_db_is_preserved_when_present`.

- **Plan 02-01 Task 2 acceptance** lists "`src/mcp_strava/adapters/sqlite/migrations.py` names preflight, backup, post-check, and parity steps" — "names" is weak. Should be: "exposes callable functions `preflight()`, `create_backup()`, `apply_migration()`, `post_check()`, `verify_parity()` (or equivalent)."

- **Plan 02-02 doesn't mention `streams` index handling.** The existing `idx_streams_act` index is in `init_db()`. Once that's gone, schema bootstrap must include indexes. Easy to miss.

- **Operator command names not finalized.** Plan 02-04 uses `db-preflight`/`db-check`/`db-migrate` "such as" — pick canonical names so tests pin them.

## Suggestions

1. **Promote `init_db()` removal to an explicit acceptance criterion in Plan 02-01 Task 2**: "`init_db()` no longer issues `ALTER TABLE` or `CREATE TABLE IF NOT EXISTS` on any code path; required schema is verified by `schema.preflight()` and applied only by `migrations.run()`." Then update `sync.py` in 02-04 to drop the `init_db(conn)` calls.

2. **Resolve the `metrics.py` boundary question now**, before execution:
   - Option A: Add `metrics.py` to the source-guard allowlist for Phase 2 with a TODO/ADR for Phase 4 cleanup.
   - Option B: Add explicit repository methods per metric query (`stream_rows_for_decoupling()`, `stream_rows_for_drift()`, etc.) and commit Plan 02-03 Task 2 to migrating all of them.
   Document the decision in the plan; the current "where practical" hedge will not survive contact with the guard.

3. **Add a synthetic-migration parity test** to `test_sqlite_safety.py`: create a v1 fixture DB, apply a fake v1→v2 migration (add a nullable column, copy values), and verify parity helpers catch row-count drift and observed-TRIMP drift. Without this, parity code ships unverified.

4. **Pin defaults explicitly** in Plan 02-01 Task 2:
   - `PRAGMA busy_timeout = 5000`
   - Backup directory: `data/backups/`
   - Backup retention: 5
   - Backup filename pattern: `strava-{YYYYMMDDTHHMMSSZ}.db`
   Add a `BackupSettings` block to `settings.py` or use existing settings surface; either way, declare them.

5. **Define a separate "create-empty-DB" entrypoint** (e.g., `connection.create_empty_mirror(path)` or `migrations.init_new_db(path)`) for fixture/dev use, distinct from `connection.open_expected_mirror(path)` which is fail-closed. Update `tests/test_phase01_validation.py::test_found02_dbconn_uses_runtime_settings_db_path` in Plan 02-01's `files_modified` list to use the new entrypoint or to expect the failure.

6. **Replace `git status` real-DB check** in Plan 02-04 Task 3 with an inode/size/mtime snapshot diff. `data/strava.db` is gitignored, so `git status` will silently pass even if the DB was mutated.

7. **Specify parity snapshotting**: parity helpers must take an `as_of` timestamp parameter so `daily_report`/training math returns identical numerics regardless of wall-clock drift during migration. Otherwise long migrations produce parity false positives.

8. **Make the source guard AST-based or grep-with-allowlist-and-deny-patterns** explicit (e.g., reject `sqlite3.connect`, `sqlite3.Connection(`, `import sqlite3 as`); commit to one mechanism in Plan 02-02 Task 1 acceptance.

9. **Add `tests/test_phase01_validation.py` and `tests/test_smoke.py` to `files_modified`** in Plan 02-01 or 02-04 if their assumptions about `DbConn` change. Currently absent; will surface as full-suite regression.

10. **Add an acceptance line for `cmd_sql` DDL boundary**: e.g., "`tests/test_repository_boundary.py` documents that `cmd_sql` permits DDL but is not invokable from any non-CLI surface and asserts no service/MCP module imports `cmd_sql`."

## Risk Assessment

**Overall risk: MEDIUM.**

Justification: The plans are structurally sound and trace cleanly to locked decisions. There's no scope creep, no over-engineering, and no obvious dependency-ordering inversion. The validation strategy is hermetic. Most concerns are **specification gaps** rather than design flaws — they will surface during execution and can be resolved per-task, but at least three (HIGH-1 `init_db()` retirement, HIGH-2 metrics.py boundary, HIGH-3 unexercised parity gate) are likely to produce execution-time rework if not pinned down before Wave 1 starts. None of them threaten the durable mirror (the fail-closed open and `Connection.backup()` choices are conservative), so the data-preservation goal is well-protected. The repository boundary is well-shaped but its enforcement strictness needs to be reconciled with `metrics.py` reality before the guard ships.

A clean execution path requires: (a) resolving HIGH-1/2/3 in the plan now, (b) pinning defaults per Suggestion 4, and (c) accepting that `metrics.py` will either need a broader migration in 02-03 or a documented allowlist exception in 02-04. With those clarifications, risk drops to LOW.

---

## OpenCode Review

Now let me load the relevant skills and review the plans systematically.
Let me examine the current source state to validate plan assumptions.
Now I have all the context needed. Here is my review:

---

# Cross-AI Plan Review — Phase 2 (Cycle 1)

## 1. Summary

Phase 2 plans are well-scoped with clear dependency ordering and thorough decision traceability. The TDD approach, threat models, and hermetic test strategy are correctly applied. The plans correctly defer Strava adapter isolation (Phase 3) and keep `cmd_sql` as an operator-only escape hatch. However, three areas need tightening before execution: parity computation specificity, the under-defined boundary between `effective_trimp` and the numeric input that feeds `training.py`, and ambiguous ownership of the source-level boundary guard enforcement mechanism.

## 2. Strengths

- **Dependency ordering is correct**: 02-01 (safety gate) → 02-02/02-03 (repository + read adoption) → 02-04 (integration). The wave structure is sound.
- **Fail-closed behavior is correctly anchored**: the plans correctly identify `sqlite3.connect(path)` silently creating a DB as the key risk and use `mode=rw` URI-based open. This is directly cited from Python/SQLite docs.
- **Backup strategy uses `Connection.backup()` API**: avoids the WAL-file footgun that would come from naive `shutil.copy()`.
- **Missing-data semantics match the actual codebase bug exactly**: `get_daily_trimp_history` line 229 (`s.heartrate IS NOT NULL`) demonstrably treats missing-HR activities as rest days. The `REST/UNKNOWN/PARTIAL/OBSERVED` status scheme directly repairs this.
- **Decision traceability is exhaustive**: every must-have maps to a D-0x decision, and every requirement maps to a plan.
- **Threat model per plan**: STRIDE breakdowns with dispositions are present and correctly scoped.
- **Hermetic test commitment**: `tmp_path`, `monkeypatch`, `reset_settings_cache()`, and the explicit `data/strava.db` non-mutation check at 02-04 Task 3 are all correct.

## 3. Concerns

### HIGH

- **H-1: Parity computation is under-specified (02-01, 02-03).** D-07 requires "deterministic numeric/load invariants such as observed TRIMP history, Banister/form/load signals, and key aggregates." The plans name this but never define *which specific functions to call, which arguments, and what constitutes a pass*. `get_daily_trimp_history` filters on HR stream data with sport-filtering; the parity check must compare repository-delegated output against the pre-refactor output on the same input data. Without specifying `calc_banister()`, `ewma()`, `calc_acwr()`, and which window sizes to compare, the parity gate may become a shallow row-count check. **Recommendation**: 02-01 Task 2 and 02-03 Task 2 must list exact function signatures and invariants to compare (e.g., "for observed-HR days in a 42-day window, `ewma(series, tau=7)` output matches to ±0.1").

- **H-2: `training.py` is absent from 02-03's `files_modified` and from the key_links despite being the consumer of numeric load input.** `training.py::calc_banister()` calls `ewma()` which receives a `series_dict` — currently sourced from `get_daily_trimp_history()`. If 02-03 introduces `DailyLoadPoint` with `effective_trimp` and changes how that dict is built, training.py is the direct downstream consumer. The plan lists `report.py`, `analytics.py`, `trends.py`, `metrics.py` in `files_modified` but not `training.py`. **Recommendation**: Add `src/mcp_strava/training.py` to 02-03's `files_modified` and `key_links` with a link from `repository.py` → `training.py` showing that Banister math receives `effective_trimp` from the daily load contract.

### MEDIUM

- **M-1: Source boundary guard has no clear implementation home (02-02, 02-04).** Plans require "identifying new raw `sqlite3.connect` usage outside allowed boundaries" but the enforcement mechanism (file-scanning test in `test_security_guards.py`) is only loosely assigned. 02-02 Task 1 says tests should assert D-10 but the implementation could range from a simple `grep` on source files to AST analysis. The allowlist (`adapters/sqlite/`, `db.py` compatibility bridge, `tests/`) is named but the enforcement implementation is not designed. **Recommendation**: Specify in 02-04 Task 1 that the guard is a pytest test using `pathlib` glob + `ast` parse to find all `sqlite3.connect` callsites and check them against the allowlist. Or use a simpler `rg`-based check with blessed paths.

- **M-2: `effective_trimp` computation for statuses other than OBSERVED is undefined (02-03).** D-15 requires "separating observed load from effective numeric input used by existing training math." For `REST`, effective_trimp = 0 (clear). For `OBSERVED`, it equals the HR-derived TRIMP (clear). But for `UNKNOWN` (activity exists, no streams) and `PARTIAL` (streams exist, no HR), what value does training math receive? The Banister EWMA gap-fills with 0 for missing dates. If `effective_trimp` is also 0 for these statuses, the numeric behavior is *preserved* but the distinction is purely in the status field — which makes the parity requirement trivial. If the plan intends to use a different value (e.g., interpolated or estimated), that changes training math and needs explicit specification. **Recommendation**: 02-03 must specify: `effective_trimp` for UNKNOWN/PARTIAL = null (training math uses 0 as today, same as current) or a specific value, with rationale.

- **M-3: Retention count for backups is unspecified (02-01).** D-04 says "count-based retention" but no maximum count is given. Without a cap, every migration creates a new backup, potentially filling disk. **Recommendation**: Specify a retention count (e.g., keep last 5 backups) in 02-01 Task 2 or in the `must_haves`.

- **M-4: Existing `init_db()` inline migration code path is partially addressed.** The plans say `DbConn` delegates connection policy and "no longer owns inline ALTER TABLE decisions on normal read/report open paths." But `init_db()` is still *called* from `sync.py::sync_activities()` at line 139. Plan 02-04 Task 2 updates `sync.py` to use repository writes but does not explicitly say whether `init_db()` is removed, refactored, or kept as a compatibility bridge. The `CREATE TABLE IF NOT EXISTS` pattern in `init_db()` contradicts D-02. **Recommendation**: 02-04 Task 2 must explicitly state that `init_db()` is either removed from runtime paths or refactored to only assert schema existence (not create/alter).

- **M-5: `metrics.py` read-path migration is vague.** Plan 02-03 Task 2 says "keep per-activity stream metric queries behind repository helpers where practical without changing the cardiac drift algorithm." `metrics.py` has ~15 direct SQL queries on the `streams` table. The plan doesn't specify which queries get repository methods and which stay direct. The `cardiac_drift.py` algorithm uses Jenks clustering over HR/velocity data; wrapping this behind a repository stream-read method is straightforward but needs explicit task scope. `enrich_activity()` (called from `report.py`) is a key integration point. **Recommendation**: 02-03 Task 2 should enumerate the metrics.py functions that get repository wrappers (at minimum: `enrich_activity`, the per-activity stream query in `calc_trimp`) and note which remain as-is.

### LOW

- **L-1: Schema version start value and increment mechanics.** Plans mention `PRAGMA user_version` but don't define what version Phase 2 starts at. Current DB likely has `user_version=0`. **Recommendation**: Define initial version (likely 1 after first migration) in 02-01.

- **L-2: 02-04 Task 3's real-DB non-mutation check is a no-op if `data/strava.db` doesn't exist.** The check (`git status --short -- data/strava.db`) passes trivially when the file is absent. This is acceptable (SAFE-04 handles missing DB) but should be documented. **Recommendation**: Add note: "If `data/strava.db` does not exist, this check is trivially satisfied; SAFE-04 handles fail-closed on expected mirror absence."

- **L-3: Threat T-02-02 is classified as Denial of Service but is really a reliability concern.** This doesn't affect plan execution but may confuse security auditors. Busy timeout and WAL are availability/reliability mitigations.

- **L-4: `athlete_zones` table is at row count 0 in the real mirror.** The plans list zones as a repository port, which is correct, but the test fixtures should include empty-zones scenarios since this is the common case.

## 4. Suggestions

- **Specify parity functions in 02-01/02-03**: List the exact function calls, window sizes, and tolerance for the numeric/load parity check. Example: "Call `calc_banister(daily_trimp_dict)` with the pre- and post-migration output on observed-HR days; assert `fitness`, `fatigue`, `form` arrays match to ±0.1."
- **Add `training.py` to 02-03 files_modified**: The daily load status contract feeds Banister math directly.
- **Specify `effective_trimp` values for UNKNOWN/PARTIAL**: "effective_trimp = None (treated as 0 by EWMA gap-fill, matching current behavior)" or whatever the intended value is.
- **Specify backup retention**: e.g., "retain last 5 backups."
- **Clarify `init_db()` fate in 02-04**: State whether it's removed, refactored to assertion-only, or kept as migration baseline.
- **Specify the source boundary guard implementation**: AST-based or `rg`-based with a list of allowed paths.
- **Add empty-zones fixture scenario to test plans**: Ensure repository methods handle the common case of 0 athlete_zones rows.

## 5. Risk Assessment

**Overall: MEDIUM**

**Justification**: The plans correctly identify the core problems (fail-closed opens, backup-before-DDL, missing-HR false-rest semantics) and have the right architecture to solve them. The TDD approach and hermetic test commitment are sound. The dependency ordering between waves is correct.

However, two HIGH-severity gaps (unspecified parity computation and missing `training.py` in the read-path migration plan) could cause the plans to produce a repository boundary that looks structurally correct but doesn't actually verify that training math produces identical results on observed data — which is the core value of this phase. Without tightening these specifications, the parity gate risks being a shallow box-check rather than a genuine data-preservation guarantee.

The MEDIUM concerns (source guard implementation placement, undefined effective_trimp, unspecified backup retention, `init_db()` ambiguity, vague metrics.py scope) are addressable during execution with clarifications in the plan documents. No HIGH concerns exist around security, data loss (backup API is correctly chosen), or MCP boundary leakage (sync/admin stays out of repository design).

**Verdict**: Plans should proceed to execution after H-1 and H-2 are resolved in the plan documents. M-1 through M-5 can be handled as execution-time clarifications but should be noted in the plans for the executor.
