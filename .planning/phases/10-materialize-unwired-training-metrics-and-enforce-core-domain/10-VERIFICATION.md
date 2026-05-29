---
phase: 10-materialize-unwired-training-metrics-and-enforce-core-domain
verified: 2026-05-29T10:00:00Z
status: passed
status_note: "Initially human_needed; all 4 items resolved 2026-05-29 via scripts — 3 RED-proven regression tests (WR-01/02/05) + a verified live re-materialize of 604 activities (non-null 0→502/597/509/603, confirmed through MCP get_workout_detail). See 10-HUMAN-UAT.md (status: passed)."
score: 13/13
overrides_applied: 0
human_verification:
  - test: "Confirm WR-01 guard behaves correctly on real data: run the full materializer over the live DuckDB and confirm no 'duplicate time_offset' rows exist in the streams table (or that duplicates are handled correctly). Check: SELECT activity_id, time_offset, COUNT(*) c FROM streams GROUP BY 1,2 HAVING c > 1 LIMIT 5;"
    expected: "Either zero rows (no duplicates exist), or if duplicates do exist, the calc_hr_recovery de-duplication path correctly re-validates the MIN_STREAM_POINTS guard against the de-duplicated count and does not crash."
    why_human: "The fix documents uniqueness as a precondition and adds a re-check, but no automated test seeds duplicate time_offset rows to assert the corrected guard path. Live data is the only source of truth for whether duplicates exist and whether the guard handles them."
  - test: "Confirm WR-02 fix: the start-HR window cannot overshoot pause_end. Inspect the calc_hr_recovery logic at src/mcp_strava/metrics.py lines 132-139 — pause_window is sliced to [pause_start_idx:end_idx+1] and start_times/end_times are derived from that slice. Verify by reviewing a real activity with short pauses (< 5 seconds of stopped velocity) that hr_start is not contaminated by post-pause moving-HR samples."
    expected: "pause_window[:5] never extends past end_idx; for pauses shorter than 5 samples the window naturally contains fewer points and hr_start is computed over a shorter but valid range."
    why_human: "No regression test seeds a pause shorter than 5 samples to assert the clamped window — the test fixture uses 33-row pauses which are always >= 5 samples. The fix is correct by inspection but the edge case (pause of 1-4 samples) has no automated coverage."
  - test: "Confirm WR-05 fix: recovery rate denominator uses sampled_rest_sec = len(pause_window) instead of wall-clock pause_dur. Spot-check against an activity with visible GPS gaps (3-second gaps in the stream): the bpm/min rate should reflect the actual sampled seconds, not the wall-clock span."
    expected: "For a clean 1Hz stream the difference is zero (sampled == wall-clock). For a stream with 3s gaps the rate is slightly higher (fewer sampled seconds in denominator) which is the correct direction — the recovery is compressed, not inflated."
    why_human: "No test exercises streams with 3-second gaps specifically to verify the denominator change. This is observable only on real data or a dedicated gap fixture."
  - test: "Live re-materialize: after running the read-model re-materialization on the live DuckDB, call MCP get_workout_detail and compare_periods and verify that hr_recovery_median_rate, vertical_speed_vmh, cardiac_drift_pct, and hrr_pct return real non-null values for activities that have the relevant streams."
    expected: "Non-null values for the four metric families where the activity has the required stream data. The VALIDATION.md post-deploy sanity query should also confirm: SELECT count(*) FILTER (WHERE hr_recovery_median_rate IS NOT NULL) AS hr_rec_nonnull, count(*) FILTER (WHERE cardiac_drift_pct IS NOT NULL) AS drift_nonnull, count(*) FILTER (WHERE hrr_pct IS NOT NULL) AS hrr_nonnull, count(*) AS total FROM activity_metric_facts; — non-null counts must be > 0."
    why_human: "Live DuckDB is a single-writer database not available in CI. The operator must run the re-materialize explicitly. This is documented in VALIDATION.md as the only mandatory manual step."
---

# Phase 10: Verification Report

