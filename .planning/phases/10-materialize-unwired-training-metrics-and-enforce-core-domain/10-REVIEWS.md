---
phase: 10
reviewers: [opencode, claude]
reviewed_at: 2026-05-29T22:05:00+06:00
plans_reviewed: [10-01-PLAN.md, 10-02-PLAN.md, 10-03-PLAN.md, 10-04-PLAN.md]
---

# Cross-AI Plan Review — Phase 10

Phase 10 plans were independently reviewed by two AI systems (OpenCode and a separate
Claude session). Both reviewers independently verified the central claims against the live
codebase (the `metrics.py:5` db import, dead-code status, the hardcoded materializer defaults,
the line-141 `hr_max_observed` reuse, and sibling-module cleanliness) rather than restating
the provided context.

## OpenCode Review

# Phase 10 Plan Review

## Summary

The four plans form a well-researched, tightly-scoped TDD sequence that simultaneously closes the last PROJECT.md core/domain separation requirement AND fixes a latent product bug (13 registered, documented, exposed metric columns silently materialized as null/zero). The research backing is unusually thorough — every claim is verified against the live codebase, the 13-column mapping table is 1:1 correct, and the four verified repo method signatures match exactly what the materializer needs. The plans are production-quality in their level of detail. A few medium-grade concerns exist around test coverage completeness and stale-reference cleanup, none of which block execution.

## Strengths

- **Rigorously verified claims**: The RESEARCH.md verification table maps every dead symbol to `grep` results; every repo method signature is confirmed line-for-line. The confidence level label (HIGH) is earned.
- **Correct TDD sequencing**: RED→GREEN pairs in plans 10-01 and 10-03 are properly ordered; the RED test will genuinely fail before the GREEN change. The boundary test (10-02) naturally passes only because 10-01 removed the offending import — exactly the right dependency ordering.
- **Clean fetch/compute split**: Moving the `repo.stream_*` calls OUT of `metrics.py` and INTO the materializer (the only caller) is the correct seam. The pure functions mirror `training.py` style (plain data → dataclass or None), maintaining architectural consistency.
- **`hrr_pct` hr_max decision is correct**: Reusing `hr_max_observed` (max-to-date, already at `_activity_fact` line 141) rather than all-time `max_heartrate()` keeps hrr_pct consistent with zone bounds and TRIMP — and aligns with the registry's documented "observed_hr_max" contract.
- **No hidden work**: The claim that rolling medians auto-populate is verified correct — `_materialize_rolling_facts` (lines 368-376) already SELECTs `hr_recovery_median_rate` and `cardiac_drift_pct`; once per-activity facts are non-null, the rolling aggregates fill for free.
- **Boundary guard avoids false positives**: The 10-02 plan explicitly calls out that `mcp_strava` prefix and sibling domain imports must NOT be forbidden. The `_import_violations` AST helper's three-form coverage (`import X`, `from X import`, `from mcp_strava import alias`) is correctly documented.
- **`DecouplingResult` dataclass handling is pragmatic**: Leaving it defined in `types.py` (10-RESEARCH recommendation) avoids touching re-exports while removing it from test imports. Minimal risk.
- **Dependency graph is clean**: 10-04 depends on {10-01, 10-03}; 10-02 depends on 10-01. Wave 2 plans (10-02, 10-03) are independent within the wave. No circular dependencies.

## Concerns

