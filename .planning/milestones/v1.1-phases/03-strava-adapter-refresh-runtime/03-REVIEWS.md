---
phase: 3
cycle: 2
reviewers: [opencode]
opencode_model: deepseek-v4-pro
reviewed_at: 2026-05-21
plans_reviewed:
  - 03-01-PLAN.md
  - 03-02-PLAN.md
  - 03-03-PLAN.md
  - 03-04-PLAN.md
cycle_1_highs_status:
  HIGH-1_D-15: FULLY_RESOLVED
  HIGH-2_D-16: FULLY_RESOLVED
  HIGH-3_D-17: FULLY_RESOLVED
  HIGH-4_D-18: FULLY_RESOLVED
  HIGH-5_D-19: FULLY_RESOLVED
new_highs_this_cycle: 0
---

# Cross-AI Plan Review — Phase 3 (Cycle 2)

> Cycle 1 review (OpenCode / deepseek-v4-pro) raised 5 HIGH-severity concerns
> against the original plan set. Commit `57c4890` landed `03-DECISIONS.md`
> (D-15…D-19) plus propagation edits to every PLAN.md and to PATTERNS.md.
> This cycle independently verifies whether each cycle-1 HIGH is closed and
> surfaces any newly raised concerns.

## OpenCode Review (cycle 2)

## Part A — Cycle-1 HIGH Resolution Verification

- **HIGH-1 (D-15):** **FULLY RESOLVED** — D-15 adds `force` parameter to `run_once` and wires `sync_activities(quick=True)` to `run_once(force=True, mode='quick')`. The `db-refresh` CLI accepts `--force`. All affected plans (`03-02-PLAN.md` must‑haves and tasks, `03-04-PLAN.md` truths and boundary test `test_sync_activities_quick_invokes_run_once_with_force_true_per_D15`) enforce the contract.  
- **HIGH-2 (D-16):** **FULLY RESOLVED** — `run_backfill` is a separate entrypoint with stage subset `streams_backfill`, `details_backfill`, distinct lease owner `refresh-backfill`. Plans `03-02` (Task 2, checks, `run_backfill` implementation) and `03-04` (truth “`backfill_activities` calls `run_backfill`”, test `test_backfill_activities_invokes_run_backfill_per_D16`) lock the design.  
- **HIGH-3 (D-17):** **FULLY RESOLVED** — Helpers move to `refresh/_sync_ops.py` (private). One‑way dependency enforced by AST guard `test_refresh_does_not_import_sync` in `03-04` and explicit deletion from `sync.py`. Plans `03-02` truth “`refresh/*` no `from mcp_strava.sync`” and `03-04` truth “`sync.py` no longer defines those names” are consistent.  
- **HIGH-4 (D-18):** **FULLY RESOLVED** — `TokenRefreshTransport` owns its own retry budget (3 attempts, `[2,8,30]` backoff) independent of data‑fetch transport. `FileTokenProvider` takes `TokenRefreshTransport`, not a raw callable. Plans `03-01` must‑haves, tests (`test_token_refresh_transport_owns_its_own_retry_budget`), and wiring in `03-04` Task 1 complete the separation.  
- **HIGH-5 (D-19):** **FULLY RESOLVED** — Dedupe uses a partial unique index `idx_refresh_requests_dedupe … WHERE consumed_at IS NULL`. `mark_refresh_requests_consumed` takes only `consumed_at` (mark‑all‑pending). Plans `03-03` include the exact DDL and repository methods; `03-03` tests verify the index and idempotent behaviour.

---

## Part B — Cycle 2 Review

### 1. Summary
The cycle‑2 plans convincingly close all five prior HIGHs by locking five explicit decisions and propagating them into every relevant plan. The design is now rigorous in its lease/checkpoint/freshness state machine, token retry split, and AST‑enforced boundary guards. The remaining issues are minor—an inconsistency in the decision text, a possible gap in the backfill query, and a few cosmetic oddities—but none would block implementation.

### 2. Strengths
- **Comprehensive decision propagation:** Every D‑15…D‑19 appears in the relevant `must_haves.truths`, task behaviour descriptions, and acceptance criteria, leaving no ambiguity for the executor.
- **Robust test‑driven design:** Hermetic fakes, explicit requirement/decision tags in test names, and AST boundary walks guarantee the new boundaries are verifiable in CI.
- **Clean split of token‑refresh retry budget:** `TokenRefreshTransport` isolates OAuth retries from data‑fetch retries, preventing cross‑contamination of failure domains.
- **Idempotent and resumable refresh:** Lease, checkpoint cursor, and partial unique index together prevent thundering‑herd and data loss on interruption.
- **Minimal impact on existing code:** `sync.py` and `db.py` become thin compatibility shims, preserving backward compatibility while moving logic to the adapter.

### 3. Concerns

**MEDIUM**
- **Inconsistency between D‑15 decision text and 03‑04‑PLAN truth.**  
  `03‑DECISIONS.md` says: “`sync_activities()` (no `quick`) calls `run_once(..., force=False, mode='quick')` – same daily idempotency as the scheduled refresh.”  
  However, `03‑04‑PLAN.md` must‑haves states: `sync_activities(quick: bool = False) … mode='quick' if quick else 'daily'`. The decision’s wording would force a `mode='quick'` label on a daily refresh, contradicting the default `mode='daily'` in `run_once`’s signature. The planning intent is obviously the opposite (daily → mode='daily'), so this is a typo in the decision file. Nevertheless, as the decision says “conflicting wording in a specific plan is superseded by this addendum”, an automated executor could pick the wrong mode. The implementer will need to resolve this ambiguity.

