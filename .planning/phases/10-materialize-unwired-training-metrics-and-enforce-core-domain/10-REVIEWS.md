---
phase: 10
cycle: 2
reviewers: [codex, opencode]
reviewed_at: 2026-05-29T22:40:00+06:00
plans_reviewed: [10-01-PLAN.md, 10-02-PLAN.md, 10-03-PLAN.md, 10-04-PLAN.md]
prior_cycle: 1
---

# Cross-AI Plan Review — Phase 10 (Cycle 2)

Cycle 2 follows a replan (commit b1aca30) that folded in cycle-1 review feedback. Plans
were independently reviewed by Codex and OpenCode. Both reviewers were asked to (a) confirm
whether the four cycle-1 concerns were resolved and (b) surface any NEW concerns. The
reviewer of record (Claude Code) additionally verified every load-bearing claim and both
cross-cutting NEW concerns against the live codebase before writing the consensus.

**Headline: no HIGH-severity concerns in either review. All four cycle-1 concerns confirmed
resolved by both reviewers.** Two reviewers converge on one MEDIUM (a between-wave red-suite
window); Codex raises two further MEDIUMs (a no-HR fixture spec ambiguity and live-ops
runbook precision). All are pre-execution edits, none block the architecture/bug-fix goal.

## Cycle-1 → Cycle-2 Resolution Status

| # | Cycle-1 concern | Resolved? | How (cycle-2) |
|---|-----------------|-----------|---------------|
| (a) | Boundary-guard RED state structurally unobservable (Claude MEDIUM-HIGH, top divergence) | YES (both) | 10-02 Task 2 adds an explicit out-of-band RED proof: transiently re-add the `mcp_strava.db` import, observe the widened test FAIL (RED_EXIT=1, violations name metrics.py + mcp_strava.db), then revert; the transient import is never committed. |
| (b) | hr_recovery / rolling-median / no-HR coverage gaps in the materializer test (both MEDIUM) | YES (both) | 10-03 Task 1 adds (i) a pause-inclusive fixture (`velocity < VEL_STOP` for `>= MIN_PAUSE_SEC`) asserting `hr_recovery_median_rate is not None AND hr_recovery_pause_count >= 1`; (ii) a `rolling_median_hr_recovery is not None` assertion proving the auto-populate column-name match; (iii) a no-HR None-path case. |
| (c) | metric_version decision + live re-materialize sanity query (Claude MEDIUM) | YES (both) | 10-03 documents an explicit "do NOT bump metric_version" decision with rationale, and embeds a post-rematerialize SQL sanity query in the T-10-DI threat mitigation. |
| (d) | 13-vs-14 column count ambiguity (Claude LOW) | YES (both) | 10-03 adds a full 14-column mapping table; `cardiac_drift_significant` is explicitly counted as the 14th column with its `1/0` collapse documented as a conscious carry-over. |

---

## Codex Review

**Summary**

Cycle 2 is materially stronger than cycle 1. The four named cycle-1 concerns are addressed in the plans: the boundary guard gets an explicit RED proof, the materializer tests now cover pause-based HR recovery, rolling medians, and no-HR paths, `metric_version` has an explicit no-bump decision plus a live sanity query, and the 13-vs-14 ambiguity is resolved with a full 14-column mapping. No new HIGH concerns. The remaining issues are execution-order and live-ops precision problems, not plan-breaking design flaws.

**Strengths**

- The phase is correctly decomposed: pure-domain extraction first, boundary guard and materializer wiring second, cleanup last.
- 10-02 now makes the boundary guard observable by transiently reintroducing the forbidden import and recording the failure.
- 10-03 directly fixes the product bug instead of deleting registered metrics.
- The hrr_pct decision is coherent: using `hr_max_observed` keeps it aligned with the fact row's existing zone/TRIMP provenance.
- The full 14-column mapping removes ambiguity around `cardiac_drift_significant`.
- The materializer test plan now includes the important missing paths: pause-inclusive HR recovery, rolling median propagation, and insufficient/no-HR behavior.

**Concerns**

