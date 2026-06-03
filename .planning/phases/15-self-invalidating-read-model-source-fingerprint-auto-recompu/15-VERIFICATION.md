---
phase: 15-self-invalidating-read-model-source-fingerprint-auto-recompu
verified: 2026-06-03T22:10:00Z
status: human_needed
score: 21/21 must-haves verified
overrides_applied: 0
human_verification:
  - test: "WR-01 — accept non-atomic bump+enqueue (3 independent commits) on the single-owner dev instance, OR wrap bump_logic_version + enqueue_metric_version_recompute in one repo.begin()/commit()"
    expected: "A crash between the bump commit and the enqueue commit must not durably advance the sidecar fingerprint while losing the mass-recompute (which would silently strand reads at N+1 with few N+1 facts)"
    why_human: "Risk-acceptance decision: the happy path is proven by passing E2E tests; the gap is a crash-window durability hazard on a single-owner dev instance. Accept-as-is vs harden is an owner call, not a code fact."
  - test: "WR-02 — accept or fix local-vs-UTC timestamp skew: _now_parts/_record_failed_run stamp computed_at/finished_at in server LOCAL time (Asia/Almaty, +5/+6) while staleness compares against UTC now_iso"
    expected: "Freshly materialized facts should not read as 'from the future' or mask/inflate the staleness threshold by up to a day near midnight"
    why_human: "Timezone behavior on the live non-UTC server; the magnitude of operator impact is a judgment call. Not exercised by the unit suite (fixtures use fixed clocks)."
  - test: "WR-03 — accept or fix _record_failed_run committing via repo.conn.commit()/rollback() raw, bypassing duckdb_process_lock()"
    expected: "Failed-run bookkeeping should honor the same single-writer lock contract as every other repository write"
    why_human: "Latent hazard for the worker/owner split; benign on the documented single-owner runtime. Accept vs route-through-locked-helpers is an owner call."
  - test: "WR-04 — accept or fix partial-batch recompute writing under-counted daily/rolling/model facts for the new version while activities for that day are still queued at N+1"
    expected: "Intermediate recompute cycles should not report daily/rolling facts as fully materialized when upstream activity rows for the day remain dirty (worker loop converges eventually, but transient reads under-count)"
    why_human: "Transient correctness during a mass recompute drain; converges by construction. Whether the transient under-count is acceptable for product reads is an owner call."
---

# Phase 15: Self-invalidating read-model, walk TRIMP discount, workout time fields — Verification Report

**Phase Goal:** Auto-recompute materialized facts when metric code/constants change (source-derived fingerprint, no manual version knob); apply a configurable walk TRIMP discount; surface workout start time and relative-time.
**Verified:** 2026-06-03T22:10:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

All three goal pillars are implemented, wired, and proven by passing tests run in this verification (not trusted from SUMMARY):

1. **Zero-knob auto-recompute (REQ-ZEROKNOB)** — source-text fingerprint → sidecar version → chokepoint compare-bump-enqueue, fully wired.
2. **Walk TRIMP discount (REQ-WALK)** — `WALK_TRIMP_DISCOUNT=0.5` applied per-sport to daily `effective_trimp`; observed stays raw; Banister consumes discounted.
3. **Workout time fields (REQ-TIME)** — materialized `start_time_local` (HH:MM, fromisoformat/strftime) + read-time `relative_time` with correct 24h-boundary formatting.

