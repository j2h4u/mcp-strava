# Cross-Activity Cardiac Cost Normalization — Research Summary

**Date:** May 2026
**Trigger:** False alarm — CC trend showed +32% growth caused by activity mix change (Run→Hike), not fitness decline.

## Core Question

Can Cardiac Cost (CC = HR / velocity) be normalized to compare across different locomotion types (Run, Walk, Hike)?

## Answer: No established formula exists

CC was designed by Véronique Billat et al. (2020) specifically for **steady-state marathon running** as a cardiac drift index. It has never been validated for cross-activity comparison.

## Why Normalization Fails

### 1. Different Metabolic Cost Curves

Walking and running have fundamentally different energy cost functions (Minetti et al., 2002):
- Walking is most efficient at ~5 km/h
- Running is most efficient at ~8–12 km/h
- At the walk-run transition (~7–8 km/h), walking costs MORE energy than running
- HR reflects energy cost linearly within a given locomotion type, but the **intercept differs** between types

### 2. Trail vs Road Running Economy Differs

Sabater Pastor (2021): Elite trail runners have **worse running economy** on flat ground than road runners. Different biomechanics → different HR↔velocity transfer function.

### 3. Uphill Locomotion Doesn't Simplify It

Zimmermann et al. (2022): On steep inclines (>20%), energy cost per meter is similar between running and walking — but this is the extreme case. On typical trail grades (5–15%), the difference is substantial.

### 4. Existing Partial Approaches

| Approach | Formula | Limitation |
|---|---|---|
| Physiological Cost Index (PCI) | (HR_ex − HR_rest) / speed | Clinical rehab; doesn't normalize walk↔run |
| %HRR-based CC | %HRR / velocity | Same locomotion at 50% HRR gives CC=50 (walk) vs CC=17 (run) |
| CC_adj (elevation) | CC − 0.45 × epkm | Fixes gradient, not locomotion type |

## Our Data Confirms It

For this athlete (May 2026):
- Run CC: 60–74 (median ~68)
- Hike CC: 104–159 (median ~147)
- Ratio: 2.2× — far beyond what any adjustment can bridge

Even after elevation adjustment (coefficient 0.45), Hike CC ≈ 104 vs Run ≈ 64 — still 1.6×.

## Decision

**Per-sport CC trends.** Each sport type tracked independently with ≥3 activity minimum for valid trend. Combined bonus weighted by activity count per sport. Walk excluded from training metrics entirely (not counted as training load).

## Key References

1. Billat V et al. (2020). "Pacing Strategy Affects the Sub-Elite Marathoner's Cardiac Drift and Performance." *Frontiers in Physiology*. PMID: 32140116.
2. Minetti AE et al. (2002). "Energy cost of walking and running at extreme uphill and downhill slopes." *Journal of Applied Physiology*. PMID: 12183501.
3. Sabater Pastor F (2021). "Performance factors of prolonged running: a particular focus on running economy and fatigue." PhD thesis, Université de Lyon.
4. Zimmermann P et al. (2022). "The Energetic Costs of Uphill Locomotion in Trail Running." *Life* 12(12):2070. PMC9787284.
5. Souto Filho JM et al. (2024). "Heart rate cost as a tool for monitoring recovery between acute training sessions." *Human Movement* 25(4):44–52. DOI: 10.5114/hm/195376.
