---
name: strava
description: Strava API integration — check gear (shoe mileage), list activities, get athlete stats. Auto-refreshes OAuth tokens.
version: 1.0.0
author: migrated from OpenClaw
metadata:
  hermes:
    tags: [strava, fitness, running, gear-tracking]
prerequisites:
  commands: [python3]
  env_vars: [STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN, STRAVA_ACCESS_TOKEN]
---

# Strava API

CLI tool for interacting with Strava API. Handles OAuth token refresh automatically.

## Quick Commands

Always run from the skill directory:
```bash
cd /opt/data/skills/productivity/strava
```

```bash
# List recent activities with TRIMP computed from SQLite (default 15)
python3 scripts/cli.py activities
python3 scripts/cli.py activities 30

# List shoes with mileage (km) — live from Strava API
python3 scripts/cli.py gear

# Get aggregate stats (recent, ytd, all-time) — live from Strava API
python3 scripts/cli.py stats

# Force token refresh (healthcheck)
python3 scripts/cli.py refresh

# Quick sync (~1-2 API calls) — fetches only new activities since last known date
python3 scripts/cli.py sync

# Full sync (~6 API calls) — full pagination from page 1, catches back-dated uploads
python3 scripts/cli.py sync --full

# Show recent sync audit log (status, counts, errors)
python3 scripts/cli.py log

# Show recent kudos (likes) grouped by activity
python3 scripts/cli.py kudos
python3 scripts/cli.py kudos 7

# Full backfill: re-fetch ALL streams (with GAP) + DetailedActivity (one-time)
#   572 activities × 2 calls = ~1144 API calls, rate-limited 190/15min ≈ 2 hours
python3 scripts/cli.py backfill

# Run SQL query on strava.db (Markdown table output)
python3 scripts/cli.py sql "SELECT sport_type, COUNT(*) FROM activities GROUP BY 1"

# Daily training report (Banister, decoupling, EF, HR recovery, vertical speed + recommendation)
python3 scripts/cli.py report
```

**All commands except `gear`, `stats`, `sync`, `refresh` read from local SQLite — zero API calls.**

## SQLite Integration (`strava.db`)

The skill maintains a local SQLite database with full activity history and second-by-second sensor streams.

```bash
# Sync new activities + streams from Strava (incremental)
python3 scripts/cli.py sync
```

### Schema
- **`activities`**: `id`, `date`, `name`, `sport_type`, `distance`, `moving_time`, `elapsed_time`, `total_elevation_gain`, `summary_json`, `detail_json` (DetailedActivity with splits/laps/best_efforts/calories/similar_activities), `synced_at`
- **`streams`**: `activity_id`, `time_offset`, `heartrate`, `velocity`, `altitude`, `cadence`, `lat`, `lng`, `grade`, `gap_speed` (Strava GAP, Run only), `gap_distance` (cumulative GAP, last point only), `is_moving` (boolean) — one row per second
- **`athlete_zones`**: cached HR zones from Strava
- **`sync_log`**: audit trail — every sync run with status, counts, API calls, errors (May 2026)

### Example Queries
- **Avg Pace per month**: `SELECT strftime('%Y-%m', date) m, AVG(distance/moving_time)*3.6 s FROM activities WHERE sport_type='Run' GROUP BY 1`
- **Max HR ever**: `SELECT MAX(heartrate) FROM streams`
- **Activities with high intensity**: `SELECT a.name, COUNT(*) sec FROM streams s JOIN activities a ON a.id=s.activity_id WHERE s.heartrate > 160 GROUP BY 1 ORDER BY 2 DESC`

## `activities` command output

Returns JSON grouped by `sport_type`. Each activity includes TRIMP and zone minutes computed from SQLite streams data.

Top-level: `by_type`, `total_weekly_trimp`, `all_types`.

## TRIMP Calculation

Computed on-the-fly from SQLite `streams` table. No separate cache files.

**Algorithm:**
TRIMP = Σ (seconds_in_zone × zone_weight) / 60 (weights: Z1=1, Z2=2, Z3=3, Z4=4, Z5=5)

**HR Zones (Karvonen, %HRR, May 2026):**
| Zone | HR Range | %HRR | Weight |
|------|----------|------|--------|
| Z0   | 0–122    | <50% | 0.5 |
| Z1   | 122–136  | 50-60% | 1   |
| Z2   | 136–150  | 60-70% | 2   |
| Z3   | 150–163  | 70-80% | 3   |
| Z4   | 163–177  | 80-90% | 4   |
| Z5   | 177+     | 90%+   | 5   |

Implementation: `Config.Zones.BOUNDS = [122, 136, 150, 163, 177, 300]`, `Config.Zones.COEFF = [0.5, 1, 2, 3, 4, 5]` — 6 bounds and 6 coefficients matching the zone table above.

**Typical TRIMP values for reference:**
- Walk (1h, Z1): ~60–90
- Easy run (1h, Z1-Z2): ~100–150
- Hike (4h, Z1-Z2): ~300–400
- Tempo run (1h, Z2-Z4): ~200–300

## `gear` command output

Returns a JSON array of shoes with `id`, `name`, `distance_km`, `primary`.

Thresholds for alerts:
- **>500 km** — mention casually, monitor wear
- **>800 km** — recommend replacement

## Token Management

Tokens auto-refresh on 401 responses. The script writes new tokens back to `.env`.

Strava access tokens expire every 6 hours. The refresh token is long-lived but should be refreshed periodically.

## Available Data Per Activity

The `/athlete/activities` endpoint returns rich data for each workout:

| Field | Description | Example |
|-------|-------------|---------|
| `average_heartrate` | Avg HR (bpm) | 101.1 |
| `max_heartrate` | Max HR (bpm) | 121 |
| `average_speed` | m/s (×3.6 for km/h) | 1.496 |
| `max_speed` | m/s | 10.249 |
| `average_cadence` | Steps/min | 109.8 |
| `total_elevation_gain` | meters climbed | 72.6 |
| `elev_high` / `elev_low` | elevation range (m) | 881.8 / 823.5 |
| `moving_time` | active seconds | 3758 |
| `elapsed_time` | total seconds (incl. pauses) | 4334 |
| `distance` | meters | 5622.2 |
| `has_heartrate` | boolean | true |
| `gear_id` | shoe used | "g21031064" |
| `device_name` | tracking device | "Samsung Health" |
| `sport_type` | "Run" or "Walk" | — |

**Derived metrics for analytics:**
- Moving ratio = `moving_time / elapsed_time` (lower = more pauses, fatigue indicator)
- Pace = `moving_time / distance` (min/km, lower is faster)
- Elevation per km = `total_elevation_gain / (distance/1000)`

## Aggregate Stats (`node scripts/strava.mjs stats`)

Returns `recent_run_totals` (last 4 weeks), `ytd_run_totals`, `all_run_totals`:
- `count`, `distance` (m), `moving_time` (s), `elevation_gain` (m)

## Cron: Gear Check (weekly, Mondays 10:00)

Job `strava_gear_check`. Runs `node scripts/strava.mjs gear`, checks thresholds, delivers to current chat.

## `report` Command (14-Day Training Panorama)

```bash
python3 scripts/cli.py report
```

Outputs JSON with a **14-day window** (not just yesterday):

### Top-Level Structure
- `today`, `yesterday`, `window_start` — date anchors
- `yesterday_activities` — detailed per-activity metrics for yesterday
- `yesterday_trimp` — total yesterday load
- `activities_14d` — all activities in 14-day window with full metrics
- `daily_trimp_14d` — `{date: trimp}` for each active day
- `total_trimp_14d`, `avg_trimp_per_day` — 14-day totals
- `active_days`, `rest_days` — activity vs rest ratio
- `by_sport` — breakdown by sport type (count, TRIMP, distance, time, elevation)
- `median_decoupling`, `median_ef`, `median_hr_recovery` — 14-day medians
- `trend_decoupling`, `trend_ef`, `trend_hr_recovery`, `trend_vertical_speed` — trend arrows (↑+X% / ↓-X% / →)
- `banister` — current Fitness/Fatigue/Form + form_zone
- `banister_history` — form and fatigue for last 7 days (trend tracking)
- `weekly_trimp` — 7-day load
- `recommendation` — action, intensity, reasons
- `weekly_plan` — adaptive training plan targeting Saturday hiking peak:
  - `completed_days`: what's already done this week (Mon-today)
  - `plan_days`: recommended activity per remaining day with projected form, fitness, fatigue
  - `saturday_form`: projected form before Saturday hike (target: +5..+15 = fresh)
  - `sunday_form_after_hike`: projected form after two consecutive hiking days (~515 TRIMP each)
  - `on_track`: whether current trajectory hits target form range
  - `alternatives`: comparison scenarios (full rest, walks every day)
  - `sparkline`: centered-on-zero form trajectory visual (scale -30..+20)

### ACWR (Acute:Chronic Workload Ratio)

Alongside Banister, the report includes ACWR — a ratio-based load metric:

- **ATL** = 7-day EWMA of daily TRIMP (same as Banister Fatigue)
- **CTL** = 28-day EWMA of daily TRIMP
- **ACWR** = ATL / CTL

| ACWR Range | Zone | Meaning |
|-----------|------|---------|
| < 0.8 | undertrained | Detraining risk |
| 0.8–1.3 | sweet_spot | Optimal load |
| 1.3–1.5 | caution | Monitor fatigue |
| > 1.5 | danger | Injury risk |

ACWR complements Banister Form: Banister measures absolute readiness (difference), ACWR measures relative load change (ratio). Daily walking inflates both ATL and CTL equally → ratio stays ~1.0, correctly reflecting "lifestyle baseline" vs "training spike".

Report includes: `acwr`, `acwr_zone`, `acwr_ctl`, `acwr_atl`, `acwr_history` (7-day trend).

### YOY (Year-over-Year) — Removed May 2026