The 4 open items below are advisory WARNINGs (durability-under-crash / timezone-skew / locking-contract / transient-undercount) that do not falsify the goal's happy path but warrant an explicit owner accept/fix decision.

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
| 9 | Chokepoint: live≠stored fingerprint → bump version, record fingerprint, enqueue every activity, no manual step | ✓ VERIFIED | `_sync_ops.py:324-331` bump+enqueue+`logic_fingerprint_changed`; `test_chokepoint_materializes_at_bumped_version_on_fingerprint_mismatch` passes |
| 10 | Chokepoint re-resolves version INTERNALLY post-bump (enqueue N+1 == materialize N+1) | ✓ VERIFIED | `_sync_ops.py:343` `current_version = repo.current_metric_version()` AFTER bump; stage no longer takes a caller metric_version; regression test asserts materialize==N+1 |
| 11 | Unseeded sidecar → ADOPT-CURRENT self-heal (write sidecar, no enqueue), no restart needed | ✓ VERIFIED | `_sync_ops.py:313-320` adopt branch + `read_model_logic_adopted` event; `test_chokepoint_adopts_current_when_sidecar_unseeded` passes |
| 12 | Fingerprint check runs even when dirty queue empty (logic-only edit still recomputes) | ✓ VERIFIED | `worker.py:65` no longer early-returns; calls `materialize_read_model_stage` on `dirty_count==0` |
| 13 | `CURRENT_METRIC_VERSION` deleted everywhere incl. `__init__` re-export + `__all__` | ✓ VERIFIED | `grep -rn CURRENT_METRIC_VERSION src/` returns nothing |
| 14 | Aggregate AND status reads pin `metric_version = current` (no old+new blend, R11) | ✓ VERIFIED | 7 `FROM activity_metric_facts` SELECTs each carry `metric_version = ?` (lines 279/322/352/383/418/461/536 ↔ pins 282/325/355/386/421/463/539); `test_missing_denominators_explicit_and_version_pin_blocks_blend` passes |
| 15 | `aggregate_services.py` threads current version into status + training aggregate reads | ✓ VERIFIED | `aggregate_services.py:74/81/82` resolve+pass `version` |
| 16 | Auto-recompute emits structured log w/ stored/current fingerprint, reason, activities_enqueued, queued_at; run record stamped trigger_reason | ✓ VERIFIED | `_sync_ops.py:333-336` event fields; `read_model_materializer.py:405/472` trigger_reason threaded+stamped |
| 17 | Walk day yields effective_trimp lower than observed by walk portion × (1−discount); non-walk unchanged | ✓ VERIFIED | `discounted_effective_trimp` Run100→100, Walk80→40, mix→140, empty→0; `repository.py:1510` applies it; `test_walk_discount_recomputes_end_to_end_on_fingerprint_mismatch` passes |
| 18 | observed_trimp stays raw undiscounted in daily + model facts; round once at end | ✓ VERIFIED | `metrics.py:327` single `round` over the summed product; `read_model_materializer.py:280` observed left raw |
| 19 | Editing WALK_TRIMP_DISCOUNT flips fingerprint; E2E option-(a) forced stored≠live proves the pipeline fires (version N→N+1, enqueue, re-materialized discount) | ✓ VERIFIED | `constants.py` is in COMPUTE_SOURCE_MODULES; `test_walk_discount_recomputes_end_to_end_on_fingerprint_mismatch` asserts version bump + enqueue + re-materialized effective_trimp |
| 20 | `start_time_local` materialized via fromisoformat+strftime (not [11:16] slice); Z/offset normalized; None on garbage; migrates additively | ✓ VERIFIED | `metrics.py:17` parse_local_hhmm (Z→06:00, offset→11:16, garbage→None); `read_model_materializer.py:228` populates; `schema.py:300` late column |
| 21 | `relative_time` read-time: <24h 'Hh Mm', ≥1d 'Nd Hh', 24h boundary '1d 0h', None on missing | ✓ VERIFIED | `metric_services.py:294` `_relative_time`; spot-check 2h30m→'2h 30m', exactly24h→'1d 0h', 3d4h→'3d 4h', future→'0h 0m', garbage→None |

