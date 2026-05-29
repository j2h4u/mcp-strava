---
phase: 10-materialize-unwired-training-metrics-and-enforce-core-domain
fixed_at: 2026-05-29T00:00:00Z
review_path: .planning/phases/10-materialize-unwired-training-metrics-and-enforce-core-domain/10-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 10: Code Review Fix Report

**Fixed at:** 2026-05-29T00:00:00Z
**Source review:** .planning/phases/10-materialize-unwired-training-metrics-and-enforce-core-domain/10-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (1 Critical + 6 Warning; 3 Info findings out of scope)
- Fixed: 7
- Skipped: 0

All fixes verified against the pure-metric and materialization test suites
(`tests/test_metrics_pure.py`, `tests/test_read_model_materialization.py`,
`tests/test_metric_services.py`, `tests/test_security_guards.py`) — 48 tests
pass. The CR-01 fix followed TDD: a failing regression test (rows with a
non-zero leading `time_offset`) was added and confirmed RED before the GREEN
source change.

## Fixed Issues

### CR-01: `calc_vertical_speed` treats the last `time_offset` as elapsed duration

**Files modified:** `src/mcp_strava/metrics.py`, `tests/test_metrics_pure.py`
**Commit:** 510efe2
**Applied fix:** Changed the denominator from `rows[-1]['time_offset']` to the
elapsed span `rows[-1]['time_offset'] - rows[0]['time_offset']`, so a
non-zero leading offset (altitude sampling that begins partway into the
activity) no longer inflates the duration and halves the reported m/h. Added a
regression test `test_calc_vertical_speed_nonzero_leading_offset` covering a
1800..3600 altitude window; it was confirmed failing (reported
`duration_hours=0.69` vs expected `0.19`) before the fix and passing after.

### WR-01: `calc_hr_recovery` silently drops samples on duplicate `time_offset`

**Files modified:** `src/mcp_strava/metrics.py`
**Commit:** b5e3ba2
**Applied fix:** Documented the uniqueness precondition on the function and
re-validated the `MIN_STREAM_POINTS` sufficiency guard against the
de-duplicated `all_times` count (not just raw `len(rows)`), so the pause-
detection math never runs over fewer points than the guard validated. Logic-
sensitive — see note below.

### WR-02: `calc_hr_recovery` start-HR window can sample rows outside the pause

**Files modified:** `src/mcp_strava/metrics.py`
**Commit:** 4868cb7
**Applied fix:** Built a `pause_window = all_times[pause_start_idx:end_idx + 1]`
slice clamped to the pause range and took the start/end HR windows as
`pause_window[:5]` / `pause_window[-5:]`, so the start window can no longer
reach past `pause_end` into moving rows when a pause is shorter than 5 samples.
Logic-sensitive — see note below.

### WR-03: cross-activity HR max fed into `calc_hrr_pct` against a single-activity median

**Files modified:** `src/mcp_strava/adapters/duckdb/read_model_materializer.py`
**Commit:** 7031204
**Applied fix:** Used the activity's own observed max (`max_hr`, already fetched
from `repo.activity_hr_range`) as the %HRR denominator, falling back to the
running cross-activity `hr_max_observed` only when this activity has no HR
samples. Numerator and denominator now share the same activity scope. Logic-
sensitive — see note below.

### WR-04: `calc_hrr_pct` coerces `hr_max` but not `hr_rest`

**Files modified:** `src/mcp_strava/metrics.py`
**Commit:** c89b64e
**Applied fix:** Coerced all three numeric inputs (`median_hr`, `hr_rest`,
`hr_max`) to float up front and performed the comparison and formula on the
coerced values, removing the asymmetric-cast smell that could raise
`TypeError` on a numeric-string `hr_rest`. Existing test values (66.7, 20.0)
unchanged.

### WR-05: pause duration is wall-clock but HR drop rate divides by it as rest seconds

**Files modified:** `src/mcp_strava/metrics.py`
**Commit:** 4f26da3
**Applied fix:** Divided the bpm/min `rate` by `len(pause_window)` (the count
of actually-sampled rest seconds) instead of the wall-clock span `pause_dur`,
so gap tolerance (up to 3s) no longer over-counts the denominator and deflates
the recovery rate. `duration` / `total_rest_sec` still report the wall-clock
span. Logic-sensitive — see note below.

### WR-06: `calc_hr_recovery` filters `rate is not None` for stats but uses unfiltered `pauses` for best/worst

**Files modified:** `src/mcp_strava/metrics.py`
**Commit:** 0d4315b
**Applied fix:** Introduced a single `rated = [p for p in pauses if p['rate']
is not None]` subset and computed `rates`, `best`, and `worst` from it, so all
three share one contract and a future nullable `rate` cannot make
`max()`/`min()` raise on `None` while `rates` silently excludes it. This also
removed the redundant `if pauses else None` guards (IN-01, incidentally).

## Verification Note

WR-01, WR-02, WR-03, and WR-05 are semantic/logic changes (guard semantics,
HR-window bounds, denominator scope, rate denominator). They pass syntax checks
and the existing test suite, but the existing tests do not exercise the exact
edge conditions these fixes target (duplicate offsets, gap-shortened pauses,
per-activity vs running max). **These four warrant a human eye on the logic
before the phase proceeds to verification** — the changes are reasoned and
documented inline, but no dedicated regression test asserts the corrected
behavior for WR-01/02/05 (only CR-01 has one). The CR-01 and WR-04 fixes are
covered by passing assertions.

## Out of Scope (Info — not addressed per fix_scope=critical_warning)

- IN-01: Redundant `if pauses else None` — incidentally removed by the WR-06 fix.
- IN-02: `pause_start_idx` / `pause_start` aliasing ambiguity — not addressed.
- IN-03: Materializer reaches into `repo._fetchone`/`_fetchall` private API — not addressed.

---

_Fixed: 2026-05-29T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
