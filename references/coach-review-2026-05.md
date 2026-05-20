# Lean Coach Review — May 2026

Subagent review of Strava analytics system from lean coaching perspective.

**Philosophy:** минимум метрик, максимум смысла. Тренировка — не про цифры, а про самочувствие.

## Findings Summary (12 items)

### 🔴 High Priority

1. **Decoupling — zombie metric.** Almost always N/A, but still computed in `enrich_activity()`, flows into `trend_decoupling`, and participates in `_decoupling_signal()` (report.py:235) which can downgrade recommendation to "easy" on a single spike. → Remove from enrichment and recommendation.

2. **Four efficiency metrics = cognitive noise.** CC, EF, CC_adj, bkm — four numbers about the same HR/velocity ratio. Athlete sees "CC down, EF up, bkm down" — one story told four ways. → Keep only CC, remove EF and bkm from output.

3. **Two different ACWR implementations.** analytics.py (simple rolling avg) vs report.py (EWMA-based). Different values for same metric → erodes trust. → Keep EWMA (TrainingPeaks standard), remove simple.

4. **VO₂max without lab.** ±3 ml/kg/min error when norm is 40-49 — difference between "age normal" and "excellent". → Remove from regular analytics, keep for annual retrospective with bold disclaimer.

### 🟡 Medium Priority

5. **Progressive signal too coarse.** ±15% binary. No intermediate values (±5%, ±10%). Single-factor (CC only). → Make gradual, add subjective wellbeing factor.

6. **Weekly plan — bruteforce where heuristic needed.** 4^N combos with full Banister simulation, 15 magic scoring weights. Incomprehensible to athlete. → Replace with heuristic: template week → adjust to current form.

7. **YoY comparison meaningless for aging athlete.** Compares to 364 days ago — noise from season, health, motivation, weight. → Remove from regular, keep for annual review.

8. **7 form zones — excessive.** Athlete can't feel difference between "very_fresh" and "peak". With τ_fatigue=9, form often negative → background anxiety. → Simplify to 3: tired (<-5), normal (-5..+10), fresh (>+10).

### 🟢 Low Priority

9. **14-day trends — statistical noise.** 4-6 data points for trend detection, mixed sport types. → Remove. Keep only 21-day CC trend.

10. **HR Recovery — duplicates and no guidance.** `median_rate` and `bpm_per_min` are same value. No instruction when metric absent ("no pauses → do a standing recovery test"). → Clean up, add guidance.

11. **Two Banister implementations.** trends.py has own EWMA, different from training.py. → Unify on `calc_banister()` from training.py.

12. **Walk TRIMP ×0.3 — undocumented magic.** Coefficient appears in context but no physiological justification found. → Document or replace with binary: walk ≤5km → 0, walk with HR in Z2 → full TRIMP.

## Core Principle After Cleanup

System should answer three questions only:
1. How do I feel? → Subjective athlete rating (add!)
2. Is load increasing safely? → CC trend + HR recovery
3. What to do today? → Form recommendation (3 zones) + ACWR (EWMA)

Everything else is noise distracting a 51-year-old athlete from the main thing: listen to your body, not the numbers.
