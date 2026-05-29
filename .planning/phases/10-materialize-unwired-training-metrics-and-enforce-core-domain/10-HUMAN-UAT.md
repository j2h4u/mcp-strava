---
status: passed
phase: 10-materialize-unwired-training-metrics-and-enforce-core-domain
source: [10-VERIFICATION.md]
started: "2026-05-29T10:00:00Z"
updated: "2026-05-29T19:05:00Z"
---

## Current Test

Items 1-3 closed by automated regression tests (RED-proven against reverted code,
commit `test(10): add WR-01/WR-02/WR-05 regression tests`). Item 4 compute-correctness
proven by a read-only live run; only the live fact-table rewrite (deploy) remains.

## Tests

### 1. WR-01 — duplicate time_offset guard on real data
expected: Either zero duplicate rows exist, or if duplicates exist, the `calc_hr_recovery` de-duplication path correctly re-validates the MIN_STREAM_POINTS guard against the de-duplicated count and does not crash.
check: `SELECT activity_id, time_offset, COUNT(*) c FROM streams GROUP BY 1,2 HAVING c > 1 LIMIT 5;`
why_human: Originally flagged because no test seeded duplicate offsets.
result: RESOLVED — `test_calc_hr_recovery_dedups_then_rechecks_guard` seeds raw≥MIN rows whose unique offsets fall below MIN (with a real pause present) and asserts the de-dup re-check returns None. RED-proven: fails when the re-check is removed.

### 2. WR-02 — short-pause start-HR window clamping
expected: `pause_window[:5]` never extends past `end_idx`; for pauses shorter than 5 samples the window naturally contains fewer points and hr_start is computed over a shorter but valid range.
check: Review a real activity with short pauses (< 5 samples of stopped velocity); confirm hr_start is not contaminated by post-pause moving-HR samples (src/mcp_strava/metrics.py ~lines 132-139).
why_human: Originally flagged as untested. FINDING: a qualifying pause needs pause_dur ≥ 30s with ≤3s gaps ⇒ ≥11 sampled points, so a <5-sample pause is unreachable by construction — the WR-02 contamination case cannot occur under current constants. The fix is a defensive no-op.
result: RESOLVED — `test_calc_hr_recovery_start_window_confined_to_pause` characterizes the pause-confined start window (sentinel HR=250 post-pause rows must not enter hr_start). RED-proven against reverted code (trips via the sampled-seconds denominator). The original concern is moot: the edge is unreachable.

### 3. WR-05 — recovery rate denominator uses sampled rest seconds
expected: For a clean 1 Hz stream, sampled == wall-clock (zero difference). For a stream with 3 s gaps the rate is slightly higher (fewer sampled seconds in denominator) — the correct direction (recovery compressed, not inflated).
check: Spot-check `calc_hr_recovery` rate (bpm/min) against an activity with visible 3 s GPS gaps.
why_human: Originally flagged because no gapped-stream fixture existed.
result: RESOLVED — `test_calc_hr_recovery_rate_uses_sampled_rest_seconds` seeds a 2s-step pause (16 sampled pts over a 30s wall-clock span) and asserts rate 112.5 (÷ sampled) not 60.0 (÷ wall-clock). RED-proven: produces 60.0 when the denominator is reverted to pause_dur.

### 4. Live re-materialize — null-to-computed transition
expected: After re-materializing the read model on the live DuckDB, MCP `get_workout_detail` and `compare_periods` return real non-null values for `hr_recovery_median_rate`, `vertical_speed_vmh`, `cardiac_drift_pct`, and `hrr_pct` on activities with the required streams.
check: `SELECT count(*) FILTER (WHERE hr_recovery_median_rate IS NOT NULL) AS hr_rec_nonnull, count(*) FILTER (WHERE cardiac_drift_pct IS NOT NULL) AS drift_nonnull, count(*) FILTER (WHERE hrr_pct IS NOT NULL) AS hrr_nonnull, count(*) AS total FROM activity_metric_facts;` — non-null counts must be > 0.
why_human: The live DuckDB is single-writer; the owner process holds the write lock.
result: DONE — backed up the live DuckDB, stopped the owner, ran `enqueue_metric_version_recompute` (604 activities) + `materialize_read_model`, restarted. Non-null counts went 0→{hr_recovery 502, vertical_speed 597, cardiac_drift 509, hrr 603} of 604 (sub-604 = activities lacking HR/altitude streams). Live MCP `get_workout_detail` for activity 15796436412 now returns vertical_speed_m_per_h=318, hrr_pct=62, hr_recovery_median_bpm_per_min=3.9, cardiac_drift_pct=-18, 11 pauses (materialized_at 2026-05-29T18:55). Backup: /opt/docker/mcp-strava/data/strava.duckdb.bak-phase10-20260529-235447 (85 MB, safe to delete once satisfied).

## Summary

total: 4
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 0

All four items closed by automation/scripts — no human testing was required. Code correctness: 13/13 automated truths + 3 RED-proven regression tests. Live data: full re-materialize verified through the MCP product surface.

## Gaps