- **MEDIUM — Materializer integration test does not cover hr_recovery columns**: `_seed_dirty_activity_with_streams` generates velocity values ≥ 3.0 m/s, well above `VEL_STOP` (0.15 m/s). No pauses exist in the synthetic data, so `calc_hr_recovery` returns `None`. The RED test in 10-03 correctly avoids asserting hr_recovery columns, but this means 6 of 13 columns are not exercised at the integration level. Covered at unit level (10-01 `test_metrics_pure.py`), but a materializer-side assertion on the `hr_recovery_pause_count >= 0` path would strengthen confidence. Mitigation: the pure-function unit tests in 10-01 cover all pause/no-pause branches; the integration gap is defensible given the fixture reuse constraint.
- **MEDIUM — Stale `enrich_activity` reference in `test_metric_services.py::_block_legacy_recompute` not addressed**: Line 251 includes `"enrich_activity"` in a forbidden-recompute list guarded by `hasattr(metric_services, name)`. Since `hasattr` returns False after deletion, the monkeypatch is silently skipped — no test failure. However, none of the four plans mention cleaning this stale entry. CONTEXT.md scope item 5 flagged this file but no plan task handles it. Low practical risk (can't fail), but missed cleanup.
- **LOW — Stale `enrich_activity` in security-guard negative-assert lists**: Lines 292, 490, 495 of `test_security_guards.py` reference `enrich_activity` in forbidden-call/import assertion lists. These are negative assertions, so they remain true post-deletion. No test failure risk, but leftover dead references accumulate.
- **LOW — `calc_cardiac_drift` default parameter consistency**: RESEARCH.md code example shows `sport_type=None` default; 10-01 must_haves shows no default; 10-03 always passes `activity.sport_type`. Cosmetic since the only caller always passes the argument, but one document should be canonical.
- **LOW — `_import_violations` does not handle `from mcp_strava import *`**: The `alias.name == '*'` case would silently pass the guard. Not a practical threat (no module uses wildcard imports), but the coverage annotation should acknowledge the gap.
- **LOW — `test_metric_registry.py` in 10-03 verify step**: It validates the registry bootstrap from fixture data, not a materializer column-value regression. The real regression guard is the existing materializer test asserting `trimp > 0`. The registry test is harmless but doesn't add the regression coverage the plan implies.

## Suggestions

- **Add a pause-inclusive synthetic stream fixture variant** (optional, post-phase): a `_seed_dirty_activity_with_pauses` helper with velocity dips below `VEL_STOP` so hr_recovery columns are exercised at the integration level. Deferrable — unit tests cover the pure function and the None-safe access is trivial.
- **Clean `_block_legacy_recompute`** in post-phase cleanup: remove `"enrich_activity"` from the forbidden list in `test_metric_services.py`; similarly remove it from the security-guard negative-assert lists (292, 490, 495).
- **Add a one-line doc comment on the `_import_violations` wildcard gap** so future readers know `from mcp_strava import *` is a blind spot.
- **Canonicalize `calc_cardiac_drift` signature with `sport_type: str | None = None`** to match the RESEARCH.md example.

## Risk Assessment

**Overall: LOW**

The plans are exceptionally well-researched and grounded in verified codebase state. The only real computational risk is the `hrr_pct` all-time-vs-max-to-date choice, which is correctly locked and documented. Data preservation is externalized to operator-run re-materialization with a read-only backup safety net — the right boundary for a code-only phase. TDD sequence correctly ordered; boundary guard proven to catch its target violation class; clean wave decomposition; no new deps, no installs, no schema changes. Remaining gaps (stale test references, integration coverage for one metric family) are low-impact and do not threaten phase correctness.

---

## Claude Review

I verified the key claims against the actual codebase before writing this review. Findings below are evidence-based, not just a restatement of the provided context.

# Phase 10 Plan Review

## 1. Summary

This is a tight, well-researched phase that correctly recognizes the architecture fix and the product-bug fix as a single change: `metrics.py` can't be wired into the materializer until it's pure, and making it pure is exactly what closes the core/domain requirement. I confirmed the central premises hold — `metrics.py:5` does import `repository_from_connection`; the three calc functions take `(conn, activity_id)` and fetch rows mid-computation; there are zero `src/` importers of any `metrics.py` function (genuinely dead); the materializer hardcodes the 13 columns to `0`/`None`; and `db.py:241` `get_daily_trimp_history` is imported only by `test_smoke.py`. The wave ordering is sound and the TDD framing is appropriate. My concerns are concentrated in **test coverage gaps** and one **structural flaw in how the boundary guard is validated** — notably the same blind-spot class that let the original leak ship green.

## 2. Strengths

- **Correct problem unification** — treating the dead-code/coupling violation and the unmaterialized-metrics bug as one change is accurate and avoids a redundant refactor pass.
- **Verified signatures and reuse** — `hr_max_observed` at `read_model_materializer.py:141` exists and is already the max-to-date value used for zones/TRIMP; reusing it (decision 3) is genuinely consistent, not a guess.
- **Sibling-module safety confirmed** — checked `hr_zones.py`, `sports.py`, `training.py`, `cardiac_drift.py`: none import `mcp_strava.db` or the adapters. So widening the guard to five modules (10-02) won't surprise-fail on a pre-existing violation.
- **Correct restraint on the legacy guard** — 10-04 explicitly leaves `legacy_db_imports` (`test_security_guards.py:88`) untouched; that set still correctly forbids re-importing `get_daily_trimp_history`/`api_request` into `cli.py`.
- **None-safe defaults preserved** — keeping the existing default when a pure fn returns `None` matches the current contract and avoids fabricating values.
- **Clean dependency graph** — 10-02 and 10-03 both depend only on 10-01, touch disjoint files, and parallelize safely in Wave 2.

## 3. Concerns

- **[MEDIUM-HIGH] 10-02's RED state is structurally unobservable.** The research's own pitfall #1 says "verify RED before metrics.py import removed." But 10-02 `depends_on: [10-01]`, and 10-01 *removes* the import. By the time the widened guard is committed, the violation is already gone — so you can never observe the new assertion failing on the real leak. This is precisely the blind spot that let the original coupling pass green. A guard you've only ever seen pass hasn't been proven to catch anything.
- **[MEDIUM] hr_recovery columns are not asserted in the materializer test.** The 10-03 RED test asserts `vertical_speed_vmh`, `cardiac_drift_quality`, `hrr_pct`, and `trimp` — but *not any* `hr_recovery_*` column. hr_recovery is named first in the phase goal, and `hr_recovery_pause_count`/`hr_recovery_total_rest_sec` default to `0` (int), not `None` — the same silent-default bug class. If wiring misses them, they stay `0` and the test passes anyway.
- **[MEDIUM] The "rolling medians auto-populate" claim has no test.** Research asserts `_materialize_rolling_facts` already SELECTs the source columns so the rolling medians populate for free. That's an untested assumption about exact column names matching. The cheapest insurance against a false claim is one assertion.
- **[MEDIUM] `hr_max` variable ambiguity + no-HR None-safety.** There are two values: `hr_max_observed` (raw, can be non-`None`) and `hr_max_used` (set to `None` when `hr_count == 0`). The plan says "reuse `hr_max_observed` (line 141)." For an activity with no HR samples but a non-null max-to-date, `calc_hrr_pct` must be `None`-safe on a present `hr_max` with `None` `median_hr`. The plan asserts pure fns are None-safe but never tests the no-HR path. Specify which variable and add a no-HR fixture asserting `hrr_pct` stays `None` without crashing.
- **[MEDIUM] Live re-materialization has no verification step or trigger mechanism.** Decision 7 is operator-run and rewrites live stored facts. But: (a) there's no before/after sanity query (e.g., count of non-null `hr_recovery_median_rate` rows) to confirm the rematerialize did what's expected; (b) the plans never mention whether `metric_version` should be bumped. If consumers/cache invalidation key off `metric_version`, bumping it is the clean idempotent trigger — a manual rematerialize is a step that can be forgotten or half-run on a single-writer DB.
- **[LOW] Column count discrepancy (13 vs 14).** Counting hardcoded defaults: hr_recovery (6) + vertical_speed (3) + cardiac_drift pct/severity/significant/quality (4) + hrr_pct (1) = **14**, but the plans say "13." Likely `cardiac_drift_significant` (defaults to `0`, handled specially) is excluded. Minor, but a miscount risks one column silently left unwired — the mapping table should enumerate all of them explicitly.
- **[LOW] `cardiac_drift_significant` semantics unchanged but worth noting.** `1 if (drift and drift.is_significant) else 0` collapses "insufficient data" and "computed, not significant" into the same `0`. Pre-existing design, not introduced here — flagged only as a conscious carry-over.

## 4. Suggestions

- **Prove the guard RED out-of-band.** During 10-02, transiently re-add the `from mcp_strava.db import repository_from_connection` line (or run the new assertion against the pre-10-01 tree / a stash) and confirm it fails, then revert. Document the observed RED in the plan's verify section. Otherwise the guard is unfalsified.
- **Extend the 10-03 RED test** to assert at least one `hr_recovery_*` column (e.g., `hr_recovery_median_rate is not None`) and one rolling-median column is populated after materialize — closing two coverage gaps in one fixture.
- **Add a no-HR activity case** asserting `hrr_pct`, `hr_recovery_median_rate`, `vertical_speed_vmh`, `cardiac_drift_*` all stay at their defaults and nothing raises. The None-path the happy-path id-920 fixture can't exercise.
- **Decide `metric_version` explicitly.** Either bump it (so rematerialization is triggered/idempotent via the normal mechanism) or state in 10-03 why it stays fixed. Add a one-line post-deploy verification query to decision 7's live-ops note.
- **Have 10-03 enumerate the full column mapping table in-plan** (all 14, including `significant`) so the executor can't drop one.

## 5. Risk Assessment

**Overall: LOW-MEDIUM.**

The factual foundation is solid — independently verified imports, dead-code status, materializer defaults, line-141 reuse, sibling-module cleanliness, and legacy-guard handling all checked out. The change is well-bounded with no new dependencies and clean wave ordering. What keeps this above LOW is that the **verification** is weaker than the **implementation**: the boundary guard (the artifact whose entire purpose is catching this leak) can't be observed failing given the dependency order, and the materializer test under-covers the very metric family the phase headlines (hr_recovery) plus the rolling-median auto-populate claim and the no-HR None path. None of these threaten the architecture goal; they threaten confidence that the product bug is durably fixed. Address the RED-guard validation and the hr_recovery/rolling-median assertions and this drops cleanly to LOW.

---

## Consensus Summary

Both reviewers independently verified the plans against the live codebase and converged on the
same headline: the **implementation is well-grounded and well-sequenced, but the verification is
weaker than the implementation**. Every factual premise (the `metrics.py:5` db import, zero `src/`
importers, the 13/14 hardcoded materializer defaults, the line-141 `hr_max_observed` reuse, the
sibling-module cleanliness, the untouched legacy guard) was confirmed by both. No HIGH-severity
concern was raised by either reviewer. Overall risk: **LOW (OpenCode) / LOW-MEDIUM (Claude)**.

### Agreed Strengths

- Correct unification of the architecture fix and the product-bug fix into one change.
- Reusing `hr_max_observed` (max-to-date, line 141) for `hrr_pct` is verified-consistent with zones/TRIMP and the registry's documented contract — not a guess.
- Clean fetch/compute seam (fetch stays in materializer, compute moves to pure functions mirroring `training.py`).
- Correct TDD/wave ordering and a clean, acyclic dependency graph (10-02 and 10-03 both depend only on 10-01 and touch disjoint files).
- 10-04 correctly leaves the `legacy_db_imports` cli.py ban in place while deleting the function.
- None-safe defaults preserved (no fabricated values on insufficient data).

### Agreed Concerns (highest priority)

1. **[MEDIUM — both reviewers] hr_recovery columns are not asserted in the 10-03 materializer test.** The synthetic fixture has no sub-`VEL_STOP` pauses, so `calc_hr_recovery` returns `None` and 6 hr_recovery columns are never exercised at the integration level — and `hr_recovery_pause_count`/`total_rest_sec` default to `0` (int), the same silent-default class the phase exists to fix. Recommend extending the RED test with a pause-inclusive fixture asserting at least one `hr_recovery_*` column.
2. **[MEDIUM — Claude, related cleanup flagged by OpenCode] Verification gaps around the rolling-median auto-populate claim and the no-HR None path.** Both are untested assumptions; one assertion each is cheap insurance.

### Divergent Views

- **Boundary-guard RED observability** — Claude rates this **MEDIUM-HIGH** (its top concern): because 10-02 `depends_on: [10-01]` and 10-01 removes the offending import, the new guard can never be observed failing on the real leak, so it is structurally unfalsified — the exact blind-spot class that let the original coupling ship green. OpenCode treats the same boundary test as a **strength** ("naturally passes only because 10-01 removed the import"), not flagging the unobservable-RED risk. Recommended resolution: prove the guard RED out-of-band during 10-02 (transiently re-add the import or run the new assertion against the pre-10-01 tree/stash, confirm failure, revert) and record the observed RED in the plan's verify section. This is the single most actionable divergence and is cheap to close.
- **Live re-materialization trigger / `metric_version`** — Claude raises this as a MEDIUM (no before/after sanity query; `metric_version` bump undecided); OpenCode does not mention it. Worth a one-line decision in 10-03 plus a verification query in the decision-7 live-ops note.
- **13 vs 14 column count** — Claude flags a LOW miscount (14 actual defaults incl. `cardiac_drift_significant`); OpenCode consistently says 13. Enumerating the full mapping table in-plan removes the ambiguity.

### Recommended pre-execution edits (all cheap, none blocking)

- Add the boundary-guard out-of-band RED proof to 10-02's verify section.
- Extend the 10-03 RED test with a pause-inclusive fixture (one `hr_recovery_*` assertion) and one rolling-median assertion; add a no-HR None-path case.
- Decide and document `metric_version` handling + a post-deploy sanity query in decision 7.
- Enumerate all 14 columns in the 10-03 mapping table; canonicalize `calc_cardiac_drift(rows, sport_type=None)`.