- **MEDIUM** — 10-01 deletes symbols while stale tests are only repaired in 10-04. That can leave the suite uncollectable between Wave 1 and Wave 3 if normal wave gates run `just test`. Move the stale `test_smoke.py` import/test cleanup into 10-01, or defer deleting the nonessential dead functions until 10-04.
- **MEDIUM** — The no-HR materializer case may encode a false expectation for `vertical_speed_vmh`. Vertical speed depends on altitude/time, not HR. If the no-HR fixture still has sufficient altitude samples, `vertical_speed_vmh` should compute. Make the fixture explicitly no-HR and no/insufficient-altitude, or only assert HR-derived defaults there.
- **MEDIUM** — The live re-materialize path still lacks an exact operator command or forced-recompute mechanism. Since `metric_version` intentionally does not change, the plan should say precisely how clean existing rows get recomputed, how the owner/single-writer rule is respected, and how the backup is checked before mutation.
- **LOW** — 10-02's transient source edit for RED proof is useful, but the shell command should be failure-safe with a `trap` restore and a final `git diff -- src/mcp_strava/metrics.py` check. An interrupted proof can otherwise leave a dirty forbidden import.
- **LOW** — The cardiac-drift integration assertion should be backed by a deterministic fixture known to produce non-null quality/pct, or the test may become brittle against algorithm quality gates.

**Suggestions**

- Add a short "between-wave suite state" note in 10-01/10-04 so executors know whether full-suite red is expected temporarily. Better: avoid temporary red by moving stale import cleanup earlier.
- Add a live-ops appendix to 10-03 with the exact re-materialization command, backup check, owner/lock handling, and the post-query expected shape.
- In 10-03, phrase the no-HR case as "HR-derived metrics remain default" unless the fixture also intentionally lacks altitude.
- Keep the `metric_version` no-bump decision, but explicitly state that the operator-run rematerialization must bypass dirty-only skipping or mark all relevant facts dirty first.
- Record the before/after sanity-query counts in the summary, not just the query text.

**Risk Assessment: MEDIUM**

Code design risk is low: the plans use existing repo methods, pure functions, and AST guards, and preserve the MCP boundary. Risk stays medium because this phase mutates persisted read-model facts in the live DuckDB runtime, and prior repo history shows live DuckDB operations need explicit backup, owner, parity, and smoke-validation discipline. Tightening the re-materialize runbook and avoiding temporary full-suite breakage would bring this close to low.

---

## OpenCode Review

## Overall Assessment

The cycle-2 replan is a substantial improvement. All four cycle-1 concerns are directly addressed: the boundary-guard RED state now has an explicit out-of-band falsification step (10-02 Task 2), the materializer test now covers the pause-inclusive hr_recovery path, a rolling-median assertion, AND the no-HR None-path (10-03 Task 1), the 13-vs-14 ambiguity is fully resolved into an explicit 14-column mapping table with `cardiac_drift_significant` properly counted, and the `metric_version` decision is documented with rationale plus a post-rematerialize sanity query. One new **MEDIUM** concern remains: a broken test suite window between waves 1 and 3 caused by deleting symbols from `metrics.py` before fixing the test imports that reference them.

### 10-01 — Extract pure metric functions

**Strengths:** Clean TDD flow (RED new test file → GREEN extract + verify imports clean); pure signatures well-specified with data-shape contracts and None-guard behavior; mirrors `training.py` style; verification includes both test pass AND a grep for residual db import.

**Concerns:**
- **MEDIUM** — Deleting dead functions in 10-01 breaks `test_smoke.py` collection until 10-04. Task 2 deletes `enrich_activity`, `calc_decoupling`, `_decoupling_invalid`, `calc_decoupling_with_gate`, `_fetch_decoupling_rows`, `calc_efficiency_factor`. But `test_smoke.py` imports `enrich_activity`, `calc_decoupling_with_gate`, `calc_efficiency_factor` at line 12 and references `_decoupling_invalid`/`calc_decoupling` at lines 128/146; the import fixes are deferred to 10-04 (wave 3). So `pytest tests/test_smoke.py` fails to collect from wave-1 completion through wave 3 — contradicting RESEARCH.md Pitfall 3 ("Order the wave so test updates land with or before the deletions"). 10-01's verify step only runs `test_metrics_pure.py` + an import sanity check, so an executor may not notice, but any full-suite/CI run will be red.
- **LOW** — `from mcp_strava.hr_zones import get_zone_model` (metrics.py line 6) — is it still used after deleting `enrich_activity`? If only the deleted code used it, it should be removed in the same "clean up now-unused imports" step; the plan says "any now-unused imports" but doesn't enumerate them.

**Suggestions:** Move the `test_smoke.py` import fixes from 10-04 Task 2 into 10-01 (same atomic commit), OR defer ALL dead-function deletions to 10-04, keeping 10-01 to new pure functions + the `db` import removal so the suite stays green through waves 1–2.

### 10-02 — Import-boundary guard

