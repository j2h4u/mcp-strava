# Cardiac Drift: Steady-State Requirement

## Definition (unanimous across all sources)

Cardiac drift (cardiovascular drift, decoupling, Pa:HR) is defined as an **increase in heart rate during prolonged exercise at constant intensity/pace**. All authoritative sources agree on the steady-state prerequisite:

| Source | Definition |
|---|---|
| Wikipedia | «during steady-state exercise … without an increase in workload» |
| Uphill Athlete | «maintain absolutely constant pace and incline» |
| Marathon Handbook | «even though the intensity of exercise has remained constant» |
| Runners Connect | «with little or no change in pace» |
| Polar Blog | «upward drift of heart rate over time, coupled with a progressive decline in stroke volume and the continued maintenance of cardiac output» |
| Runlovers | «after about 15-20 minutes of continuous exercise at constant intensity» |

**Formula:** `Decoupling = (HR₂/pace₂) / (HR₁/pace₁) − 1` — assumes `pace₁ ≈ pace₂`. When pace changes structurally, the formula measures pace change, not cardiac drift.

## Physiological Mechanism

1. Rising core body temperature → blood shunted to skin for cooling
2. Dehydration → reduced plasma volume → lower stroke volume
3. Heart rate rises to compensate, maintaining cardiac output
4. **This only happens when workload is constant.** If you slow down, HR drops — that's not drift, it's pacing.

## This Athlete's Data (May 2026)

Empirical CV of velocity for recent activities:

### Runs (all "Night Run", ~5-6 km)
| Activity | CV | vel₁ (km/h) | vel₂ (km/h) | Decoupling |
|---|---|---|---|---|
| 18430206018 | 34.0% | 6.4 | 5.3 | +1.9% |
| 18417222349 | 49.7% | 6.9 | 4.5 | +32.3% |
| 18404324814 | 34.6% | 6.2 | 5.6 | +2.4% |
| 18404316927 | 39.3% | 7.0 | 6.5 | +8.5% |
| 18376180263 | 32.2% | 6.9 | 6.1 | +4.7% |
| 18255614810 | 38.9% | 7.0 | 5.4 | +19.3% |
| 18217015490 | 37.5% | 6.9 | 6.2 | +0.1% |

**Pattern:** The athlete runs hard for ~2/3, then walks the last ~1/3. Velocity drops from ~7→~5.5 km/h between halves. CV range: 32-50%. **All exceed 25% threshold.**

### Hikes
| Activity | CV | vel₁ (km/h) | vel₂ (km/h) | Decoupling |
|---|---|---|---|---|
| Morning Hike (11.1km) | 31.5% | 3.6 | 3.6 | -0.9% |
| T1 (16.3km) | 51.2% | 3.0 | 5.2 | -39.7% |
| T1 TrailRun (13.8km) | 47.8% | 3.6 | 5.3 | -32.3% |
| Relaxing hike to T1 | 45.7% | 2.8 | 4.0 | -28.5% |
| Big [REDACTED-LOCATION] Lake | 42.2% | 3.0 | 4.2 | -27.2% |
| Алешкин мост | 38.1% | 2.8 | 3.3 | -17.1% |
| Кумбель (22.1km) | 37.8% | 3.0 | 3.6 | -20.0% |
| Мынжылкы TrailRun | 41.4% | 3.8 | 5.7 | -36.8% |

**Pattern:** Ascent (slow) vs descent (fast) creates structural pace change. CV range: 31-51%. **All exceed 25% threshold.** Decoupling is consistently negative (HR lower in second half because descent is easier).

## Threshold Selection

**Chosen: `Config.Thresholds.PACE_CV_MAX = 0.25` (25%)**

Rationale:
- Normal steady run on varied terrain: CV 5-12%
- Normal hike with terrain variation: CV 10-18%
- Run with walking cooldown (5 min walk at end of 30 min run): CV ~20%
- Run 2/3 + walk 1/3 (this athlete's pattern): CV ~27%
- Hike with significant ascent/descent: CV 31-51%

25% is the sweet spot: generous enough to allow normal terrain variation, strict enough to catch structural pace changes. At this threshold, **all of this athlete's current activities are excluded from decoupling** — the metric is effectively N/A for this training style.

## Gating Logic

Decoupling is computed only when pace is steady enough for the metric to be valid:

1. First test pace variability (coefficient of variation of velocity).
2. If CV exceeds the threshold, the activity is gated out — decoupling is reported as **N/A**: explicitly invalid, not zero and not "missing data".
3. Otherwise compute decoupling normally.

Downstream consumers (trend and recommendation logic) skip N/A values rather than treating them as zero.

## Agent Narrative Rule

When decoupling is N/A (pace too variable), do NOT say «нет данных» or «не удалось посчитать». The metric is not missing — it's deliberately excluded because it's invalid for this activity pattern. Focus narrative on CC, EF, Banister, and ACWR instead.
