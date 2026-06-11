---
phase: 15-self-invalidating-read-model-source-fingerprint-auto-recompu
plan: 06
subsystem: metric-platform
tags: [read-model, recompute, atomicity, transaction, duckdb-lock, timezone, utc, freshness, materializer, gap-closure]

requires:
  - phase: 15-03
    provides: "fingerprint compare+bump+enqueue chokepoint (materialize_read_model_stage), R11 version pin, _record_failed_run, partial-batch materialize"
provides:
  - "WR-01: fingerprint bump + mass-enqueue wrapped in one repo.begin()/commit() — atomic-or-nothing, so a failed enqueue cannot durably advance the stored fingerprint and silently strand reads at N+1"
  - "WR-02: freshness staleness clock is UTC end-to-end (_freshness_now) across all producers; instants compared in UTC, display/calendar values left local"
  - "WR-03: _record_failed_run commits through the lock-aware _commit_if_standalone()/rollback() under duckdb_process_lock()"
  - "WR-04: dirty_activity_rows_for_materialization extends a limited batch to whole-day boundaries so daily/rolling rollups never read a half-materialized day"
affects: [refresh, freshness, read-model-materializer]

tech-stack:
  added: []
  patterns:
    - "Compose two auto-committing repository writes into one atomic unit via repo.begin()/commit() (each helper _commit_if_standalone no-ops inside a tx)"
    - "Separate clocks by purpose: UTC-naive instant for staleness comparisons (_freshness_now), local wall-clock for calendar/display (as_of_day, start_time_local)"
    - "Whole-day batch boundaries: never split a calendar day's activities across recompute batches so per-day aggregates cannot transiently under-count"

key-files:
  created: []
  modified:
    - "src/mcp_strava/refresh/_sync_ops.py"
    - "src/mcp_strava/application/freshness.py"
    - "src/mcp_strava/application/metric_services.py"
    - "src/mcp_strava/application/aggregate_services.py"
    - "src/mcp_strava/application/product_facts.py"
    - "src/mcp_strava/adapters/duckdb/read_model_materializer.py"
    - "src/mcp_strava/adapters/duckdb/repository.py"
    - "tests/test_refresh_runtime.py"
    - "tests/test_application_services.py"
    - "tests/test_read_model_materialization.py"

key-decisions:
  - "WR-02 fixed by making the freshness instant UTC at every PRODUCER (the now-default path), not by zone-handling; health.py's local-vs-local datetime.now() pair was left untouched because both sides are local and internally consistent (changing one side would break the pair)"
  - "WR-02: relative_time treated as an instant duration (correct under UTC); only the start_time_local wall-clock label stays local — so defaulting product_facts/metric_services freshness clocks to UTC is safe for both freshness and relative_time"
  - "WR-04 fixed at the repository fetch boundary (whole-day extension in dirty_activity_rows_for_materialization), reviewer option (b), rather than per-fact completeness flags — a day is the atomic unit the daily/rolling rollups read"
  - "All four WARNINGs confirmed as REAL bugs against the source before fixing (verify-panel-findings-against-code); none were force-changed"

patterns-established:
  - "Pattern 1: atomic compose of standalone repository writes via an explicit transaction wrapper at the call site"
  - "Pattern 2: instant-comparison clocks are UTC-naive end-to-end; wall-clock/calendar values stay local — the two are threaded separately, never conflated"
  - "Pattern 3: recompute batches respect whole-day boundaries so per-day aggregate reads are never half-migrated"

requirements-completed: []

duration: ~45min
completed: 2026-06-04
---

# Phase 15 Plan 06: Harden the four advisory WARNINGs (WR-01..04) Summary

**Closed all four phase-15 review/verification WARNINGs as real bugs via TDD: atomic fingerprint bump+enqueue (no silent under-invalidation), UTC-end-to-end freshness clock (no Almaty-offset staleness skew), lock-honoring failed-run bookkeeping, and whole-day recompute batches (no partial-batch under-count).**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-06-04 (session start)
- **Completed:** 2026-06-04
- **Tasks:** 4 fixes (8 RED/GREEN commits + 1 style + 1 docs)
- **Files modified:** 10 (7 source, 3 test) + deferred-items

## Accomplishments

