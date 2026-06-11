---
phase: 15-self-invalidating-read-model-source-fingerprint-auto-recompu
plan: 03
subsystem: metric-platform
tags: [fingerprint, read-model, self-invalidation, recompute, metric-version, R11, observability]
requires:
  - phase: 15-01
    provides: "compute_logic_fingerprint() + COMPUTE_SOURCE_MODULES (live source-text fingerprint)"
  - phase: 15-02
    provides: "read_model_logic_version sidecar + current_metric_version/current_logic_version/bump_logic_version + adopt-current seed (stored-is-None self-heal deferred here)"
provides:
  - "Fingerprint compare + bump + mass-enqueue trigger at the single materialize chokepoint (wires the orphan enqueue_metric_version_recompute)"
  - "Stored-is-None adopt-current self-heal at the chokepoint (heals a transient 15-02 seed failure without a restart)"
  - "materialize_read_model_stage with the caller-passed metric_version REMOVED — the stage re-resolves the version internally post-bump (enqueue version == materialize version)"
  - "cached_logic_fingerprint() per-process memo of the live fingerprint"
  - "Worker empty-queue gate: a logic-only edit with no dirty source rows is still detected"
  - "R11 metric_version=current pin across _where_clause, _effective_range_for_metric, and every query_status_facts SELECT"
  - "CURRENT_METRIC_VERSION constant fully deleted; all paths source the int from repo.current_metric_version()"
  - "Self-explanatory observability: read_model_logic_recompute / _adopted / materialize-done events; trigger_reason=logic_fingerprint_changed on the refresh-run record"
affects:
  - "15-04 rides this trigger to validate the WALK_TRIMP_DISCOUNT auto-recompute end-to-end"
tech-stack:
  added: []
  patterns:
    - "Compare-and-bump-and-enqueue at a single chokepoint; version re-resolved INTERNALLY post-bump (never caller-passed) so enqueue N+1 == materialize N+1"
    - "Adopt-current self-heal on unseeded sidecar (write current/fallback version + live fingerprint, enqueue nothing)"
    - "Per-process module-level memo for the live fingerprint (cached wrapper, not lru_cache, so getsource-monkeypatch tests bypass it)"
    - "R11 version pin as a parameterized `metric_version = ?` predicate threaded from the caller, never string-formatted (T-15-05)"
key-files:
  created: []
  modified:
    - "src/mcp_strava/refresh/_sync_ops.py"
    - "src/mcp_strava/refresh/runtime.py"
    - "src/mcp_strava/refresh/worker.py"
    - "src/mcp_strava/metric_registry.py"
    - "src/mcp_strava/adapters/duckdb/repository.py"
    - "src/mcp_strava/adapters/duckdb/__init__.py"
    - "src/mcp_strava/adapters/duckdb/read_model_materializer.py"
    - "src/mcp_strava/adapters/duckdb/aggregate_queries.py"
    - "src/mcp_strava/application/metric_services.py"
    - "src/mcp_strava/application/aggregate_services.py"
    - "src/mcp_strava/application/product_facts.py"
    - "tests/test_refresh_runtime.py"
    - "tests/test_training_aggregates.py"
    - "AGENTS.md"
key-decisions:
  - "materialize_read_model_stage drops the caller-passed metric_version and re-resolves it internally AFTER the bump/adopt, so the enqueue version and materialize version can never disagree (cycle-2 stale-version guard)"
  - "Worker empty-queue gate uses option (b): on dirty_count==0 still call the chokepoint once (cheap no-op on fingerprint match, recompute on mismatch), rather than moving the fingerprint check ahead of the dirty-count read"
  - "Unseeded sidecar self-heals by adopting current (write sidecar, enqueue nothing) — auto-recompute is robust to a transient 15-02 seed failure without a repo re-creation or restart"
  - "R11 pin threaded as an explicit metric_version param resolved by the caller (aggregate_services / product_facts), not a dataclass field, matching the plan's 'resolved by the CALLER' directive"
  - "test fixture: reverted the deliberate v2 activity/model facts back to v1 and added one dedicated v2 stale row (activity 106) so the version-pin test proves exclusion without shifting every other fixture-coupled numeric expectation"
patterns-established:
  - "Pattern 1: a single self-invalidating chokepoint owns detect -> bump -> enqueue -> materialize, with the version re-resolved post-bump"
  - "Pattern 2: per-process memo of an immutable-within-process value (live source fingerprint) to bound idle-cycle cost"
