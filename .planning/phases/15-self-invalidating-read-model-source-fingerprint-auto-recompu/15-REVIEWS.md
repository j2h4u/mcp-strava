---
phase: 15
review_cycle: 2
reviewers: [codex, opencode]
reviewed_at: 2026-06-03T18:40:00Z
plans_reviewed: [15-01-PLAN.md, 15-02-PLAN.md, 15-03-PLAN.md, 15-04-PLAN.md, 15-05-PLAN.md]
prior_cycle: 1
prior_cycle_commit: abe0bbe
context: >
  Cycle-2 review of the amended Phase 15 plans. The plans were amended (commit abe0bbe)
  to fold in 4 HIGH + 6 MEDIUM findings from cycle 1. This review verifies whether the
  prior HIGHs are resolved and whether the amendments (notably the rewave to a strictly
  serial W1->W2->W3->W4->W5 structure) introduced new HIGH concerns.
---

# Cross-AI Plan Review — Phase 15 (Cycle 2)

## Codex Review

**Summary**
The amended plans resolve all prior HIGH findings on the text. Phase 15 is close, but not
fully executable yet because the amendments introduce one new HIGH risk: `current_metric_version()`
is now explicitly memoized, but the recompute path bumps the version and then may reuse a stale
cached or caller-resolved version. The wave serialization is mostly justified through 15-04, but
15-05's dependency on 15-04 looks over-serialized.

**Prior HIGH Resolution Table**

| Prior HIGH | Status | Evidence |
|---|---|---|
| H1: `15-02` must depend on `15-01` | RESOLVED | `15-02` frontmatter now has `depends_on: [15-01]`; Task 2 imports `compute_logic_fingerprint` added by `15-01`. |
| H2: version pinning incomplete | RESOLVED | `15-03` Task 3 explicitly threads `metric_version` through `query_training_aggregates`, `_where_clause`, `_effective_range_for_metric`, `query_status_facts`, and `aggregate_services.py`. |
| H3: deleting `CURRENT_METRIC_VERSION` breaks defaults and misses re-export | RESOLVED | `15-03` Task 1 removes the constant from `repository.py`, `adapters/duckdb/__init__.py`, `__all__`, and makes `update_activity_source_state_and_enqueue_dirty` plus `materialize_read_model` require explicit `metric_version`. |
| H4: `metric_registry` omitted from fingerprint modules | RESOLVED | `15-01` must-have says `mcp_strava.metric_registry is in COMPUTE_SOURCE_MODULES`; implementation tuple includes it. |
| Seed robustness: `ImportError` breaks `from_connection()` | RESOLVED | `15-02` requires `try/except Exception` around fingerprint compute plus seed insert, and tests an `ImportError` path where `from_connection()` still succeeds. |

**New Concerns**

HIGH: Stale cached metric version can break the recompute path.
`15-02` requires `current_metric_version()` to cache the resolved value for the repo lifetime.
`15-03` then says the trigger does `bump_logic_version(new_version, ...)` and afterwards resolves
`current_version = repo.current_metric_version()`. It also says `runtime.py` and `worker.py` should
read `repo.current_metric_version()` and pass it into `materialize_read_model_stage`. If the cache
was populated before the bump, or the caller passes the pre-bump version, the dirty rows may be
enqueued for version N+1 while materialization still runs version N. Amend the plan to require
`bump_logic_version()` to update/invalidate the memoized current version and require
`materialize_read_model_stage` to resolve the version internally after the fingerprint check, not
accept a caller-resolved version.

MEDIUM: `15-05` is over-serialized behind `15-04`.
`15-02 -> 15-03` is real. `15-03 -> 15-04` is justified because `15-04` includes the zero-knob
recompute integration proof. But `15-05` only needs `15-03` for recompute/version plumbing and
touches time-field/schema/payload concerns; it does not depend on the walk discount semantics from
`15-04`. It can likely be `depends_on: [15-03]` and run parallel with `15-04`, with ordinary
file-conflict coordination.

MEDIUM: unseeded sidecar self-healing is inconsistent.
`15-02` says a skipped seed leaves the sidecar unseeded and defers to the next cycle, but `15-03`
says when `stored is None`, "do nothing." That is safe for no-recompute, but it does not guarantee
adoption. Add an explicit adopt-current branch at the chokepoint: if `stored is None` and live
fingerprint computes, write the sidecar with the current/fallback version and do not enqueue.

MEDIUM: `15-04` overclaims its constant-change E2E proof.
The must-have says changing `WALK_TRIMP_DISCOUNT` flips the fingerprint and auto-recomputes. The
implementation text correctly notes monkeypatching the constant does not change `inspect.getsource`,
but option `(b)` only proves recalculation uses the patched constant, not fingerprint-triggered
recompute. Require option `(a)` or an equivalent forced stored/live fingerprint mismatch integration
test, and rely on `15-01` for source-text sensitivity.

LOW: `15-05` threat model still says string slicing.
The task text correctly requires `datetime.fromisoformat()` and forbids `[11:16]`, but T-15-10 still
says "opaque string slice ([11:16])." Clean that up to avoid executor confusion.

