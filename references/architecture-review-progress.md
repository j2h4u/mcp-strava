# Architecture Review Progress — All Rounds

## Round 1 (May 9, 2026) — 16 findings

### 🔴 Critical (3)
1. `accumulate` not imported → `cmd_weekly` NameError — analytics.py
2. `return` not in correct `if` → `cmd_trend` always returned None — trends.py
3. SQL f-string `VEL_MOVING` not parameterized — analytics.py

### 🟠 High (3)
4. Dead `rolling_avg()` — analytics.py
5-8. Magic numbers moved to Config: TRIMP_HEAVY_DAY, MIN_HR_POINTS, MIN_ALT_POINTS, BANISTER_WARMUP_DAYS

### 🟡 Medium (3)
9. Dead `ZONES_SQL` import — cli.py
10. Dead `dc_to_dict` import — report.py
11. `get_db()` deprecated — db.py

### 🟢 Low (7)
12-16. `_build_trimp_cases` after init, `simulate_forward` closure, `ewma()` duplicate alpha

## Round 2 (May 9, 2026) — 15 findings

### 🔴 Critical (1)
F1. SQL `?` without parameter tuple — analytics.py (regression from Round 1 fix #3)

### 🟠 High (2)
F2. Monkey-patching DailyReport dataclass (already had fields — false positive)
F3. Double dict→PlanDay conversion in `calc_weekly_plan` — training.py

### 🟡 Medium (3)
F4. Dead `Config` import — sync.py
F5. Direct `TRIMP_SQL` import bypassing `Config.SQL.TRIMP` — cli.py
F6. Mid-function imports — training.py, report.py

### 🟢 Low (9)
F7. Duplicate post-weekend simulation lines — training.py (fixed with F3)
F8. `max_hr` int vs float type mismatch — metrics.py
F9. Mixed dict/dataclass access in `_form_sparkline` (fixed with F3)
F10. Fragile `weekly_trimp` comprehension — report.py
F11. `dc_to_dict` not in types.py docstring
F12-F13. `.env` loading without error handling, `refresh_token()` bare KeyError — db.py
F14. `sync.py.bak` garbage file
F15. `activity_templates` type annotation (minor)

## Round 3 (May 10, 2026) — 7 findings

### 🟡 Medium (1)
1. `urllib.error` not explicitly imported — db.py

### 🟢 Low (4)
2. `_fetch_with_retry` no retry loop — sync.py
3. `api_schema.py` docstring overstated usage — SKILL.md
4. `cli.py.bak` garbage file
5. `get_db()` removed entirely — db.py

### 🔵 Info (2)
6. `dc_to_dict` could expose `_raw` fields — types.py
7. `max_hr` inconsistency between cli.py and metrics.py

## Round 4 (May 10, 2026) — Fresh Eyes — 13 findings

### 🔴 Critical (4)
1. `_pace_too_variable` name lies — returns True for <2 points (not "too variable")
2. VO₂max without elevation correction — analytics.py
3. `daily_report`: `all_dates` excludes today but `total_trimp_14d` includes today
4. ACWR recalculates Banister 7 times (O(N²))

### 🟠 Medium (5)
5. Two implementations of Banister formula — training.py
6. `trend()` returns string, logic parses `'↑' in ...` — fragile
7. EF computed two different ways — metrics.py + analytics.py
8. `dc_to_dict` filters `startswith('_raw')` — too broad
9. Magic number 75 for walk/run — training.py

### 🟡 Light (4)
10. `calc_vertical_speed` uses elapsed time — metrics.py
11. TRIMP = 0 masks NULL vs real 0 — metrics.py
12. Week streak naming — analytics.py
13. Outdated Samsung Health comment — metrics.py

## Round 5 (May 10, 2026) — Fresh Eyes — 12 findings

### 🔴 Critical (2)
1. `trends.py` Banister without per-step rounding — divergence from training.py
2. Streaks count only HR-filtered activities — analytics.py

### 🟡 Medium (4)
3. `calc_progressive_signal` uses `'↑' in` instead of `startswith` — training.py
4. `_form_sparkline` bug: `bar[vi]` overwrites zero-marker when form=0
5. `ewma()` infinite loop when end < start — training.py
6. ACWR inconsistent between modules (rolling avg vs EWMA)

### 🟢 Low (6)
7. Double rounding in `forward_simulate`
8. Duplicate MIN_STREAM_POINTS check in `calc_decoupling_with_gate`
9. `YOY_SHIFT_DAYS` comment imprecise
10. `BOUNDS` magic 300 — no comment
11. `HIKE_TRIMP_TEMPLATE` looking suspiciously high — no explanation
12. `trends.py` inefficient week filter

## Round 6 (May 10, 2026) — Split Math + Edge Cases — 2 findings

### 🔴 Critical (1)
1. `calc_efficiency_factor`: `avg_hr == 0` → ZeroDivisionError — metrics.py:129

### 🟡 Data (1)
2. `past_acwr or 0` masks None as real 0 — report.py:111

### Math review (zero errors)
All 9 areas verified correct: Banister alpha, _sim_one_day equivalence, TRIMP SQL, Decoupling Pa:HR, CC/bkm/EF, VO₂max ACSM, ACWR (both), Form zones, Weekly plan scoring.

## Round 7 — Coaching + SRE Changes (May 10, 2026)

No new bugs found. Three methodology improvements from coach review:

1. **HR zones recalibrated**: Strava zones [118,147,162,177,300] → Karvonen [136,150,163,177,300]. 93% of running was in Z1-Z2; now correctly distributed.
2. **Medium run template**: `run_medium` (150 TRIMP, ~8-10km) added to weekly plan. Expands brute-force from 3^N to 4^N combos.
3. **Progressive signal**: Decoupling trend → CC trend. Decoupling was N/A for this athlete (pace too variable); CC is always available from EF data.
4. **urlopen timeout**: `timeout=30` on all `urllib.request.urlopen` calls — prevents cron hangs.

## Total: 83 findings across 7 rounds, all closed
