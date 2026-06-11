---
phase: 15
phase_name: "self-invalidating-read-model-source-fingerprint-auto-recompu"
project: "mcp-strava"
generated: "2026-06-04"
counts:
  decisions: 8
  lessons: 5
  patterns: 7
  surprises: 6
missing_artifacts:
  - "15-UAT.md (no user-acceptance file; verification was scripted)"
---

# Phase 15 Learnings: Self-invalidating read-model, walk TRIMP discount, workout time fields

## Decisions

### Fingerprint covers the full recursive import closure, not a "compute vs plumbing" subset
`COMPUTE_SOURCE_MODULES` lists the full 14-module transitive `mcp_strava.*` closure reachable from `read_model_materializer`, not the plan's literal 8-module "compute" subset.

**Rationale:** It is the only self-consistent definition where the AST-walk completeness check and the direct-import assertion cannot disagree. It makes coverage automatic-by-construction — no human judgment call can silently drop a module. Over-invalidation (a `settings.py` env-knob edit also flips the fingerprint) is the safe, cheap direction; under-invalidation is the exact bug the phase prevents.
**Source:** 15-01-SUMMARY.md

### Adopt-current seed makes deploying the phase a no-op recompute
The `read_model_logic_version` sidecar is seeded at repository construction with the *live* `compute_logic_fingerprint()`, so the first refresh after deploy sees `stored == live` and recomputes nothing.

**Rationale:** Turning `metric_version` into a system-managed counter must not itself trigger a full recompute on rollout. Seed-equals-current by construction guarantees that.
**Source:** 15-02-SUMMARY.md

### The materialize stage re-resolves the version internally post-bump (never caller-passed)
On a fingerprint mismatch the chokepoint bumps, then re-reads `current_metric_version()` from the sidecar memo rather than trusting a caller-passed int.

**Rationale:** Guarantees the just-enqueued dirty rows (N+1) and the materialize version (N+1) agree — a stale caller value can never leave rows queued at N+1 while materialization runs at N (cycle-2 stale-version guard).
**Source:** 15-03-SUMMARY.md

### R11 — pin `metric_version = current` on every fact/aggregate/status read; never blend
Point, aggregate, and status SELECTs all bind `metric_version = current` (bound as `?`, never string-formatted).

**Rationale:** Reads must be current-version-only. Blending an old and a new version in one aggregate would silently corrupt totals during/after a recompute.
**Source:** 15-03-SUMMARY.md

### Walk TRIMP discount lives in a pure domain function, out of SQL, rounded once
`discounted_effective_trimp(by_sport)` discounts only the Walk-sport portion in `metrics.py`; the per-sport daily aggregation mirrors the per-day total range/bounds; `observed_trimp` stays raw.

**Rationale:** Keep domain math out of SQL and storage; round a single time at the end (a rounding case was chosen where per-sport rounding would visibly differ). The constant lives in a fingerprinted module so editing it auto-recomputes — the zero-knob proof.
**Source:** 15-04-SUMMARY.md

### Split the materialized wall-clock label from the read-time relative value
`start_time_local` (HH:MM) is a materialized fact column (a stable wall-clock label); `relative_time` ("Nd Hh"/"Hh Mm" ago) is computed at read time from `now`.

**Rationale:** One is a fixed historical fact, the other is relative to the moment of the query — they have different lifetimes and must not share storage.
**Source:** 15-05-SUMMARY.md

### WR-02 is a UTC fix, not timezone-handling
The data-freshness staleness clock was made UTC end-to-end; only genuinely mixed UTC-stored-vs-local-`now` comparisons were corrected. `health.py`'s `datetime.now()` vs worker `datetime.now()` pair was deliberately left untouched (local-vs-local, internally consistent).

**Rationale:** Store/compare instants in UTC; localize only for display. The local wall-clock (`start_time_local`) is a legitimate display label, not an instant for arithmetic. Switching one side of the already-consistent local pair would have *introduced* skew.
**Source:** 15-06-SUMMARY.md

### WR-04 fixed at the repository fetch boundary (whole-day atomic batch), not per-fact flags
`dirty_activity_rows_for_materialization` extends a limited batch to whole-day boundaries instead of adding per-fact `completeness_status` flags.