requirements-completed: [REQ-ZEROKNOB]
duration: 28min
completed: 2026-06-03
---

# Phase 15 Plan 03: Wire the Detector to the Recompute Summary

**The materialize chokepoint now self-invalidates: a live-vs-stored source-fingerprint mismatch bumps metric_version, mass-enqueues every activity, and recomputes at the just-bumped version — the hand-maintained `CURRENT_METRIC_VERSION` constant is gone and all aggregate/status reads pin to the current version (R11), so a logic edit recomputes itself with no manual step and a mixed-version DB never blends.**

## Performance

- **Duration:** ~28 min
- **Started:** 2026-06-03T15:00:00Z (approx)
- **Completed:** 2026-06-03T15:28:00Z
- **Tasks:** 4
- **Files modified:** 14

## Accomplishments
- Wired the orphan `enqueue_metric_version_recompute`: at the single materialize chokepoint, `stored != live` fingerprint bumps the version, records the new fingerprint, and enqueues every activity — auto-recompute now actually happens.
- Closed the cycle-2 stale-version hole: `materialize_read_model_stage` no longer accepts a caller-passed `metric_version`; it re-resolves the version INTERNALLY post-bump so the enqueue version (N+1) and the materialize version (N+1) are guaranteed equal.
- Implemented the 15-02-deferred `stored is None` adopt-current self-heal, so a transient seed failure heals on the next loaded-modules cycle without a process restart.
- Deleted `CURRENT_METRIC_VERSION` everywhere; every read/materialize/enqueue path sources the int from `repo.current_metric_version()`.
- R11: pinned `metric_version = current` across `_where_clause`, `_effective_range_for_metric`, and every `query_status_facts` SELECT — point, aggregate, AND status reads return only-current-or-empty.
- Self-explanatory observability events plus a per-process fingerprint memo so idle cycles do not re-walk `inspect.getsource`.

## Task Commits

1. **Task 1 + Task 2: delete CURRENT_METRIC_VERSION; fingerprint trigger + observability + worker empty-queue gate** - `8d0032b` (feat) — combined per the plan's caller-edit atomicity note (Task 1 constant removal and Task 2 stage-signature change edit the same runtime.py/worker.py caller lines and must land together).
2. **Task 3: R11 metric_version pin across all aggregate + status reads** - `8df4ae8` (feat)
3. **Task 4: AGENTS.md plain-language self-recompute line** - `a617f07` (docs)

_Note: Tasks 1 and 2 share a commit because their caller edits are entangled (an intermediate state where the constant is deleted but the stage still requires the param would not import/run)._

## Files Created/Modified
- `src/mcp_strava/refresh/_sync_ops.py` - The chokepoint: fingerprint compare -> bump+enqueue or adopt-current; internal post-bump version resolution; recompute/adopted/materialize-done events; module-level `_emit`.
- `src/mcp_strava/metric_registry.py` - `cached_logic_fingerprint()` per-process memo of the live fingerprint (uncached `compute_logic_fingerprint()` retained for seed + tests).
- `src/mcp_strava/refresh/runtime.py` / `worker.py` - Updated chokepoint callers to stop passing `metric_version`; worker no longer early-returns past the fingerprint check on an empty dirty queue.
- `src/mcp_strava/adapters/duckdb/repository.py` - Removed `CURRENT_METRIC_VERSION`; made `update_activity_source_state_and_enqueue_dirty`'s `metric_version` required; internal callers pass `self.current_metric_version()`.
- `src/mcp_strava/adapters/duckdb/read_model_materializer.py` - `materialize_read_model` `metric_version` made required; new `trigger_reason` param threaded into the refresh-run record.
- `src/mcp_strava/adapters/duckdb/__init__.py` - Dropped the `CURRENT_METRIC_VERSION` re-export + `__all__` entry.
- `src/mcp_strava/adapters/duckdb/aggregate_queries.py` - R11 `metric_version = ?` pin in `_where_clause`, `_effective_range_for_metric`, `_activity_fact_count`, and every status-path `activity_metric_facts` SELECT; new `metric_version` param on `query_training_aggregates`/`query_status_facts` and the internal helpers.
- `src/mcp_strava/application/metric_services.py` - All `CURRENT_METRIC_VERSION` uses re-sourced from `repo.current_metric_version()`.
- `src/mcp_strava/application/aggregate_services.py` - Resolves the current version once and threads it into `read_model_status()` + `query_training_aggregates()`.
- `src/mcp_strava/application/product_facts.py` - Resolves + threads the current version into `query_status_facts()`.
- `tests/test_refresh_runtime.py` - Two new regression tests (stale-version N+1 guard, adopt-current self-heal); existing fakes updated to the new stage signature + `current_metric_version`.
- `tests/test_training_aggregates.py` - All aggregate/status calls pass `metric_version=1`; fixture seeds the sidecar to v1 and a dedicated v2 stale row (106); mixed-version test rewritten to assert no-blend (`metric_version_status == "single"`).
- `AGENTS.md` - One plain-language sentence: the read-model self-recomputes on any metric logic change, no version bump, no manual step.

