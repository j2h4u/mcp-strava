---
phase: 2
reviewers: [opencode, claude]
reviewed_at: 2026-05-21T10:32:55Z
plans_reviewed: [02-01-PLAN.md, 02-02-PLAN.md, 02-03-PLAN.md, 02-04-PLAN.md]
cycle: 2
previous_cycle_reviewed_at: 2026-05-21T10:21:36Z
replanning_commit: b1b3882
current_high: 0
---

# Cross-AI Plan Review - Phase 2

## Consensus Summary

Both requested reviewers found that the Cycle 2 replan fully resolves the four Cycle 1 HIGH concerns. The current plan set now includes explicit parity functions and tolerances, brings `training.py` into the load-status contract, retires `init_db()` schema-changing DDL from runtime/sync paths, and resolves the `metrics.py` boundary by requiring full repository-backed stream/activity reads with no source-guard allowlist exception.

Both reviewers reported:

`CYCLE_SUMMARY: current_high=0`

## Current HIGH Concerns

None.

### Agreed Strengths

- Cycle 1 HIGH concerns are addressed by explicit plan text, task actions, acceptance criteria, and automated test gates.
- Parity is now concrete: frozen windows/as-of inputs, named training/load functions, numeric tolerance, and a synthetic schema-changing migration test.
- `training.py` is included in the implementation and verification path for the `DailyLoadPoint.effective_trimp` series.
- `init_db()` is explicitly removed from schema-changing runtime behavior or reduced to assertion-only compatibility behavior, with sync/backfill prohibited from calling it.
- `metrics.py` is not allowlisted; Phase 2 must move its stream/activity SQL behind repository helpers.
- Formerly drifting defaults are pinned: busy timeout, backup directory/name/retention, operator command names, AST guard shape, and real-DB non-mutation snapshot checks.

### Agreed Concerns

No current HIGH concerns remain.

### Divergent Views

None material to convergence. Claude noted a few residual LOW/MEDIUM execution risks, such as concurrent sync versus `db-migrate` and the accepted operator `cmd_sql` DDL escape hatch, but did not classify them as phase-blocking.

## OpenCode Review

Now let me review each Cycle 1 HIGH against the current plan text.

---

# Cross-AI Plan Review - Phase 2 (Cycle 2)

## Cycle 1 HIGH Disposition

| # | Cycle 1 HIGH | Current Plan Evidence | Verdict |
|---|-------------|----------------------|---------|
| 1 | Parity verification under-specified | 02-01 _must_haves_ names exact functions (`get_daily_trimp_history(days=42)`, `calc_banister(..., today_str=as_of)`, `ewma(..., tau=7/28/42)`, report ACWR inputs), frozen `as_of` windows, tolerance <=0.1, and a synthetic schema-changing migration. | **FULLY RESOLVED** |
| 2 | `training.py` absent from 02-03 contract | 02-03 `files_modified` includes `src/mcp_strava/training.py`; `key_links` maps `types.py` -> `training.py`; _must_haves_ states `training.py` receives `{date: effective_trimp}` series. | **FULLY RESOLVED** |
| 3 | `init_db()` DDL not explicitly retired | 02-01 AC: `init_db()` contains no `CREATE TABLE`/`ALTER TABLE`; 02-04 AC: `sync.py` contains no `init_db(` calls and `init_db` is assertion-only; _must_haves_: sync paths assert schema through preflight, never call schema-changing bootstrap. | **FULLY RESOLVED** |
| 4 | `metrics.py` boundary vs source guard contradiction | 02-03 commits to full repository migration of all stream/activity SQL in `metrics.py` (10 functions enumerated in Task 2 action); 02-04 _must_haves_ and AC explicitly deny `metrics.py` from the allowlist and fail the guard if direct SQL remains. | **FULLY RESOLVED** |

All four Cycle 1 HIGHs are addressed by explicit plan text and verification criteria. No mitigation is merely implied - each has concrete acceptance criteria, task-level actions, and automated test gates.

## Current HIGH Concerns

None.

The replan is thorough. The plans now specify:

- Exact parity functions, frozen windows, and tolerances (02-01 _must_haves_)
- Synthetic migration to exercise unverified parity infrastructure (02-01 _must_haves_, Task 1 behavior)
- `effective_trimp` values for all four statuses (02-03 _must_haves_: `REST`/`UNKNOWN`/`PARTIAL` = 0.0, `OBSERVED` = observed)
- AST-based source guard with explicit allowlist and no `metrics.py` exception (02-02 Task 1, 02-04 _must_haves_)
- Operator command names pinned (`db-preflight`, `db-check`, `db-migrate` in 02-04 Task 2)
- Backup retention (5), directory (`data/backups/`), busy_timeout (5000ms) explicitly stated (02-01 Task 2)
- DB non-mutation check uses inode/size/mtime not `git status` (02-04 Task 3)
- Phase 1 test update in `files_modified` (02-01)

---

CYCLE_SUMMARY: current_high=0

## Current HIGH Concerns

None.

---

## Claude Review

# Phase 2 Plan Review - Cycle 2 (Claude)

## Summary