**Risk Assessment**
Overall risk is HIGH until the cached-version invalidation issue is amended, because it can defeat
the core self-invalidating behavior. After that fix, MEDIUM: the prior HIGHs are resolved, and the
remaining issues are mostly scheduling, test precision, and plan consistency.

---

## OpenCode Review

# Phase 15 — Review Cycle 2

## 1. Summary

All five prior HIGH concerns (H1–H4 + seed-robustness) are **fully resolved** in the amended plans
with concrete, verifiable plan text. No new HIGH concerns were introduced. Three MEDIUM notes
(worker idle perf, 15-04 e2e ambiguity, status-fact line-number precision) deserve attention during
execution but are not blockers. The serialization of waves 2→3→4→5 is slightly conservative but
justified by real code-shared-file dependencies. **The phase is executable.**

## 2. Prior HIGH Resolution Table

| Prior HIGH | Verdict | Evidence from amended plan text |
|---|---|---|
| **H1**: 15-02 must `depends_on:[15-01]` | **RESOLVED** | 15-02-PLAN.md YAML header: `depends_on: [15-01]`. Task 2 says "import compute_logic_fingerprint INSIDE the method (runtime)". |
| **H2**: Version pinning incomplete | **RESOLVED** | 15-03-PLAN.md Task 3 covers ALL three paths: `_effective_range_for_metric` pinned `metric_version = ?`; `query_status_facts` adds `metric_version = ?` to each direct SELECT; `aggregate_services.py` resolves `version` once and threads it into `read_model_status` + `query_training_aggregates`. No-blend test covers point, aggregate, AND status reads. |
| **H3**: `CURRENT_METRIC_VERSION` deletion breaks default arg + incomplete removal scope | **RESOLVED** | 15-03-PLAN.md Task 1 removes the re-export from `adapters/duckdb/__init__.py:5` AND `__all__` line 10; makes both default args required; verification `grep -rn CURRENT_METRIC_VERSION src/` returns nothing. Codebase confirmed symbol on lines 5 and 10. |
| **H4** (codex): `metric_registry` omitted from `COMPUTE_SOURCE_MODULES` | **RESOLVED** | 15-01-PLAN.md tuple now includes `"mcp_strava.metric_registry"`; verified `read_model_materializer.py:11` imports from `metric_registry`. |
| **Seed-path robustness** (opencode) | **RESOLVED** | 15-02-PLAN.md Task 2 wraps the fingerprint compute in a SEPARATE inner `try/except Exception` distinct from the `CatalogException` guard; Task 3 verifies with a monkeypatch ImportError test. |

## 3. New Concerns

### MEDIUM — One
**Worker idle-cycle fingerprint computation cost.** 15-03 Task 2 picks option (b): when
`dirty_count==0`, still call `materialize_read_model_stage` once. The trigger block calls
`compute_logic_fingerprint()` (import_module + inspect.getsource over 8 modules) on every idle cycle.
Likely negligible on a single-user local service, but a permanent per-cycle overhead. Mitigation: a
per-process fingerprint cache, or option (a). Not a blocker.

### MEDIUM — Two
**15-04 zero-knob end-to-end proof remains ambiguously specified.** The plan offers (a) vs (b)
without choosing; option (b) is just a unit test of the discount function and does not prove the
fingerprint → recompute pipeline. Recommendation: pick (a) and document the choice.

### MEDIUM — Three
**`query_status_facts` per-SELECT line numbers may be imprecise.** Verified code shows
`query_status_facts` (line 163) iterates `STATUS_FACT_REGISTRY` and delegates to `_query_status_fact`;
the actual SELECTs are likely inside that inner function. Intent (pin every direct fact-table query)
is clear and correct; executor should search for fact-table access patterns rather than rely on the
listed line numbers.

