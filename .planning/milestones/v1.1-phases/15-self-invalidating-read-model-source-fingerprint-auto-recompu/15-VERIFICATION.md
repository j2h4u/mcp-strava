---
phase: 15-self-invalidating-read-model-source-fingerprint-auto-recompu
verified: 2026-06-04T00:00:00Z
status: passed
score: 21/21 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 21/21
  gaps_closed:
    - "WR-01 — bump_logic_version + enqueue_metric_version_recompute now wrapped in one repo.begin()/commit() with rollback-on-error; atomic-or-nothing (fix 9988fa1, test 48e08d4)"
    - "WR-02 — freshness staleness clock is UTC-naive end-to-end via _freshness_now() across all producers; instant comparisons in UTC, display/calendar values stay local; health.py local-vs-local pair correctly untouched (fix 94f15d2, test d202e41)"
    - "WR-03 — _record_failed_run commits via lock-aware repo._commit_if_standalone()/rollback() under duckdb_process_lock() (fix 7bc30b4, test 8642502)"
    - "WR-04 — dirty_activity_rows_for_materialization extends a limited batch to whole-day boundaries so daily/rolling reads never under-count a half-recomputed version (fix 195d29b, test 2cbc610)"
  gaps_remaining: []
  regressions: []
---

# Phase 15: Self-invalidating read-model, walk TRIMP discount, workout time fields — Verification Report

**Phase Goal:** Auto-recompute materialized facts when metric code/constants change (source-derived fingerprint, no manual version knob); apply a configurable walk TRIMP discount; surface workout start time and relative-time.
**Verified:** 2026-06-04T00:00:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure (plan 15-06 hardened the four advisory WARNINGs WR-01..04 that left the initial pass at `human_needed`).

## Goal Achievement

All three goal pillars are implemented, wired, and proven by passing tests run in this verification (not trusted from SUMMARY):

1. **Zero-knob auto-recompute (REQ-ZEROKNOB)** — source-text fingerprint → sidecar version → chokepoint compare-bump-enqueue, fully wired.
2. **Walk TRIMP discount (REQ-WALK)** — `WALK_TRIMP_DISCOUNT=0.5` applied per-sport to daily `effective_trimp`; observed stays raw; Banister consumes discounted.
3. **Workout time fields (REQ-TIME)** — materialized `start_time_local` (HH:MM, fromisoformat/strftime) + read-time `relative_time` with correct 24h-boundary formatting.

The initial pass returned `human_needed` ONLY because four advisory WARNINGs (WR-01..04) were owner accept-or-harden decisions. The owner chose to HARDEN ALL FOUR; plan 15-06 closed each via a failing-test-first (RED) → fix (GREEN) commit pair. This re-verification confirms all four fixes are real and correct against source + tests, with no regressions to the 21 goal must-haves.

### Re-verification: gap closure (WR-01..04)

