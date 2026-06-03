---
phase: 15-self-invalidating-read-model-source-fingerprint-auto-recompu
plan: 04
subsystem: metric-platform
tags: [trimp, walk-discount, banister, read-model, fingerprint, zero-knob, recompute, per-sport]

requires:
  - phase: 15-01
    provides: "compute_logic_fingerprint() + COMPUTE_SOURCE_MODULES (constants.py is in the closure, so editing WALK_TRIMP_DISCOUNT flips the fingerprint)"
  - phase: 15-03
    provides: "materialize chokepoint that compares stored-vs-live fingerprint and bumps+enqueues+re-materializes on mismatch"
provides:
  - "WALK_TRIMP_DISCOUNT = 0.5 developer constant (constants.py, no env)"
  - "discounted_effective_trimp(by_sport) pure domain fn — Walk portion discounted, round ONCE at the end"
  - "observed_trimp_history_by_sport(...) per-day per-sport raw TRIMP aggregation (same range/bounds as observed_trimp_history)"
  - "daily_load_points_between applies the Walk discount to effective_trimp for OBSERVED days; observed_trimp stays the raw daily sum"
  - "First real end-to-end proof of the zero-knob auto-recompute: forced stored!=live fingerprint mismatch -> version bump + mass-enqueue + re-materialized discounted effective_trimp"
affects: ["future metric-constant edits ride this same auto-recompute pipeline", "any Banister/ACWR/form consumer now sees walk-discounted load"]

tech-stack:
  added: []
  patterns:
    - "Per-sport daily aggregation (GROUP BY day, sport_type) as a sibling of the per-day total, reusing build_trimp_sql + _sport_where_clause so the breakdown stays aligned with the total"
    - "Discount applied in the read-model assembly (effective_trimp), NOT in the SQL sum — observed stays raw, effective carries the multiplier, round once at the domain boundary"
    - "Zero-knob E2E proof via forced stored!=live fingerprint (option a): drive the real chokepoint compare-bump-enqueue-materialize path, not a monkeypatched constant"

key-files:
  created: []
  modified:
    - "src/mcp_strava/constants.py"
    - "src/mcp_strava/metrics.py"
    - "src/mcp_strava/adapters/duckdb/repository.py"
    - "tests/test_metrics_pure.py"
    - "tests/test_duckdb_repository.py"

key-decisions:
  - "WALK_TRIMP_DISCOUNT lives in constants.py (a COMPUTE_SOURCE_MODULES member) so editing it auto-recomputes by construction — no manual fingerprint manifest update needed; the 15-01 completeness AST-walk test already covers it"
  - "discounted_effective_trimp rounds ONCE on the final summed total (not per-sport), proven by a case where per-sport rounding would visibly differ ({Walk:0.25,Run:0.04} -> 0.2, not 0.1)"
  - "observed_trimp_history_by_sport returns UNDISCOUNTED raw per-sport values; the Walk multiplier is owned solely by discounted_effective_trimp in metrics.py (domain boundary), not by the SQL"
  - "E2E proof uses option (a) — a deliberately-wrong stored fingerprint forces the real chokepoint mismatch — because monkeypatching the in-memory constant does NOT change inspect.getsource text and so cannot drive a real recompute"
  - "repository.py imports metrics.discounted_effective_trimp: adapter-imports-domain is allowed and introduces no cycle (metrics.py imports only cardiac_drift/constants/types)"

patterns-established:
  - "Pattern 1: a per-sport daily aggregation mirrors its per-day total query (shared SQL builders + filters) so the two never drift"
  - "Pattern 2: sport-specific load adjustments live in a pure domain fn over a per-sport map, keeping the multiplier out of SQL and roundable once at the boundary"

requirements-completed: [REQ-WALK]

duration: 8min
completed: 2026-06-03
---

# Phase 15 Plan 04: Walk TRIMP Discount Summary

**WALK_TRIMP_DISCOUNT (0.5) now discounts the Walk-sport portion of each day's effective TRIMP via a pure per-sport domain fn, so effective_trimp < observed_trimp on walk days and the Banister load model stops counting walks at full load — and because the constant lives in a fingerprinted compute module, editing it auto-recomputes the read model end-to-end (proven by a forced stored!=live fingerprint mismatch driving a real version bump + mass-enqueue + re-materialize).**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-03T15:34:13Z
- **Completed:** 2026-06-03T15:42:40Z
- **Tasks:** 1 TDD feature (RED -> GREEN; REFACTOR folded into GREEN)
- **Files modified:** 5

## Accomplishments
- Added `WALK_TRIMP_DISCOUNT = 0.5` to `constants.py` — a developer constant (no env) inside the fingerprint closure, so editing it triggers auto-recompute with no manual version bump.
- Added `discounted_effective_trimp(by_sport)` to `metrics.py` — a pure domain fn that discounts only the Walk portion and rounds ONCE at the end (no per-sport rounding drift); imports no storage.
- Added `observed_trimp_history_by_sport(...)` to the repository — per-day per-sport raw TRIMP over the SAME range/bounds as `observed_trimp_history`, reusing `build_trimp_sql` + `_sport_where_clause`.
- Wired the discount into `daily_load_points_between`: OBSERVED days now set `effective_trimp = discounted_effective_trimp(day's per-sport map)`; `observed_trimp` stays the raw daily sum; the Banister series consumes the discounted value unchanged.
- Delivered the first real end-to-end proof of the zero-knob auto-recompute: a forced stored!=live fingerprint mismatch bumps the version, mass-enqueues, and re-materializes the walk day with the discounted effective TRIMP.