### LOW — Serialization waves 2→5
15-05 declares `depends_on: [15-03, 15-04]`. 15-03 dependency is clearly correct. The 15-04
dependency is logically unnecessary (Walk discount and time fields don't interact) but defensible on
code-safety grounds: both plans modify `repository.py` and `read_model_materializer.py` in adjacent
areas. Lost parallelism is one serialized commit cycle — trivial cost. Not actionable.

### LOW — `_parse_local_hhmm` helper placement
15-05 Task 1 says to factor a module-level helper used by both `read_model_materializer.py` (adapter)
and `metric_services.py` (application). Placing it in either creates a layering import. The implementer
should place it in a neutral location (e.g. `constants.py` or a new lightweight module). Low risk.

### LOW — 15-01 YAML `depends_on: []`
Correct and consistent — 15-01 is the foundational plan.

## 4. Risk Assessment

**Overall: LOW.** All 5 prior HIGH concerns are fully resolved with traceable evidence. No new HIGH
found by this reviewer. The three MEDIUM notes are implementation-level. Serialization is conservative
but justified. **The phase is ready for execution.**

---

## Consensus Summary

Both reviewers independently confirm that **all 5 prior HIGH concerns (H1–H4 + seed-path robustness)
are FULLY RESOLVED** in the amended plans, with traceable evidence cited from the plan text and
cross-checked against the codebase (`__init__.py:5/10`, `read_model_materializer.py:11`). The cycle-1
fold-in succeeded on every prior HIGH.

The reviewers **diverge on one new finding**, which was verified against the source during this review
and is folded in as a genuine HIGH (see below).

### Agreed Strengths (both reviewers)

- All prior HIGHs resolved with explicit, verifiable plan text (not hand-waving).
- H2 version pin now threads through the entire aggregate/status read path (`_where_clause`,
  `_effective_range_for_metric`, `query_status_facts`, `aggregate_services.py`), not just `_where_clause`.
- H3 constant removal is exhaustive (symbol + re-export + `__all__` + required params), with a
  `grep`-returns-nothing verification gate.
- Seed-path `ImportError` guard is correctly separated from the `CatalogException` guard.

### Agreed Concerns (raised or accepted by both — fold in manually)

1. **[MEDIUM] 15-04 zero-knob E2E proof is ambiguously specified (option a vs b).** Both reviewers
   flag that option (b) only proves the discount recalculates with a patched constant — it does NOT
   prove the fingerprint→recompute pipeline fires. Pick option (a): force a real stored-vs-live
   fingerprint mismatch at the chokepoint and assert recompute. Lean on 15-01 for source-text sensitivity.
2. **[MEDIUM] 15-05 is over-serialized behind 15-04.** Codex (MEDIUM) and OpenCode (LOW) agree the
   15-04 dependency is logically unnecessary — Walk discount and time fields don't interact. OpenCode
   accepts it on shared-file (`repository.py`, `read_model_materializer.py`) merge-safety grounds.
   Decision needed: keep serial for file-conflict safety, or relax 15-05 to `depends_on: [15-03]` and
   coordinate the shared-file edits. Low real cost either way (one serial commit cycle).
3. **[MEDIUM] `query_status_facts` line numbers (265/307/336/366/392/432/501) are imprecise.** The
   real SELECTs live inside the per-definition `_query_status_fact` delegate. The intent is correct;
   the executor should grep for fact-table access in the status path rather than trust the line list.

### Divergent View (verified against code → folded in as HIGH)

- **[HIGH] Stale memoized / caller-resolved `metric_version` can defeat the recompute.** Codex raises
  this as a new HIGH; OpenCode does not flag it. **Verified against source during this review:**
  `materialize_read_model_stage(repo, metric_version, ...)` (`_sync_ops.py:270`) takes
  `metric_version` as a **caller-resolved parameter**, and 15-03 Task 2 keeps that shape (worker/runtime
  resolve `repo.current_metric_version()` and pass it in). 15-02 Task 2 mandates that
  `current_metric_version()` **memoizes** its result on the repo instance for the repo lifetime. The
  trigger then `bump_logic_version(N+1)` → `enqueue_metric_version_recompute(N+1)` (dirty rows at N+1).
  If the memo was populated to N before the bump, OR the caller passed a pre-bump N into the stage,
  materialization runs at stale N while dirty rows are queued at N+1 — a self-defeating version
  mismatch that the plans do not currently close. The plans never state that `bump_logic_version()`
  invalidates the memo, and they explicitly pass a caller-resolved `metric_version` into the stage
  rather than re-resolving after the fingerprint check. This is a real interaction-bug introduced by
  the cycle-1 amendments (memoization + required-param threading).

  **Required fix (fold into 15-02/15-03 before execution):** (a) `bump_logic_version()` must invalidate/
  update the memoized `current_metric_version` on the repo instance; AND (b) the chokepoint must
  resolve `metric_version` **internally, after** the fingerprint compare-and-bump — `materialize_read_model_stage`
  should derive the version from `repo.current_metric_version()` post-bump rather than trust a
  caller-resolved value. Together these guarantee enqueue version == materialize version on the
  recompute cycle.

### Other items to fold (LOW)

- 15-05 threat model T-15-10 still describes the old `[11:16]` "opaque string slice" — stale vs the
  amended `fromisoformat` parse; tidy to avoid executor confusion (codex LOW).
- `_parse_local_hhmm` helper needs a layering-neutral home (not adapter, not application) to avoid an
  import-direction violation (opencode LOW).
- 15-03 worker option (b) computes the fingerprint every idle cycle; cheap on a single-user instance,
  but a per-process fingerprint cache or option (a) avoids the permanent per-cycle cost (opencode MEDIUM/perf).

### Net Assessment

The cycle-1 HIGHs are closed. One NEW HIGH (memoized/caller-resolved version vs post-bump version)
remains unresolved and is verified in the source — it must be folded into 15-02/15-03 before execution.
After that single fix, the phase drops to MEDIUM/LOW (the rest are scheduling, test-precision, and
plan-consistency items). The strict W1→W5 serialization is sound: every `depends_on` references only
earlier waves and each edge is backed by a real data/code dependency; the only soft edge (15-05→15-04)
is a defensible shared-file merge-safety choice, not a correctness requirement.

**Current cycle unresolved HIGH count: 1.**