- **`activities_missing_streams` query may miss activities that already have some stream rows.**  
  The repository helper uses `LEFT JOIN streams s ON s.activity_id = a.id WHERE s.activity_id IS NULL`. If an activity has one stream type (e.g., alt) but another (e.g., HR) is missing, the activity will not be returned by `activities_missing_streams`. The `backfill` stage is intended to fill gaps, but this query only covers completely absent stream rows. Partial gap fills (e.g., after an interrupted daily refresh) could remain unfilled until the next daily run. The plan mentions D‑08 (“missing … must never be silently interpreted …”), but the backfill would silently skip those activities. The executor should either use a more precise completeness check (e.g., join against the expected `STREAM_KEYS`) or document this limitation for a later phase.

**LOW**
- **Loss of historical “quick sync” behaviour.**  
  The old `sync_activities(quick=True)` skipped stream/details fetching; the new `force=True` path runs the full five‑stage daily pipeline. While CLI‑03 permits syntax changes, operators accustomed to a fast, quota‑light mirror update may be surprised. The `mode='quick'` tag is currently only audit metadata; if a lightweight “summaries‑only” path is desired later, no hook exists in the stage machine.

- **Mode label inconsistency in sync_activities(quick=False).**  
  As noted above, the decision text typos; the eventual code should clearly document that `sync_activities()` without `quick` maps to `mode='daily'`.

- **`checkpoint_stage` enum values could collide between daily and backfill stages.**  
  The plan defines `Stage.streams_backfill`, `Stage.details_backfill`, etc., alongside the daily `streams`, `details`. The runtime distinguishes them, but a future merge error could route daily resume into a backfill stage. The minimal defence is the RuntimeError for incompatible checkpoint seen in `run_once`. This is acceptable but fragile.

### 4. Suggestions
- **Clarify D‑15’s mode mapping in `03‑DECISIONS.md`.**  Change the line “`sync_activities()` (no `quick`) calls `run_once(..., force=False, mode='quick')`” to `… force=False, mode='daily'` to match the plans and the default parameter.  
- **Refine the `activities_missing_streams` query or document the limitation.**  At minimum, add a comment in the repository method that activities with partial stream rows will not be re‑fetched by backfill; a future enhancement could check completeness against the known stream keys.  
- **Consider exposing a `mode='quick-summaries'` in a later phase** if operators demand a low‑quota quick‑sync, but for Phase 3 the current full‑stage force is adequate.

### 5. Risk Assessment
**Overall risk: LOW**  
All HIGH concerns are resolved. The remaining MEDIUM issues are resolvable with small clarifications or are acceptable trade‑offs for the phase scope. The architecture is cohesive, the test suite enforces the new boundaries, and the implementation can proceed with confidence.

---

## CYCLE 2 VERDICT

- HIGH-1 (D-15): FULLY RESOLVED — `force` flag satisfies ad‑hoc sync; wiring, tests, and CLI are coherent apart from a minor decision‑text typo.
- HIGH-2 (D-16): FULLY RESOLVED — `run_backfill` with stage subset and distinct lease owner is specified and tested.
- HIGH-3 (D-17): FULLY RESOLVED — helpers move to `refresh/_sync_ops.py`, one‑way dependency enforced by AST guard and deletion from `sync.py`.
- HIGH-4 (D-18): FULLY RESOLVED — `TokenRefreshTransport` owns retry budget; data‑transport does not burn its budget on token failures.
- HIGH-5 (D-19): FULLY RESOLVED — partial unique index DDL is verbatim, `mark_refresh_requests_consumed` uses single‑parameter mark‑all‑pending, and tests cover dedupe.

New HIGHs raised this cycle: 0
- None.

---

## Consensus Summary

Only one external reviewer (OpenCode / deepseek-v4-pro) participated this cycle,
so "consensus" reduces to a single-reviewer judgement.

### Cycle-1 HIGH Resolution
| Prior HIGH | Decision | Status |
|------------|----------|--------|
| HIGH-1 — `run_once()` vs `sync_activities(quick=True)` semantic gap | D-15 | FULLY RESOLVED |
| HIGH-2 — `backfill_activities()` under-specified | D-16 | FULLY RESOLVED |
| HIGH-3 — sync helper migration path ambiguous | D-17 | FULLY RESOLVED |
| HIGH-4 — token refresh retry budget shared with data fetch | D-18 | FULLY RESOLVED |
| HIGH-5 — `refresh_requests` dedupe SQL syntax invalid | D-19 | FULLY RESOLVED |

### New HIGHs raised this cycle
None.

### New MEDIUMs to track (non-blocking)
- **D-15 wording typo** in `03-DECISIONS.md` — line saying `sync_activities()` (no `quick`) maps to `mode='quick'` contradicts the `mode='daily'` default in `run_once`'s signature in `03-04-PLAN.md` and the obvious intent. Fix during execution: change `mode='quick'` → `mode='daily'` in that sentence of D-15.
- **`activities_missing_streams` query** in `03-03-PLAN.md` only flags activities with zero stream rows, so an activity with partial stream coverage is not re-fetched by `run_backfill`. Either widen the query or document this as a known limitation.
- **`checkpoint_stage` enum overlap** between daily (`streams`, `details`) and backfill (`streams_backfill`, `details_backfill`) — protected today by the `run_once` RuntimeError on incompatible checkpoint, which the reviewer flagged as adequate-but-fragile.

### Convergence verdict
With all 5 cycle-1 HIGHs FULLY RESOLVED and zero new HIGHs raised, the
convergence loop has converged on Phase 3 plans. Remaining MEDIUMs are
clarifications/edge cases that should be addressed during execution or in
a follow-up phase, not blockers for `/gsd-execute-phase 3`.