**Phase Goal:** Finish the deferred 2026-05-25 decision (quick task 260525-jpo): make `metrics.py` a pure domain module and wire its compute into the read-model materializer so the registered-but-empty metrics (hr_recovery, vertical_speed, cardiac_drift, hrr_pct + rolling medians) are actually computed instead of stored as null/0 — closing the last open PROJECT.md requirement (core/domain separation) and fixing a latent product bug.
**Verified:** 2026-05-29T10:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | metrics.py exposes pure calc_hr_recovery(rows), calc_vertical_speed(rows), calc_cardiac_drift(rows, sport_type=None), calc_hrr_pct(median_hr, hr_rest, hr_max) with plain-data signatures | VERIFIED | All four functions present at file top, correct signatures confirmed by reading src/mcp_strava/metrics.py |
| 2 | metrics.py no longer imports from mcp_strava.db | VERIFIED | `grep -n "from mcp_strava.db import" src/mcp_strava/metrics.py` exits 1 (no match) |
| 3 | `import mcp_strava.metrics` succeeds with no mcp_strava.db dependency | VERIFIED | `uv run python -c "import mcp_strava.metrics; print('OK')"` outputs OK |
| 4 | calc_hrr_pct(150, 50, 200) == 66.7 | VERIFIED | Runtime check returns 66.7 |
| 5 | All four pure functions return None on insufficient input | VERIFIED | test_metrics_pure.py covers all None guards; 4 tests pass |
| 6 | All 14 previously-default metric columns are wired in _activity_fact (hr_recovery_pause_count, hr_recovery_total_rest_sec, hr_recovery_median_rate, hr_recovery_best_rate, hr_recovery_worst_rate, hr_recovery_avg_rate, vertical_speed_vmh, vertical_speed_total_ascent_m, vertical_speed_duration_hours, cardiac_drift_pct, cardiac_drift_severity, cardiac_drift_significant, cardiac_drift_quality, hrr_pct) | VERIFIED | All 14 column assignments confirmed in materializer at lines 208-223 |
| 7 | _activity_fact fetches stream rows via repo and calls pure functions | VERIFIED | Lines 162-177 in materializer: hr_rows, alt_rows, drift_rows, median_hr fetched; calc_hr_recovery/calc_vertical_speed/calc_cardiac_drift/calc_hrr_pct called |
| 8 | hrr_pct uses per-activity observed max (with cross-activity fallback) | VERIFIED | hr_max_for_hrr = max_hr if max_hr is not None else hr_max_observed at line 176; explicit WR-03 comment in code |
| 9 | Rolling medians populate automatically — asserted, not assumed | VERIFIED | test_duckdb_materializer_rolling_median_populates asserts rolling["median_hr_recovery"] is not None; test passes |
| 10 | Pause-inclusive fixture exercises hr_recovery family at integration level | VERIFIED | test_duckdb_materializer_pause_inclusive_hr_recovery: 33-row stopped fixture, asserts hr_recovery_median_rate not None and pause_count >= 1; passes |
| 11 | No-HR case: only HR-derived columns stay at defaults, no crash | VERIFIED | test_duckdb_materializer_no_hr_columns_stay_at_defaults passes; correctly does not assert vertical_speed_* |
| 12 | Domain import-boundary guard widened: training/metrics/cardiac_drift/hr_zones/sports forbidden from importing mcp_strava.db and mcp_strava.adapters.duckdb | VERIFIED | test_read_modules_do_not_import_storage_strava_or_refresh covers all 5 modules with 4-prefix disallow tuple; passes; out-of-band RED proof documented in 10-02-SUMMARY.md |
| 13 | Dead code removed: get_daily_trimp_history, enrich_activity refs, stale test imports | VERIFIED | grep exits 1 on all three checks; db.py, test_smoke.py, test_metric_services.py, test_security_guards.py all clean |