YoY comparisons (coach review #7) removed from regular analytics. YoY compares 28d now vs 28d ~364 days ago — noisy for aging athletes: season, health, motivation, weight all confound. Replaced by 90d CC trend.

### 14-Day Trends — Removed May 2026

`trend_decoupling`, `trend_ef`, `trend_hr_recovery`, `trend_vertical_speed` + `median_decoupling`, `median_ef`, `median_hr_recovery` removed from `daily_report()` (coach review #9). Over 4–6 data points, these are statistical noise. Kept: Banister/Acwr for load; CC for efficiency; progressive signal for quality.

### CC-Only Output (May 2026)

EF, bkm, VO2max removed from `RollingEfficiency` and `WeeklyDigest` (coach reviews #2, #4). CC and CC_adj are the sole cardiac efficiency metrics in output. One story, one number.

### EnrichedActivity Cleanup (May 2026)

`decoupling_pct`, `decoupling_result`, and `efficiency_factor` removed from `EnrichedActivity` (coach reviews #1, #2). Decoupling almost always N/A for this athlete (pace CV > 25%); EF replaced by CC in progressive signal. `enrich_activity()` no longer calls `calc_decoupling_with_gate()` or `calc_efficiency_factor()` — both functions remain available for ad-hoc use.

### HR Recovery — bpm_per_min Removed (May 2026)

`bpm_per_min` duplicate field removed from `HrRecovery` (coach review #10). `median_rate` is the sole primary metric.

### Form Zones — Simplified to 3 (May 2026)

7-zone classification reduced to 3: `tired` (form < -5), `normal` (-5..10), `fresh` (>10). Coach review #8. `_form_zone()` and `_form_zone_short()` updated. `BanisterResult.form_zone` docstring fixed.

### HR Anomaly Detection (May 2026)

`check_hr_anomalies()` added to metrics.py (sports medicine review #12). Checks for >30 bpm jumps between consecutive stream points. Flags only when ≥3 anomalies found (isolated single jumps = sensor noise). Wired into `daily_report()` safety_warnings. Samsung Health data on this athlete is clean — function acts as silent safety net.

### Hike Safety — TRIMP Threshold (May 2026)

Consecutive-hike alert now fires only when total TRIMP > 800 over two days (sports medicine review #16). Temperature >28°C check pending Open-Meteo API integration.

### Orthopaedic Load Tracking — 10% Rule (May 2026)

`safety_warnings` now enforces the running 10% rule (sports medicine review #14): weekly running km must not increase >10% vs previous week. >15% triggers a hard warning (stress fracture risk). Running = 2.5-3× body weight impact per step — masters athletes are especially vulnerable.

### Cardiac Drift Detection — Jenks-Based (May 2026)

Intra-activity cardiac drift detection added (sports medicine review #11). Algorithm: Jenks natural breaks clusters velocity into pace zones, then compares median HR in early vs late segments within each cluster. Works with variable pace (unlike Pa:HR decoupling which requires CV ≤25%).

**Files:** `strava_lib/cardiac_drift.py` (pure Python, no numpy required), `constants.py::Config.Drift` (per-sport thresholds), `types.py::CardiacDriftResult`, `metrics.py::calc_cardiac_drift()`, `training.py::calc_progressive_signal()`, `report.py::daily_report()`.

**Per-sport thresholds:** Run=10%, TrailRun=12%, Hike=8%, Walk=6% (walk is most sensitive — any drift = fatigue sentinel).

**Integration points:**
- `enrich_activity()` — computes drift for every activity (~0.4s with 600pt subsample)
- `daily_report()` — significant/severe drift → `safety_warnings`
- `calc_progressive_signal()` — drift trend over 21 days → modifies `load_bonus` (±5% or ±10%). **Only training sports** (Run, Hike, TrailRun); Walk is excluded (lower threshold 6% + higher volatility = noise).

Also added `EnrichedActivity.cc` (Cardiac Cost) — pre-computed in enrichment, reused by progressive signal to avoid redundant SQL queries.

### Narrative Guidelines for Daily Report

The cron job generates a coach-style narrative in Russian.ntegration.

### Orthopaedic Load Tracking — 10% Rule (May 2026)

`safety_warnings` now enforces the running 10% rule (sports medicine review #14): weekly running km must not increase >10% vs previous week. >15% triggers a hard warning (stress fracture risk). Running = 2.5-3× body weight impact per step — masters athletes are especially vulnerable.

### Cardiac Drift Detection — Jenks-Based (May 2026)

Intra-activity cardiac drift detection added (sports medicine review #11). Algorithm: Jenks natural breaks clusters velocity into pace zones, then compares median HR in early vs late segments within each cluster. Works with variable pace (unlike Pa:HR decoupling which requires CV ≤25%).

**Files:** `strava_lib/cardiac_drift.py` (pure Python, no numpy required), `constants.py::Config.Drift` (per-sport thresholds), `types.py::CardiacDriftResult`, `metrics.py::calc_cardiac_drift()`, `training.py::calc_progressive_signal()`, `report.py::daily_report()`.

**Per-sport thresholds:** Run=10%, TrailRun=12%, Hike=8%, Walk=6% (walk is most sensitive — any drift = fatigue sentinel).

**Integration points:**
- `enrich_activity()` — computes drift for every activity (~0.4s with 600pt subsample)
- `daily_report()` — significant/severe drift → `safety_warnings`
- `calc_progressive_signal()` — drift trend over 21 days → modifies `load_bonus` (±5% or ±10%). **Only training sports** (Run, Hike, TrailRun); Walk is excluded (lower threshold 6% + higher volatility = noise).

Also added `EnrichedActivity.cc` (Cardiac Cost) — pre-computed in enrichment, reused by progressive signal to avoid redundant SQL queries.

### Narrative Guidelines for Daily Report

The cron job generates a coach-style narrative in Russian.

**Readiness (how rested / fresh the body is):**
Use Banister Form + ACWR together. Describe in terms of energy, not metrics.

| Banister Form Zone | ACWR | What to say |
|---|---|---|
| overtrained (<-30) | >1.5 | "Тело на пределе, нужна пауза. Никакой нагрузки минимум 2–3 дня." |
| very_tired (-15..-30) | 1.3–1.5 | "Накопилась усталость. Сегодня лучше без нагрузок, дать организму восстановиться." |
| tired (-5..-15) | 1.0–1.3 | "Лёгкая усталость, но ничего критичного. Спокойная прогулка или лёгкая пробежка — ок." |
| neutral (-5..+5) | 0.8–1.3 | "Состояние нормальное. Можно тренироваться в привычном режиме." |
| fresh (+5..+15) | 0.8–1.0 | "Чувствуешь себя бодро — хороший день для нагрузки. Можно прибавить." |
| very_fresh (+15..+30) | <0.8 | "Отличная свежесть! Идеальный день для долгого бега или похода." |
| peak (>30) | <0.8 | "Пик формы. Если планировали что-то серьёзное — сегодня день." |

When Banister and ACWR disagree (e.g. Form says tired but ACWR says sweet spot), trust ACWR for load assessment and Banister for readiness. Explain naturally: "Нагрузка сбалансированная, но тело чуть тяжёлое — сегодня лучше полегче."

**Load trend (is training load going up, down, or stable):**
Don't mention ACWR by name. Say:
- ACWR rising toward 1.3 → "Нагрузка растёт"
- ACWR stable 0.8–1.3 → "Нагрузка в норме"
- ACWR falling below 0.8 → "Нагрузка снизилась"
- ACWR > 1.5 → "Нагрузка резко выросла, нужно притормозить"

**Training quality (decoupling / EF from runs and hikes):**
Never mention decoupling % or EF numbers. Say:
- Decoupling < 5% → "Сердце спокойно справляется с нагрузкой"
- Decoupling 5–10% → "Небольшой пульсовый сдвиг, но в пределах нормы"
- Decoupling > 10% → "Пульс на последних километрах заметно выше, чем в начале — признак усталости"
- Decoupling N/A (pace too variable) → Do NOT mention decoupling at all. Don't say "нет данных" or "не удалось посчитать." The metric is not applicable, not missing. Focus on CC and EF trends instead.
- EF improving → "Бежишь эффективнее, на тот же пульс — быстрее"
- EF declining → "Экономичность чуть просела, каждый kilometr даётся тяжелее"

**Weekly plan sparkline:**
Keep the emoji sparkline (🟠→🟡→🟢→🔵🎯) — it's visual and intuitive.

**General rules:**
- Speak like a coach, not a scientist: "тело просит паузу", "хороший день для бега", "накопилась усталость"
- One sentence per insight. No more than 6–8 sentences total.
- If there's nothing remarkable, say so briefly — don't invent drama.
- Yesterday's activity: describe what was done (ran, walked, hiked) and how it felt (heart rate, pace) — no raw metrics unless the user asks.
- The plan for the week should be about *days and actions*, not projected form numbers. Say "в среду отдых, в четверг лёгкая пробежка" instead of "в среду форма поднимется до +4".
- **Activity timing**: Use `start_time` (HH:MM) to correctly describe when each activity happened:
  - 00:00–05:00 → "ночная, после полуночи" + always name the *previous* day: "ночь с пятницы на субботу". These are the tail of the prior day — the athlete hasn't slept yet.
  - 05:00–12:00 → "утренняя"
  - 12:00–18:00 → "дневная"
  - 18:00–00:00 → "вечерняя"
  - **Critical rule — same-date activities >12h apart**: When two activities fall on the same calendar date but are separated by 12+ hours (e.g., 00:18 and 22:34), they span a full day of sleep and daily life. NEVER write "две ночные прогулки" — this creates the false impression they happened in the same night. Instead, describe them separately with explicit timing: "одна — сразу после полуночи (ночь с пятницы на субботу), вторая — уже вечером субботы". Always mention sleep/daytime happened between them. Same for morning + evening activities on the same date.
- **Weekend projections**: Do NOT state obvious post-weekend form projections. [REDACTED-NAME] already knows hiking affects form. The `post_weekend` data is context-only. Never say things like "если планируешь поход — один день, не два" or "два дня подряд снесут форму". Only mention weekend hiking if projection shows form dropping to dangerous levels (form < -30), and even then — once, briefly.

### Constants (single source of truth)

All athlete parameters and algorithm constants live in `strava_lib/constants.py` within the `Config` hierarchy (Athlete, Model.Banister, Model.ACWR, Zones, Thresholds, Efficiency, Metrics, Plan):

```python
from strava_lib.constants import Config

Config.Athlete.HR_MAX              # 191
Config.Thresholds.PACE_CV_MAX      # 0.25
Config.Model.Banister.TAU_FATIGUE  # 9
Config.Zones.BOUNDS                # [136, 150, 163, 177, 300]   # Karvonen (May 2026)
Config.Efficiency.CC_ELEV_COEFF    # 0.45
Config.SQL.TRIMP                   # pre-generated TRIMP SQL fragment

| Path | Value | Source |
|------|-------|--------|
| `Config.Athlete.DATE_OF_BIRTH` | `datetime([REDACTED-DOB])` | User-provided |
| `Config.Athlete.HR_MAX` | `191` | Observed max from hike streams |
| `Config.Athlete.HR_REST` | `53` | Samsung Health monthly avg |
| `Config.Model.Banister.TAU_FATIGUE` | `9` days | Age-adjusted: slower recovery at 50+ |
| `Config.Model.Banister.TAU_FITNESS` | `42` days | Standard Banister model |
| `Config.Model.Banister.ALPHA_FATIGUE` | `≈0.074` | Computed: `1 − 0.5^(1/τ)` (τ=9, age-adjusted) |
| `Config.Model.Banister.ALPHA_FITNESS` | `≈0.016` | Computed: `1 − 0.5^(1/τ)` |
| `Config.Model.ACWR.TAU_ATL` | `7` days | Acute load window |
| `Config.Model.ACWR.TAU_CTL` | `28` days | Chronic load window |
| `Config.Zones.BOUNDS` | `[122, 136, 150, 163, 177, 300]` | Karvonen (HRrest=53, HRmax=191): 6 zones incl. Z0 (<50% HRR) |
| `Config.Zones.COEFF` | `[0.5, 1, 2, 3, 4, 5]` | Zone multipliers (Z0 weight 0.5) |
| `Config.Thresholds.VEL_STOP` | `0.15` m/s | Standing still threshold |
| `Config.Thresholds.VEL_MOVING` | `0.3` m/s | Minimum "in motion" velocity |
| `Config.Thresholds.VEL_RUN_MIN` | `1.8` m/s | Min velocity for VO₂max calc |
| `Config.Thresholds.PACE_CV_MAX` | `0.25` | Max velocity CV for decoupling validity |
| `Config.Efficiency.CC_ELEV_COEFF` | `0.45` | Elevation CC adjustment |
| `Config.Efficiency.YOY_SHIFT_DAYS` | `364` | ~52 weeks for year-over-year |
| `Config.Metrics.MIN_STREAM_POINTS` | `120` | Min second-by-second rows for valid calculation |
| `Config.Metrics.MIN_MOVING_TIME` | `300` s | Min moving time for EF calc |
| `Config.Metrics.MIN_PAUSE_SEC` | `30` s | Min pause duration for HRR detection |
| `Config.Plan.HIKE_TRIMP_TEMPLATE` | `515` | TRIMP for a typical hike day |
| `Config.Plan.TRIMP_EASY` | `80` | TRIMP ceiling for easy effort classification |
| `Config.Plan.TRIMP_MEDIUM` | `120` | TRIMP ceiling for medium effort classification |
| `Config.Model.PROGRESSIVE_WINDOW` | `21` days | Window for progressive signal quality analysis |
| `Config.Plan.Score.TARGET_HIT` | `100` | Scoring: form in 5..15 target |
| `Config.Plan.Score.SAFETY_CRITICAL` | `30` | Penalty for form < -20 during simulation |
| `Config.Plan.Score.VARIETY_BONUS` | `5` | Reward per unique activity type |
| `Config.Plan.TRIMP_HEAVY_DAY` | `300` | Yesterday TRIMP above which intensity is capped |
| `Config.Plan.TRIMP_WALK_RUN_BOUNDARY` | `75` | Below = walk-like, above = run-like (within EASY) |
| `Config.Metrics.MIN_HR_POINTS` | `60` | Minimum HR data points for EF calculation |
| `Config.Metrics.MIN_ALT_POINTS` | `60` | Minimum altitude points for vertical speed |
| `Config.Model.BANISTER_WARMUP_DAYS` | `90` | Days to warm up Banister before trend analysis |
| _(14 scoring weights total)_ | — | See `Config.Plan.Score` in constants.py |
| `SPORT_RUN/WALK/HIKE/TRAILRUN` | individual strings | Avoid hardcoded sport names |
| `TRAINING_SPORTS` | 25 types (from sports.py) | Structured training filter |
| `RUNNING_SPORTS` | 3 types: Run, TrailRun, VirtualRun | Running biomechanics (GAP, VO₂max) |
| `ALL_SPORTS` | 50 types (from sports.py) | All known sport types |

SQL fragments for TRIMP are auto-generated via `_build_trimp_cases()` → `_ZONES_SQL`, `_TRIMP_SQL`, `_ZONES_SQL_S`, `_TRIMP_SQL_S`.

### Banister History Window

`_daily_trimp_history(conn)` — uses **all available history** (no day limit). Banister EWMA with τ=42 needs ~200+ days to fully warm up. With a 90-day window, fitness was severely underestimated (~80 vs ~100), causing false "very_tired" readings.

### Sport Type Groups (constants.py → sports.py)

All sport type logic is centralized in `constants.py`:

| Constant | Value | Purpose |
|----------|-------|---------|
| `SPORT_RUN/WALK/HIKE/TRAILRUN` | Individual strings | Avoid hardcoded sport names |
| `TRAINING_SPORTS` | 25 types (from sports.py registry) | Structured training (not lifestyle) |
| `RUNNING_SPORTS` | 3 types: Run, TrailRun, VirtualRun (from sports.py) | Running biomechanics (GAP applies) |
| `ALL_SPORTS` | 50 types (from sports.py registry) | Iteration over all types |

TrailRun is treated identically to Run for GAP streams, VO2max estimation, and efficiency windows (`[7, 28, 90]`). Walk is excluded from training metrics (decoupling, EF trends, progressive signal).

### Sport Registry (sports.py)

All sport type logic is centralized in `scripts/strava_lib/sports.py`. The module defines a `SPORT_REGISTRY` dictionary with all 50 Strava sport types, each annotated with metadata:

| Field | Type | Description |
|---|---|---|
| `is_training` | bool | True for structured training (Run, Hike, TrailRun, etc.) |
| `is_running` | bool | True for running biomechanics (Run, TrailRun, VirtualRun) |
| `eff_windows` | list[int] | Efficiency windows to track (e.g., `[7, 28, 90]`) |
| `hr_based` | bool | True if HR-based metrics (TRIMP, decoupling) are meaningful |
| `category` | str | Human-readable category (Running, Cycling, Water, Winter, etc.) |

**Pre-computed groups:**
- `SPORT_TRAINING` — 25 types with `is_training=True` (Run, TrailRun, Hike, Ride, VirtualRide, etc.)
- `SPORT_RUNNING` — 3 types with `is_running=True` (Run, TrailRun, VirtualRun)
- `SPORT_ALL` — all 50 registered types

**Helper functions:**
- `is_training(sport)` — check if a sport type is structured training
- `is_running(sport)` — check if a sport type uses running biomechanics
- `get_eff_windows(sport)` — get efficiency windows for a sport
- `build_eff_config()` — build per-sport efficiency configuration from registry
- `detect_new_types(sport_types)` — find unknown sport types given a list of strings

**Auto-detection during sync:** After each sync, `sync_activities()` fetches all distinct sport types from the DB and passes them to `detect_new_types()`. Unknown types are saved to the database but excluded from all analytics (no TRIMP, no decoupling, no efficiency metrics). The sync output prints a list of unknown types with instructions to add them to `SPORT_REGISTRY`.

`constants.py` re-exports `SPORT_TRAINING`, `SPORT_RUNNING`, and `SPORT_ALL` from `sports.py` — all other modules import from `constants` to avoid coupling to the registry module directly.

### Walk Activity Filtering

Decoupling, Efficiency Factor, and HR Recovery trends are computed **only for TRAINING_SPORTS (Run/Hike/TrailRun)**. Walk produces noisy decoupling (frequent stops, uneven pace) that inflates trend signals. The `calc_progressive_signal()` function also excludes Walk from its 21-day analysis window.

| Metric | Description | What it tells you |
|--------|-------------|-------------------|
| **TRIMP** | Zone-weighted training load | Overall effort of the activity |
| **Banister Fitness** | 42-day EWMA of daily TRIMP | Long-term aerobic capacity (slow to build, slow to lose) |
| **Banister Fatigue** | 7-day EWMA of daily TRIMP | Short-term accumulated tiredness (quick to build, quick to clear) |
| **Banister Form** | Fitness - Fatigue | Current readiness. Negative = tired, positive = fresh/peaking |
| **Form Zones** | overtrained (<-30), very_tired (-15..-30), tired (-5..-15), neutral (-5..5), fresh (5..15), very_fresh (15..30), peak (>30) | Actionable classification |
| **Decoupling %** | HR/pace ratio drift from 1st to 2nd half (stops filtered, vel < 0.3 m/s excluded). Raw HR/vel is used — empirical analysis of this athlete's 178k stream points shows they naturally adjust pace on hills, making GAP correction unnecessary (norm_eff ≈ 1.0 across ±10% grades). **Validity gate:** decoupling requires steady-state pace (CV of velocity ≤ PACE_CV_MAX=25%). Above this threshold, pace is too variable for the metric to be meaningful (e.g. run→walk structural change, mountain ascent/descent). When CV > 25%, `decoupling_pct` is `None` and the activity is excluded from trends. For this athlete's training pattern (runs with walking segments, hikes with ascent/descent), most activities exceed the threshold — decoupling is effectively N/A. | Aerobic base quality. <5% = good. >10% = fatigue accumulating. N/A when pace too variable. |
| **Efficiency Factor** | avg_velocity / avg_HR × 100 | Running economy. Higher = more speed per heartbeat. Track over weeks for fitness trend |
| **HR Recovery** | Finds ALL pauses (velocity < 0.15 m/s for 30+ sec) and measures HR drop rate | CV fitness. Higher avg = faster recovery. Returns best/worst/avg/median rate, pause count, total rest time. N/A for continuous activities with no stops. |
| **Vertical Speed** | Ascent rate in m/h | Climbing power. Useful for hiking/trail comparisons |
| **Start Time** | HH:MM (local) from `start_date_local` | Time of day — lets LLM correctly classify "night walk at 01:00" vs "morning hike at 10:30" |

### Trend Calculation (`_trend()`)
Compares avg of first half vs second half of values. Returns `↑+X%` (rising >10%), `↓-X%` (falling >10%), or `→-X%` (stable). Requires ≥4 data points.

### Progressive Overload Signal (`calc_progressive_signal()`)

Second goal of the planner: if training quality metrics are improving, gradually increase load. If declining, reduce.

**Analyzes 21-day window of activities using per-sport metrics:**

- **CC trend per sport type** (May 2026): CC values are grouped by sport_type. Each sport with ≥3 activities gets its own trend (stored in `cc_trends` dict). Bonuses are weighted by activity count per sport. This prevents false alarms when activity mix changes (e.g. hiking instead of running makes CC look worse — Hike CC ≈ 159 vs Run ≈ 68, mixing them creates artificial trends).
- **Cardiac Drift — only training sports** (May 2026): Walk activities are excluded from drift trend. Walk has a lower threshold (6% vs Run's 10%) and higher volatility, making it noise for training quality assessment.
- EF removed May 2026 — CC and EF are perfectly anti-correlated (CC = 100/EF), using both was double-counting
- Decoupling removed May 2026 — almost always N/A due to pace variability
- **Signal clamped** to [-15%, +20%]: `grow` (≥+5%), `hold` (middle), `reduce` (≤-5%)

**Output fields:** `ProgressiveSignal` includes `cc_trends: dict[str, Optional[str]]` (per-sport, e.g. `{'Run': '→-0%', 'Hike': None}`) plus backward-compatible `cc_trend: Optional[str]` (combined).
- **Signal clamped** to [-15%, +20%]: `grow` (≥+5%), `hold` (middle), `reduce` (≤-5%)

**How it affects the plan:** `load_bonus` scales walk/run/run_medium TRIMP templates:
- +15% bonus: walk 69→79, run 79→91, run_medium 150→173 TRIMP
- -15% penalty: walk 69→59, run 79→67, run_medium 150→128 TRIMP
- Scoring also rewards active plans when `grow`, penalizes aggressive plans when `reduce`

**Output in report:** `progressive_signal` dict with `load_bonus`, `signal`, `ef_trend` (now always None), `cc_trend`, `reasons`.

**Known issues:** CC = 100/EF double-counting (see pitfalls), periodization and age adjustment missing. Full coach review → `references/coach-review-2026-05.md`.

### Recommendation Logic

`_generate_recommendation()` uses **pure predicates + priority merge** (refactored May 2026). Each signal is a pure function returning `(action, intensity, reason)` — no mutation of shared state:

1. **`_form_signal()`** — form zone → (action, intensity, reason). Overtrained/very_tired → rest; tired → easy+low; fresh/peak → train+high.
2. **`_load_signal()`** — weekly TRIMP > 800 → downgrade to easy; < 200 → bump to high.
3. **`_ratio_signal()`** — >85% active days → downgrade to easy.
4. **`_decoupling_signal()`** — max decoupling > 10% on last 3 activities → downgrade to easy.

**Merge:** Action uses priority `rest > easy > train`. Intensity takes `max` of all signals (rest forces `low`). Post-processing caps (yesterday load > 300, form trend slope < -1) apply after merge — each cap is independent of the others. Every signal is testable in isolation.

**Confidence:** computed from data completeness (`_confidence()`): <7 total days → `low`, 7–13 → `medium`, 14+ → `high`. Passed through to `Recommendation.confidence` for LLM narrative decisions.

## Weekly Plan (embedded in report)

`calc_weekly_plan()` — brute-force optimization of rest/walk/run combos for remaining weekdays. **Two goals**: (1) bring form to +5..+15 by Saturday, (2) progressive overload — scale load up/down based on quality trends.

Scoring: Saturday form in target zone (+100), total TRIMP bonus (+0.1/point), variety bonus (+5/unique activity), safety penalty (-30 if form < -20 during week), progressive bonus (scales with load_bonus × active TRIMP). 3^N combos where N = remaining weekdays.

## Command: trend

`python3 cli.py trend [WEEKS]` — training quality metrics over time. Three metrics:

1. **Time in Zone (TiZ)** — % days where form is in -10..+20 (optimal trainable range). Higher = more sustainable training.
2. **Form Velocity** — 4-week rolling slope of weekly avg form. Positive = form rising (fresh). Negative = form crashing (overtrained).
3. **Crash Rate** — % weeks where avg form drops below -30. Lower = fewer wasted recovery weeks.

Also tracks: weekly TRIMP total, Δfitness, avg/min/max form. Rolling 4-week TiZ average for smoothing.

**Why NOT "Fitness ROI" (Δfitness/TRIMP):** This metric is misleading for Banister because fitness = EMA(TRIMP). More load always increases fitness by definition — even when you're overtrained. The problem is fatigue grows faster. TiZ + Form Velocity capture the real picture: are you training sustainably?

**Baseline comparison:** Historical data shows three phases:
- Phase 1 (Oct-Dec 2025): Heavy hikes, TiZ=0%, avg form -69, 7/8 weeks crashed. Fitness "grew" but form was destroyed.
- Phase 2 (Jan-Mar 2026): Light walks/runs, TiZ=74%, avg form +8, 0 crashes. Fitness grew sustainably.
- Phase 3 (Apr-May 2026): Hikes returned, TiZ=39%, avg form -24, 4/9 weeks crashed. Form velocity -4.7/week.

The coach's goal: maintain Phase 2's TiZ (>70%) even during hiking seasons by tapering before weekends.

## Command: backtest

`python3 cli.py backtest [WEEKS]` — tests the weekly planner against historical data. For each past week:
1. Simulates what plan would be generated on Monday (same optimization algorithm)
2. Compares planned Saturday form vs actual Saturday form
3. Checks if following the plan would have produced better form than reality

Returns JSON with:
- `composite_score` (0-100): single number for algorithm comparison. Higher = better algorithm.
  - target_hit (0-40): % weeks plan hits +5..+15
  - improvement (0-30): % weeks plan beats reality
  - accuracy (0-30): how close plan predicts reality (lower error = higher score)
- `summary`: hit rates, improvement rate, average error
- `weekly_detail`: per-week breakdown

**Usage for algorithm tuning:** Change scoring weights / activity templates / target range in `calc_weekly_plan()`, then run `backtest 24` and compare composite_score. Goal: maximize composite_score.

## Cron: Daily Activity Digest (daily, 09:00 → Reports topic)

Job `strava_daily_analysis`. Runs `sync` then `report`, writes narrative morning briefing. Uses the weekly plan + post_weekend projections. LLM receives JSON and writes a coach-style narrative (6-10 sentences, Russian).

**⚠️ Gear exclusion required in prompt:** The daily analysis cron prompt MUST explicitly prohibit running `cli.py gear` or mentioning shoe/gear info. Without this, the LLM will spontaneously run `gear` «to be helpful», duplicating the separate `strava_gear_check` job. The `report` JSON contains zero gear data — all gear contamination comes from LLM initiative, not from the data.

## Training Load Model Design Decisions (May 2026)

### Walk TRIMP Discount in Banister
Daily walking is **lifestyle baseline**, not training stimulus. Without discount, Walk TRIMP (~60-90/day) continuously feeds the Fatigue EWMA (τ=7) and never lets it clear — the model sees "no rest days, constant overload" and flags fatigue even when the athlete feels fine.

**Fix:** Walk TRIMP is multiplied by a discount factor (default 0.3) before entering `calc_banister()`. Run and Hike TRIMP enter at full value. This means a 80-TRIMP walk contributes only 24 to Fatigue, while a 100-TRIMP run contributes 100.

**Rationale explored:** Four alternatives were evaluated:
- ACWR (ratio ATL/CTL) — naturally handles daily walking (inflates both equally → ratio ~1.0), but requires 28+ days of history for stable CTL. Less intuitive for athlete communication.
- Baseline Subtraction (subtract 28d average TRIMP, only excess counts) — elegant but complex, and sensitive to window length.
- WHOOP/Apple Watch approaches — proprietary, not reproducible.
- **Walk discount** — simplest, most transparent, preserves existing Banister infrastructure. Chosen.

### Decoupling & EF: Validity Gates

Decoupling and Efficiency Factor are **only meaningful for sustained-effort activities** with steady pace. Two gates filter invalid measurements:

1. **Walk exclusion**: Walk activities are excluded from trend calculations. Walk has inherently variable pace/HR (frequent stops, terrain, low intensity) that produces noisy, misleading decoupling signals (e.g., +266% decoupling "trend" driven entirely by walks).

2. **Pace variability gate** (May 2026): CV of velocity within an activity must be ≤ `PACE_CV_MAX` (25%). Above this, pace is too uneven for decoupling to be valid — the formula assumes steady-state effort. See `references/cardiac-drift-steady-state-requirement.md` for research citations, empirical CV data from this athlete, and threshold rationale.
When CV > 25%, `DecouplingResult.decoupling_pct` is `None` with `pace_too_variable=True`. These activities contribute nothing to trend calculations — same as Walk exclusion.

**Impact on this athlete**: As of May 2026, virtually ALL of [REDACTED-NAME]'s activities (Run and Hike) exceed the 25% CV threshold. His training pattern (run with walking segments, mountain hikes) does not produce steady-state efforts. Decoupling is effectively N/A for his current style. Other metrics (CC, EF, Banister Form, ACWR) carry the training quality signal instead.

**Fix:** `_decoupling_invalid(velocities)` is a pure function that checks whether decoupling is valid (CV vs `Config.Thresholds.PACE_CV_MAX`, plus minimum data gates). `calc_decoupling_with_gate()` orchestrates: fetch rows → gate check → `calc_decoupling(rows)` (pure decoupling math, no gate). Callers use `calc_decoupling_with_gate()` — they never need to call the gate or pure calc directly. `_enrich_activity()` propagates `decoupling_pct=None` to `EnrichedActivity`, and trends/recommendation logic already filter out `None` values — no downstream changes needed.

### User Context
- [REDACTED-NAME] walks daily as lifestyle (5-6 km evening walks). This is NOT training — it's commuting/relaxation.
- Training sessions (Run, Hike) happen 2-3x per week.
- The Banister model was originally designed for athletes with clear training days and rest days. Daily walking violates the "rest day" assumption. The Walk discount compensates.

## Efficiency Metrics for Weekly Digest

### Cardiac Cost (CC) — Billat 2020

**Formula:** CC = avg_HR / avg_velocity (BPM per m/s). Lower = more efficient.

**Cross-activity normalization:** CC naturally normalizes Walk and Run because both are forward locomotion. For this athlete:
- Walk CC = 68.4, Run CC = 63.8 (only 7% difference)
- Beats/km shows 16% difference (Walk 1106, Run 950) — CC is the better normalizer

**Hike does NOT normalize:** Hike CC = 121 (2× higher). Even after elevation adjustment (`cc_adj`, coefficient −0.45/mkpm), adjusted Hike CC ≈ 104 vs Run ≈ 62. Terrain, rough ground, and different biomechanics dominate. Hike tracked separately.

**Weekly digest format:** Compare this week's CC (Walk+Run combined) vs last week and vs same period last year. User wants weekly frequency with full breakdown.

### Beats per Kilometer (beats/km)

**Formula:** avg_HR × time_minutes / distance_km. Lower = more efficient. Literally "how many heartbeats you spend per kilometer".

**Use case:** More intuitive than CC for explaining to the user. But only valid within same sport type. Best for Run-to-Run comparisons.

**Data reference (this athlete, 5km runs):**
- Feb-Apr 2025: 1078 beats/km
- Feb-Apr 2026: 978 beats/km (−100 beats/km = 500 fewer heartbeats per 5km run)

**Stability (Run-only CV):** CC 7.4%, beats/km 8.5%, EF 7.5% — all comparable. CC slightly most stable.

### Why Not Garmin VO2max-style?

Garmin/Firstbeat estimate VO2max from HR-pace relationship during runs only (GPS + ≥70% HRmax + ≥10 min). For this athlete at fixed pace (7-9 min/km), HR was unchanged YoY (120 bpm both periods). The improvement shows as *same HR at 4× volume*, not *lower HR at same pace*. This makes pace-at-fixed-HR less sensitive for this athlete than CC or beats/km.

### Weekly Digest (`weekly` command)

```bash
python3 scripts/cli.py weekly
```

**Frequency:** Weekly (user preference). Delivered via cron every Sunday evening.

## Sync & Backfill

### Quick Sync (default) vs Full Sync

Two sync modes, different tradeoffs:

| Mode | Command | API calls | Mechanism | Use |
|---|---|---|---|---|
| **Quick** | `cli.py sync` | 1–2 | `after=<latest_date − 1d>`, only new activities | Daily cron |
| **Full** | `cli.py sync --full` | ~6 | Full pagination from page 1, every activity re-verified | Weekly cron |

**Quick sync details:**
- Queries `MAX(date)` from local DB, uses Strava's `after=` parameter to fetch only recent activities
- 7-day overlap — catches late kudos/likes (can be placed days after the activity) and timezone edge cases. For this athlete (~1-3 activities/day) the overlap is ~7-21 activities — still fits in one API page
- Overlap is idempotent — existing activities are UPDATE'd, not duplicated
- Phases 2–4 (streams, details, schema validation) are always incremental regardless of mode
- Phase 5 (kudos) runs after Phase 4 — fetches kudos for activities with `kudos_count > 0` in last 30 days that haven't been synced yet
- Cost: ~1-2 API calls on most days plus 1 call per activity with unsynced kudos

**Full sync details:**
- Paginates ALL activities from the API, comparing each against the local DB
- Catches: back-dated uploads, activities missed due to sync failures, Strava-side corrections
- Cost: ~6 API calls regardless of new activity count
- Weekly cadence recommended — daily full sync is wasteful

**Guarantee:** A missed activity from any date WILL be caught by the next full sync. Quick sync alone can miss back-dated uploads older than the latest DB date.

### `sync` — Incremental daily sync (5 phases)
Phase 1: Activity summaries from `/athlete/activities` (after= filter for quick mode, pages of 100).
Phase 2: Streams with GAP (`grade_adjusted_speed`, `moving`) for activities without streams.
Phase 3: DetailedActivity (`splits_metric`, `laps`, `best_efforts`, `calories`, `similar_activities`) for activities without `detail_json`.
Phase 4: Schema validation — unknown sport types + Summit field detection.
Phase 5: Kudos — fetches kudos for recent activities with `kudos_count > 0` that haven't been synced yet.

Daily quick sync costs ~1-2 API calls (plus 1 per activity with unsynced kudos). Full sync costs ~6 API calls regardless.

### Sync Audit (`sync_log`)

Every `sync` run writes to the `sync_log` table. View recent runs:

```bash
python3 scripts/cli.py log        # last 10 syncs
python3 scripts/cli.py log 20     # last 20
```

Output format: `timestamp ✓ +N new  M streams  K details  C calls` (or `✗` for failures with error message).

### Kudos Sync (Phase 5)

Fetches the list of athletes who gave kudos (likes) to recent activities. API details: `references/kudos-api.md`.

**Endpoint:** `GET /activities/{id}/kudos?per_page=100` — returns array of `SummaryAthlete` objects (`id`, `firstname`, `lastname`). Requires `activity:read` scope (same as existing).

**Table:** `kudos(activity_id INTEGER, firstname TEXT, lastname TEXT, fetched_at TEXT, PRIMARY KEY (activity_id, firstname, lastname))`. No `athlete_id` — Strava's kudos endpoint only returns `firstname` and `lastname` (the `id` field is omitted in the minimal SummaryAthlete response).

**Incremental logic:** Phase 5 runs after Phase 4 in every sync. It queries:
```sql
SELECT id FROM activities
WHERE kudos_count > 0                          -- from summary_json
  AND date >= date('now', '-30 days')          -- recent window
  AND NOT EXISTS (kudos for this activity)     -- not yet synced
```

Cost: 1 API call per activity with unsynced kudos. First run may fetch 10-30 activities; subsequent runs only 0-2 (new activities or those whose kudos_count grew).

**Query kudos data:**
```bash
# Who kudoed which activities this week
python3 scripts/cli.py sql "SELECT a.name, a.date, k.firstname, k.lastname
FROM kudos k JOIN activities a ON a.id=k.activity_id
WHERE a.date >= date('now','-7 days') ORDER BY a.date DESC"

# Top kudoers all-time
python3 scripts/cli.py sql "SELECT firstname, lastname, COUNT(*) cnt
FROM kudos GROUP BY athlete_id ORDER BY cnt DESC LIMIT 10"
```

**Why 7-day quick sync overlap matters for kudos:** A friend may kudo Monday's run on Thursday. Quick sync's 7-day overlap re-fetches Monday's activity summary → sees increased `kudos_count` → Phase 5 fetches the new kudos. Without the overlap, the kudos would only be caught on the next full sync.

### `backfill` — One-time bulk fill (SAFE, idempotent)
Finds ONLY activities missing GAP streams or `detail_json`. Skips everything already fetched. Prints count before starting. Safe to run repeatedly — if nothing is missing, exits instantly with "Nothing to backfill."

**DO NOT re-implement a full-scan backfill** — the old version re-fetched all 574 activities (30 hours). The current version is incremental.

### Rate Limiter
`RateLimiter` class (190 calls/15min window). Uses dual strategy: client-side counter as fallback, but prefers Strava's `X-RateLimit-Usage` response headers when available (more accurate — accounts for quota shared with phone/watch). On 429 responses, honors `Retry-After` header for precise wait duration. `_fetch_with_retry` wraps API calls with network-error retry (exponential backoff 1s→5s→30s), 401 auto-refresh, and 429 Retry-After handling. After rate-limit sleep, server-usage state is reset so the next call re-syncs from fresh headers.

### GAP Streams (Grade Adjusted Pace)
Strava returns `grade_adjusted_speed` as a per-second stream **only for Run**. Walk and Hike do NOT get it. We have `grade_smooth` for all types, so Minetti GAP can be computed for Walk/Hike if needed. Key difference: Strava GAP ≈ Minetti GAP on flat (<2%), but diverges +15-18% on 5% grades (Strava is more aggressive).

### Stream keys requested
```
time,heartrate,velocity_smooth,altitude,cadence,latlng,grade_smooth,grade_adjusted_speed,grade_adjusted_distance,moving
```

## Strava API Coverage

**Full reference:** `scripts/strava_lib/strava_api_reference.py` — documents every endpoint, field, and data model.

### What we sync (resource_state=2, SummaryActivity)
GET /athlete/activities → list of activities with ~50 fields each. We store `summary_json` in DB. Currently parse ~15 fields into `StravaActivity` dataclass (types.py).

### What we DON'T fetch yet but CAN (resource_state=3, DetailedActivity)
GET /activities/{id} returns 67+ fields including:
- **splits_metric** — per-km splits with `average_grade_adjusted_speed` (Strava's GAP!) and `average_heartrate`
- **best_efforts** — auto-detected best times for 400m, 1km, 5km etc. with PR tracking
- **laps** — auto-detected laps with speed/cadence data
- **similar_activities** — trend across comparable activities (direction: -1/0/1, last 5 speeds)
- **calories** — energy expenditure (kcal)
- **gear_detail** — full shoe info including `retired` flag

### What requires Summit (💰 402 Payment Required)
- Activity zones (suffer_score, time-in-zone distribution) — GET /activities/{id}/zones
- perceived_exertion (RPE 1-10) — included in DetailedActivity but null for free accounts
- Segment effort history — GET /segment_efforts

### Streams available (free)
time, heartrate, velocity_smooth, altitude, cadence, latlng, grade_smooth, distance, moving — all at "high" resolution (~1 point/second). No power (cycling only), no temperature (Samsung Health doesn't provide).

### To get GAP/laps/splits: need Phase 2 sync
Currently `cmd_sync` only fetches list + streams. To get DetailedActivity data, add a second phase that calls GET /activities/{id} for each new activity and stores splits/laps/best_efforts in DB. This costs 1 API call per new activity (~1-3/day).

## Code Architecture (refactored May 2026)

`scripts/cli.py` — CLI dispatcher (263 lines). **Post-decoupling:** zero cross-module private imports, zero duplicated Banister logic. `cmd_sync`/`cmd_backfill` delegate to `sync.py`, `cmd_trend` delegates to `trends.py`. Only `cmd_backtest` keeps inline logic (orchestrator, not domain).

`scripts/strava_lib/` package:

| Module | Responsibility |
|---|---|
| `types.py` | All dataclass contracts: BanisterResult, EnrichedActivity, DailyReport, WeeklyPlan, ProgressiveSignal, Recommendation, ActivityMetrics, RollingEfficiency, **SimDay** (Banister simulation output), PlanDay, WeeklyDigest, **BySportBreakdown**, **CompletedDay**, **PostWeekendSim**, **SparklineBar**, etc. + `dc_to_dict()` serializer + Strava API parsers (StravaActivity covers both Summary+Detailed, 65+ fields) |
| `strava_api_reference.py` | Complete Strava API map: every endpoint, field, data model. Marked with ✅/🔵/💰/⬜. Documents GAP availability (Run only), Summit-only features, stream channels |
| `api_schema.py` | Machine-readable field schemas (FieldSchema, EndpointSchema, ValidationResult). Reference contracts for API response structure — validation functions available for manual use. |
| `sports.py` | Sport type registry: 50 Strava sport types with metadata (`is_training`, `is_running`, `eff_windows`, `hr_based`, `category`). Helper functions and pre-computed groups (`SPORT_TRAINING`=25 types, `SPORT_RUNNING`=3, `SPORT_ALL`=50). Auto-detects unknown types during sync |
| `constants.py` | Athlete profile (HR_MAX=191, HR_REST=53, DOB), algorithm params (tau, zones, coefficients), SQL builders (`_build_trimp_cases`). Re-exports `SPORT_TRAINING`/`SPORT_RUNNING`/`SPORT_ALL` from sports.py |
| `db.py` | SQLite connection (`DbConn` context manager), schema init, Strava API wrappers (OAuth refresh, `api_request`), `get_daily_trimp_history`, zone classification |
| `sync.py` | Strava API operations: `RateLimiter`, `STREAM_KEYS`, `sync_activities()` (5-phase incremental sync + quick/full modes), `_sync_kudos()`, `backfill_activities()` (incremental GAP+details) |
| `trends.py` | Multi-week training quality trends: `compute_trends()` (TiZ, form velocity, crash rate, rolling windows) |
| `metrics.py` | Per-activity metrics: `_decoupling_invalid()` (validity gate), `calc_decoupling()` (pure Pa:HR), `calc_decoupling_with_gate()` (orchestrator), `calc_efficiency_factor()`, `calc_hr_recovery()`, `calc_vertical_speed()`, `enrich_activity()`. NOTE: `calc_decoupling_with_gate` delegates the MIN_STREAM_POINTS check to `calc_decoupling` (no duplicate check). `analytics.py` has a bulk EF computation via JOIN — same formula, different query pattern. |
| `training.py` | Banister model (EWMA, form zones, sparkline), ACWR, progressive signal, weekly plan simulation. `forward_simulate()` delegates to `_sim_one_day()` (single Banister step, unified May 2026). Also: `ewma()`, `trend()` helpers |
| `analytics.py` | Rolling-window efficiency (`rolling_eff`), weekly digest, trends, YoY comparisons, `median`/`pct_change` helpers. Uses `ALL_SPORTS`, `RUNNING_SPORTS` from constants. `rolling_avg` replaced by `_prefix_sums()` + `rolling_avg_from_prefix()` — O(1) for all hot-path calls in `weekly_digest()`. Legacy `rolling_avg()` removed May 2026. |
| `report.py` | Daily report (14d panorama + recommendation + ACWR + progressive signal + weekly plan) |

CLI: `sync|backfill|trend` delegate to respective modules (`sync.py`, `trends.py`). `report|weekly` delegate to library (`report.py`, `analytics.py`). `activities|gear|stats|sql|refresh|backtest|raw` kept inline.

**Rolling-window metrics** (not naive weekly snapshots). All comparisons are smoothed-rolling vs shifted-smoothed-rolling — industry standard (TrainingPeaks CTL/ATL, WHOOP WPA, Catapult).

**Output JSON structure:**

```
{
  "period": { today, weekday, data_days, first_activity },

  "current_state": {
    "load": {
      daily_avg_trimp_7d,     // short-term load
      daily_avg_trimp_28d,    // chronic load
      daily_avg_trimp_90d,    // quarterly baseline
      acwr                    // 7d/28d ratio
    },
    "efficiency": {           // per sport, MEDIAN aggregation
      "Run":  { "7d": {...}, "28d": {...}, "90d": {...} },
      "Walk": { "7d": {...}, "28d": {...} },
      "Hike": { "28d": {...}, "90d": {...} }
      // each window: count, active_days, total_km, total_time_h,
      //              total_elev_m, median_epkm, median_cc, median_cc_adj
    },
    "volume": {               // per sport, 7d + 28d
      "Run":  { "7d": {...}, "28d": {...} },
      "Walk": { "7d": {...}, "28d": {...} },
      "Hike": { "28d": {...} }
    }
  },

  "trends": {                 // % change: current rolling vs shifted rolling
    "load_7d": -13.2,         // 7d avg now vs 7d avg 7d ago
    "load_28d": 13.4,         // 28d avg now vs 28d avg 28d ago
    "load_90d": 16.6,         // 90d avg now vs 90d avg 90d ago
    "Run_28d_median_cc": 5.5, // CC-only (May 2026): EF/bkm/vo2max removed
    "run_90d_median_cc": -0.3 // long-term Run CC trend (quarterly)
  },

  "yoy": {},                  // removed May 2026 (coach review #7)

  "context": {
    "season": "spring",
    "last_hike_days_ago": 9,
    "activity_streak": 0,
    "rest_streak": 1
  },

  "this_week": [ ... ]        // activities since Monday
}
```

**Why rolling windows:** Weekly snapshot CV=49%, 7d rolling CV=29%, 28d rolling CV=11%. One hike shouldn't make a week look 3× the previous. Rolling windows smooth out this noise.

**Why median not mean for efficiency:** A single slow recovery run or outlier hike skews the mean. Median is robust to outliers. Run CC per-activity CV is 7% — stable enough for trend detection when aggregated.
### Cardiac efficiency metrics (per sport):

| Metric | Formula | Direction |
|--------|---------|-----------|
| **%HRR (Heart Rate Reserve)** | (avg_HR − HRrest) / (HRmax − HRrest) × 100 | ↓ better — less of heart's capacity used |
| Cardiac Cost (CC) | avg_HR / avg_velocity | ↓ better |
| CC adjusted (CC_adj) | CC − 0.45 × epkm | ↓ better (elevation-normalized) |
| Beats per km | avg_HR × time_min / dist_km | ↓ better |
| Efficiency Factor | avg_velocity / avg_HR × 100 | ↑ better |
| Elevation per km (epkm) | total_elev / dist_km | context only |

**%HRR (May 2026):** Added after expert panel. Answers "how much of the heart's reserve capacity was used". **Uses MEDIAN HR from streams** (not Strava's average) — robust to wrist sensor spikes and cadence lock. Formula: `(median_HR − HRrest) / (HRmax − HRrest) × 100`. HRmax from `SELECT MAX(heartrate) FROM streams` (live, cached). HRrest=53 from Samsung Health.

**Elevation adjustment:** Regression on this athlete's data shows +0.45 CC per m/km of elevation gain (Run=0.41, Walk=0.50, Hike=0.48; averaged). `cc_adj` strips this out, giving flat-ground equivalent CC. For Run/Walk with stable routes (~12-13 m/km), the effect is small (~0.6% in YoY). For Hike (20-122 m/km), the adjustment is significant but Hike CC remains non-comparable to Run/Walk due to different biomechanics. `cc_adj` is included in trends and yoy alongside raw `cc`.

**Window sizes by sport:**
- Run: 7d, 28d, 90d (enough data for all three)
- Walk: 7d, 28d (daily activity, short windows sufficient)
- Hike: 28d, 90d (infrequent, needs larger windows for meaningful medians)

**Trend calculation method:** Each trend compares current rolling window to the same-size window shifted back by its own length. E.g., `load_28d` compares last 28 days vs the 28 days before that. This gives a true "how am I doing vs my own recent baseline" comparison without snapshot noise.

**Agent narrative rules for weekly digest:**
Same as daily report — no raw numbers. Agent interprets metrics and tells a story:
- "Сердце работает эффективнее — за месяц CC снизился" instead of "CC went from 72.2 to 69.7"
- Highlight the most notable change (biggest improvement or regression)
- YoY comparison is motivational — "Год назад ты..." format
- If nothing remarkable happened, say so briefly
- Always include: what was done, what changed, what it means for next week
- Use trends for direction, yoy for big-picture progress, context for color

## VO2max Estimation Research (May 2026)

User asked: can we extract more value from HR data? Three approaches investigated:

## Cardiac Drift Research (May 2026)

Expert panel (5 roles: statistician, sports physician, coach, data engineer, physiologist)
evaluated Jenks Natural Breaks-based intra-activity cardiac drift as an alternative
to Pa:HR decoupling. Full synthesis: `references/cardiac-drift-expert-panel.md`.
Algorithm: `/opt/data/cardiac_drift.py` (~400 lines, Fisher-Jenks DP + auto-k via GVF).

Key findings: wrist sensor noise comparable to drift signal → conservative thresholds needed.
Walk-as-sentinel is the highest-value use case (any drift on walk = systemic fatigue).
Three-level architecture: L1 silent → L2 soft post-workout context → L3 alert after 3+ episodes.
Not yet integrated — pending implementation decision.

(Full cardiac drift steady-state requirement analysis: `references/cardiac-drift-steady-state-requirement.md`)

### Method 1: Uth et al. HR Ratio (non-exercise)
**Formula:** VO2max = 15.3 × (HRmax / HRrest)
- This athlete: 15.3 × (191/55) = **53.1** ml/kg/min
- **Accuracy:** ±5 ml/kg/min. Tends to overestimate. Useful as upper bound.

### Method 2: ACSM Running Equation + HR Extrapolation (sub-maximal, Garmin-like)
**Formula:** VO2 = 0.2 × velocity(m/min) + 3.5; VO2max = VO2 × (HRmax / HR_exercise)
- This athlete: median **45.0** ml/kg/min (range 40-49 across months)
- Monthly breakdown shows clear seasonal pattern (Aug peak ~49, winter ~42)
- **Accuracy:** ±3-4 ml/kg/min. Underestimates vs lab. This is what Garmin/Firstbeat use (with additional corrections for HR dynamics).
- **Sensitivity:** Can detect ~2-3 ml/kg/min changes over months. Sufficient for trend tracking.

### Method 3: Jack Daniels VDOT (race-based)
Requires all-out race effort. Not applicable — athlete doesn't race.

### What VO2max = 45 means for this athlete (age ~40):
- Normative: "Good" (40-48). Near bottom of "Good", far from "Excellent" (48-56).
- Comparable to recreational runners. With structured threshold training, could reach 48-50.

### HR Zones Analysis
Current Strava zones (0-118, 118-147, 147-162, 162-177, 177+) are poorly calibrated:
- 93% of running time spent in Z1-Z2 — athlete rarely reaches threshold
- Karvonen zones (using HRreserve=136): Z2 aerobic = 137-150 bpm — better matches actual training
- LTHR estimated at 162-175 bpm (85-92% HRmax) — only 0.6% of running time in this range

**Data available:** HRmax=191 (observed in hikes), HRrest=55 (morning baseline). Both stable.

### HR Recovery (HRR)
- Mean HRR-60 during activity pauses: 10 bpm (very low)
- But this is NOT true end-of-exercise HRR — it's pauses mid-activity
- Cleveland Clinic threshold: HRR-60 ≥ 30 = "good", ≥ 40 = "excellent"
- **Problem:** Streams end with the activity, no post-exercise data captured
- **Verdict:** HRR data is too noisy with current setup to be useful

### Implementation Status
- VO2max: implemented in analytics.py, available in weekly digest output
- HR zones: **migrated to Karvonen** (May 2026). Replaced legacy Strava zones [118,147,162,177,300] with [136,150,163,177,300] — TRIMP now correctly classifies running effort.
- HRR: not viable with current data (no post-exercise streams)

### Key References
- Uth et al. (2004): VO2max = 15.3 × (HRmax/HRrest)
- Firstbeat white paper (2005/2012): VO2 estimation from HR + respiration + on/off dynamics
- HRV4Training (Altini 2016): sub-maximal HR is best predictor (R²=0.67 vs 0.54 for anthropometrics)
- ACSM running equation: VO2 = 0.2 × v(m/min) + 3.5

## Long-Term Trend Analysis

For analyzing metric trends over 6+ months (EF, pace, decoupling):

- **Theil-Sen estimator** (not OLS) — robust to outliers, median of all pairwise slopes. Use for "is EF improving?" questions. Available in numpy (manual implementation). Check if confidence interval crosses zero before declaring a trend.
- **LOWESS** (locally weighted scatterplot smoothing) — shows the real curve, not a straight line. `frac=0.35` works well for monthly data. Reveals seasonal patterns and plateaus that linear regression misses.
- **Seasonal decomposition** — compare same months year-over-year (Feb vs Feb, Mar vs Mar) instead of raw sequential trend. Seasonal amplitude can be ~0.15 EF (summer vs winter).
- **Volume×EF is more meaningful than EF alone** — EF measures "efficiency per heartbeat" but ignores that the athlete may be doing 4× more volume at the same efficiency. Always contextualize EF with run count and distance.

No statsmodels/scipy available — implement LOWESS manually with numpy.

## Pitfalls

- **No node_modules in skills**: Hermes security scanner blocks npm dependencies inside skill directories (flags README examples as credential exposure). Use inline code instead. The script uses a 5-line .env parser instead of the `dotenv` npm package.
- **skill_manage write_file for scripts**: When creating a skill with `action='create'`, the `file_content`/`file_path` params register metadata but don't write the file. Use `action='write_file'` separately to actually create script files on disk.
- **Deterministic scripts > curl-based instructions**: When migrating skills from other agents, prefer keeping the working script as-is over rewriting as "API documentation + curl commands". Scripts are reproducible, testable, and don't depend on LLM correctly assembling requests.
- **`read_file` dedup returns stale cached content**: When a file was already read earlier in the session, `read_file` returns `{'status': 'unchanged', 'content_returned': False}` instead of the actual file contents. This is a tool-level dedup optimization. Fallback: use `terminal cat` or `search_files` (with `target='content'` and a common substring) to re-read the file. The `execute_code` hermes-tools `read_file` function has the same dedup behavior.
- **`_fetch_with_retry` now catches network errors (May 2026, expert panel review)**: Previously only handled `_rate_limited` (429) — any `URLError`, `socket.timeout`, or `OSError` would crash the entire sync with no retry. Now catches these with exponential backoff (1s → 5s → 30s) across 3 attempts. If modifying the retry logic, keep the backoff and ensure all network-layer exceptions are caught.
- **LLM spontaneously runs `gear` in daily analysis — cron prompt must forbid it**: The `report` command returns zero gear data, but the LLM sees `cli.py gear` in the skill docs and runs it unprompted «to be helpful». This duplicates the separate `strava_gear_check` cron. Fix: the daily_analysis cron prompt must explicitly say «DO NOT check or mention shoe gear — handled by a separate job». The prohibition needs to be in the prompt, not just in the skill — the LLM will ignore skill docs when it's in «helpful» mode. Decoupling (Pa:HR) is defined as HR increase during CONSTANT effort. When pace changes structurally (run→walk, ascent→descent), the formula `(HR₂/pace₂)/(HR₁/pace₁) − 1` measures pace change, not cardiac drift. This athlete's runs have walking segments (CV 32-50%) and hikes have ascent/descent variation (CV 31-51%). The decoupling validity gate (`Config.Thresholds.PACE_CV_MAX`=25%) correctly excludes all of them via `_decoupling_invalid()` → `calc_decoupling_with_gate()`. Do NOT interpret missing decoupling as a data gap — it's a deliberate validity decision. Use CC, EF, Banister, and ACWR for training quality signal instead.

- **Refactoring safety — verify function signatures after extraction**: When extracting functions from a god module into separate files, signature mismatches are the #1 bug. Three critical bugs were introduced during the May 2026 decoupling: (1) `weekly_digest()` lost its `conn` parameter — runtime TypeError on `weekly` command; (2) `detect_new_types()` was passed a DB connection instead of the `list[str]` it expects — runtime crash on sync; (3) `_insert_streams()` INSERTs into `latlng` column that didn't exist in the CREATE TABLE schema (pre-existing, surfaced by fresh-DB audit). **Rule**: after any refactoring that moves functions between modules, verify the call site matches the target signature — smoke tests (`tests/test_smoke.py`) catch these before release.
- **No backward compatibility shims — this is solo-developed code**: There are zero external consumers, zero API contracts, zero obligations. When refactoring, NEVER keep legacy dict wrappers, compatibility layers, or shim functions «на всякий случай». If `forward_simulate` returns `list[SimDay]`, every caller uses `.form` — no dict-access backwards-compat layer. The user will immediately challenge any backward-compat hesitation. Clean break every time.
- **Backfill must be incremental**: Never re-fetch all activities. `cmd_backfill` only queries activities missing `detail_json` or GAP streams. Old "full scan" version took 30 hours and hung on network timeout (no urllib timeout). New version: idempotent, skips already-fetched, prints count upfront.
- **`urllib.error` must be imported explicitly**: `except urllib.error.HTTPError` works without an explicit `import urllib.error` only because `urllib.request` happens to load it into `sys.modules`. Python's spec does not guarantee this — it can break with version upgrades or alternative implementations. Always add `import urllib.error` alongside `import urllib.request`.
- **`urllib.request` timeout**: All `urlopen` calls now use `timeout=30` (May 2026). Prevents cron jobs from hanging indefinitely on network stalls.
- **API response types must be validated before iteration (May 2026, expert panel review)**: `sync_activities()` now checks `isinstance(data, list)` before iterating in Phase 1, and `isinstance(data, dict)` for stream/detail responses. Strava can return error dicts (`{"message": "error", "errors": [...]}`) instead of lists — iterating over a dict silently processes its keys, corrupting the DB. If adding new API calls to the sync pipeline, always validate the response type before use.
- **`api_request` returns tuple `(data, rate_headers)` (May 2026, expert panel review)**: After the sync reliability review, `api_request` returns a `(data, rate_headers)` tuple — NOT just data. `rate_headers` is a dict with `usage_15min`, `usage_daily`, `limit_15min` from Strava's `X-RateLimit-*` response headers. ALL callers must unpack: `data, _rate = api_request(...)`. The `_fetch_with_retry` wrapper feeds rate_headers into `RateLimiter.update_from_headers()`. When adding new direct `api_request` calls, always unpack the tuple — a bare `data = api_request(...)` will assign the tuple to `data` and break downstream logic.

- **`RateLimiter` uses server-reported usage + `Retry-After` (May 2026, expert panel review)**: The RateLimiter now has `update_from_headers(rate_info)` — when available, it trusts Strava's `X-RateLimit-Usage` header over the client-side counter. This is essential because other clients (phone, watch) share the same API quota. On 429 responses, `Retry-After` is parsed and honored instead of blind retry. After a rate-limit sleep, `_server_usage` is reset to `None` so the next call re-syncs from fresh headers. **Important — after receiving 429, `mark_rate_limited()` must be called**: Without it, the RateLimiter doesn't know the quota is exhausted, and the next `wait()` lets the call through → immediate 429 again → 3 rapid failures. `_fetch_with_retry` calls `limiter.mark_rate_limited()` on every 429 before sleeping. Any new retry loop that bypasses `_fetch_with_retry` must also call `mark_rate_limited()` on rate-limit responses.

- **`.env` file must be `chmod 600` (May 2026, expert panel review)**: The `.env` file contains Strava OAuth tokens. Before the review it was world-readable (644). After any new deployment or token rotation, run `chmod 600 /path/to/strava/.env`. The `DbConn` does NOT auto-fix permissions — it's a one-time setup step.

- **DbConn sets `wal_autocheckpoint=1000` + `check_same_thread=False` (May 2026, expert panel review)**: `PRAGMA wal_autocheckpoint=1000` prevents WAL file unbounded growth after large backfills. `check_same_thread=False` allows future multi-threaded access. Both set in `DbConn.__enter__()` — no caller changes needed.

- **`cmd_sync`/`cmd_backfill` wrapped in try/except (May 2026, expert panel review)**: Both CLI commands now catch all exceptions, print the error + full traceback to stderr, and exit with code 1. Previously, unhandled exceptions produced a bare Python traceback on stdout — invisible in cron unless `MAILTO` is configured. The traceback now goes to stderr which cron typically captures.

- **`_insert_streams` uses 5000-row batches (May 2026, expert panel review)**: Stream insertion now processes rows in 5000-row batches with `executemany` + `commit` per batch, instead of one giant transaction. A 4-hour activity (~14,400 rows) stays fast; an ultra-marathon (~86,400 rows) won't create a memory-hungry transaction. If changing `batch_size`, keep it ≤10000 to stay under SQLite's practical transaction size limit.
- **Strava `suffer_score` requires premium**: Always 0 for free accounts. TRIMP is the replacement metric.
- **Decoupling: raw HR/vel works for this athlete, GAP not needed**: Empirical analysis of 178k stream points (Apr 2026) showed this athlete naturally adjusts pace on hills — HR/vel ratio is ~1.0 across ±10% grades. Minetti GAP (factor 0.5-2.5x) severely distorts the ratio by inflating downhill effort. Three alternatives tested: (1) Minetti GAP — breaks on downhill (factor 0.5 makes stops look like 2x effort); (2) grade-stratified flat-only comparison — works but loses data; (3) raw HR/vel with stop filtering (vel > 0.3 m/s) — simplest and most accurate for this athlete.
- **Strava GAP streams (grade_adjusted_speed)**: Strava DOES return per-second GAP for Run activities (discovered May 2026). It's a stream channel like velocity_smooth — same 4045 points, per-second. BUT only for Run — Walk and Hike get `grade_adjusted_distance` in the response dict but NOT `grade_adjusted_speed`. Key difference: Strava GAP ≠ Minetti GAP. On 5% grade, Strava GAP is 15-18% higher than Minetti. On flat (<2%), they match within ~1%. Strava uses a proprietary formula (race-pace prediction); Minetti is from lab metabolic data. The `strava_api_reference.py` documents this. Current sync does NOT fetch GAP streams — would need to add `grade_adjusted_speed` to the streams key list in `cmd_sync`. Zero extra API calls (comes free with existing streams request).
- **Banister + daily walking = false fatigue**: Without Walk TRIMP discount, daily walks (~60-90 TRIMP) continuously feed the 7-day Fatigue EWMA and never let it clear. The model sees "no rest days" and flags overtraining incorrectly. Fix: Walk TRIMP × 0.3 before entering Banister. See "Training Load Model Design Decisions" section above.
- **Decoupling on Walk is noise**: Walk activities have inherently variable pace/HR (stops, terrain, low intensity). Including them in decoupling/EF trends produces wildly misleading signals. Fix: only Run and Hike feed trend calculations. See "Training Load Model Design Decisions" section above.
- **Weekly plan brute-force**: `calc_weekly_plan()` tries all 4^N combinations (rest/walk/run/run_medium × N remaining weekdays) and scores by: Saturday form in +5..+15 (primary), total TRIMP (secondary, maintain fitness), variety bonus, safety penalty for form < -20, progressive overload bonus. Activity TRIMP templates: rest=0, walk=69, run=79, run_medium=150 (base, scaled by load_bonus from progressive signal).
- **Backtest shows 100% improvement**: Historical test of 12 weeks shows following the planner would have produced better Saturday form in every single week. Without planner, athlete hit target form only 33% of weeks; with planner, 58%. Key insight: athlete's natural pattern (hike-heavy weekends without tapering) causes form to crash mid-week.
- **High form weeks (Feb)**: When form is very high (>+25) on Monday, the planner can't bring it to target (+5..+15) in just 5 days — even all-rest only drops ~30 points. This is a limitation, not a bug. Plan correctly suggests maximum load.
- **New sport types are auto-detected, not silently ignored**: After sync, Phase 4 scans DB for unknown `sport_type` values and prints warnings. Unknown types are saved but excluded from analytics (safe default). Add them to `SPORT_REGISTRY` in `sports.py` to enable training metrics.
- **Schema validation catches Summit activation**: Phase 4 also checks SummaryActivity/DetailedActivity JSON against `api_schema.py` field contracts. Summit fields (`suffer_score`, `perceived_exertion`) that become non-null trigger a warning: subscription may be active.
- **`_active_sports()` must handle both dicts and dataclasses**: analytics.py helper iterates `acts_by_date` which contains `ActivityMetrics` objects (from `build_acts_by_date`) — use `getattr(a, 'sport', '')`, not `a.get()`.
- **`weekly_digest(conn)` returns `Optional[WeeklyDigest]`**: `None` when no activity data, never a raw dict. `cmd_weekly` checks `if result is None` and prints `{"error": "no data"}` for backward-compatible JSON. Before May 2026 it returned a raw dict, forcing `isinstance(result, dict)` anti-pattern — eliminated.
- **DbConn adoption is complete (May 2026)**: All functions use `with DbConn() as conn:` — zero manual `get_db()/close()` remain. `get_db()` was removed entirely (May 10, 2026); `DbConn.__enter__` opens connections directly via `sqlite3.connect()`. `cli.py` no longer imports `get_db`. Early-adoption lessons: mass-converting via batch indentation scripts corrupts files; convert one function at a time with `py_compile` verification. See the corruption incident below for what NOT to do.
- **Never use batch indentation scripts on complex Python files**: A script that blindly adds 4 spaces to every line between `conn = get_db()` and `conn.close()` destroyed `strava.py` when `conn.close()` was nested inside `try/finally` at a different indentation level. The script kept indenting past the function boundary, cutting first 4 characters from every subsequent line (`def ` → ``, `class` → `s`, `# --` → `- `). Recovery required full file reconstruction. **Rule**: for indentation changes on files >100 lines, use `python3 -m py_compile` after EACH change, or use Python's `tokenize` module for safe re-indentation.
- **Architectural review references**: See `references/architecture-review-2026-05.md` for the original code quality findings. See `references/architecture-review-progress.md` for final resolution status — **83 findings across 5 review rounds are now closed** (May 10, 2026): 16 round 1 + 15 round 2 + 7 round 3 + 13 round 4 + 12 round 5. Dead code, broken imports, type inconsistencies, error handling gaps, rounding inconsistencies, sparkline bugs, streak data-source errors — all resolved. See `references/dependency-graph-2026-05.md` for full import graph and coupling metrics.
- **Sync reliability review**: See `references/sync-review-2026-05.md` — two-round expert panel review (May 20, 2026). 9 fixes applied: network retry, type validation, parameterized SQL, rate-limit headers, Retry-After, WAL checkpoint, CLI error handling, batched inserts, sync_log audit table.
- **Coach review**: See `references/coach-review-2026-05.md` — 12 recommendations from lean coaching perspective (decoupling removal, metric consolidation, simplification).
- **Sports medicine review**: See `references/sports-medicine-review-2026-05.md` — 16 recommendations from evidence-based medicine perspective (safety gaps, age adjustments, physiological assumptions).
- **Expert panel pattern**: See `references/expert-panel-pattern.md` — reusable workflow for complex multi-discipline design (used for cardiac drift, May 2026).
- **Clinical review progress**: See `references/clinical-review-progress.md` — combined status tracker for all 28 coach + sports-medicine recommendations.
- **`dc_to_dict` uses `obj.__dict__`** — removing a field from a dataclass silently drops it from JSON output. Before removing any field from a dataclass that flows into `dc_to_dict()`, use `search_files` with `target='content'` to verify zero external readers reference the field by name (e.g., `.decoupling_pct`, `.bpm_per_min`). Removing a field that's still accessed elsewhere causes `AttributeError` at runtime. This pattern was applied successfully May 10 when cleaning `EnrichedActivity` (decoupling_pct, efficiency_factor, decoupling_result) and `HrRecovery` (bpm_per_min).
- **`types.py` shadows stdlib `types`**: Our `strava_lib/types.py` has the same name as Python's standard library `types` module. When `sys.path` includes `strava_lib/` directly, `import types` resolves to our dataclass file instead of the stdlib, breaking stdlib imports (`enum` → `types.MappingProxyType` → crash). Running tests or scripts from outside the `scripts/` directory requires careful path management. Fix: always run from `scripts/` directory, or use `importlib.util.spec_from_file_location()` for test imports. See `tests/test_smoke.py` for working test import pattern.
- **Smoke tests miss CLI commands — subagent review is the safety net**: The 3 smoke tests (`test_imports`, `test_daily_report`, `test_forward_simulate`) cover module imports and pure math but do NOT exercise `cmd_weekly` or `cmd_trend`. THREE critical bugs have now slipped through smoke tests across two sessions: (1) missing `from itertools import accumulate` → `NameError` on `cmd_weekly`; (2) wrongly-indented `return` → `compute_trends()` always returns None; (3) f-string→`?` conversion without passing the parameter tuple → `sqlite3.ProgrammingError` on `cmd_weekly`. All three caught by subagent architecture review or CLI runtime testing, never by smoke tests. **Rule**: after any session that touches `analytics.py`, `trends.py`, `training.py`, or modifies SQL queries, run `python3 scripts/cli.py weekly` and `python3 scripts/cli.py trend 4` before declaring done. Smoke tests alone are NOT sufficient.
- **Multi-round subagent review workflow**: After major refactoring sessions, spawn 2-3 parallel subagents: (1) architecture review — reads every file, finds dead imports/code, signature mismatches, anti-patterns; (2) runtime verification — runs smoke tests + all CLI commands; (3) fresh-eyes review — logical errors, edge cases, misleading names/comments. Then fix findings grouped **by file** (not by severity) for efficiency. Repeat until zero issues found. **Six rounds** over three sessions found **65 issues total** (16→15→7→13→12→2). **Crucial**: architecture-only reviews miss logic bugs; always include a fresh-eyes reviewer. **Timeout workaround**: when 16-file review times out (>600s), split into two 4-file scoped reviews (math + edge cases).
- **Group multi-file fixes by file, not by severity**: When a subagent review returns issues across 5+ files, group fixes by file and fix everything in one file before moving to the next. This is faster than jumping between files for each severity level and reduces context-switching errors. The user explicitly prefers this approach: "По возможности группируем проблемы по файлам."

- **SQL IN clauses must be parameterized, not f-string interpolated (May 2026, expert panel review)**: `get_daily_trimp_history()` used f-string interpolation for the sport filter IN clause — safe with current constants, but fragile. If anyone adds a sport name with a quote character, SQL breaks. Now uses `','.join('?' * len(TRAINING_SPORTS))` with `params.extend(TRAINING_SPORTS)`. Any new dynamic IN clause must follow this pattern.

- **SQL parameterization: ? without parameter tuple = runtime crash**: When converting f-string SQL interpolation to parameterized queries, always pass the parameter tuple. A bare ? without a matching tuple causes sqlite3.ProgrammingError. Verify with python3 scripts/cli.py weekly after any SQL change. (`f"...{value}..."`) to parameterized queries (`?...`), you MUST pass the parameter tuple as the second argument to `conn.execute(sql, (value,))`. The `?` placeholder without a matching tuple causes `sqlite3.ProgrammingError: Incorrect number of bindings supplied` — the exact bug that broke `cmd_weekly` in May 2026 after a previous fix converted the f-string but forgot the tuple. If the value is a constant from Config, consider hardcoding it in the SQL string instead (e.g., `WHERE s.velocity > 0` vs `WHERE s.velocity > ?`). Either way, verify with `python3 scripts/cli.py weekly` immediately after any SQL change.

- **Banister per-step rounding must be consistent across modules**: `training.py:_sim_one_day` rounds fitness/fatigue to 1 decimal at each Banister step. `trends.py:compute_trends()` originally did NOT round — causing floating-point divergence of 0.5–2.0 form points after 500+ days. Fixed May 2026: `f = round(f + alpha * (t - f), 1)`. Any new Banister implementation MUST match this per-step rounding convention.

- **`forward_simulate` delegates to `_sim_one_day` — don't round twice**: `_sim_one_day` already returns `round(f2, 1)`. `forward_simulate` was doing `fitness=round(f, 1)` on the already-rounded value — harmless but misleading double-rounding. Removed May 2026. If modifying either function, keep the single source of rounding.

- **Streaks in `weekly_digest` must use `raw_daily`, not `acts_by_date`**: `acts_by_date` is built from `get_activity_metrics()` which JOINs streams and filters `WHERE s.heartrate IS NOT NULL`. Activities without HR data are excluded from this index, causing streaks to incorrectly break. Fixed: streak loops now use `d.isoformat() in raw_daily` (from `get_daily_trimp_history`, which includes ALL activities via LEFT JOIN).

- **`_form_sparkline`: bar[vi] overwrites zero-marker when form=0**: The sparkline sets `bar[zi] = '┃'` (zero line) then `bar[vi] = '█'` (value). When value position equals zero position, the value marker overwrites the zero marker. Fixed: `bar[vi] = '█' if vi != zi else bar[vi]` — preserves the ┃ at zero.

- **`ewma(series_dict, tau, end_date)` — guard against end < start**: When `end_date` (or `all_dates[-1]` default) is before `all_dates[0]`, the `while d <= end` loop runs forever. Added `if end < start: return {}` guard (May 2026).

- **ACWR differs between `analytics.py` and `report.py` — document it**: `analytics.py:weekly_digest` uses simple rolling average (7d sum / 28d sum). `report.py:daily_report` uses EWMA-based (ATL τ=7 / CTL τ=28). Same concept, different smoothing — values will differ. Both valid. Comment added May 2026.

- **`calc_progressive_signal` must use `startswith('↑')`, not `'↑' in`**: `trend()` returns formatted strings like `'↑+15%'`. The documented contract says callers should use `startswith('↑')`. Using `'↑' in` works with the current format but would break if the format ever added a prefix. Fixed: all three call sites now use `.startswith()`. (May 2026)
- **CC = 100/EF — double-counting in progressive signal (RESOLVED May 2026)**: Now reads `cc` directly from `EnrichedActivity.cc` (pre-computed in enrichment), eliminating the `100/EF` conversion that caused double-counting with the EF trend. Progressive signal uses CC-only signal + HRR + cardiac drift.

- **CC trends are per-sport (May 2026)**: `calc_progressive_signal()` groups CC values by sport_type. Run CC (≈64–74) and Hike CC (≈104–159) operate at different scales — mixing them creates false trends when activity mix changes. Each sport with ≥3 activities gets its own trend; bonuses are weighted by activity count. A switch from running to hiking no longer triggers a false "CC rising" alarm. Research confirms no established formula exists for cross-activity CC normalization — per-sport separation is the scientifically correct approach. See `references/cross-activity-cc-research.md`.

- **Cardiac drift trend excludes Walk (May 2026)**: `calc_progressive_signal()` filters drift to `TRAINING_SPORTS` only. Walk has the lowest drift threshold (6%) and highest count (12 of 19 activities in a typical 14-day window), creating a 386% false-positive trend. Walk drift is inherently volatile (frequent stops, variable pace) — its signal is noise for training quality assessment.

- **Cardiac drift negative values are warmup, not fatigue**: The Jenks-based drift algorithm often produces negative drift (e.g., -10%) on run activities. This is a warmup effect — HR is higher in the first 20-30 minutes (cold start, cardiac ramping) and settles lower in steady state. Negative drift should be classified as `'stable'` or `'warmup'`, never `'significant'`. Only positive drift indicates possible fatigue. See `references/cardiac-drift-expert-panel.md`.

- **Cardiac drift subsample threshold scaling**: `cardiac_drift()` subsamples to 600 points for performance (O(n²) Jenks). The `min_segment_duration` parameter is in SECONDS but `extract_contiguous_runs` counts POINTS. After 6:1 subsampling, 60 points = 360 seconds → filters out short walk segments. Fix: scale thresholds proportional to `subsample_step` (`min_dur_pts = max(2, min_segment_duration // subsample_step)`). If changing `max_points`, verify `min_dur_pts` still allows typical 1-2 minute walk segments through.

- **`trend()` arrow prefix is the stable contract**: Returns `'↑+X%'`, `'↓-X%'`, or `'→X%'`. Callers parsing direction MUST use `startswith('↑')`/`startswith('↓')` — the arrow prefix is guaranteed. Docstring documents this explicitly.

- **`trend()` near-zero clamp** (May 2026): When |avg1| < 5, percentage change is meaningless — a tiny 3pp shift crossing zero produces exaggerated signals like '↓-100%'. In this region: absolute shifts < 5pp return '→0%' (noise); larger shifts use a floor denominator of 5 to avoid division explosion. Callers are unaffected — the format stays `'↑+X%'` / `'↓-X%'` / `'→X%'`.

- **Cross-activity CC normalization — no established formula exists** (May 2026): Research confirms CC was designed by Billat (2020) exclusively for steady-state marathon running. No published method normalizes CC between walking, running, and hiking — they have different optimal speeds, metabolic cost curves, and HR-velocity relationships. Per-sport separation is the scientifically correct approach. Full synthesis: `references/cardiac-cost-cross-activity-research.md`.

- **Don't present multi-line SQL as 'one command' — wrap it in a CLI subcommand (May 2026)**: When the user needs a data query, a multi-line `cli.py sql "..."` call is a wall of text, not one command. The user will call this out. If a query is useful enough to present, wrap it in a dedicated CLI subcommand (e.g., `cli.py log` instead of a 10-line SELECT). Threshold: if the SQL wraps in a terminal window, it needs a subcommand.

- **CLI commands must have a single responsibility (May 2026)**: Don't mix operational logs with data display. `cli.py log` shows sync audit — status, counts, errors. `cli.py kudos` shows kudos data — activity name, who liked it. When the user asks for kudos, don't add kudos display to the log command. Each subcommand does one thing, named for what it returns.

## Smoke Tests (12 tests, ~280 lines)

Three integration + nine unit tests in `tests/test_smoke.py`. No dependencies beyond stdlib + our modules.

Run all 12:
```bash
cd /opt/data/skills/productivity/strava/scripts
python3 -c "
import sys, importlib.util
sys.path.insert(0, '../tests')
spec = importlib.util.spec_from_file_location('test_smoke', '../tests/test_smoke.py')
test_smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_smoke)
test_smoke.test_imports()
test_smoke.test_daily_report()
test_smoke.test_forward_simulate()
test_smoke.test_ewma()
test_smoke.test_form_zone()
test_smoke.test_trend()
test_smoke.test_sim_one_day()
test_smoke.test_decoupling_invalid()
test_smoke.test_calc_decoupling()
test_smoke.test_median_pct_change()
test_smoke.test_sports_registry()
print('ALL 12 TESTS PASSED')
"
```

| Test | Type | What it covers |
|------|------|---------------|
| `test_imports` | Integration | All 14 public symbols + Config paths |
| `test_daily_report` | Integration | Full pipeline: DB → metrics → Banister → ACWR → recommendation |
| `test_forward_simulate` | Unit | Banister 5-day forward simulation |
| `test_ewma` | Unit | Empty, single value, half-life decay, gaps |
| `test_form_zone` | Unit | All 7 zone boundaries (-30, -15, -5, 5, 15, 30, peak) |
| `test_trend` | Unit | <4 values, rising, falling, stable, zero denominator |
| `test_sim_one_day` | Unit | Single Banister step: fatigue decays faster than fitness |
| `test_decoupling_invalid` | Unit | <2 points, standing still, steady pace, variable pace |
| `test_calc_decoupling` | Unit | Positive decoupling from 120 synthetic stream rows |
| `test_median_pct_change` | Unit | Empty, odd/even median; None/zero for pct_change |
| `test_sports_registry` | Unit | is_training, is_running, eff_windows, detect_new_types |

**When to run:** After any refactoring — catches broken imports, signature mismatches, formula regressions. All 12 run in <5s.

**Why no pytest:** `types.py` naming conflict with stdlib prevents standard `python3 -m pytest` discovery. The `spec_from_file_location` pattern above works around it. If `types.py` is ever renamed, standard pytest will work.
