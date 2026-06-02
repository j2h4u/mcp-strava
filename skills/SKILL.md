---
name: strava
description: Answer questions about the user's own Strava training history through a read-only MCP server — daily training briefs, fitness/fatigue/form and overtraining (ACWR) checks, week-over-week or arbitrary period comparisons, single-workout deep dives, forward fitness projections, and gear/shoe mileage. Use when the user asks about their running, cycling, hiking, or other training — recent workouts, load, form, freshness, trends, or questions like "am I overtraining", "how does this week compare", or "where will my fitness be".
---

# strava

Read-only access to the user's own Strava training data through a local mirror. The tools return **facts and numbers** — you turn them into insight. There is no sync, SQL, token, or admin surface, and you never trigger a refresh: the mirror updates itself on a timer.

## What you can do

- **Daily training brief** — where the user's model sits today (fitness, fatigue, form, ACWR) plus recent load. Start with `get_fitness_state`, then list recent sessions with `list_workouts`.
- **Spot overtraining or detraining** — read `form`/`form_zone` and `acwr`/`acwr_zone` from `get_fitness_state`; the zones say when load is in the sweet spot, risky, or undertrained.
- **Deep-dive one workout** — full metrics for a single session (HR zones, cardiac cost/drift, recovery, elevation, gear, kudos) via `get_workout_detail`, using an `activity_id` from `list_workouts`.
- **Compare two periods** — this week vs. last, this month vs. last year, or any two date ranges, globally or per sport, via `compare_periods` (deltas, trends, per-sport breakdown).
- **Project fitness under a plan** — where fitness/fatigue/form land by a target date under rest/easy/maintain or a custom load plan, via `project_fitness_state`.
- **Trends over time** — bucketed metrics by day/week/month/year/all-time, global or per sport, via `get_training_aggregates` (prepared bundles cover the common views).
- **Gear & shoe mileage** — gear facts come back on `get_workout_detail`; use them to flag shoes nearing replacement.

You don't need parameter schemas here — each tool is self-describing, so read its schema from the tool itself when you call it.

## Working with the results

Every tool wraps its metrics with `freshness`, `completeness`, `warnings`, and `rationale`. Before trusting a value:

- Check `completeness.status` — `partial`/`stale` means treat the answer as provisional and say so.
- Surface `warnings` (e.g. `read_model_not_current`, `workout_not_found`); never silently drop them.
- Expand abbreviations (TRIMP, ACWR, HRR, CC) on first use and explain what a number means in context.

## Hard, multi-disciplinary calls

When a question spans several disciplines at once — statistics, physiology, coaching, and data quality (e.g. "am I overtrained and should I back off before the race?") — reason as a small **expert panel** over the facts instead of from a single viewpoint: take each perspective, note where they agree and disagree, then synthesize. See [expert-panel-pattern.md](expert-panel-pattern.md) for the roster and process.

## Boundaries

- **Facts, not coaching.** The server never diagnoses, prescribes, or gives medical advice. Interpretation, narrative, and judgement are yours.
- **Read-only.** No sync, backfill, raw-Strava, SQL, token, admin, or recompute tools exist — don't ask for or invent them. Refresh is internal.