**Strengths:** Reuses the existing `_import_violations` AST helper (zero new infra); Pitfall 2 (sibling domain imports stay allowed) explicitly handled by forbidding only storage/adapter prefixes; Task 2 provides the explicit throwaway RED proof that directly and definitively closes the cycle-1 unfalsifiability concern; the `from mcp_strava import db` form is covered by the helper's line 222–226 branch (verified against source).

**Concerns:**
- **LOW** — Task 2 RED proof uses fragile `cp` gymnastics; if interrupted between the swap and the restore, the working tree is corrupt. `git checkout` recovers it, but a single `edit`-then-revert is less fragile.
- **LOW** — No explicit pre-check that `hr_zones` and `sports` have zero storage imports today (almost certainly true per RESEARCH §Pitfall 2; could add a "guard passes before 10-02" check).

### 10-03 — Wire pure functions into the materializer

**Strengths:** All three cycle-1 coverage gaps addressed — (b-i) pause-inclusive hr_recovery, (b-ii) rolling-median auto-populate assertion, (b-iii) no-HR None-path; (d) 13-vs-14 fully resolved with a 14-row mapping table; (c) metric_version decision documented with rationale + embedded sanity query; the full mapping table maps every column to its source expression; `hr_max_observed` reuse is locked.

**Concerns:**
- **LOW** — `_activity_fact` may fetch streams for activities that don't have them (4 fetches return empty, pure fns return None, None-safe access handles it). Not new overhead (median-HR fetch already in the zone path), just noting per-activity no-op queries.
- **LOW** — The rolling-median assertion requires "enough activities with non-null hr_recovery_median_rate"; the plan doesn't specify how many the seed helper creates. If the single seeded activity isn't enough, the executor must add more. Could specify a minimum (e.g., "seed 3 activities with pause-inclusive streams").

### 10-04 — Delete dead db.py code and repair stale tests

**Strengths:** RESEARCH dead-code table is the authoritative pre-verified source; Task 3 covers the stale `enrich_activity` refs that CONTEXT scope item 5 called out but no prior plan addressed; `legacy_db_imports` explicitly preserved; `DecouplingResult` handling follows the RESEARCH recommendation; cleanup-only, no forward coupling.

**Concerns:**
- **LOW** — Task 3 removes `enrich_activity` from forbidden_calls sets (negative assertions); correct since the function no longer exists, but worth confirming no separate positive test asserts it IS forbidden. From source line 292 it's a negative check — tautologically correct to remove, no risk.
- **LOW** — Task 1's verify step doesn't grep for orphaned imports after deleting `get_daily_trimp_history`; add `python -c "import mcp_strava.db"` to confirm db.py still imports cleanly.

## New Concerns Summary (OpenCode)

| # | Severity | Concern | Plan |
|---|----------|---------|------|
| 1 | MEDIUM | Deleting dead functions from `metrics.py` in 10-01 breaks `test_smoke.py` collection until 10-04 (violates RESEARCH Pitfall 3) | 10-01 ↔ 10-04 |
| 2 | LOW | 10-02 Task 2 RED proof uses a fragile `cp` chain that could corrupt the working tree if interrupted | 10-02 |
| 3 | LOW | Rolling-median assertion in 10-03 may need more seeded activities than the fixture provides | 10-03 |

## Risk Assessment: LOW

The phase is well-scoped, has zero external dependencies, and all four cycle-1 concerns are substantively resolved. The TDD structure is sound and the plans are detailed enough that an executor won't need to make architectural decisions. The one MEDIUM (test-suite red window) requires only reordering deletions relative to test fixes — no change to the actual code changes, no new files, no dependency restructuring.

---

## Consensus Summary

Both reviewers independently confirm the cycle-2 replan resolves all four cycle-1 concerns and
introduces **no HIGH-severity issues**. Overall risk: **LOW (OpenCode) / MEDIUM (Codex)** — the
divergence is entirely about live-ops/runtime mutation discipline, not the code design.

The reviewer of record verified the load-bearing claims and both cross-cutting NEW concerns
against the live codebase:
- `metrics.py:5` db import + the conn-coupled calc signatures, the 14 hardcoded materializer
  defaults (lines ~190–205), `hr_max_observed` at line 141 (via `max_heartrate_to_date`),
  `athlete.hr_rest` and `activity.sport_type` in scope, all four repo method signatures, the
  `_import_violations` helper + the `test_read_modules_do_not_import_strava_or_refresh` family
  (3 modules, strava/refresh prefix tuple at line 374), the sibling `cardiac_drift` import to
  preserve (line 10), and the enrich_activity refs at 292/490/495 (security_guards) + 251
  (metric_services) — **all match the plans exactly.**