**Score:** 21/21 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/mcp_strava/metric_registry.py` | COMPUTE_SOURCE_MODULES + compute/cached_logic_fingerprint | ✓ VERIFIED | tuple @2486 (14-module closure), fn @2504, cached @2545; start_time_local + relative_time metrics registered |
| `tests/test_logic_fingerprint.py` | determinism/sensitivity/completeness + unconditional getsource smoke | ✓ VERIFIED | 11 tests incl. `test_getsource_succeeds_on_every_compute_source_module`, all pass |
| `src/mcp_strava/adapters/duckdb/schema.py` | sidecar DDL + DUCKDB_TABLES + start_time_local late col | ✓ VERIFIED | @262 DDL, @25 table, @300 late column |
| `src/mcp_strava/adapters/duckdb/repository.py` | version helpers + memo + seed + observed_trimp_history_by_sport | ✓ VERIFIED | @730/745/765/787; @1306 per-sport agg; @1510 discount applied |
| `src/mcp_strava/refresh/_sync_ops.py` | fingerprint compare+bump+enqueue+adopt at chokepoint | ✓ VERIFIED | @276-360; wires orphan enqueue_metric_version_recompute |
| `src/mcp_strava/refresh/worker.py` | empty-queue gate fix | ✓ VERIFIED | @65 no early return; calls stage on dirty_count==0 |
| `src/mcp_strava/adapters/duckdb/aggregate_queries.py` | metric_version=? pin across _where_clause/_effective_range/status | ✓ VERIFIED | all 7 fact SELECTs pinned; signatures take metric_version |
| `src/mcp_strava/application/aggregate_services.py` | threads current version | ✓ VERIFIED | @74/81/82 |
| `src/mcp_strava/constants.py` | WALK_TRIMP_DISCOUNT=0.5 (no env) | ✓ VERIFIED | @135 |
| `src/mcp_strava/metrics.py` | discounted_effective_trimp + parse_local_hhmm (pure, no storage import) | ✓ VERIFIED | @307, @17; domain boundary intact (imports only constants) |
| `src/mcp_strava/application/metric_services.py` | relative_time + start_time_local on payload, now threaded | ✓ VERIFIED | @294/337/369/370; now param @329/410 |
| `tests/test_docker_runtime.py` | packaged-install getsource smoke | ✓ VERIFIED | @300; PASSED (container running) — getsource OK under pip install /app |
| `AGENTS.md` | one plain-language self-recompute line, no manual-version wording | ✓ VERIFIED | @179; no CURRENT_METRIC_VERSION/version-constant/manual-recompute residue |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `metric_registry.compute_logic_fingerprint` | `inspect.getsource / import_module` | sha256 over sorted name\x00source pairs | ✓ WIRED | @2522-2523 runtime import inside fn (no top-level cycle, confirmed by import) |
| `_sync_ops.materialize_read_model_stage` | `repository.enqueue_metric_version_recompute` | fingerprint mismatch → mass enqueue | ✓ WIRED | @328-329; orphan now called |
| `aggregate_queries._where_clause` | metric_version pin | WHERE metric_version = ? | ✓ WIRED | parameterized `?`, never formatted |
| `read_model_materializer._activity_fact` | `activity_metric_facts.start_time_local` | HH:MM from start_date_local | ✓ WIRED | @228 |
| `metric_services._activity_payload` | relative_time | now − activity_dt formatted | ✓ WIRED | @370 |
| `repository._ensure_schema_extensions` | sidecar seed row | idempotent insert-if-absent w/ live fingerprint | ✓ WIRED | seed adopts-current; idempotent across constructions (test passes) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| effective_trimp (daily facts) | per-sport raw TRIMP map | `observed_trimp_history_by_sport` (real DuckDB group-by day+sport) → `discounted_effective_trimp` | Yes | ✓ FLOWING |
| start_time_local (payload) | fact column → parse fallback | materialized column / `parse_local_hhmm(summary.start_date_local)` | Yes | ✓ FLOWING |
| relative_time (payload) | now − parsed start_date_local | service `now` param + summary_json | Yes | ✓ FLOWING |
| metric_version (chokepoint materialize) | post-bump resolved int | `repo.current_metric_version()` off memo-invalidated sidecar | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Package compiles on 3.14 (PEP 758 except A,B valid) | `py_compile` of 3 flagged files | COMPILE OK | ✓ PASS |
| Fingerprint deterministic 64-hex, cached==compute | import + call | len 64, hex True, cached==compute True | ✓ PASS |
| Discount math | `discounted_effective_trimp` | Run100→100, Walk80→40, mix→140, empty→0 | ✓ PASS |
| parse_local_hhmm | Z/offset/garbage/None | 06:00 / 11:16 / None / None | ✓ PASS |
| relative_time 24h boundary | `_relative_time` | 2h30m, 1d 0h @24h, 3d 4h, future→0h 0m, garbage→None | ✓ PASS |
| ruff check src tests | `uv run ruff check` (via .venv) | All checks passed | ✓ PASS |
| ruff format --check src tests | `.venv ruff format --check` | 105 files already formatted | ✓ PASS |
| pyright src | `uv run pyright src` | 0 errors, 0 warnings | ✓ PASS |
| Full unit suite | `.venv -m pytest -q` | 385 passed | ✓ PASS |
| 10 goal-critical regression tests | targeted pytest | 10 passed | ✓ PASS |
| Packaged-install getsource smoke | `tests/test_docker_runtime.py::...packaged_install` | 1 passed (container up) | ✓ PASS |

> Note: `.venv/bin/python -m pyright` (wrong invocation) reported 10 third-party import-resolution errors (duckdb/mcp stubs not on path). The project's actual gate is `uv run pyright src` (Justfile:22, CI ci.yml:41) which resolves the venv and reports 0 errors. SUMMARY's "pyright clean" claim is accurate.

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes declared for this phase. Equivalent runnable verification covered by the unit suite + docker compose exec packaged-install smoke (both run above and passing).

### Requirements Coverage

The phase requirement IDs (REQ-ZEROKNOB, REQ-WALK, REQ-TIME) are **phase-local labels** declared in PLAN frontmatter and the ROADMAP "Requirements" prose line. They are NOT formal IDs in `.planning/REQUIREMENTS.md` (which tracks FOUND-/SAFE-/READMODEL-/REGISTRY- style IDs). This is consistent with how the ROADMAP describes Phase 15 — its requirements are stated as prose, not mapped to a REQUIREMENTS.md row (the closest formal item, REGISTRY-03, remains Deferred and is not claimed by this phase). No orphaned formal requirement is assigned to Phase 15 in the traceability table. All three phase-local labels are accounted for below.

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| REQ-ZEROKNOB | 15-01, 15-02, 15-03, 15-05 | Zero-knob read-model auto-invalidation | ✓ SATISFIED | Truths 1-16, 19; E2E recompute test passes |
| REQ-WALK | 15-04 | Port Hermes WALK_TRIMP_DISCOUNT so walks stop counting at full TRIMP in Banister | ✓ SATISFIED | Truths 17-19; discount + E2E tests pass |
| REQ-TIME | 15-05 | Finer workout time granularity (start HH:MM + relative ago) | ✓ SATISFIED | Truths 20-21; parse + relative_time spot-checks pass |

Note: phase-local labels are not added to REQUIREMENTS.md traceability; if the owner wants formal traceability, a REQUIREMENTS.md row mapping these capabilities to Phase 15 could be added (informational, not a gap).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| metrics.py / read_model_materializer.py / metric_services.py | 45 / 79,85,104 / 168,263,290 | `except A, B:` (PEP 758) | ℹ️ Info | NOT a defect — valid bare-tuple syntax on Python ≥3.14 (project pinned); compiles, lints, 385 tests pass. Reviewer CR-01 BLOCKER correctly dismissed. |
| _sync_ops.py | 324-331 | bump + enqueue not in one transaction | ⚠️ Warning | WR-01 — see Human Verification (crash-window durability) |
| read_model_materializer.py | 27,380 | local-time vs UTC staleness stamps | ⚠️ Warning | WR-02 — see Human Verification |
| read_model_materializer.py | 392-394 | `_record_failed_run` bypasses process lock | ⚠️ Warning | WR-03 — see Human Verification |
| read_model_materializer.py | 413-484 | partial-batch under-counts daily/rolling for new version | ⚠️ Warning | WR-04 — see Human Verification |

No debt markers (TBD/FIXME/XXX without follow-up reference) found in phase-15 files. No stub/placeholder/empty-return anti-patterns: every artifact carries substantive, data-flowing implementation.

### Human Verification Required

The 4 advisory WARNINGs from 15-REVIEW.md (WR-01..04) are real code observations confirmed against the source in this verification, but none falsify the phase goal — the happy-path auto-recompute, discount, and time fields are all proven by passing tests. Each is an owner accept-or-harden decision (detailed in frontmatter `human_verification`):

1. **WR-01** — non-atomic bump+enqueue (3 commits): crash between commits could durably advance the fingerprint while losing the mass-recompute. Fix is a one-`begin()/commit()` wrap; the reviewer supplied the patch. Accept on single-owner dev vs harden.
2. **WR-02** — local-vs-UTC timestamp skew (Asia/Almaty +5/+6) on age-based staleness.
3. **WR-03** — `_record_failed_run` raw commit bypassing `duckdb_process_lock()` (latent worker/owner-split hazard).
4. **WR-04** — partial-batch recompute reports daily/rolling/model facts as complete while upstream activities are still queued at N+1 (transient under-count; converges).

Per the project memory ("prefer scripted verification over human_needed"), WR-01 and WR-03 in particular are cheaply fixable with the reviewer-supplied patches if the owner prefers hardening over acceptance; they are surfaced here for that decision rather than auto-applied because they were classified advisory in the approved review.

### Gaps Summary

No goal-blocking gaps. All 21 must-have truths are VERIFIED against the codebase (not trusted from SUMMARY) and backed by tests executed during this verification: 385 pytest pass, ruff check + format --check clean, `uv run pyright src` 0 errors, package compiles and imports on Python 3.14.2, and the live container's packaged-install fingerprint smoke passes. The phase goal — zero-knob auto-recompute, walk TRIMP discount, and workout time fields — is achieved.

Status is `human_needed` (not `passed`) solely because the 4 advisory durability/correctness WARNINGs (WR-01..04) require an explicit owner accept-or-harden decision. They are not blockers: the goal's happy path is fully functional and proven.

---

_Verified: 2026-06-03T22:10:00Z_
_Verifier: Claude (gsd-verifier)_