The Cycle 2 replan (b1b3882) addresses every Cycle 1 HIGH with concrete, verifiable acceptance criteria. The four areas that previously blocked execution - parity specificity, `training.py` inclusion, `init_db()` retirement, and `metrics.py` boundary - now have named functions, named files, named statements, and pass/fail thresholds. Defaults that were drifting (busy_timeout, backup retention/path/naming, operator command names, real-DB non-mutation check mechanics, fail-closed test split) are pinned. The plan set is ready to execute.

## Cycle 1 HIGH Resolution Check

### HIGH-1: Parity verification under-specified - FULLY RESOLVED

02-01 must_haves now name exact functions, arguments, and tolerance:

> "Parity compares exact functions and frozen windows: `get_daily_trimp_history(days=42, sport_filter='training')`, `calc_banister(..., today_str=as_of)`, `calc_banister_series(..., end_date=as_of)`, `ewma(..., tau=7/28/42, end_date=as_of)`, report ACWR inputs, and activity aggregate row counts with numeric tolerance <= 0.1 for rounded load outputs."

02-01 Task 1 acceptance also requires a **synthetic v1->v2 schema-changing test migration** so parity helpers are exercised against real before/after data rather than shipping unverified. Tests freeze `as_of`/today instead of wall-clock. This is the strongest possible Phase 2 specification of D-07.

### HIGH-2: `training.py` absent from load-status migration - FULLY RESOLVED

02-03 now lists `src/mcp_strava/training.py` in `files_modified`, adds a key_link `types.py -> training.py` via "DailyLoadPoint exposes observed numeric input separately from completeness status", and explicitly commits in must_haves: "`training.py` receives a plain `{date: effective_trimp}` series derived from `DailyLoadPoint.effective_trimp`; Banister, EWMA, ACWR, and weekly-plan behavior stay numeric and deterministic." Parity tests import training.py functions directly. Acceptance criterion: "`src/mcp_strava/training.py` is included in the implementation scope and still receives a `{date: numeric_effective_trimp}` mapping."

### HIGH-3: `init_db()` implicit DDL retirement - FULLY RESOLVED

02-01 Task 2 action now explicitly: "Convert `db.py::init_db()` from implicit `CREATE TABLE IF NOT EXISTS`/`ALTER TABLE` behavior to either an assertion-only compatibility wrapper around `schema.preflight()` or remove it from runtime callers; `init_db()` must issue no schema-changing DDL on read, report, sync, or backfill paths."

Acceptance: "`src/mcp_strava/db.py::init_db` either does not exist or contains no `CREATE TABLE`, `CREATE INDEX`, or `ALTER TABLE` statements."

02-04 reinforces from the sync side: "`src/mcp_strava/sync.py` contains no `init_db(` calls", with a test guard that fails if sync.py calls `init_db(` or if `init_db()` retains DDL. D-02 is now enforceable at phase exit.

### HIGH-4: `metrics.py` boundary conflict - FULLY RESOLVED

02-03 commits to full migration, not "where practical": "`metrics.py` stream access is fully moved behind repository helper methods in Phase 2; the pure cardiac drift algorithm in `cardiac_drift.py` is unchanged." Task 2 action enumerates every affected function (`_get_hr_max`, `_fetch_decoupling_rows`, `calc_cardiac_drift`, `calc_efficiency_factor`, `calc_hr_recovery`, `calc_vertical_speed`, `enrich_activity`, `check_z5_minutes`, `check_hr_anomalies`).

02-04 closes the door from the guard side: "The source guard does not allowlist `metrics.py`; Phase 2 execution must migrate its stream/activity SQL reads behind repository helper methods" - with a test guard that fails if metrics.py retains direct SQL. Plans 02-03 and 02-04 are now consistent.

## Other Improvements Worth Noting

- Defaults pinned: `PRAGMA busy_timeout=5000`, backup dir `data/backups/`, retention=5, filename `strava-YYYYMMDDTHHMMSSZ.db`.
- Fail-closed entrypoint split: `create_empty_mirror`/`open_fixture_db` separate from production `mode=rw` open; `test_phase01_validation.py` is in 02-01 `files_modified`.
- AST-based source guard with explicit Phase 2 allowlist (`adapters/sqlite/**`, `db.py` bridge, `cli.py::cmd_sql`, tests).
- Real-DB non-mutation check now uses `(exists, inode, size, mtime_ns)` snapshots; git status is supplemental only because the files are gitignored.
- Operator command names pinned: `db-preflight`, `db-check`, `db-migrate`.
- `DailyLoadPoint` semantics for UNKNOWN/PARTIAL explicitly specified: `effective_trimp=0.0` with `observed_trimp=None`, preserving current numeric behavior while keeping status distinct from REST.

## New HIGH Concerns Discovered in Cycle 2

Reviewed the plans for new gaps introduced by the replan or previously unsurfaced execution blockers. None found at HIGH severity:

- `get_daily_trimp_history` signature compatibility is now pinned (delegates internally, keeps `(conn, days, sport_filter)` shape).
- `training.py` change scope is bounded ("only as needed to accept or normalize...without changing Banister formulas").
- Concurrent sync vs `db-migrate` is not addressed but is single-operator and Phase 3+ concern.
- `cmd_sql` DDL escape hatch remains accepted (T-02-08) without a guard test that operators cannot loop back into migration tooling - minor, not phase-blocking.

These are LOW/MEDIUM at most and do not justify another replan cycle.

CYCLE_SUMMARY: current_high=0

## Current HIGH Concerns

None.