**Score:** 13/13 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mcp_strava/metrics.py` | Pure domain functions, no storage import | VERIFIED | 256 lines; imports only constants, types, cardiac_drift; four pure functions present |
| `tests/test_metrics_pure.py` | Unit tests for all four pure functions | VERIFIED | 189 lines; 5 tests (4 original + CR-01 regression test_calc_vertical_speed_nonzero_leading_offset) |
| `src/mcp_strava/adapters/duckdb/read_model_materializer.py` | Materializer calling pure functions for all 14 columns | VERIFIED | calc_hr_recovery/calc_vertical_speed/calc_cardiac_drift/calc_hrr_pct imported at line 11; all 14 columns wired lines 208-223 |
| `tests/test_read_model_materialization.py` | 4 new integration tests (populated columns, pause-inclusive, rolling-median, no-HR) | VERIFIED | All 4 tests present at lines 282, 305, 319, 339; all pass |
| `tests/test_security_guards.py` | Widened boundary guard for domain modules | VERIFIED | test_read_modules_do_not_import_storage_strava_or_refresh at line 373; 5 modules, 4 prefixes; passes |
| `src/mcp_strava/db.py` | get_daily_trimp_history removed | VERIFIED | grep exits 1 |
| `tests/test_smoke.py` | No dangling imports from deleted symbols | VERIFIED | No get_daily_trimp_history, DecouplingResult, enrich_activity, calc_decoupling_with_gate |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/mcp_strava/metrics.py` | `mcp_strava.cardiac_drift` | `from mcp_strava.cardiac_drift import cardiac_drift as _drift_algo` | WIRED | Line 9 of metrics.py |
| `src/mcp_strava/adapters/duckdb/read_model_materializer.py` | `mcp_strava.metrics` | `from mcp_strava.metrics import calc_hr_recovery, calc_vertical_speed, calc_cardiac_drift, calc_hrr_pct` | WIRED | Line 11 of materializer |
| `_activity_fact` | `repo.stream_hr_velocity_time_rows / stream_altitude_rows / stream_hr_velocity_simple_rows / activity_median_heartrate` | row fetch feeding pure functions | WIRED | Lines 162-165 of materializer |
| `_materialize_rolling_facts` | `hr_recovery_median_rate / cardiac_drift_pct` source columns | SELECT in rolling facts query | WIRED | Lines 423-424 of materializer confirm correct column name match |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `_activity_fact` in read_model_materializer | hr_rec (HrRecovery) | repo.stream_hr_velocity_time_rows(activity_id) → DuckDB query | Yes — parameterized repo method returns rows from streams table | FLOWING |
| `_activity_fact` | vspeed (VerticalSpeed) | repo.stream_altitude_rows(activity_id) → DuckDB query | Yes | FLOWING |
| `_activity_fact` | drift (CardiacDriftResult) | repo.stream_hr_velocity_simple_rows(activity_id, VEL_MOVING) → DuckDB query | Yes | FLOWING |
| `_activity_fact` | hrr (float or None) | calc_hrr_pct(median_hr, athlete.hr_rest, hr_max_for_hrr) — median_hr from repo.activity_median_heartrate | Yes | FLOWING |
| rolling_median_hr_recovery | median_hr_recovery | _materialize_rolling_facts SELECTs hr_recovery_median_rate from metric_rows | Yes — asserted by test_duckdb_materializer_rolling_median_populates | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| calc_hrr_pct(150,50,200) == 66.7 | `uv run python -c "from mcp_strava.metrics import calc_hrr_pct; print(calc_hrr_pct(150,50,200))"` | 66.7 | PASS |
| import mcp_strava.metrics exits 0 | `uv run python -c "import mcp_strava.metrics; print('OK')"` | OK | PASS |
| Full test suite | `uv run python -m pytest -q` | 320 passed in 132.89s | PASS |
| Focused metric + materialization + guard tests | `uv run python -m pytest tests/test_metrics_pure.py tests/test_read_model_materialization.py tests/test_security_guards.py -q` | 36 passed | PASS |

---

### Probe Execution

Step 7c: SKIPPED — no probe-*.sh files found in scripts/ for this phase, and phase is a Python package unit (not a migration/CLI phase with probe contracts).

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| Core/domain separation (PROJECT.md Active) | 10-01, 10-02, 10-04 | metrics.py must not import storage tier; enforced by AST guard | SATISFIED | metrics.py has no mcp_strava.db import; test_read_modules_do_not_import_storage_strava_or_refresh passes; out-of-band RED proof confirmed guard catches the violation |
| fix unmaterialized registered metrics (260525-jpo preserve-and-fix) | 10-01, 10-03 | hr_recovery, vertical_speed, cardiac_drift, hrr_pct + rolling medians must be computed not null/0 | SATISFIED | All 14 columns wired in _activity_fact; 4 integration tests pass including pause-inclusive, rolling-median, no-HR cases; live re-materialize is the only remaining manual step |