## Decisions Made
See `key-decisions` frontmatter. Headline: the stage re-resolves the version internally post-bump (never caller-passed), and the worker empty-queue gate uses option (b) (call the chokepoint once on an empty queue) for the smaller change.

## Deviations from Plan

### Test-fixture adjustment (not a deviation rule, but a notable execution choice)

**1. Reverted the deliberate v2 fixture rows to v1 + added one dedicated v2 stale row**
- **Found during:** Task 3 — the R11 pin made the existing `_aggregate_fixture` mixed-version rows (activity 103 at v2, a v2 model fact) get filtered out, shifting numeric expectations in 4 unrelated tests (all-time defaults, registry modes, compare-periods, the old mixed test).
- **Issue:** Those rows existed only to feed the old "blend is visible" assertion, which R11 now forbids.
- **Fix:** Reverted 103 and the model fact to v1 (restoring every other test's numbers) and added one dedicated v2 stale activity (id 106, trimp 12345.0) in the same May bucket. The version-pin test asserts the pin excludes 106 (`metric_version_status == "single"`, aggregate value 310.0 not 12655.0, status read current-only). This keeps the R11 proof while avoiding blast-radius recompute of fixture-coupled numbers.
- **Files modified:** `tests/test_training_aggregates.py`
- **Verification:** `uv run pytest -q tests/test_training_aggregates.py` — all pass.
- **Committed in:** `8df4ae8`

---

**Total deviations:** 0 auto-fixed under Rules 1-4 (the fixture change above is planned test-maintenance the plan explicitly anticipated: "Update any existing mixed-version aggregate test to assert the new 'pinned current' behavior").
**Impact on plan:** None — all four tasks executed as written; the fixture reshaping is the lower-blast-radius way to satisfy the plan's own "assert pinned-current, keep metric_version_count as the tripwire" instruction.

## Issues Encountered
- The full suite's `current_metric_version()` resolution exposed several worker-path `FakeRepo` test doubles that lacked the method (they previously relied on the deleted constant). Added `current_metric_version` to each and stubbed the chokepoint for the periodic-refresh-cycle tests that now reach the empty-queue gate. Resolved; no production impact.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The detector is now wired to the recompute end-to-end: 15-04 can add `WALK_TRIMP_DISCOUNT` (a metric-constant edit) and expect the facts to recompute themselves on the next refresh with no manual version bump.
- The R11 pin closes the digest version-blend hole; aggregate/status reads are current-only.

## Self-Check: PASSED

- FOUND: `src/mcp_strava/refresh/_sync_ops.py` (chokepoint trigger)
- FOUND: `src/mcp_strava/adapters/duckdb/aggregate_queries.py` (R11 pin)
- FOUND: `tests/test_refresh_runtime.py` (stale-version + adopt tests)
- FOUND: `tests/test_training_aggregates.py` (version-pin no-blend test)
- FOUND: `AGENTS.md` (self-recompute line)
- FOUND: `.planning/phases/15-.../15-03-SUMMARY.md`
- FOUND commit: `8d0032b` (Task 1+2 feat)
- FOUND commit: `8df4ae8` (Task 3 feat)
- FOUND commit: `a617f07` (Task 4 docs)
- Gates: `ruff check` clean, `ruff format --check` clean (105 files), `pyright src` 0 errors, `pytest` 365 passed (was 363; +2 new tests, no regressions).

---
*Phase: 15-self-invalidating-read-model-source-fingerprint-auto-recompu*
*Completed: 2026-06-03*