## Task Commits

This is a `type: tdd` plan executed as one feature through the RED/GREEN gate cycle:

1. **RED — failing tests for Walk TRIMP discount** - `772ec81` (test)
2. **GREEN — apply Walk TRIMP discount to daily effective_trimp** - `e4511a3` (feat)

**Plan metadata:** committed with this SUMMARY + STATE/ROADMAP/REQUIREMENTS (docs).

_REFACTOR gate: no separate commit — the domain boundary was clean by construction (metrics.py imports no storage) and the only cleanup (a `ruff format` reflow of the generator expression in `metrics.py`) was folded into the GREEN commit._

## Files Created/Modified
- `src/mcp_strava/constants.py` - `WALK_TRIMP_DISCOUNT = 0.5` with a plain-language comment explaining the discount and its zero-knob fingerprint coupling.
- `src/mcp_strava/metrics.py` - `discounted_effective_trimp(by_sport)` pure fn (per-sport multiplier, round once); imports `SPORT_WALK`/`WALK_TRIMP_DISCOUNT` + `collections.abc.Mapping`.
- `src/mcp_strava/adapters/duckdb/repository.py` - new `observed_trimp_history_by_sport(...)`; `daily_load_points_between` now fetches the per-sport map and applies the discount to `effective_trimp` for OBSERVED days; imports `discounted_effective_trimp`. Inline comments trace metric -> per-sport raw -> discounted effective at each hop.
- `tests/test_metrics_pure.py` - 6 pure-fn cases (constant=0.5, run-only unchanged, walk-only halved, mixed, empty=0.0, round-once-at-the-end).
- `tests/test_duckdb_repository.py` - per-sport breakdown test (same range as the total), the discount-walk-portion-only test (walk day discounted, run-only day unchanged), and the option-(a) zero-knob E2E recompute test.

## Decisions Made
See `key-decisions` frontmatter. Headlines: the discount is owned by the pure domain fn (out of SQL, rounded once); the per-sport aggregation mirrors the per-day total to stay aligned; the E2E proof drives the real fingerprint chokepoint (option a), not a patched constant.

## Deviations from Plan

None - plan executed exactly as written. (All four plan artifacts were produced; the discount was applied at the exact line the plan named — `daily_load_points_between` OBSERVED-day effective assignment — and the model-fact `observed_trimp` at `read_model_materializer.py:281` was left unchanged, consuming the discounted Banister `trimp` as the plan specified.)

## Issues Encountered
Two test-authoring corrections during the GREEN gate (the implementation was correct on first run; the tests asserted the right behavior the wrong way):

1. **Misplaced enqueue assertion in the E2E test.** I initially asserted `dirty_before >= 1` measured BEFORE calling the stage. But the N=1 cycle had already cleared the dirty queue, and the mass-enqueue we are proving happens INSIDE the stage. The recompute log confirmed `activities_enqueued: 2` and the version bump fired correctly. Fixed by asserting `activities_materialized` from the v2 run record instead — the correct proof the enqueue+recompute ran.
2. **Unpinned daily-fact fetch returned both versions.** `fetch_daily_load_facts(...)` without a `metric_version` arg returned both the v1 (first cycle) and v2 (recompute) rows for 2026-05-21, and `next()` picked v1. Fixed by pinning the fetch to `metric_version=2` (the bumped version).

Both were fixed within the GREEN gate; no production-code change was required for either.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The zero-knob auto-recompute is now validated end-to-end with a real metric-constant edit, closing REQ-WALK and giving 15-05 (workout time fields) a proven recompute foundation: any new computed field added to a fingerprinted module will recompute itself the same way.
- Walk-discounted effective TRIMP now flows into every downstream Banister/ACWR/form consumer; on the next live refresh of the dev instance the walk days will recompute their fatigue/form with the discount applied.

## Self-Check: PASSED

- FOUND: `src/mcp_strava/constants.py` (WALK_TRIMP_DISCOUNT)
- FOUND: `src/mcp_strava/metrics.py` (discounted_effective_trimp)
- FOUND: `src/mcp_strava/adapters/duckdb/repository.py` (observed_trimp_history_by_sport + discount wiring)
- FOUND: `tests/test_metrics_pure.py` (pure-fn cases)
- FOUND: `tests/test_duckdb_repository.py` (per-sport + discount + E2E tests)
- FOUND commit: `772ec81` (RED test)
- FOUND commit: `e4511a3` (GREEN feat)
- Gates: `ruff check` clean, `ruff format --check` clean (105 files), `pyright src` 0 errors, full `pytest` 374 passed (was 365; +9 new, no regressions); domain import-boundary + fingerprint-completeness guards (26 tests) green.

## TDD Gate Compliance
- RED gate present: `772ec81` `test(15-04): add failing tests for Walk TRIMP discount` (collection failed on the missing `WALK_TRIMP_DISCOUNT` import — a genuine RED).
- GREEN gate present: `e4511a3` `feat(15-04): apply Walk TRIMP discount to daily effective_trimp` (all 9 targeted tests + full suite green).
- REFACTOR gate: intentionally no separate commit (clean by construction; format reflow folded into GREEN).

---
*Phase: 15-self-invalidating-read-model-source-fingerprint-auto-recompu*
*Completed: 2026-06-03*
