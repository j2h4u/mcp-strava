---
phase: 10-materialize-unwired-training-metrics-and-enforce-core-domain
reviewed: 2026-05-29T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - src/mcp_strava/metrics.py
  - src/mcp_strava/db.py
  - src/mcp_strava/adapters/duckdb/read_model_materializer.py
  - tests/test_metrics_pure.py
  - tests/test_read_model_materialization.py
  - tests/test_security_guards.py
  - tests/test_metric_services.py
  - tests/test_smoke.py
findings:
  critical: 1
  warning: 6
  info: 3
  total: 10
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-05-29T00:00:00Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Reviewed the Phase 10 conversion of `metrics.py` to a pure domain module, the wiring of pure
metric functions into `_activity_fact`, the extended import-boundary AST guard, and the deletion
of `db.py::get_daily_trimp_history`.

The pure/storage boundary is sound: `metrics.py` imports only `constants`, `types`, and
`cardiac_drift`, with no storage imports, and the AST guard in `test_security_guards.py` enforces
this. The deleted `get_daily_trimp_history` has no remaining call sites (only the forbidden-import
guard references the name). The wiring in `_activity_fact` correctly fetches plain rows via the
repository and passes them to pure functions.

However, the metric computations contain one correctness defect that produces semantically wrong
output (the `calc_vertical_speed` duration uses an absolute time offset rather than an elapsed
span) and several robustness gaps around duplicate/non-monotonic stream timestamps and
denominator-source mismatches. The `calc_hr_recovery` pause detector also mixes wall-clock duration
with index-based HR sampling in ways that drift when the stream has gaps.

## Critical Issues

### CR-01: `calc_vertical_speed` treats the last `time_offset` as elapsed duration, inflating m/h when the stream does not start at offset 0

**File:** `src/mcp_strava/metrics.py:183`
**Issue:**
```python
duration_hours = rows[-1]['time_offset'] / 3600
```
This assumes the first stream row has `time_offset == 0`. The repository query
(`stream_altitude_rows`) orders by `time_offset` and filters `altitude IS NOT NULL`, so the first
returned row is whichever altitude sample has the smallest offset — which is **not guaranteed to be
0**. If altitude sampling begins partway into the activity (a common Strava pattern when the
barometer warms up, or when the leading samples have NULL altitude), the denominator is the
*absolute* offset of the last sample, not the elapsed span of the altitude series.

Concrete failure: altitude present only for `time_offset` 1800..3600 (a 30-min climbing window 30
min into a ride). `total_ascent` is computed correctly over those rows, but `duration_hours =
3600/3600 = 1.0 h` instead of the true `(3600-1800)/3600 = 0.5 h`. The reported `vmh` is then
**half** the real ascent rate. The metric silently produces wrong values rather than failing.

The pure unit test (`tests/test_metrics_pure.py:85-90`) only exercises rows that start at
`time_offset == 0`, so it never catches this.

**Fix:**
```python
elapsed_sec = rows[-1]['time_offset'] - rows[0]['time_offset']
duration_hours = elapsed_sec / 3600
if duration_hours < 0.05:  # < 3 min
    return None
```

## Warnings

### WR-01: `calc_hr_recovery` collapses rows with duplicate `time_offset`, silently dropping samples

**File:** `src/mcp_strava/metrics.py:84`
**Issue:**
```python
by_time = {r['time_offset']: r for r in rows}
all_times = sorted(by_time.keys())
```
The `len(rows) < MIN_STREAM_POINTS` guard runs against the raw row count, but the algorithm then
operates on `by_time` keyed by `time_offset`. If two rows share a `time_offset` (DuckDB does not
enforce uniqueness on `streams(activity_id, time_offset)` from this query alone), one is silently
discarded and `len(all_times) < len(rows)`. Pause durations and HR averages are then computed over
fewer points than the guard validated, and `pause_dur = pause_end - pause_start` (a time delta) no
longer corresponds to the number of sampled seconds.