| WR | Fix | Source verified | Test (RED→GREEN) | Status |
| -- | --- | --------------- | ---------------- | ------ |
| WR-01 atomicity | `_sync_ops.py:335-344` — `repo.begin()` → `bump_logic_version` + `enqueue_metric_version_recompute` → `except: rollback()/raise` → `commit()`. Each helper `_commit_if_standalone` no-ops inside the tx, so the pair is all-or-nothing. | `_sync_ops.py:335-344` | `48e08d4` / `9988fa1`; `test_chokepoint_bump_and_enqueue_are_atomic_on_enqueue_failure` injects an enqueue crash AFTER the bump, **reopens a fresh repo**, and asserts durable version still `1` with the STALE fingerprint (NOT advanced to live) — so the next cycle still detects the mismatch and recomputes. | ✓ CLOSED |
| WR-02 UTC freshness | `application/freshness.py:22-34` `_freshness_now()` (UTC-naive). Defaulted at every producer: `get_freshness_service:140`, `metric_services._freshness_clock:386-395` (4 call sites), `aggregate_services:69`, `product_facts:60/235/352`. Staleness compares instant-to-instant in UTC against `last_success_at` (parsed UTC-naive by `_parse_dt`). The local `checked_at = now or datetime.now()` feeds only calendar/display (`_latest_as_of_day`, relative_time) — a deliberate separate clock. `health.py:137` `datetime.now()` vs worker `datetime.now()` is local-vs-local and internally consistent → correctly UNTOUCHED. `_now_parts`/`_record_failed_run` local `computed_at`/`finished_at` stamps are audit/display, NOT staleness-comparison inputs. | `application/freshness.py`, `metric_services.py`, `aggregate_services.py`, `product_facts.py`; `health.py` confirmed untouched | `d202e41` / `94f15d2`; `test_WR_02_freshness_now_default_is_utc_not_local` (clock proxy simulating +6h skew) | ✓ CLOSED |
| WR-03 lock | `read_model_materializer.py:392-400` `_record_failed_run` now commits via `repo._commit_if_standalone()` (holds `duckdb_process_lock()`) and rolls back via `repo.rollback()` — no raw `repo.conn.commit()/rollback()`. | `read_model_materializer.py:392-400` | `8642502` / `7bc30b4`; `test_WR_03_record_failed_run_commits_under_process_lock` instruments `_commit_if_standalone` on a repo subclass and asserts the depth-0 failed-run commit routes through the lock-aware helper (impossible under the buggy raw-commit path). | ✓ CLOSED |
| WR-04 partial-batch | `repository.py:616-654` `dirty_activity_rows_for_materialization` — rows ordered by `(activity_day, activity_id)`, so only the LAST day of a limited slice can be cut; it pulls that day's remaining dirty rows (`WHERE ... AND activity_day = CAST(? AS DATE)`), de-duped by `activity_id`. Daily/rolling rollups therefore never read a half-materialized day. | `repository.py:616-654` | `2cbc610` / `195d29b`; `test_WR_04_partial_batch_does_not_undercount_daily_facts` (read range `2026-05-21..2026-05-22`; RED demonstrated the under-count, GREEN passes). | ✓ CLOSED |

