---
phase: 15
review_cycle: 3
reviewers: [codex, opencode]
reviewed_at: 2026-06-03T19:05:00Z
plans_reviewed: [15-01-PLAN.md, 15-02-PLAN.md, 15-03-PLAN.md, 15-04-PLAN.md, 15-05-PLAN.md]
prior_cycle: 2
prior_cycle_commit: 213a82d
amendment_commit: f7e2bea
context: >
  Cycle-3 review of the Phase 15 plans after commit f7e2bea amended them to fix the single
  remaining cycle-2 HIGH (stale memoized / caller-resolved metric_version that could defeat
  the self-invalidating recompute). The fix: bump_logic_version() now invalidates the
  current_metric_version memo, and materialize_read_model_stage drops its caller-passed
  metric_version param and re-resolves the version internally AFTER the fingerprint bump
  (callers in runtime.py x3 + worker.py updated). This cycle verifies the HIGH is fully
  resolved and that removing the chokepoint param / adding the post-bump re-resolution did
  not introduce any new HIGH. MEDIUM/LOW folds (15-04 option-a E2E, 15-05 rewaved parallel
  to 15-04, status-path grep instruction, per-process fingerprint cache, parse_local_hhmm
  home) were also confirmed coherent.
unresolved_high_count: 0
---

# Cross-AI Plan Review — Phase 15 (Cycle 3)

## Codex Review

**Summary**

The cycle-2 HIGH is fully resolved in the amended plan text. The plans now require both
necessary fixes: `bump_logic_version()` invalidates the memo, and `materialize_read_model_stage()`
removes the caller-provided `metric_version` and re-resolves internally after compare/bump.
No new HIGH. One MEDIUM plan-text inconsistency remains around the unseeded-sidecar self-healing
path, plus one LOW stale-wording issue.

**Prior-HIGH Resolution Verdict: RESOLVED.**

Evidence:
- 15-02-PLAN.md:17 must-have explicitly says `bump_logic_version()` invalidates the cached
  `current_metric_version` memo.
- 15-02-PLAN.md:81 requires invalidation at the END of the bump, after the upsert, and says
  callers must not be responsible for resetting the memo.
- 15-02-PLAN.md:105 adds the same-repo regression test: populate memo at `v`, bump to `v+1`,
  then assert `current_metric_version()` returns `v+1`.
- 15-03-PLAN.md:25 must-have says the chokepoint re-resolves internally after compare-and-bump,
  not from a caller-passed pre-bump value.
- 15-03-PLAN.md:85 and :108 explicitly update all four stage callers: runtime.py:108,
  runtime.py:179, runtime.py:273, worker.py:69.
- 15-03-PLAN.md:110 gives the correct ordering: `bump_logic_version(new_version, ...)`, enqueue
  at `new_version`, then `current_version = repo.current_metric_version()` after memo invalidation.

This closes the stale `N` vs dirty-queue `N+1` failure.

**New Concerns**

HIGH: None. Removing the `metric_version` parameter from `materialize_read_model_stage` is safe
in the plan: all four current callers are named and updated. The lower-level materializer still
needs a version, and the plan keeps that as a required parameter supplied by the stage.

MEDIUM: unseeded sidecar self-healing text is still inconsistent. 15-02-PLAN.md:87 says if seeding
is skipped, "15-03's chokepoint adopts-current on the next cycle." But 15-03-PLAN.md:110 says
`stored is None` does nothing and adoption is handled by the 15-02 seed. Not a HIGH because the
fallback `current_metric_version()` still gives a usable version and `from_connection()` can retry
seeding on later repo creation. The plan should either add an explicit `stored is None`
adopt-current branch at the chokepoint or remove the claim that 15-03 performs adoption.

LOW: stale threat-boundary wording in 15-05. 15-05-PLAN.md:135 still says `start_date_local` is
"sliced," while the must-haves and mitigation correctly require `datetime.fromisoformat()` parsing.
The actionable task text is clear, so this is only cleanup.

**MEDIUM Fold Confirmation** — coherent: 15-04 option-a E2E required; 15-05 re-waved to wave 4,
`depends_on: [15-03]`, function-level coordination on the only shared file; status-path grep
instruction replaces stale line numbers; worker empty-queue gate fixed; per-process live
fingerprint cache added (uncached retained for seed/tests); `parse_local_hhmm` placed in `metrics.py`.

**Risk Assessment**

Overall risk MEDIUM/LOW. No unresolved HIGH blockers in the amended plan text. The only meaningful
remaining issue is the unseeded-sidecar adoption inconsistency, worth cleaning before execution
because it affects plan clarity and rare seed-failure recovery.

