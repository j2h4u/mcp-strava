# Cardiac Cost: Cross-Activity Normalization Research

_For athletes, coaches, and developers: why `mcp-strava` tracks cardiac cost per sport instead of normalizing it across activity types._

**Question:** Can Cardiac Cost (CC = HR / velocity) be normalized to compare across locomotion types (Run, Walk, Hike)?
**Answer:** No. No published method normalizes CC across activities — track it per sport. Details and sources below.

**Date:** May 2026
**Context:** False alarm — CC trend showed +32% growth because a single Hike (CC=159)
was mixed with Runs (CC≈68) in the same trend window. Investigation into whether
CC can be normalized across locomotion types.

## Key Sources

### Billat et al. (2020) — Origin of Cardiac Cost
- **Definition:** CC = HR / velocity (bpm per m/s), introduced as a **cardiac drift index
  for marathon running** at constant speed.
- **Scope:** Steady-state running only. Never designed for cross-activity comparison.
- **Paper:** "Pacing Strategy Affects the Sub-Elite Marathoner's Cardiac Drift and Performance"
  (PubMed 32140116)

### Sabater Pastor (2021) — PhD Thesis
- **Finding:** Elite trail runners have **worse running economy** on flat ground than
  road runners. Different biomechanics → different HR↔velocity transfer function.
- Even within "running," economy differs by discipline.
- **Full text:** HAL theses tel-03726471

### Zimmermann et al. (2022) — Uphill Locomotion
- **Finding:** At steep inclines (>20%), energy cost per meter (Cr) is similar between
  uphill running and uphill walking (~6.9 J/kg/m). HR also not significantly different.
- BUT this only holds at extreme gradients. At typical trail grades (5–15%),
  differences are substantial.
- **Paper:** "The Energetic Costs of Uphill Locomotion in Trail Running" (PMC 9787284)

### Souto Filho et al. (2024) — Heart Rate Cost
- **HRC** = HR / speed (m/min) during submaximal constant-speed running.
- Validated as a recovery monitoring tool (sensitive to fatigue 24h post-training).
- **Still single-locomotion:** running only, constant speed.
- **Paper:** Human Movement 2024;25(4):44–52

## Why Cross-Activity Normalization Fails

### 1. Different optimal speeds
- Walking: most efficient at ~5 km/h (1.4 m/s)
- Running: most efficient at ~8-12 km/h (2.2-3.3 m/s)
- At transition speed (~7-8 km/h), walking costs MORE energy than running

### 2. Different HR-velocity slopes
- The relationship between HR and metabolic cost is linear **within** a locomotion type,
  but the intercept differs between walking and running.
- Same %HRmax at different speeds means different things for walk vs run.

### 3. Terrain/grade amplifies differences
- Minetti's energy cost formulas differ for walking vs running at the same gradient.
- Our CC_adj (elevation coefficient 0.45) only corrects for gradient, not locomotion type.

### 4. No published normalization formula exists

| Approach | Formula | Limitation |
|---|---|---|
| Physiological Cost Index (PCI) | (HR_ex − HR_rest) / speed | Clinical gait analysis; doesn't normalize walk↔run |
| %HRR-based CC | %HRR / velocity | 50% HRR at 1 m/s (walk) = 50 vs 50% HRR at 3 m/s (run) = 17 |
| CC_adj (elevation) | CC − 0.45 × epkm | Fixes gradient, not locomotion type |

## Conclusion

Per-sport CC tracking is the **only scientifically defensible approach**. No published
method normalizes Cardiac Cost between walking, running, and hiking. The literature
treats them as separate activities with different physiological determinants.

## Practical Implementation (May 2026)

- Progressive-load signal: CC grouped by sport type, ≥3 activities per sport required
- Bonuses weighted by activity count per sport
- Walk excluded from all progressive-signal metrics (not counted as training load)
- Hike CC tracked separately from Run CC

## Athlete-Specific Data

| Sport | Typical CC | Range |
|-------|-----------|-------|
| Run   | 64–74     | 60–80 |
| Walk  | 68–76     | 65–85 |
| Hike  | 104–159   | 100–160 |

Run and Walk CC overlap (both forward locomotion on flat/moderate terrain).
Hike CC is ~2× higher; even after elevation adjustment (coefficient 0.45),
Hike CC ≈ 104 vs Run ≈ 64 — still 1.6×. Terrain, rough ground, and different
biomechanics dominate.

## References

1. Billat V et al. (2020). "Pacing Strategy Affects the Sub-Elite Marathoner's Cardiac Drift and Performance." *Frontiers in Physiology*. PMID: 32140116.
2. Minetti AE et al. (2002). "Energy cost of walking and running at extreme uphill and downhill slopes." *Journal of Applied Physiology*. PMID: 12183501.
3. Sabater Pastor F (2021). "Performance factors of prolonged running: a particular focus on running economy and fatigue." PhD thesis, Université de Lyon. HAL: tel-03726471.
4. Zimmermann P et al. (2022). "The Energetic Costs of Uphill Locomotion in Trail Running." *Life* 12(12):2070. PMC9787284.
5. Souto Filho JM et al. (2024). "Heart rate cost as a tool for monitoring recovery between acute training sessions." *Human Movement* 25(4):44–52. DOI: 10.5114/hm/195376.