All eight RED/GREEN commits exist at HEAD with correct ordering (verified via `git cat-file -t`); 4 new tests pass; full suite advanced 385 → **389 passed**, no regressions.

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | `compute_logic_fingerprint()` returns same 64-char sha256 hex across processes / PYTHONHASHSEED | ✓ VERIFIED | `metric_registry.py:2504`; import printed 64-char hex; `test_fingerprint_matches_fresh_subprocess` + `test_fingerprint_independent_of_pythonhashseed` pass |
| 2 | Editing a listed module's source flips fingerprint; unlisted does not | ✓ VERIFIED | `test_altering_a_listed_module_changes_fingerprint` + `test_altering_an_unlisted_module_does_not_change_fingerprint` pass |
| 3 | Completeness poka-yoke fails (CI red) if a materializer-path compute module is omitted from `COMPUTE_SOURCE_MODULES` | ✓ VERIFIED | `test_compute_source_modules_covers_full_compute_path` + `test_materializer_direct_imports_are_all_listed` pass; tuple is full 14-module closure incl. `metric_registry` |
| 4 | `metric_registry` is in the tuple so registry-owned schema (start_time_local) flips the fingerprint | ✓ VERIFIED | `test_metric_registry_is_listed` passes; `COMPUTE_SOURCE_MODULES` at `metric_registry.py:2486` includes it |
| 5 | `read_model_logic_version` singleton table exists, seeded at current fingerprint so first refresh after deploy does NOT recompute | ✓ VERIFIED | `schema.py:262` CREATE IF NOT EXISTS + `schema.py:25` in DUCKDB_TABLES; `test_logic_version_seed_adopts_current_fingerprint_on_fresh_db` passes |
| 6 | `current_metric_version()` / `current_logic_version()` / `bump_logic_version()` round-trip | ✓ VERIFIED | `repository.py:730/745/765`; `test_logic_version_helpers_round_trip_via_bump` passes |
| 7 | `bump_logic_version()` invalidates the `current_metric_version` memo (no stale pre-bump version) | ✓ VERIFIED | `repository.py:787` resets cache to None; `test_bump_logic_version_invalidates_current_metric_version_memo` passes |
| 8 | Seed wrapped in try/except so ImportError/getsource OSError does not break from_connection() | ✓ VERIFIED | `test_logic_version_seed_skips_on_import_error_and_reads_fall_back` passes (falls back to fact-table max) |
| 9 | Chokepoint: live≠stored fingerprint → bump version, record fingerprint, enqueue every activity, no manual step | ✓ VERIFIED | `_sync_ops.py:324-353` bump+enqueue+`logic_fingerprint_changed`; `test_chokepoint_materializes_at_bumped_version_on_fingerprint_mismatch` passes |
| 10 | Chokepoint re-resolves version INTERNALLY post-bump (enqueue N+1 == materialize N+1) | ✓ VERIFIED | `_sync_ops.py:357` `current_version = repo.current_metric_version()` AFTER bump; stage no longer takes a caller metric_version; regression test asserts materialize==N+1 |
| 11 | Unseeded sidecar → ADOPT-CURRENT self-heal (write sidecar, no enqueue), no restart needed | ✓ VERIFIED | `_sync_ops.py:312-323` adopt branch + `read_model_logic_adopted` event; `test_chokepoint_adopts_current_when_sidecar_unseeded` passes |
| 12 | Fingerprint check runs even when dirty queue empty (logic-only edit still recomputes) | ✓ VERIFIED | `worker.py:65` no longer early-returns; calls `materialize_read_model_stage` on `dirty_count==0` |
| 13 | `CURRENT_METRIC_VERSION` deleted everywhere incl. `__init__` re-export + `__all__` | ✓ VERIFIED | `grep -rn CURRENT_METRIC_VERSION src/` returns nothing |
| 14 | Aggregate AND status reads pin `metric_version = current` (no old+new blend, R11) | ✓ VERIFIED | 7 `FROM activity_metric_facts` SELECTs each carry `metric_version = ?`; `test_missing_denominators_explicit_and_version_pin_blocks_blend` passes |
| 15 | `aggregate_services.py` threads current version into status + training aggregate reads | ✓ VERIFIED | `aggregate_services.py` resolve+pass `version` |
| 16 | Auto-recompute emits structured log w/ stored/current fingerprint, reason, activities_enqueued, queued_at; run record stamped trigger_reason | ✓ VERIFIED | `_sync_ops.py:346-353` event fields; `read_model_materializer.py` trigger_reason threaded+stamped |
| 17 | Walk day yields effective_trimp lower than observed by walk portion × (1−discount); non-walk unchanged | ✓ VERIFIED | `discounted_effective_trimp` Run100→100, Walk80→40, mix→140, empty→0; `repository.py:1510` applies it; `test_walk_discount_recomputes_end_to_end_on_fingerprint_mismatch` passes |
| 18 | observed_trimp stays raw undiscounted in daily + model facts; round once at end | ✓ VERIFIED | `metrics.py:327` single `round` over the summed product; `read_model_materializer.py` observed left raw |
| 19 | Editing WALK_TRIMP_DISCOUNT flips fingerprint; E2E option-(a) forced stored≠live proves the pipeline fires (version N→N+1, enqueue, re-materialized discount) | ✓ VERIFIED | `constants.py` is in COMPUTE_SOURCE_MODULES; `test_walk_discount_recomputes_end_to_end_on_fingerprint_mismatch` asserts version bump + enqueue + re-materialized effective_trimp |
| 20 | `start_time_local` materialized via fromisoformat+strftime (not [11:16] slice); Z/offset normalized; None on garbage; migrates additively | ✓ VERIFIED | `metrics.py:17` parse_local_hhmm (Z→06:00, offset→11:16, garbage→None); `read_model_materializer.py:228` populates; `schema.py:300` late column |
| 21 | `relative_time` read-time: <24h 'Hh Mm', ≥1d 'Nd Hh', 24h boundary '1d 0h', None on missing | ✓ VERIFIED | `metric_services.py:294` `_relative_time`; spot-check 2h30m→'2h 30m', exactly24h→'1d 0h', 3d4h→'3d 4h', future→'0h 0m', garbage→None |