- **CONFIRMED (red-suite window):** `metrics.py:6` `from mcp_strava.hr_zones import get_zone_model`
  is used only by the deleted `enrich_activity` path → correctly an unused-import-to-remove.
  `test_smoke.py:12` imports symbols 10-01 deletes while the repair is in 10-04 (wave 3) → the
  between-wave uncollectable-suite window is real.
- **CONFIRMED (no-HR/altitude spec ambiguity):** 10-03 line 132 asserts `vertical_speed_vmh is None`
  in the no-HR case, but `calc_vertical_speed` reads altitude rows independently of HR. If the
  no-HR fixture reuses the ascending-altitude seed and only nulls HR, that assertion will FAIL.

### Agreed Strengths

- Correct phase decomposition (pure extraction → guard + wiring → cleanup); clean acyclic wave graph.
- The 10-02 out-of-band RED proof definitively closes the cycle-1 unfalsifiable-guard concern.
- 10-03 fixes the product bug (computes the registered metrics) rather than deleting them, honoring decision 260525-jpo "preserve and fix".
- `hr_max_observed` reuse for `hrr_pct` is verified-consistent with zones/TRIMP provenance.
- The full 14-column mapping removes the `cardiac_drift_significant` miscount.
- Materializer test now covers pause-inclusive hr_recovery, rolling-median, and no-HR paths.

### Agreed Concerns (highest priority)

1. **[MEDIUM — both] Between-wave red-suite window.** 10-01 deletes `metrics.py` symbols that
   `test_smoke.py:12` still imports; the test repair is deferred to 10-04 (wave 3). Any
   full-suite/`just test` run is uncollectable from wave-1 completion through wave 3, contradicting
   RESEARCH Pitfall 3. **Recommended fix (both reviewers agree):** move the `test_smoke.py` import
   fixes into 10-01 (same atomic commit), OR defer the nonessential dead-function deletions to
   10-04 — keeping 10-01 to new pure functions + the `db` import removal so the suite stays green
   through waves 1–2. Verified real against the live tree.

### Divergent Views

- **Overall risk level** — OpenCode rates **LOW** (code-design lens); Codex rates **MEDIUM** because
  the phase mutates live DuckDB read-model facts and prior incidents show live DuckDB ops need
  explicit backup/owner/parity/smoke discipline. Resolution: this is a framing difference, not a
  contradiction — the code change is low risk; the operator-run live re-materialize is the medium-risk
  step, which is exactly why decision 7 is operator-gated. Tightening the runbook (below) closes it.
- **No-HR fixture (`vertical_speed_vmh`)** — Codex flags a MEDIUM spec ambiguity that OpenCode does
  not. Verified real: the assertion is only correct if the no-HR fixture ALSO lacks sufficient
  altitude. **Recommended:** either make the no-HR fixture no-HR-and-no/low-altitude, or scope the
  no-HR assertions to HR-derived columns (`hrr_pct`, `hr_recovery_*`) and assert `vertical_speed_*`
  separately on an altitude-bearing fixture.
- **Live-ops runbook precision** — Codex MEDIUM (no exact rematerialize command / forced-recompute
  given metric_version is intentionally fixed); OpenCode does not raise it. **Recommended:** add a
  live-ops appendix to 10-03 stating the exact re-materialize command, that it must mark relevant
  facts dirty / bypass dirty-only skipping (since metric_version doesn't change), the backup-intact
  check on `~/backups/mcp-strava-safe/`, the single-writer/owner handling, and the expected
  before/after sanity-query counts.

### Recommended pre-execution edits (all cheap, none blocking)

- Close the red-suite window: move `test_smoke.py` import fixes into 10-01, or defer the
  dead-function deletions to 10-04. (Agreed MEDIUM — the one edit worth making before execution.)
- Fix the no-HR fixture's `vertical_speed_vmh` expectation (make it altitude-poor, or scope the
  assertion to HR-derived columns).
- Add the live-ops runbook appendix to 10-03 (exact command, dirty/forced recompute, backup check,
  owner handling, expected counts).
- Enumerate the now-unused `metrics.py` imports to drop (line 6 `get_zone_model`, `get_settings`,
  `json`, `parse_strava_activity`, `EnrichedActivity`, `DecouplingResult`).
- Harden the 10-02 RED-proof shell (trap-based restore + final `git diff` check), or use an
  edit-then-revert instead of the `cp` chain.
- Specify a minimum seeded-activity count for the rolling-median assertion in 10-03.