**Fix:** Either assert uniqueness upstream, or detect and reject duplicate offsets:
```python
if len({r['time_offset'] for r in rows}) != len(rows):
    # duplicate timestamps — operate on the raw ordered list instead of a dict
    ...
```
At minimum, document the uniqueness precondition on the function and the repository query.

### WR-02: `calc_hr_recovery` start-HR window can sample rows outside the pause

**File:** `src/mcp_strava/metrics.py:116`
**Issue:**
```python
start_times = all_times[pause_start_idx:pause_start_idx+5]
hr_start = sum(by_time[t]['heartrate'] for t in start_times) / len(start_times)
```
This grabs 5 indices from the *global* sorted timeline starting at the pause's first index. The
loop that found the pause (`while j < len(all_times)`) breaks on a >3 s gap or on
`velocity >= STOP_VEL`. When the pause is shorter than 5 samples (possible only via gaps, since a
≥30 s pause normally has ≥30 one-second rows, but gaps shorten it), `start_times` reaches *past*
`pause_end` into moving rows, biasing `hr_start` toward the moving HR and corrupting the recovery
`drop`. The `end_times` window (line 121) is correctly clamped to `end_idx+1`, but `start_times`
is not clamped to the pause end.

**Fix:** Clamp the start window to the pause range:
```python
pause_window = all_times[pause_start_idx:end_idx + 1]
start_times = pause_window[:5]
end_times = pause_window[-5:]
```

### WR-03: `_activity_fact` feeds a cross-activity HR max into `calc_hrr_pct` against a single-activity median

**File:** `src/mcp_strava/adapters/duckdb/read_model_materializer.py:166-171`
**Issue:**
```python
median_hr = repo.activity_median_heartrate(activity_id)      # this activity only
...
hrr = calc_hrr_pct(median_hr, athlete.hr_rest, hr_max_observed)  # running max across ALL activities to date
```
`median_hr` is the median HR of *this one activity*, but `hr_max_observed` is
`max_heartrate_to_date(activity_day)` — the running maximum across **all** activities up to this
day. %HRR = `(median - rest) / (max - rest)`. Using a global denominator with a per-activity
numerator means the reserve fraction is computed against a max the athlete may have hit weeks
earlier on a different effort. For an easy recovery run after a hard race week, `hrr_pct` is
understated relative to that activity's own peak. This may be intentional (stable
population-level denominator), but it is not documented and the per-activity `observed_max_hr` is
already available from `repo.activity_hr_range` two lines below — the choice deserves an explicit
comment or a switch to the per-activity max.

**Fix:** Document the intent, or use the activity's own observed max:
```python
min_hr, max_hr = repo.activity_hr_range(activity_id)
hrr = calc_hrr_pct(median_hr, athlete.hr_rest, max_hr if max_hr is not None else hr_max_observed)
```

### WR-04: `calc_hrr_pct` casts `hr_max` to float but not `hr_rest`, so a string `hr_rest` raises mid-formula instead of being guarded

**File:** `src/mcp_strava/metrics.py:208-212`
**Issue:**
```python
if float(hr_max) <= hr_rest:        # hr_max coerced, hr_rest not
    return None
return round((median_hr - hr_rest) / (float(hr_max) - hr_rest) * 100, 1)
```
The defensive `float(hr_max)` cast implies inputs may arrive as non-float (the materializer passes
`hr_max_observed`, an `int`, and `athlete.hr_rest`). The comparison `float(hr_max) <= hr_rest`
mixes a coerced `hr_max` with an un-coerced `hr_rest`; if `hr_rest` is ever a numeric string this
raises `TypeError` rather than returning `None`, and the inconsistency makes the guard fragile. The
asymmetry is a latent type-mismatch smell.

**Fix:** Coerce both consistently or neither:
```python
hr_max_f = float(hr_max)
hr_rest_f = float(hr_rest)
if hr_max_f <= hr_rest_f:
    return None
return round((float(median_hr) - hr_rest_f) / (hr_max_f - hr_rest_f) * 100, 1)
```