**Score:** 21/21 truths verified

> Goal must-haves were verified in full in the initial pass and spot-checked here via the green suite (389 passed). No regression: the 15-06 fixes touch only freshness-clock defaults, the failed-run commit path, the dirty-batch fetch boundary, and the bump+enqueue transaction wrapper — none alter the fingerprint/discount/time-field happy path.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/mcp_strava/refresh/_sync_ops.py` | WR-01: atomic bump+enqueue in one repo.begin()/commit() | ✓ VERIFIED | @335-344 begin/try/rollback/commit; helpers no-op inside tx |
| `src/mcp_strava/application/freshness.py` | WR-02: `_freshness_now()` UTC-naive default | ✓ VERIFIED | @22-34; used as default in `get_freshness_service` and re-exported |
| `src/mcp_strava/application/metric_services.py` | WR-02: `_freshness_clock(now)` routes 4 freshness call sites | ✓ VERIFIED | @386-395; build_freshness_metadata gets `_freshness_clock(now)`; local `checked_at` kept for calendar |
| `src/mcp_strava/application/aggregate_services.py` | WR-02: freshness `checked_at` defaults to `_freshness_now()` | ✓ VERIFIED | @69 |
| `src/mcp_strava/application/product_facts.py` | WR-02: three bundle clocks default to `_freshness_now()` | ✓ VERIFIED | @60/235/352 |
| `src/mcp_strava/adapters/duckdb/read_model_materializer.py` | WR-03: `_record_failed_run` commits via lock-aware helpers | ✓ VERIFIED | @392-400 `_commit_if_standalone()`/`rollback()`; no raw conn.commit |
| `src/mcp_strava/adapters/duckdb/repository.py` | WR-04: whole-day extension in `dirty_activity_rows_for_materialization` | ✓ VERIFIED | @616-654; remainder pull for last day, de-duped |
| `src/mcp_strava/refresh/health.py` | WR-02: local-vs-local pair deliberately UNTOUCHED | ✓ VERIFIED | @137 `datetime.now()` vs worker `datetime.now()`; documented internally-consistent local pair |
| `tests/test_refresh_runtime.py` | WR-01 atomicity test (reopen-DB durability assertion) | ✓ VERIFIED | `test_chokepoint_bump_and_enqueue_are_atomic_on_enqueue_failure` passes |
| `tests/test_application_services.py` | WR-02 UTC-default freshness test | ✓ VERIFIED | `test_WR_02_freshness_now_default_is_utc_not_local` passes |
| `tests/test_read_model_materialization.py` | WR-03 lock test + WR-04 whole-day under-count test | ✓ VERIFIED | `test_WR_03_record_failed_run_commits_under_process_lock` + `test_WR_04_partial_batch_does_not_undercount_daily_facts` pass |

(The phase-goal artifacts — metric_registry, schema, aggregate_queries, constants, metrics, AGENTS.md, etc. — were VERIFIED in the initial pass and remain green; re-listed there.)

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `_sync_ops` fingerprint-mismatch branch | `bump_logic_version` + `enqueue_metric_version_recompute` | one `repo.begin()/commit()` (rollback on error) | ✓ WIRED | @335-344; atomic-or-nothing — proven by WR-01 reopen-DB test |
| `metric_services` / `aggregate_services` / `product_facts` / `get_freshness_service` | `build_freshness_metadata` staleness `now` | `_freshness_now()` (UTC-naive) default | ✓ WIRED | comparison clock UTC; local `checked_at` separated for calendar/display |
| `_record_failed_run` | `duckdb_process_lock()` | `repo._commit_if_standalone()` / `repo.rollback()` | ✓ WIRED | @392-400; raw conn.commit removed |
| `dirty_activity_rows_for_materialization` (limited) | whole-day batch | last-day remainder pull, de-dup by activity_id | ✓ WIRED | @643-654 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 8 RED/GREEN commits exist at HEAD, correct order | `git cat-file -t` + `git log --oneline` | all 8 OK; RED before GREEN per WR | ✓ PASS |
| WR-01..04 targeted tests | `pytest -k "atomic or utc or freshness or lock or commit or whole_day or under_count or partial or process_lock"` | 9 passed (incl. all 4 named WR tests) | ✓ PASS |
| ruff check src tests | `uv run ruff check src tests` | All checks passed | ✓ PASS |
| ruff format --check src tests | `uv run ruff format --check src tests` | 105 files already formatted | ✓ PASS |
| pyright src | `uv run pyright src` | 0 errors, 0 warnings, 0 informations | ✓ PASS |
| Full unit suite | `.venv/bin/python -m pytest -q` | 389 passed (was 385; +4 new WR tests, no regressions) | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes declared for this phase. Equivalent runnable verification covered by the unit suite (run above, 389 passed).

### Requirements Coverage

Unchanged from the initial pass. Phase-local labels REQ-ZEROKNOB / REQ-WALK / REQ-TIME are all SATISFIED (truths 1-21). No orphaned formal REQUIREMENTS.md ID is assigned to Phase 15.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| metrics.py / read_model_materializer.py / metric_services.py / health.py | various | `except A, B:` (PEP 758) | ℹ️ Info | NOT a defect — valid bare-tuple syntax on Python ≥3.14 (project pinned 3.14.2); compiles, lints, 389 tests pass. Reviewer CR-01 BLOCKER correctly dismissed. |

All four prior ⚠️ WARNINGs (WR-01 non-atomic bump+enqueue, WR-02 local/UTC staleness skew, WR-03 lock bypass, WR-04 partial-batch under-count) are now CLOSED with tests (see re-verification table). No debt markers (TBD/FIXME/XXX without follow-up) found in phase-15 files. No stub/placeholder/empty-return anti-patterns.

> Out-of-scope pre-existing drift in `deploy/gateway_register.py` (ruff `UP035` + format) dates to phase 05, NOT phase 15; already logged in `deferred-items.md`. Not charged against this phase.

### Human Verification Required

None. The four advisory WARNINGs that left the initial pass at `human_needed` have been hardened (owner chose harden-all) and are now proven by tests. Per project memory ("prefer scripted verification over human_needed"), each WR was closed with a failing-test-first proof rather than punted to the operator.

### Gaps Summary

No gaps. All 21 must-have truths remain VERIFIED, and all four advisory WARNINGs (WR-01..04) are closed against the source with RED→GREEN test pairs that exist at HEAD:

- **WR-01** — bump+enqueue atomic in one `repo.begin()/commit()`; the durability test reopens a fresh DB and confirms a failed enqueue does NOT advance the stored fingerprint, so the next cycle still recomputes.
- **WR-02** — staleness clock UTC-naive end-to-end (`_freshness_now()`) at every producer; the Almaty offset can no longer skew computed age. `health.py`'s local-vs-local pair was correctly left untouched (changing one side would break the pair); local `checked_at` is a separate calendar/display clock, not a staleness input.
- **WR-03** — `_record_failed_run` honors `duckdb_process_lock()` via `_commit_if_standalone()`/`rollback()`.
- **WR-04** — `dirty_activity_rows_for_materialization` extends a limited batch to whole-day boundaries, so daily/rolling rollups never read a half-materialized day.

Gates green: ruff check + ruff format --check clean, `uv run pyright src` 0 errors, **389 pytest pass** (385 + 4 new WR tests, zero regressions). The phase goal — zero-knob auto-recompute, walk TRIMP discount, and workout time fields — is achieved and hardened. **Status: passed.**

---

_Verified: 2026-06-04T00:00:00Z (re-verification after gap closure)_
_Verifier: Claude (gsd-verifier)_
