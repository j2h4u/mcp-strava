# Clinical Review Progress — Coach + Sports Medicine

Combined status of all 28 recommendations (12 coach + 16 sports-medicine).
Last audit: May 10, 2026.

## Coach Review (12 items)

| # | Finding | Status | Resolution |
|---|---------|--------|------------|
| 1 | Decoupling — zombie metric, remove from enrichment & recommendation | ✅ Done | Removed from recommendation (May 2026 predicates). 14d trends removed May 10. **May 10: removed from enrichment** — `decoupling_pct`/`decoupling_result`/`efficiency_factor` fields deleted from `EnrichedActivity`, computation removed from `enrich_activity()`. `calc_decoupling_with_gate` kept (public API). |
| 2 | Four efficiency metrics → CC-only | ✅ Done | `median_bkm`/`median_ef` removed from `RollingEfficiency` (May 10). `get_activity_metrics()` no longer computes bkm/EF. |
| 3 | Two ACWR → one EWMA | ✅ Done | Rolling-avg ACWR removed from `analytics.py` (May 2026). Only EWMA in `report.py`. |
| 4 | VO₂max without lab → remove | ✅ Done | VO2max removed from `RollingEfficiency`, trends, `get_activity_metrics()` (May 10). |
| 5 | Progressive signal too coarse → graded + subjective | ✅ Partial | CC trend now graded (±5/±10/±15%, May 2026). HRR blocks positive bonus. **Missing: subjective wellbeing factor.** |
| 6 | Weekly plan bruteforce → heuristic | ✅ Partial | `NO_REST_PENALTY` added (May 2026). Still 4^N brute-force. **Missing: heuristic replacement, deload weeks.** |
| 7 | YoY meaningless → remove | ✅ Done | Entire YoY section deleted from `weekly_digest()` (May 10). |
| 8 | 7 form zones → 3 | ✅ Done | `_form_zone()`: tired (<-5), normal (-5..10), fresh (>+10). `_form_zone_short()`: 🟠/🟢/🔵. Docstring fixed May 10. |
| 9 | 14-day trends → remove | ✅ Done | `trend_*`/`median_*` (decoupling/EF/HRR/vertical_speed) removed from `daily_report()` (May 10). |
| 10 | HR Recovery duplicates + no guidance | ✅ Done | `bpm_per_min` removed from `HrRecovery` (May 10). Only `median_rate` remains. Guidance on absent metric still missing but low priority. |
| 11 | Two Banister → one | ✅ Done | `trends.py` uses `calc_banister_series()` from `training.py` (May 2026). |
| 12 | Walk TRIMP ×0.3 undocumented → binary | ✅ Done | Replaced with `sport_filter='training'` in `get_daily_trimp_history()` — clean exclusion (May 2026). |

## Sports Medicine Review (16 items)

| # | Finding | Status | Resolution |
|---|---------|--------|------------|
| 1 | Walk TRIMP ×0.3 not in code | ✅ Done | `sport_filter='training'` excludes Walk from Banister (May 2026). |
| 2 | No Z5 time control | ✅ Done | `check_z5_minutes()` → `safety_warnings` in `daily_report()` (May 2026). |
| 3 | Weekly plan infinite load growth | ✅ Partial | `NO_REST_PENALTY=25` added. **Missing: deload weeks, mandatory rest beyond scoring penalty.** |
| 4 | HR recovery computed but ignored | ✅ Done | HRR added to `calc_progressive_signal()` — blocks positive `load_bonus` when declining (May 2026). |
| 5 | ACWR danger >1.5 too high for 50+ | ✅ Done | `ACWR_DANGER = 1.35` in `constants.py`. |
| 6 | τ_fatigue=9 still low → 10-14 | ✅ Done | `TAU_FATIGUE = 10` in `constants.py`. At lower end of 10-14 range. |
| 7 | No RHR trend monitoring | ❌ Not done | Static HRrest=53. Needs Samsung Health weekly tracking. |
| 8 | No deload weeks | ❌ Not done | Neither weekly plan nor progressive signal has deload concept (every 3-4 weeks, -30-40%). |
| 9 | CC not temperature-corrected | ❌ Not done | Needs Open-Meteo API integration. [REDACTED-LOCATION] summer +30-35°C → CC inflated 15-25%. |
| 10 | VO₂max without age adjustment | ✅ Moot | VO₂max removed from regular analytics (May 10). |
| 11 | Decoupling N/A → blind spot | ❌ Not done | No intra-activity cardiac drift alternative (HR first 20% vs last 20%). |
| 12 | HR anomaly detection (>30 bpm jumps) | ❌ Not done | No inter-point HR jump checks. |
| 13 | Subjective markers (sleep/RPE/mood) | ❌ Not done | `perceived_exertion` parsed but unused. |
| 14 | Orthopaedic load tracking (10% rule) | ❌ Not done | No weekly km increase tracking. |
| 15 | Z1 problem → Z0 + Z1 split | ✅ Done | `BOUNDS=[122,136,...]`, `COEFF=[0.5,1,...]` — Z0 at 0.5×. |
| 16 | Hike safety — two hikes + heat | ✅ Partial | Consecutive-hike alert with >800 TRIMP threshold added (May 10). **Missing: temperature >28°C check (needs Open-Meteo API).** |

## Summary

| Priority | Done | Partial | Not Done | Total |
|----------|------|---------|----------|-------|
| 🔴 Critical (coach) | 4 | 0 | 0 | 4 |
| 🔴 Critical (sports-med) | 5 | 0 | 0 | 5 |
| 🟡 Medium (coach) | 3 | 1 | 0 | 4 |
| 🟡 Important (sports-med) | 1 | 0 | 5 | 6 |
| 🟢 Low (coach) | 4 | 0 | 0 | 4 |
| 🟢 Desirable (sports-med) | 1 | 1 | 3 | 5 |

**Total: 18 done, 2 partial, 8 not done = 28**

## Remaining Work (prioritized)

1. 🟡 SportMed #3/#8 — Deload weeks + mandatory rest (same solution area)
2. 🟡 SportMed #9 — Temperature correction via Open-Meteo
3. 🟡 Coach #5 — Subjective wellbeing factor in progressive signal
4. 🟢 SportMed #11 — Intra-activity cardiac drift
5. 🟢 SportMed #12 — HR anomaly detection
6. 🟢 SportMed #13 — Subjective markers (morning check-in)
7. 🟢 SportMed #14 — Orthopaedic load tracking
8. 🟢 SportMed #7 — RHR trend monitoring
9. 🟢 SportMed #16 — Temperature >28°C in hike alert
