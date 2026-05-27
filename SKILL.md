---
name: strava
description: Read-only training-analytics MCP tools over a local Strava mirror — workouts, current fitness state, period comparison, fitness projection, and bucketed training aggregates. Returns numbers and facts; you do the interpretation.
version: 2.0.0
metadata:
  hermes:
    tags: [strava, fitness, running, training-analytics, mcp]
---

# strava

`mcp-strava` is a local Strava mirror exposed as a **read-only MCP server**. It answers
factual training questions — what you trained, how much load you carried, where your
fitness model sits, how two periods differ, and where a chosen plan would take you.

**The one rule:** ask training questions and read back the facts. The surface is
read-only and factual — it returns numbers, never coaching. Interpretation,
narrative, and any judgement are the calling agent's job. Mirror refresh and
freshness are handled internally on a timer; you never trigger a sync.

All six tools return the same envelope (see [Response envelope](#response-envelope)).
Dates are ISO `YYYY-MM-DD`. `sport`/`sport_type` filters use Strava sport names
(e.g. `Run`, `Ride`, `Hike`).

## Tools

### `get_fitness_state`
Answers: *where is my fitness model right now?* No parameters.
`data` is a flat metric map: model state (`fitness`, `fatigue`, `form`, `form_zone`,
`acwr`, `acwr_zone`) plus rolling-window facts (e.g. `weekly_trimp`, `daily_avg_trimp_7d/28d/90d`,
`active_days`, `rest_days`, `volume_7d/28d`, rolling medians for cardiac cost / HR recovery / drift).

### `list_workouts`
Answers: *what workouts happened, with volume and intensity?*
Params: `limit` (1–200, default 20), `start_date`, `end_date`, `sport` (all optional).
`data` is a list of compact rows: `activity_id`, `activity_date`, `sport_type`, `activity_name`,
`distance_km`, `moving_time_min`, `elevation_m`, `trimp`, `avg_hr`, `max_hr`, `kudos_count`,
and per-row `completeness`. Use the `activity_id` to drill in with `get_workout_detail`.

### `get_workout_detail`
Answers: *full metrics for one workout.*
Params: `workout_id` (int activity id).
`data` is the full activity payload: everything from the list rows plus HR-zone minutes,
HR-recovery metrics, vertical-speed/ascent, cardiac cost (raw + adjusted), cardiac drift
(`pct`, `severity`, `significant`, `quality`), `hrr_pct`, anomaly count, gear (`gear_id`,
`gear_name`, `gear_distance_km`, `gear_primary`), and `kudos_names`. Returns `data: null`
with a `workout_not_found` warning if the id is unknown.

### `compare_periods`
Answers: *how does period A differ from period B?*
Params: `period_a_start`, `period_a_end`, `period_b_start`, `period_b_end` (required),
`sport` (optional). End dates are exclusive.
`data` has `periods`, a `global` section, and a `per_sport` section. Each metric carries
both periods' values plus `delta`, `delta_pct`, `trend_direction` (`up`/`down`/`flat`/`unavailable`),
`sample_size`, `coverage`, and `missing_reasons`. Distribution metrics report `bucket_deltas`
and `distribution_overlap_pct` instead of a scalar delta.

### `project_fitness_state`
Answers: *where would my fitness/fatigue/form land under a given plan by a target date?*
Params: `target_date` (today..+90 days), `scenarios` (list from `rest`, `easy`, `maintain`,
`custom`), `custom_daily_trimp` (required only for the `custom` scenario — list of
`{date, trimp}` rows within today..target, monotonic, unique).
`data` is `{target_date, scenarios}`; each scenario gives `daily_rows`
(`projected_daily_trimp/fitness/fatigue/form` per day), `target_date_form`,
`model_assumptions`, and `post_weekend_monday_form` when the target is a weekend.

### `get_training_aggregates`
Answers: *bucketed training metrics over a window.*
Params: `end_date` (exclusive) and `bucket` (required); plus `start_date`, `metric_ids`,
`metric_bundle`, `scope` (`global` default, or `per_sport`), `sports` (at most one),
`include_empty_buckets`, `as_of_day`, `window_days`.
`data` has `request`, the resolved `metrics` list, and `rows` (one per bucket × metric:
value or distribution, `completeness_status`, `missing_reasons`, `sample_size`,
`activity_count`, bucket bounds). A `bundle` block is added when `metric_bundle` is set.

## Response envelope

Every tool returns `data` wrapped with factual metadata:

- `data` — the result (shape per tool above).
- `freshness` — how current the underlying mirror is.
- `completeness` — `status` (`complete` / `partial` / `stale` / `unavailable`),
  a `missing` reason list, and `coverage` (incl. read-model status).
- `warnings` — structured items (e.g. partial coverage, `read_model_not_current`,
  `workout_not_found`). Surface these; do not silently ignore them.
- `rationale` — short codes explaining how the numbers were derived.

Always check `completeness.status` and `warnings` before trusting a value.
`partial`/`stale` means treat results as provisional and say so.

## Boundaries

- **Read-only and factual.** No sync, backfill, raw-Strava, SQL, token, admin, or
  recompute tools exist — do not ask for or invent them. Refresh is internal.
- **No interpretation.** The service returns numbers and facts; it does not coach,
  diagnose, or give medical advice. Reasoning and narrative are the agent's job —
  expand abbreviations on first use and explain what numbers mean in context.