Note: REQUIREMENTS.md traceability table does not map any requirement ID to Phase 10 — this phase closes informal requirements from PROJECT.md (Active items) and the deferred task 260525-jpo, neither of which appear in the formal REQUIREMENTS.md v1/v1.1 tables. No orphaned REQUIREMENTS.md IDs detected for Phase 10.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/mcp_strava/adapters/duckdb/read_model_materializer.py` | 43, 64, 253, 350, 372, 380 | `repo._fetchone(...)` / `repo._fetchall(...)` private API called with inline SQL from materializer | INFO | Flagged as IN-03 in 10-REVIEW.md; explicitly out of scope per fix_scope=critical_warning in REVIEW-FIX.md; pre-existing pattern, not introduced by Phase 10 |

No TBD/FIXME/XXX debt markers found in files modified by this phase.

---

### Human Verification Required

#### 1. WR-01: Duplicate time_offset handling (no automated regression)

**Test:** Query the live DuckDB for duplicate (activity_id, time_offset) rows in the streams table: `SELECT activity_id, time_offset, COUNT(*) c FROM streams GROUP BY 1,2 HAVING c > 1 LIMIT 5;`
**Expected:** Either zero rows (duplicates do not exist in the live mirror, so the WR-01 path is never exercised), or if duplicates exist, calc_hr_recovery handles them without crashing and the MIN_STREAM_POINTS guard is re-validated against the de-duplicated count.
**Why human:** The fix adds a de-duplication guard and documents the precondition, but no automated test seeds duplicate time_offset rows to assert the path. The edge case is benign in CI data but unknown for the live mirror.

#### 2. WR-02: Short-pause start-HR window clamping (no automated regression for < 5-sample pauses)

**Test:** Review src/mcp_strava/metrics.py lines 132-139. The `pause_window = all_times[pause_start_idx:end_idx + 1]` slice is correct by inspection. For confidence, identify any live activity with very short pauses (1-4 stopped samples) and confirm hr_start is not contaminated by post-pause moving-HR.
**Expected:** pause_window[:5] contains only pause samples; for pauses < 5 samples the slice is naturally shorter but correct.
**Why human:** Test fixture uses 33-row pauses (well above 5). No test covers a 1-4 sample pause. The fix is correct but the edge is only exercisable on real data or a gap-specific fixture.

#### 3. WR-05: Recovery rate denominator uses sampled_rest_sec not wall-clock (no gap-data regression test)

**Test:** On a live activity or synthetic fixture with stream gaps (2-3 second gaps in the hr/velocity stream), verify that calc_hr_recovery computes `sampled_rest_sec = len(pause_window)` (the number of actually-sampled points) rather than `pause_dur` (the wall-clock span). The bpm/min rate should be slightly higher for a gapped stream than for a contiguous one with the same total pause time.
**Expected:** For a clean 1Hz stream the results are identical. For a 3s-gap stream the rate is slightly higher — the correct direction. No crash.
**Why human:** No test seeds a gapped stream specifically to verify the denominator change. The code change is correct by inspection (replaces `pause_dur / 60` with `sampled_rest_sec / 60`) but is not regression-tested.

#### 4. Live re-materialize: confirm null-to-computed transition on the live DuckDB

**Test:** Run the read-model re-materialization on the live DuckDB. Then execute the VALIDATION.md sanity query and call MCP `get_workout_detail` / `compare_periods`.
**Expected:** Non-null hr_recovery_median_rate, vertical_speed_vmh, cardiac_drift_pct, hrr_pct values for activities with the relevant streams. The sanity query `SELECT count(*) FILTER (WHERE hr_recovery_median_rate IS NOT NULL) AS hr_rec_nonnull, count(*) FILTER (WHERE cardiac_drift_pct IS NOT NULL) AS drift_nonnull, count(*) FILTER (WHERE hrr_pct IS NOT NULL) AS hrr_nonnull, count(*) AS total FROM activity_metric_facts;` must show non-null counts > 0.
**Why human:** Live DuckDB is a single-writer database not available in CI; the re-materialize is an explicit operator action. This is the final acceptance step for the product bug fix.

---

### Gaps Summary

No gaps. All 13 must-have truths are verified. The four human verification items concern:
- Three logic-change edge cases (WR-01/02/05) that have inline documentation and passing test suites but lack dedicated regression tests for the specific edge conditions the review fixes address.
- One mandatory live-ops step (live re-materialize) that cannot be automated by design.

The CR-01 fix (vertical_speed elapsed-span bug) has a dedicated regression test (`test_calc_vertical_speed_nonzero_leading_offset`) and is fully covered. WR-03 (per-activity vs cross-activity HR max) and WR-04 (symmetric float coercion) are covered by existing assertions through the materializer and metrics tests respectively.

---

_Verified: 2026-05-29T10:00:00Z_
_Verifier: Claude (gsd-verifier)_