### WR-05: Pause duration is wall-clock time but HR drop rate divides by it as if it were rest seconds

**File:** `src/mcp_strava/metrics.py:112,125`
**Issue:**
```python
pause_dur = pause_end - pause_start          # wall-clock delta between two offsets
rate = round(drop / (pause_dur / 60), 1) if pause_dur > 0 else 0   # bpm/min
```
`pause_dur` is the difference between two `time_offset` values, which equals elapsed seconds only
when samples are contiguous at 1 s spacing. The inner loop tolerates gaps up to 3 s
(`if t2 - all_times[j-1] > 3: break`), so a pause may legitimately contain 1–3 s gaps and
`pause_dur` over-counts the actual sampled rest seconds. The `rate` (bpm/min) is then computed
against an inflated denominator, understating recovery rate. Minor for clean 1 Hz streams, but
the function's own gap tolerance creates the inconsistency.

**Fix:** Compute rate against the count of sampled pause seconds, or tighten the gap tolerance to 1 s
so `pause_dur` and sample count coincide.

### WR-06: `calc_hr_recovery` filters `rate is not None` for stats but uses unfiltered `pauses` for best/worst

**File:** `src/mcp_strava/metrics.py:143-161`
**Issue:**
```python
rates = sorted(p['rate'] for p in pauses if p['rate'] is not None)   # filtered
best = max(pauses, key=lambda p: p['rate'])                          # unfiltered
```
`rate` is always a number (it is assigned `0` or a rounded float at line 125, never `None`), so the
`is not None` filter is dead and the two code paths agree *today*. But the inconsistency is a
correctness trap: if a future change makes `rate` nullable, `max(pauses, key=...)` will raise
`TypeError` on `None` while `rates` would have silently excluded it. Pick one contract.

**Fix:** Drop the dead `is not None` filter (rate is never None), or make `best`/`worst` operate on
the same filtered subset:
```python
rated = [p for p in pauses if p['rate'] is not None]
rates = sorted(p['rate'] for p in rated)
best = max(rated, key=lambda p: p['rate']) if rated else None
worst = min(rated, key=lambda p: p['rate']) if rated else None
```

## Info

### IN-01: Redundant `if pauses else None` after `if not pauses: return None`

**File:** `src/mcp_strava/metrics.py:146-147`
**Issue:** Line 140 already returns `None` when `pauses` is empty, so `best = ... if pauses else None`
and `worst = ... if pauses else None` can never take the `else` branch. Dead defensive code.
**Fix:** Drop the `if pauses else None` guards on lines 146-147.

### IN-02: Unused/unnecessary `pause_start_idx` aliasing and `i = j` comment redundancy

**File:** `src/mcp_strava/metrics.py:97-98`
**Issue:** `pause_start = t` and `pause_start_idx = i` are both retained, but `pause_start` is only
used for `pause_dur` and the `'time'` field, while `pause_start_idx` indexes `all_times`. The two
parallel "start" variables (one a time value, one an index) are easy to confuse and were the root of
WR-02. Consider keeping only the index and deriving `pause_start = all_times[pause_start_idx]`.
**Fix:** Reduce to a single index-based anchor to remove the time/index ambiguity.

### IN-03: `_stream_counts` / `_zone_seconds` reach into `repo._fetchone` (private API) from the materializer

**File:** `src/mcp_strava/adapters/duckdb/read_model_materializer.py:43,64,253,350,372,380`
**Issue:** The materializer calls `repo._fetchone(...)` and `repo._fetchall(...)` directly with inline
SQL rather than going through named repository methods (the pattern used for
`stream_hr_velocity_time_rows`, `activity_trimp`, etc.). Mixing raw private-method SQL with the
typed repository surface in the same module blurs the storage boundary the phase set out to enforce
and makes these queries invisible to the `_zone_seconds`/`stream_*` method-level tests.
**Fix:** Promote the inline aggregate queries to named `DuckDBRepository` methods for consistency
with the rest of the wiring, so all stream/fact SQL lives behind the repository.

---

_Reviewed: 2026-05-29T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