**Unresolved HIGH count: 0**

---

## OpenCode Review

**Summary**

The cycle-2 HIGH (stale memoized/caller-resolved `metric_version` defeating recompute) is fully
resolved by the amended plan text, with explicit, verifiable text in both 15-02 (memo invalidation)
and 15-03 (signature removal + internal post-bump re-resolution + regression test). No new HIGH
concerns were introduced. The five MEDIUM folds from cycle 2 are coherent and correctly applied.
The phase is executable.

**Prior HIGH Resolution Verdict: FULLY RESOLVED.** Three independent plan-text amendments close it:

| Fix | Document | Cite |
|-----|----------|------|
| Memo invalidation | 15-02 Task 2 | "bump_logic_version() MUST invalidate the current_metric_version memo on the repo instance at the END of the bump (after the upsert commits)" |
| Signature change (remove caller param) | 15-03 Task 2 | "REMOVE the `metric_version: int` parameter from materialize_read_model_stage" |
| Internal post-bump re-resolution | 15-03 Task 2 | "resolve current_version = repo.current_metric_version() AFTER the bump (the 15-02 memo was just invalidated by bump_logic_version, so this returns the NEW version on a recompute cycle)" |
| Stale-version regression test | 15-03 Task 2 | "Add a regression test... forces stored != live, runs the stage on the SAME repo, and asserts the metric_version actually materialized equals the bumped (N+1) version" |

Together: the repo memo is cleared inside `bump_logic_version` after the upsert, and the stage's
only version source is a fresh `repo.current_metric_version()` call that occurs AFTER bump returns,
guaranteeing the memo is already cleared and the re-read hits the freshly-written sidecar row
(N+1 on recompute, stored N on no-change). No caller can inject a stale version because the param
no longer exists on the stage signature.

**New Concerns**

All four callers updated? MEDIUM → LOW. The plan explicitly lists all 4 callers (runtime.py
108/179/273, worker.py 69) in both Task 1 and Task 2. No positional-arg shift affects callers
because the removed param (`metric_version`) comes BEFORE the remaining positional `now_iso`;
after removal the first two positional args are `repo` and `now_iso` — exactly what all 4 callers
pass. No caller breakage risk. Minor LOW: Task 1 and Task 2 both say to update callers (redundant
but not contradictory) — executor should remove the param and update callers in one atomic commit.

Post-bump internal re-resolution: No concerns. The flow is serial and single-threaded (DuckDB is
single-owner): read stored → compute live (cached) → on mismatch bump(N+1) (upserts + invalidates
memo) + enqueue(N+1) → `current_metric_version()` fresh read → N+1 → materialize at N+1.
(1) memo invalidation happens at end of bump, re-read is after bump returns → guaranteed cleared;
(2) no other code path calls `current_metric_version()` between bump and re-read (adjacent in the
same function body); (3) unseeded `stored is None` path: no bump, fallback to fact-table max or 1,
correct; (4) the regression test directly validates enqueue-version == materialize-version.

**MEDIUM fold coherence** — all RESOLVED: 15-04 option-a E2E; 15-05 `depends_on: [15-03]` rewave
with function-level coordination; status-path grep instruction; `cached_logic_fingerprint()`
per-process cache; `parse_local_hhmm` in `metrics.py`.

**Minor observations (LOW)**

1. Unseeded sidecar never self-heals at the chokepoint: if the 15-02 seed fails transiently
   (import error), the sidecar stays unseeded until the next `from_connection` (service restart).
   Degrades gracefully (fallback version, no crash), but auto-recompute unavailable until restart.
   Not a correctness issue.
2. Dual update of callers across Task 1 and Task 2 — do signature removal + caller update atomically.
3. 15-05 T-15-10 threat model cleaned up (no longer "opaque string slice"); now uses
   `datetime.fromisoformat()` + `strftime('%H:%M')`.

**Risk Assessment**

Overall: LOW. The single cycle-2 HIGH is fully resolved across both 15-02 (memo invalidation) and
15-03 (signature removal + internal re-resolution + regression test). All five MEDIUM folds coherent.
No new HIGH. The two LOW notes (unseeded self-heal deferral, caller-update atomicity) are
implementation-level and do not affect correctness.

**Unresolved HIGH count: 0**

---

## Consensus Summary

Both reviewers independently and unambiguously conclude that the **single cycle-2 HIGH (stale
memoized / caller-resolved `metric_version`) is FULLY RESOLVED**, and that the amendments introduced
**zero new HIGH concerns**. Both cite specific amended plan text:

- 15-02 Task 2 / must-have: `bump_logic_version()` invalidates the `current_metric_version` memo at
  the END of the bump (after the upsert commits); same-repo regression test (populate memo at v →
  bump to v+1 → assert read returns v+1).
