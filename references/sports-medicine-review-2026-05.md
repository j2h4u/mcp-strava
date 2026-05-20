# Sports Medicine Review — May 2026

Subagent review of Strava analytics system from evidence-based sports medicine perspective.

**Approach:** заботливый врач, фанат доказательной медицины. Каждая рекомендация имеет физиологическое обоснование. Цель — здоровье атлета, а не скорость.

Athlete: [REDACTED-NAME], 51, [REDACTED-LOCATION]. HRmax=191 (observed), HRrest=53. Karvonen zones.

## Findings Summary (16 items)

### 🔴 Critical (bugs & safety gaps)

1. **Walk TRIMP ×0.3 NOT IMPLEMENTED in code.** `get_daily_trimp_history()` returns full TRIMP without sport_type filtering. `calc_banister()` receives everything as-is. All walking feeds Fatigue at full weight. Documented, not implemented. Also: 0.3 coefficient is physiologically questionable — HR at 130 during walking = same cardiac load as running at 130. The 3.3× reduction makes no cardiological sense; it only makes orthopaedic sense.

2. **No Z5 time control.** System counts Z5 minutes for TRIMP but doesn't warn if athlete spends >5 min in Z5 (HR>177). For age [REDACTED-AGE], prolonged Z5 is a cardiological risk. → Add warning.

3. **Weekly plan optimizer rewards infinite load growth.** `score += sum(trimps) * LOAD_BONUS` — higher load plans always win. No mandatory rest days, no deload weeks. Combined with progressive signal → positive feedback loop: load grows → CC drops → load_bonus grows → load grows further. → Add mandatory rest day penalty + deload week concept.

4. **HR recovery computed but ignored.** Most reliable physiological fatigue marker — slowing HR recovery after pauses. Computed, outputs to report, but NOT used in progressive signal or recommendations. → Add HRR trend to `calc_progressive_signal()` — >15% slowing should block load_bonus.

5. **ACWR danger >1.5 — too high for 50+.** Masters athlete research: injury risk increases significantly at ACWR >1.3. → Lower to 1.4 or 1.35. Add `ACWR_DANGER_AGE50` to Config.

### 🟡 Important (should be backlogged)

6. **τ_fatigue=9 still low for 50+.** Masters athletes need 40-60% longer recovery after high intensity. Recommended: 10-14 days. → Raise to 10-12, monitor. Could make adaptive: RHR rises → tau increases.

7. **No RHR trend monitoring.** Single static HRrest=53. Weekly RHR trend of +5 bpm = early sign of overtraining, infection, or cardiac pathology. → Add weekly RHR tracking from Samsung Health.

8. **No deload weeks.** Neither weekly plan nor progressive signal has deload concept (every 3-4 weeks, -30-40% volume). Essential for masters athletes. → Add forced deload.

9. **CC not temperature-corrected.** [REDACTED-LOCATION] summer +30-35°C → cardiac drift adds 10-20 bpm → CC rises 15-25% without fitness change. System interprets as "load feels heavier" and outputs reduce/-15%. → Add temperature correction via Open-Meteo API.

10. **VO₂max without age adjustment.** ACSM formula uses no age coefficient. For age [REDACTED-AGE], systematic overestimation of 3-5 ml/kg/min. → Use age-adjusted formula or Rockport walking test.

11. **Decoupling N/A → blind spot.** Main fatigue detection metric doesn't work for this athlete. No alternative. → Add intra-activity cardiac drift: compare HR in first 20% vs last 20% of time at stable pace.

### 🟢 Desirable (quality improvements)

12. **HR anomaly detection.** Check for inter-point HR jumps >30 bpm in streams → possible arrhythmia or sensor artifact. AFib prevalence 3-5% at 50+.

13. **Subjective markers.** Strava Summit `perceived_exertion` parsed in types.py:65 but unused. Without Summit → simple morning check-in (sleep/RPE/mood).

14. **Orthopaedic load tracking.** Separate running volume tracking: 10% rule, warning at >15% weekly km increase. Running produces 2.5-3× body weight impact per step.

15. **Z1 problem.** Current Z1 (<136) includes recovery HR (90-110) at full ×1 TRIMP weight. 60-80 min daily walking at HR 90-110 = 60-80 TRIMP/day of "load" that is physiologically recovery. → Split Z1: Z0 (recovery, <122 — 50% HRR) with ×0.5, Z1 (122-136) with ×1.0.

16. **Hike safety.** Two hikes in one weekend = 1030 TRIMP over 2 days. 10-12 hours of activity. Risk: rhabdomyolysis, heat stroke ([REDACTED-LOCATION] summer +35°C), acute myocardial injury. → Alert if total >800 TRIMP and temp >28°C.

## Physiologically Incorrect Assumptions Found

- **Banister linear dose-response.** Assumes each TRIMP unit gives same additive fatigue contribution. False above lactate threshold — fatigue grows nonlinearly, especially at 50+.
- **Edwards TRIMP coefficients (1,2,3,4,5).** Arithmetic zone multipliers mask exponential physiological cost difference between Z1 and Z5. Lucia TRIMP or individualized TRIMP would be more accurate.
- **ACSM VO₂ extrapolation.** Assumes linear HR-VO₂ to HRmax — violated above ventilatory threshold. For aging athlete with high HRrest, systematic overestimation.
- **EF over entire activity.** Cardiac drift adds 5-15% to HR over 1-2 hours. Averaging over whole activity biases EF downward. Should use first stable segment.
