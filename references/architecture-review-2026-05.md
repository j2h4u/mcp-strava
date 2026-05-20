# Architectural Review — May 2026

Full codebase audit by subagent (deepseek-v4-pro).  
Code under review: `/opt/data/skills/productivity/strava/scripts/`

---

## 🔴 Critical

### 1. Scoring logic duplication ✅ FIXED May 2026
`cmd_backtest` (~line 481) and `calc_weekly_plan` (~line 370) — **not actually duplicated**: cmd_backtest correctly calls `calc_weekly_plan()` from training.py. The only real duplication was Banister forward simulation (~15 lines): `sim_past()` in backtest mirrored `simulate_forward()` in training. Fixed by extracting `forward_simulate()` into training.py as shared public function.

### 2. Unused `DbConn` class
`DbConn` (`db.py:20-31`) is a proper context manager but was only used in `get_zones()`.  
**Fix**: adopted in `cmd_activities`, `cmd_sql`, `cmd_weekly`, `report.py:daily_report()`. Remaining functions use manual `get_db()/close()` — `sync_activities`, `backfill_activities`, `compute_trends`, `cmd_backtest`, `cmd_strava_raw`.

---

## 🟠 High

### 3. `weekly_digest()` mixed return types ✅ FIXED May 2026
`analytics.py:172-339` now returns `Optional[WeeklyDigest]` — `None` on no data, `WeeklyDigest` dataclass otherwise. `cmd_weekly` checks `if result is None`. The `isinstance(result, dict)` anti-pattern eliminated.

### 4. SQL via f-strings (3 sites)
| File | Line | Query |
|------|------|-------|
| `metrics.py` | 33-38 | `_fetch_decoupling_rows` |
| `training.py` | 178-183 | `calc_progressive_signal` |
| `metrics.py` | 277-280 | `_enrich_activity` |

Values are static (from `Config`), but pattern is fragile.  
**Fix**: parameterized queries with `?` placeholders.

---

## 🟡 Medium

### 5. Raw dict instead of dataclasses
| Location | Field | Current | Should be |
|----------|-------|---------|-----------|
| `WeeklyDigest` | `.period`, `.current_state`, `.trends`, `.yoy`, `.context` | `dict` | Typed dataclasses |
| `DailyReport` | `.by_sport` | `dict` | `dict[str, SportSummary]` |
| `WeeklyPlan` | `.completed_days`, `.post_weekend`, `.activity_templates` | `list[dict]` / `dict` | Typed dataclasses |
| `_form_sparkline()` | return | `list[dict]` | `list[SparklineBar]` — type fixed: `sparkline: list[dict]` |
| `simulate_forward()` | return | `list[dict]` | ✅ Fixed: `list[SimDay]` (new dataclass) |

### 6. Unused imports (5 sites) — 3 of 5 resolved May 2026

| File | Import | Why unused | Status |
|------|--------|------------|--------|
| `cli.py` | `_build_trimp_cases` | Never called | Still present |
| `training.py` | `import math` | No `math.*` usage | Still present |
| `sports.py` | `import logging` + `logger` | No `logger.info()` calls | Still present |
| `report.py` | `_form_zone` (from training) | Never called in report.py | ✅ Removed |
| `cli.py` | `_enrich_activity` (from metrics) | Never called in cli.py | ✅ Removed |

### 7. Magic numbers not in Config
| Value | Location | Meaning |
|-------|----------|---------|
| `120` | `metrics.py` ×3 | Min stream points |
| `300` | `metrics.py:110` | Min moving_time for EF |
| `515` | `training.py:441` | Hike TRIMP template |
| `30` | `metrics.py:152` | Min pause for HRR |
| `21` | `training.py:175` | Progressive signal window |

### 8. α-coefficient duplication
`alpha = 1 - pow(0.5, 1.0 / tau)` duplicated in 4 places.  
**Fix**: add `Config.Model.Banister.alpha_fatigue` / `.alpha_fitness` as `@property`.

---

## 🟢 Low

### 9. Private functions imported cross-module ✅ ALL FIXED May 2026
All cross-module `_private` imports resolved:
- `_enrich_activity` → `enrich_activity` (metrics.py public API)
- `_ewma` → `ewma`, `_trend` → `trend` (training.py public API)
- `_form_zone` → removed (was dead import in report.py)
- `_enrich_activity` → removed from cli.py (was dead import)
Zero cross-module private imports remain.

### 10. Pure closures buried in large functions — partially fixed May 2026
- `_sim_one_day()` inside `calc_weekly_plan` — still inline
- `simulate_forward()` inside `calc_weekly_plan` — ✅ extracted: calls shared `forward_simulate()` (training.py)
- `sim_past()` inside `cmd_backtest` — ✅ removed: replaced by direct calls to `forward_simulate()`

### 11. `DecouplingResult.ef_first` / `ef_second` always None
Reserved for future use but never populated. Either implement or remove.

### 12. `rolling_avg()` O(n²)
`analytics.py:53-57` recomputes sum from scratch each call.  
**Fix**: prefix sums for O(n). Not critical for current data volumes.

### 13. `_generate_recommendation()` mutation chain
`report.py:175-266` — 5 sequential checks each mutating `action`/`intensity`. Order-dependent and hard to test.  
**Fix**: chain of pure predicates → merge with priority (rest > easy > train).

---

## Summary by priority (updated May 2026)

| Priority | Count | Action | Status |
|----------|-------|--------|--------|
| 🔴 Critical | 2 | Extract scoring, expand DbConn | #1 (Banister sim) ✅, #2 (DbConn) partial |
| 🟠 High | 2 | Fix return types, parameterize SQL | #3 (weekly_digest return types) ✅, #4 (SQL f-strings) not started |
| 🟡 Medium | 4 | Dataclass contracts, dead imports, magic numbers, α-coefficients | #6 (3 of 5 dead imports) ✅ |
| 🟢 Low | 5 | Cross-module privates, pure extractions, dead fields, perf, recommendation | #9 (all cross-module privates) ✅, #10 (forward_simulate) ✅ |

**Resolved this session (May 2026):**
- `forward_simulate()` extracted to training.py — zero duplicated Banister simulation
- All cross-module private imports resolved (3 renames, 2 dead import removals)
- File renamed `strava.py` → `cli.py`, cron jobs updated