- 15-03 Task 2: `materialize_read_model_stage` loses its `metric_version` parameter and re-resolves
  `repo.current_metric_version()` INTERNALLY, after the fingerprint compare-and-bump; regression
  test asserts materialized version == bumped N+1.

**Independent code verification (this cycle):** The orchestrator verified the prior-HIGH fix and the
param-removal against the live source (plans not yet executed):
- The current chokepoint signature is `materialize_read_model_stage(repo, metric_version, now_iso,
  renew_lease, limit=None)` (`_sync_ops.py:269`). Removing `metric_version` yields `(repo, now_iso,
  renew_lease, limit=None)`.
- There are EXACTLY 4 callers — runtime.py:108, runtime.py:179, runtime.py:273, worker.py:69 — and
  each passes `CURRENT_METRIC_VERSION` as the 2nd positional arg immediately followed by `now_iso`.
  Deleting that one argument line at each site shifts `now_iso` up to 2nd positional, matching the
  new signature. No keyword caller depends on the removed name; no positional misalignment results.
  The plan names all 4 sites. The param-removal is mechanically clean → the reviewers' "no new HIGH"
  conclusion holds against the actual source.

### Agreed Strengths

- Cycle-2 HIGH closed at BOTH ends: memo invalidation inside `bump_logic_version` (single guaranteed
  point) AND param removal + post-bump internal re-resolution at the chokepoint, plus a dedicated
  same-repo regression test guarding it.
- Post-bump re-resolution is correct in a single-threaded, single-owner DuckDB process: the memo is
  cleared before the re-read, no intervening `current_metric_version()` call can re-stale it, and the
  unseeded fallback path is sound.
- All five cycle-2 MEDIUM folds applied coherently (15-04 option-a E2E, 15-05 parallel rewave,
  status-path grep, per-process fingerprint cache, layering-neutral helper home).

### Agreed Concerns (fold in manually — none are HIGH)

1. **[MEDIUM] Unseeded-sidecar self-healing text is inconsistent across 15-02 and 15-03.** 15-02:87
   claims "15-03's chokepoint adopts-current on the next cycle," but 15-03:110 says when `stored is
   None` the chokepoint does nothing (adoption handled by the 15-02 seed). Both reviewers flag this
   (codex MEDIUM, opencode LOW). Functionally safe — `current_metric_version()` falls back to the
   fact-table max (or 1) so reads never break, and a later `from_connection()` re-attempts the seed —
   but if the seed fails transiently (e.g. ImportError), auto-recompute is unavailable until the next
   repo creation / service restart. **Fix options:** (a) add an explicit `stored is None` adopt-current
   branch at the chokepoint (write the sidecar with the current/fallback version + live fingerprint,
   do NOT enqueue), OR (b) reword 15-02:87 to drop the claim that 15-03 performs adoption and state
   the seed re-attempts on next `from_connection`. Either makes the two plans agree.

### Other items to fold (LOW)

- **Caller-update atomicity (opencode):** Task 1 and Task 2 of 15-03 both instruct updating the 4
  stage callers — redundant but not contradictory. Execute the signature removal + all 4 caller edits
  as one atomic commit to avoid a transient broken-import state.
- **15-05 threat-row wording (codex):** T-15-10's "trust boundary" line still describes the value as
  "sliced"; the must-haves/mitigation correctly require `fromisoformat()` parsing. Cosmetic cleanup.
- **ROADMAP wave metadata is stale (orchestrator note):** `.planning/ROADMAP.md` still lists 15-05 in
  "Wave 4 (blocked on Wave 3)" and 15-04 in "Wave 3," whereas the amended plan frontmatter has both
  15-04 and 15-05 at `wave: 4` / `depends_on: [15-03]`. Plan frontmatter is the source of truth for
  the executor; the ROADMAP prose is a doc-consistency tidy, not a blocker.

### Divergent Views

None of substance. The only delta is severity labeling of the unseeded-sidecar item (codex MEDIUM
vs opencode LOW); both agree it is non-blocking and below HIGH. Both reviewers report **Unresolved
HIGH count: 0**.

### Net Assessment

The cycle-2 HIGH is closed and independently verified against the source. No new HIGH was introduced
by removing the chokepoint's `metric_version` param or by the post-bump internal re-resolution. The
phase is **executable**. Remaining items are one MEDIUM plan-text consistency tidy (unseeded-sidecar
adoption: make 15-02 and 15-03 agree) and a few LOW cosmetic/atomicity notes — fold manually; none
require a replan loop.

**Current cycle unresolved HIGH count: 0.**
