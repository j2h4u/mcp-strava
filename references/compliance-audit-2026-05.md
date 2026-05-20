# Compliance Audit — May 2026

Full audit of Strava analytics system against coach review (12 items) and sports medicine review (16 items). Updated after May 10 cleanup + quick fixes session.

## Coach Review (12 items)

| # | Recommendation | Status | Notes |
|---|---------------|--------|-------|
| 1 | Decoupling — remove from enrichment & recs | ✅ | Removed from EnrichedActivity (May 10). Removed from recommendation predicates (May). |
| 2 | CC-only, remove EF/bkm from output | ✅ | RollingEfficiency only median_cc/median_cc_adj (May 10). |
| 3 | Two ACWR → one EWMA | ✅ | analytics.py ACWR removed (May). |
| 4 | VO₂max remove from regular | ✅ | ACSM formula removed (May 10). |
| 5 | Progressive signal too coarse | ⚠️ | CC graded scale (3 levels) + HRR blocking added. No subjective wellbeing factor. |
| 6 | Weekly plan bruteforce → heuristic | ⚠️ | Still uses product(). NO_REST_PENALTY added. No heuristic replacement. |
| 7 | YoY remove | ✅ | YoY section deleted from weekly_digest (May 10). |
| 8 | 7 form zones → 3 | ✅ | _form_zone(): tired/normal/fresh (May). Docstring fixed (May 10). |
| 9 | 14-day trends remove | ✅ | trend_*/median_* removed from daily_report (May 10). |
| 10 | HR Recovery duplicates | ✅ | bpm_per_min removed from HrRecovery (May 10). |
| 11 | Two Banister → one | ✅ | trends.py uses calc_banister_series() from training.py (May). |
| 12 | Walk TRIMP ×0.3 magic | ✅ | Replaced with sport_filter='training' binary exclusion (May). |

## Sports Medicine Review (16 items)

| # | Recommendation | Status | Notes |
|---|---------------|--------|-------|
| 1 | Walk TRIMP not implemented | ✅ | sport_filter='training' excludes Walk from Banister (May). |
| 2 | Z5 time control | ✅ | check_z5_minutes() → safety_warnings (May). |
| 3 | Weekly plan infinite load growth | ⚠️ | NO_REST_PENALTY added. No deload concept. Positive feedback loop remains. |
| 4 | HR recovery used | ✅ | HRR in calc_progressive_signal() — blocks load_bonus when declining (May). |
| 5 | ACWR danger lowered | ✅ | ACWR_DANGER = 1.35 in constants.py (May). |
| 6 | τ_fatigue raised | ✅ | TAU_FATIGUE = 10 (May). Still at low end of recommended 10-14. |
| 7 | RHR trend monitoring | ❌ | Static HRrest=53. No weekly Samsung Health tracking. |
| 8 | Deload weeks | ❌ | Neither plan nor progressive signal has deload (every 3-4 weeks, -30-40%). |
| 9 | CC temperature correction | ❌ | No Open-Meteo API integration. [REDACTED-LOCATION] summer +30-35°C → CC inflated 15-25%. |
| 10 | VO₂max age adjustment | ✅ moot | VO₂max removed from regular analytics. |
| 11 | Intra-activity cardiac drift | ❌ | No HR first 20% vs last 20% comparison. Decoupling gap unfilled. |
| 12 | HR anomaly detection | ✅ | check_hr_anomalies() added (May 10). Flags ≥3 jumps >30 bpm/second. |
| 13 | Subjective markers | ❌ | perceived_exertion parsed but unused. No morning check-in. |
| 14 | Orthopaedic load tracking | ❌ | No 10% rule, no weekly km increase warning. |
| 15 | Z1 problem → Z0 + Z1 | ✅ | Z0 (recovery <122, ×0.5) added to Zones (May). |
| 16 | Hike safety | ⚠️ | Consecutive-hike alert + >800 TRIMP threshold added (May 10). Temp >28°C check pending. |

## Summary

- ✅ Done: 18/28
- ⚠️ Partial: 3/28 (coach #5, sportmed #3, #16)
- ❌ Remaining: 7/28 (coach #6, #10; sportmed #7, #8, #9, #11, #13, #14)

## Priority for Next Sessions

1. SportMed #9 — CC temperature correction (high impact for [REDACTED-LOCATION] summer)
2. SportMed #14 — Orthopaedic load tracking (quick, medical necessity)
3. SportMed #11 — Intra-activity cardiac drift (fills decoupling gap)
4. SportMed #3/#8 — Deload weeks (architectural, overlaps with coach #6)
5. Coach #5 — Subjective wellbeing in progressive signal
6. SportMed #7 — RHR trend monitoring
7. SportMed #13 — Subjective markers
8. Coach #6 — Weekly plan heuristic replacement
9. Coach #10 — HR Recovery guidance when absent
