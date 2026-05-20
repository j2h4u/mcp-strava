# Cardiac Drift Expert Panel — May 2026

Five subagents spawned to design intra-activity cardiac drift detection
for [REDACTED-NAME]'s variable-pace running pattern (walk-run interleaving).

## Panel Composition

| Role | Task |
|------|------|
| Sports Statistician | Algorithm choice: Jenks natural breaks vs KMeans. Auto-k, drift aggregation |
| Sports Doctor | Clinical thresholds for 50+, altitude correction, nocebo risk, language |
| Running Coach | Actionability per sport (run/hike/walk), example phrases in Russian |
| Data Engineer | Code integration plan: files, dataclasses, progressive signal wiring |
| Physiologist | Mechanisms of cardiac drift, altitude effects, sensor limitations |

## Key Consensus

**Algorithm:** Jenks Natural Breaks (global DP optimum, deterministic) over KMeans.
Pure Python implementation (no numpy in system python3).

**Thresholds per sport:** Run=10%, TrailRun=12%, Hike=8%, Walk=6%.
Walk is most sensitive — any drift on walk is a fatigue sentinel.

**Architecture:** Three integration points:
- `enrich_activity()` — per-activity computation
- `daily_report()` — safety_warnings for significant/severe
- `calc_progressive_signal()` — drift trend over 21 days

**Language:** NEVER show numbers. Phrases like:
- "Сердце устаёт быстрее к концу тренировок"
- "Выносливость улучшается"

**Warnings:** Samsung Health wrist sensor (±8-15 bpm on run) — drift signal
comparable to noise. No real-time alerts. Need ≥3 episodes before flagging.

## Discovered During Implementation

- **Subsampling bug:** `min_segment_duration=60` (seconds) passed directly to
  `extract_contiguous_runs` which treats it as point count. After 6:1 subsampling,
  60 points = 360 seconds → filters out all short walk segments. Fix: scale
  threshold proportional to subsample step.

- **Negative drift = warmup:** Most run activities show negative drift because
  HR is higher during warmup (first 20-30 min) then settles to steady-state.
  This is normal physiology, not fatigue. Should classify negative drift as
  "stable/warmup", not "significant".