- **WR-01 (atomicity):** The fingerprint-mismatch branch of the materialize chokepoint now wraps `bump_logic_version` + `enqueue_metric_version_recompute` in one `repo.begin()/commit()` with rollback-on-error. A crash between the two steps can no longer durably advance the stored fingerprint while losing the mass-enqueue — the exact silent under-invalidation this phase exists to prevent. Proven by a test that injects an enqueue failure and asserts (via a reopened DB) the stored version/fingerprint did NOT advance, so the next cycle still detects the mismatch.
- **WR-02 (timezone skew):** Added `_freshness_now()` (UTC-naive, matching the basis `last_success_at` is parsed into) and routed the DEFAULTED freshness clock through it at every producer — `get_freshness_service`, the four `metric_services` call sites (via `_freshness_clock`), `aggregate_services`, and the three `product_facts` bundles. Staleness is now compared instant-to-instant in UTC; the Almaty (+5/+6) offset can no longer inflate computed age and misclassify a fresh mirror as aging/stale. Display-local `start_time_local` and the local-vs-local `health.py` pair were deliberately left untouched.
- **WR-03 (lock bypass):** `_record_failed_run` now commits via `repo._commit_if_standalone()` and rolls back via `repo.rollback()` — both hold `duckdb_process_lock()` — instead of raw `repo.conn.commit()/rollback()`. The failed-run bookkeeping can no longer interleave with another writer's transaction.
- **WR-04 (partial-batch under-count):** `dirty_activity_rows_for_materialization` now extends a limited batch to whole-day boundaries (rows are ordered by `activity_day, activity_id`, so only the last day can be cut — its remaining dirty rows are pulled in). Daily/rolling rollups never read a half-materialized day, so a day's load sums cannot under-count while its activity_count reports the full day.
- Full gate green: **389 passed** (was 385; +4 new tests, no regressions), `ruff check` / `ruff format --check` clean on in-scope files, `uv run pyright src` 0 errors.

## Task Commits

Each fix is an atomic RED (test) → GREEN (fix) pair:

1. **WR-01 atomic bump+enqueue** — `48e08d4` (test) → `9988fa1` (fix)
2. **WR-02 UTC freshness clock** — `d202e41` (test) → `94f15d2` (fix)
3. **WR-03 failed-run under process lock** — `8642502` (test) → `7bc30b4` (fix)
4. **WR-04 whole-day batch (no under-count)** — `2cbc610` (test) → `195d29b` (fix)

**Format fixup:** `6ad35b4` (style: ruff format the WR-01 test + WR-04 fix)
**Out-of-scope log:** `a9cb472` (docs: deferred-items)

## Files Created/Modified

- `src/mcp_strava/refresh/_sync_ops.py` — WR-01: wrap bump+enqueue in one transaction with rollback-on-error.
- `src/mcp_strava/application/freshness.py` — WR-02: add `_freshness_now()` (UTC-naive); use it as the `get_freshness_service` default.
- `src/mcp_strava/application/metric_services.py` — WR-02: add `_freshness_clock(now)`; route the four `build_freshness_metadata` calls through it (local `checked_at` kept for calendar/relative_time).
- `src/mcp_strava/application/aggregate_services.py` — WR-02: default the freshness-only `checked_at` to `_freshness_now()`.
- `src/mcp_strava/application/product_facts.py` — WR-02: default the three bundle `checked_at` clocks to `_freshness_now()` (calendar comes from the explicit `as_of_day`).
- `src/mcp_strava/adapters/duckdb/read_model_materializer.py` — WR-03: `_record_failed_run` commits via lock-aware helpers.
- `src/mcp_strava/adapters/duckdb/repository.py` — WR-04: whole-day extension in `dirty_activity_rows_for_materialization`.
- `tests/test_refresh_runtime.py` — WR-01 atomicity test.
- `tests/test_application_services.py` — WR-02 UTC-default freshness test (clock proxy simulating +6h skew).
- `tests/test_read_model_materialization.py` — WR-03 lock test + WR-04 whole-day under-count test.

## Decisions Made

