---
status: partial
phase: 10-materialize-unwired-training-metrics-and-enforce-core-domain
source: [10-VERIFICATION.md]
started: "2026-05-29T10:00:00Z"
updated: "2026-05-29T10:00:00Z"
---

## Current Test

[awaiting human testing]

## Tests

### 1. WR-01 — duplicate time_offset guard on real data
expected: Either zero duplicate rows exist, or if duplicates exist, the `calc_hr_recovery` de-duplication path correctly re-validates the MIN_STREAM_POINTS guard against the de-duplicated count and does not crash.
check: `SELECT activity_id, time_offset, COUNT(*) c FROM streams GROUP BY 1,2 HAVING c > 1 LIMIT 5;`
why_human: The fix documents uniqueness as a precondition and adds a re-check, but no automated test seeds duplicate time_offset rows. Live data is the only source of truth for whether duplicates exist and whether the guard handles them.
result: [pending]

### 2. WR-02 — short-pause start-HR window clamping
expected: `pause_window[:5]` never extends past `end_idx`; for pauses shorter than 5 samples the window naturally contains fewer points and hr_start is computed over a shorter but valid range.
check: Review a real activity with short pauses (< 5 samples of stopped velocity); confirm hr_start is not contaminated by post-pause moving-HR samples (src/mcp_strava/metrics.py ~lines 132-139).
why_human: No regression test seeds a pause shorter than 5 samples; the fixture uses 33-row pauses (always ≥ 5). Correct by inspection but the 1-4 sample edge has no automated coverage.
result: [pending]

### 3. WR-05 — recovery rate denominator uses sampled rest seconds
expected: For a clean 1 Hz stream, sampled == wall-clock (zero difference). For a stream with 3 s gaps the rate is slightly higher (fewer sampled seconds in denominator) — the correct direction (recovery compressed, not inflated).
check: Spot-check `calc_hr_recovery` rate (bpm/min) against an activity with visible 3 s GPS gaps.
why_human: No test exercises 3 s-gap streams to verify the `len(pause_window)` denominator change. Observable only on real data or a dedicated gap fixture.
result: [pending]

### 4. Live re-materialize — null-to-computed transition
expected: After re-materializing the read model on the live DuckDB, MCP `get_workout_detail` and `compare_periods` return real non-null values for `hr_recovery_median_rate`, `vertical_speed_vmh`, `cardiac_drift_pct`, and `hrr_pct` on activities with the required streams.
check: `SELECT count(*) FILTER (WHERE hr_recovery_median_rate IS NOT NULL) AS hr_rec_nonnull, count(*) FILTER (WHERE cardiac_drift_pct IS NOT NULL) AS drift_nonnull, count(*) FILTER (WHERE hrr_pct IS NOT NULL) AS hrr_nonnull, count(*) AS total FROM activity_metric_facts;` — non-null counts must be > 0.
why_human: The live DuckDB is a single-writer database not available in CI. The operator must run the re-materialize explicitly. Documented in VALIDATION.md as the only mandatory manual step.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
