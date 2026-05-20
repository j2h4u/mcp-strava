# Cardiac Cost: Cross-Activity Normalization Research

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
- **PCI (Physiological Cost Index)** = (HR_exercise − HR_rest) / speed — used in clinical
  gait analysis, but still doesn't normalize walk vs run.
- **%HRR-based CC** = %HRR / velocity — partially normalizes for HR range, but still
  gives different scales: 50% HRR at 1 m/s (walk) = 50, 50% HRR at 3 m/s (run) = 17.

## Conclusion

Per-sport CC tracking is the **only scientifically defensible approach**. No published
method normalizes Cardiac Cost between walking, running, and hiking. The literature
treats them as separate activities with different physiological determinants.

## Practical Implementation (May 2026)

- `calc_progressive_signal()`: CC grouped by `sport_type`, ≥3 activities per sport required
- Bonuses weighted by activity count per sport
- Walk excluded from all progressive signal metrics (is_training=False)
- Hike CC tracked separately from Run CC

## Athlete-Specific Data

| Sport | Typical CC | Range |
|-------|-----------|-------|
| Run   | 64–74     | 60–80 |
| Walk  | 68–76     | 65–85 |
| Hike  | 104–159   | 100–160 |

Run and Walk CC overlap (both forward locomotion on flat/moderate terrain).
Hike CC is 2× higher even after elevation adjustment — terrain, rough ground,
and different biomechanics dominate.