**Rationale:** Daily/rolling rollups read a whole day as their atomic unit, so making the day the indivisible batch unit is the simplest correct fix and keeps the worker drain loop converging.
**Source:** 15-06-SUMMARY.md

---

## Lessons

### `except A, B:` is valid PEP 758 syntax on Python 3.14 — verify reviewer findings against the pinned runtime
A cross-AI code reviewer flagged parenthesis-less `except A, B:` as a Python-2 `SyntaxError` and called it a release BLOCKER ("the test suite cannot have passed against this tree"). The project is pinned to Python ≥3.14, where PEP 758 makes this valid (catches both exception types). It compiles, imports, and 385 tests pass.

**Context:** The claim was disproved by the already-green suite. Reviewer findings are leads, not facts — re-derive severity against the actual runtime and config before acting. Dismissed in 15-REVIEW.md with evidence; saved to project memory.
**Source:** 15-REVIEW.md, 15-VERIFICATION.md, 15-05-SUMMARY.md

### Deploy preflight enforces a table the self-heal seed would create — but runs first
The deploy preflight fails closed on a missing `read_model_logic_version` table *before* the repository's idempotent adopt-current seed can create it, so a pre-Phase-15 live DB crash-loops instead of self-migrating.

**Context:** Surfaced when the rebuilt container met a 2-day-old dev mirror. Worked around by running the in-code seed once; the durable ordering fix (migrate before/within preflight, or make preflight self-heal-tolerant) is deferred to the deploy layer.
**Source:** 15-05-SUMMARY.md

### A multi-commit bump+enqueue is a silent under-invalidation crash window
Originally `bump_logic_version` and `enqueue_metric_version_recompute` were two separate auto-committed statements. A crash between them durably advances the stored fingerprint while losing the enqueue → next cycle sees `stored == live` and never recomputes — the exact failure the phase exists to kill. Proving the fix required a test that *reopens a fresh DB* after an injected failure, not just in-memory state.

**Context:** WR-01, the highest-priority gap-closure fix; now wrapped in one `begin()/commit()` with rollback.
**Source:** 15-06-SUMMARY.md, 15-REVIEW.md

### `python` is not on PATH outside the venv — bare `py_compile` "command not found" masquerades as failure
A `python -m py_compile` check reported "command not found" (not a syntax error) because the interpreter only exists at `.venv/bin/python`. This briefly looked like a compile failure during the false-BLOCKER investigation.

**Context:** Always validate with `.venv/bin/python` or `uv run` (Python 3.14), never the host interpreter (which may be <3.14 and would genuinely choke on PEP 758).
**Source:** this session; 15-05-SUMMARY.md reviewer note

### Deleting a shared constant surfaces hidden coupling in test doubles
Removing `CURRENT_METRIC_VERSION` exposed several worker-path `FakeRepo` doubles that had silently relied on it and lacked `current_metric_version()`.

**Context:** Each had to gain the method and a stubbed chokepoint. Deleting a constant is a cheap way to find every place that depended on it — the compiler/tests become the search.
**Source:** 15-03-SUMMARY.md

---

## Patterns

### Coverage-by-construction poka-yoke (AST import-closure assertion)
A static AST walk recomputes the reachable module set and asserts exact equality with the explicit `COMPUTE_SOURCE_MODULES` tuple, naming the offender on any missing/extra module.

**When to use:** Whenever a hand-maintained manifest must stay in sync with a derivable truth — make the test recompute the truth and fail loudly on drift, rather than trusting a human to update the list.
**Source:** 15-01-SUMMARY.md

### Prove a hash is content-derived, not `hash()`, via PYTHONHASHSEED variation
The fingerprint determinism test asserts equality across `PYTHONHASHSEED=0/1/random` and in a fresh subprocess.

**When to use:** Any persisted/compared digest that must be stable across processes — guard against accidentally depending on salted builtin `hash()`.
**Source:** 15-01-SUMMARY.md

### Single memo invalidation point inside the mutator
`current_metric_version()` is memoized; the memo is cleared *inside* `bump_logic_version()` (after the standalone commit), making the mutator the one guaranteed invalidation site.

**When to use:** Cache a hot read derived from a rarely-changed row; invalidate at the single write that can change it, not at call sites.
**Source:** 15-02-SUMMARY.md

### Structured `_emit` JSON diagnostic instead of `except: pass`
The seed-skip path emits a structured `read_model_logic_version_seed_skipped` event (with `error_type` + truncated error) rather than swallowing the failure silently.

