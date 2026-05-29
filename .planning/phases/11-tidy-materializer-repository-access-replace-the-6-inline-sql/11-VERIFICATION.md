---
phase: 11-tidy-materializer-repository-access-replace-the-6-inline-sql
verified: 2026-05-30T00:00:00Z
status: passed
score: 3/3 must-haves verified
overrides_applied: 0
---

# Phase 11: Tidy Materializer Repository Access — Verification Report

**Phase Goal:** Replace the 6 inline-SQL `repo._fetchone`/`repo._fetchall` call sites in `read_model_materializer.py` with named methods on `DuckDBRepository`. No behavior change; full test suite stays green. Closes IN-03 from Phase 10.
**Verified:** 2026-05-30T00:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `read_model_materializer.py` contains no calls to `repo._fetchone` or `repo._fetchall` | VERIFIED | `grep -v "^#" read_model_materializer.py \| grep -c "repo\._fetchone\|repo\._fetchall"` → **0** |
| 2 | `DuckDBRepository` has named methods covering all 6 former call sites | VERIFIED | `grep -c "def stream_counts_for_activity\|def zone_seconds_for_activity\|def daily_fact_sums\|def rolling_load_aggregate\|def training_model_row\|def rolling_cardiac_metric_rows" repository.py` → **6** |
| 3 | Full pytest suite exits 0 — no materialization behavior changed | VERIFIED | `uv run pytest tests/test_read_model_materialization.py -x -q` → **6 passed**; `uv run pytest tests/test_duckdb_repository.py -x -q` → **5 passed**; orchestrator-recorded full-suite run: **323 passed** |

**Score:** 3/3 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mcp_strava/adapters/duckdb/repository.py` | 6 new named query methods | VERIFIED | All 6 methods present at lines 1361–1475, positioned after `stream_altitude_rows`. Each uses `_fetchone`/`_fetchall` internally — correct. |
| `src/mcp_strava/adapters/duckdb/read_model_materializer.py` | Updated callers using named repo methods | VERIFIED | `_stream_counts` (line 43) and `_zone_seconds` (line 54) are one-liner delegations; `_materialize_daily_facts` (line 236), `_materialize_rolling_facts` (lines 320–322) use named methods only. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `read_model_materializer.py` | `DuckDBRepository` | `repo.stream_counts_for_activity`, `repo.zone_seconds_for_activity`, `repo.daily_fact_sums`, `repo.rolling_load_aggregate`, `repo.training_model_row`, `repo.rolling_cardiac_metric_rows` | WIRED | All 6 named methods called at the correct sites; no files outside `repository.py` call `_fetchone`/`_fetchall` (grep returned empty). |

---

### Data-Flow Trace (Level 4)

Not applicable — this is a no-behavior-change refactor. SQL text, parameter order, and parameter types were verified byte-identical by the code reviewer (11-REVIEW.md). No new data paths introduced.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Materializer tests pass | `uv run pytest tests/test_read_model_materialization.py -x -q` | 6 passed | PASS |
| Repository tests pass | `uv run pytest tests/test_duckdb_repository.py -x -q` | 5 passed | PASS |
| Full suite (orchestrator-recorded) | `uv run pytest -q` | 323 passed | PASS |

---

### Probe Execution

No probes declared for this phase.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| Code quality / boundary hygiene (Phase 10 REVIEW IN-03) | 11-01-PLAN.md | Materializer must not call private repository helpers | SATISFIED | Zero `_fetchone`/`_fetchall` calls outside `repository.py`; 6 named public methods created; tests green. |

Note: This requirement is an intra-project code-review finding, not a formal REQUIREMENTS.md ID. No entry in REQUIREMENTS.md maps to Phase 11 — the traceability table covers v1 through v2 requirements, all assigned to Phases 1–7. Phase 11 is a tidy-up phase that satisfies an internal quality constraint from Phase 10's review. No orphaned REQUIREMENTS.md IDs found.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `repository.py:1397` | 1397 | `tuple(int(...) for ...)` returns `tuple[int, ...]` not `tuple[int,int,int,int,int]` | INFO | Static-checker annotation mismatch only; runtime always 5 elements; identical to pre-refactor behavior. Flagged as IN-03 in 11-REVIEW.md. |
| `repository.py:1399,1419` | 1399, 1419 | `daily_fact_sums`, `rolling_load_aggregate` typed `dict\|None` but callers dereference unconditionally | WARNING | Latent `TypeError` if row were None; both are `SUM`/`COUNT` with no `GROUP BY` so DuckDB always returns a row. Pre-refactor shape identical. Flagged as WR-01 in 11-REVIEW.md. |

No `TBD`, `FIXME`, or `XXX` markers in modified files. No stubs. No placeholder returns. WR-01 is a pre-existing latency (not introduced by this phase); not a blocker.

---

### Human Verification Required

None.

---

### Gaps Summary

No gaps. All 3 must-have truths verified against the live codebase. The boundary is fully closed: the materializer calls only named public methods; `_fetchone`/`_fetchall` are confined to `repository.py`. Tests green. The code-review warnings (WR-01, IN-01, IN-02, IN-03) are all pre-existing or optional style improvements — none block the phase goal.

---

_Verified: 2026-05-30T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