See `key-decisions` frontmatter. Headlines:
- WR-02 is a UTC fix, not zone-handling. `health.py:138` (`datetime.now()` vs the worker's `datetime.now()`) is a deliberately-untouched local-vs-local pair — both sides are local and internally consistent, and the code already documents this; switching one side to UTC would BREAK the pair. Only genuinely mixed (UTC-stored vs local-now) freshness comparisons were corrected.
- `relative_time` is a duration between two instants, so it is correct (indeed better) under a UTC clock; only the `start_time_local` HH:MM wall-clock label must stay local — which it does (it is a materialized fact column, not derived from the freshness clock).
- WR-04 fixed at the repository fetch boundary (whole-day batch) rather than per-fact `completeness_status` flags, because the daily/rolling rollups read a whole DAY as their atomic unit; making the day the indivisible batch unit is the simplest correct fix and keeps the worker drain loop converging.

## Deviations from Plan

The objective explicitly authorized confirming whether each WARNING was a real bug and skipping any that were not. All four were confirmed real against the source and fixed; none were force-changed or skipped.

### Auto-fixed Issues

**1. [Rule 3 - Blocking] WR-04 test read used an exclusive-upper-bound day range**
- **Found during:** WR-04 RED
- **Issue:** `fetch_daily_load_facts(start, end, ...)` filters `day < end_day` (exclusive). The first draft passed `start == end == "2026-05-21"`, yielding an empty result and a misleading RED.
- **Fix:** Read range widened to `"2026-05-21" .. "2026-05-22"`; the RED then correctly demonstrated the under-count (activity 921 unmaterialized while the daily fact was written as complete).
- **Files modified:** `tests/test_read_model_materialization.py`
- **Verification:** RED then failed on the intended assertion (`fact_921 is None`); GREEN passes.
- **Committed in:** `2cbc610` (WR-04 RED)

**2. [Rule 3 - Blocking] WR-03 test could not monkeypatch the DuckDB connection's read-only `commit`**
- **Found during:** WR-03 RED
- **Issue:** `_duckdb.DuckDBPyConnection.commit` is a read-only C attribute — `monkeypatch.setattr(conn, "commit", ...)` raised `AttributeError`.
- **Fix:** Reframed the test to instrument `_commit_if_standalone` on a repo subclass and assert the failed-run path routes a depth-0 commit through the lock-aware helper (impossible under the buggy raw-commit code, which never reaches `_commit_if_standalone`).
- **Files modified:** `tests/test_read_model_materialization.py`
- **Verification:** RED fails with an empty `commit_under_lock` list; GREEN passes.
- **Committed in:** `8642502` (WR-03 RED)

---

**Total deviations:** 2 auto-fixed (both Rule 3 — test-harness blockers, not source bugs).
**Impact on plan:** None on scope. Both were test-construction issues resolved before the corresponding GREEN; the fixes and their proofs are exactly as the objective specified.

## Issues Encountered

- **Out-of-scope pre-existing drift in `deploy/gateway_register.py`** — `ruff check` flags `UP035` (`from typing import Callable`) and `ruff format --check` would reformat it. Both pre-exist HEAD and are untouched by 15-06 (deploy tooling, off the runtime import path), so per the scope boundary they were logged to `deferred-items.md`, NOT fixed. Suggest a quick `style`/`chore` task to run `ruff check --fix` + `ruff format` over `deploy/`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All four phase-15 advisory WARNINGs are closed with tests; the verification `human_needed` items (WR-01..04) are now hardened rather than accepted.
- No new threat surface introduced; no schema changes. The fixes are internal correctness hardening of the existing recompute/freshness paths.

## Self-Check: PASSED

- FOUND: `src/mcp_strava/refresh/_sync_ops.py` (WR-01)
- FOUND: `src/mcp_strava/application/freshness.py` (WR-02 `_freshness_now`)
- FOUND: `src/mcp_strava/adapters/duckdb/read_model_materializer.py` (WR-03)
- FOUND: `src/mcp_strava/adapters/duckdb/repository.py` (WR-04 whole-day batch)
- FOUND commit: `48e08d4` / `9988fa1` (WR-01 test/fix)
- FOUND commit: `d202e41` / `94f15d2` (WR-02 test/fix)
- FOUND commit: `8642502` / `7bc30b4` (WR-03 test/fix)
- FOUND commit: `2cbc610` / `195d29b` (WR-04 test/fix)
- Gates: `ruff check` clean, `ruff format --check` clean (in-scope), `uv run pyright src` 0 errors, `pytest` 389 passed (+4 new, no regressions).

---
*Phase: 15-self-invalidating-read-model-source-fingerprint-auto-recompu*
*Completed: 2026-06-04*