**When to use:** Any defensive try/except around optional/self-healing work — surface the diagnostic code/value so an operator isn't forced to source-dive.
**Source:** 15-02-SUMMARY.md

### Zero-knob E2E proof drives the real chokepoint, not a patched constant
The walk-discount E2E test forces a real fingerprint mismatch → bump → mass-enqueue → re-materialize and asserts the recomputed value, rather than stubbing the version.

**When to use:** Proving an auto-invalidation/auto-recompute mechanism — exercise the actual detector path so the test fails if the wiring breaks, not just the math.
**Source:** 15-04-SUMMARY.md

### Migrate a live DB through the project's own in-code seed path
The pre-Phase-15 dev mirror was migrated by opening it once via `DuckDBRepository.from_path` (whose constructor runs `ensure_provenance_columns` + `_seed_logic_version`) — no ad-hoc DDL.

**When to use:** Bringing an old database to a new schema when the code already contains an idempotent additive migration — reuse it instead of writing throwaway SQL that can diverge from the real path.
**Source:** 15-05-SUMMARY.md

### Whole-day atomic batch keeps aggregate reads version-consistent mid-recompute
Extending the materialization batch to whole-day boundaries makes the day the indivisible unit, so daily/rolling reads never see a half-recomputed day.

**When to use:** When a read aggregates over a natural grouping and a partial write of that group would under-count — make the group the atomic batch unit at the fetch boundary.
**Source:** 15-06-SUMMARY.md

---

## Surprises

### The "release BLOCKER" was a false positive already disproved by 385 passing tests
The headline blocker (`except A, B:` SyntaxError) contradicted a green test suite from the start — modules that "cannot import" can't run 385 passing tests. The contradiction was the tell.

**Impact:** Cost an investigation, but reinforced verifying panel findings against hard evidence (the runtime + the suite) before acting. Net review dropped from 1 BLOCKER+4 warnings to 0 blocking + 4 advisory.
**Source:** 15-REVIEW.md, 15-VERIFICATION.md

### The fingerprint closure is 14 modules, not the plan's literal 8
The materializer transitively imports `settings` (→ `hr_zones`, `mcp_content`; `connection → settings`; `repository → connection/schema/sports/types`), so the real reachable closure is nearly double the plan's "compute" subset.

**Impact:** The plan's own completeness assertions were inconsistent with its literal tuple; listing reality (which the plan explicitly delegated) was the only self-consistent resolution.
**Source:** 15-01-SUMMARY.md

### The R11 version pin shifted numbers in 4 unrelated tests
Pinning to current-version filtered out deliberately-mixed-version fixture rows that fed an old "blend is visible" assertion, changing expected values in all-time defaults, registry modes, and compare-periods tests.

**Impact:** Required reshaping the fixture (revert blended rows to v1, add one dedicated v2 stale row) to keep the R11 proof while restoring every other test's numbers — a reminder that version-pinning has fixture blast radius.
**Source:** 15-03-SUMMARY.md

### The rebuilt container crash-looped on a 2-day-old dev database
The dev mirror predated Phase 15 and lacked the sidecar table + new column; deploy preflight fails closed before the in-code self-heal can run.

**Impact:** Surfaced a latent (since 15-02) preflight-vs-seed ordering gap; worked around for dev, durable fix deferred to the deploy layer.
**Source:** 15-05-SUMMARY.md

### `DuckDBPyConnection.commit` is a read-only C attribute — can't be monkeypatched
The WR-03 RED test couldn't `monkeypatch.setattr(conn, "commit", ...)` (raised `AttributeError`), so it was reframed to instrument `_commit_if_standalone` on a repo subclass.

**Impact:** Minor test-harness rework; a reminder that C-extension attributes resist the usual monkeypatch reflex — instrument the wrapper, not the native object.
**Source:** 15-06-SUMMARY.md

### A WR-04 RED gate was silently empty due to an exclusive-upper-bound range
`fetch_daily_load_facts` filters `day < end_day`; passing `start == end` returned nothing, producing a misleading (passing-for-the-wrong-reason) RED until the range was widened.

**Impact:** Caught before GREEN; underscores checking that a RED test fails for the *intended* reason, not an off-by-one in the query bounds.
**Source:** 15-06-SUMMARY.md
