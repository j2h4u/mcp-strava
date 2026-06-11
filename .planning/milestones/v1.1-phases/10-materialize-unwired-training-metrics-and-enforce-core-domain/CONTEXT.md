# Phase 10 — Context

> Seeded 2026-05-29 from a deep investigation session. This is the gathered context
> for planning; everything below was verified against the code (not assumed).

## Why this phase exists

Two things turned out to be the same job:

1. **The last open PROJECT.md requirement** — "Separate core/domain training logic from
   SQLite, Strava HTTP, CLI formatting, and MCP transport." An assessment found 3 of 4
   concerns clean and *guard-enforced* (HTTP, MCP, CLI). The only remaining violation is
   `src/mcp_strava/metrics.py`: it is **storage-coupled** (`from mcp_strava.db import
   repository_from_connection`, fetches rows mid-computation) **and dead** (zero production
   importers).

2. **A latent product bug discovered in passing.** A whole family of training metrics is
   **registered, documented with formulas, and exposed** via `get_workout_detail` /
   `compare_periods` (see `application/metric_registry.py`) — but **never materialized**.
   `adapters/duckdb/read_model_materializer.py::_activity_fact` writes **hardcoded defaults**
   (0/None) for them. So MCP/CLI consumers get null/zero silently. Affected:
   - `hr_recovery_*` (pause_count, total_rest_sec, median/best/worst/avg_rate)
   - `vertical_speed_*` (vmh, total_ascent_m, duration_hours)
   - `cardiac_drift_*` (pct, severity, significant, quality)
   - `hrr_pct`
   - rolling: `rolling_median_hr_recovery`, `rolling_median_cardiac_drift_pct` (these will
     populate automatically once the per-activity facts are computed — `_materialize_rolling_facts`
     already SELECTs `hr_recovery_median_rate` / `cardiac_drift_pct`).

The only implementation of these formulas lives in the dead `metrics.py`. So fixing the bug
(compute them) and fixing the architecture (pure domain module) are the **same** move.

## Decision history (do not relitigate)

- Quick task **260525-jpo** ("Clean Core Metric Registry Without Losing Derived Signals",
  2026-05-25) explicitly recorded: *"If a useful registered metric is empty or duplicated,
  **fix the formula/materialization instead of deleting it**."* and listed `hr_recovery_*`
  and `cardiac_drift_*` under **Preserve And Fix**. That task only deleted true aliases
  (`atl`/`ctl` → `fatigue`/`fitness`, duplicate `z5_seconds`). **This phase completes the
  unfinished "fix the materialization" half of that decision.** Deleting these metrics is
  OFF THE TABLE.
- `decoupling` and Efficiency Factor (EF) were **deliberately removed from enrichment in
  May 2026** (see `metrics.py::enrich_activity` docstring) and are **not** in the
  registry/materializer → they are abandoned and safe to delete as dead code.
- ⚠️ An assessment subagent claimed the materializer "reimplements" these formulas — that was
  **WRONG** (verified: `_activity_fact` lines ~190–204 are defaults, not compute). Don't trust
  that claim; the formulas exist only in `metrics.py`.

## Scope

1. **`metrics.py` → pure domain module.** Extract pure functions from the current
   conn-coupled ones: `calc_hr_recovery(rows)`, `calc_vertical_speed(rows)`,
   `calc_cardiac_drift(rows, sport_type)`, and add pure `calc_hrr_pct(median_hr, hr_rest, hr_max)`.
   Remove `from mcp_strava.db import repository_from_connection`. Mirror the clean ideal in
   `src/mcp_strava/training.py` (pure functions over plain data → dataclasses).
2. **Delete abandoned dead code** from `metrics.py`: `enrich_activity`, `calc_decoupling`,
   `_decoupling_invalid`, `calc_decoupling_with_gate`, `_fetch_decoupling_rows`,
   `calc_efficiency_factor`. Verify each is unregistered + unused in `src/` before removing.
3. **Wire pure functions into `read_model_materializer.py::_activity_fact`** (~line 117–218):
   fetch rows via the repo (`stream_hr_velocity_time_rows`, `stream_altitude_rows`,
   `stream_hr_velocity_simple_rows`, `activity_median_heartrate`) and populate the ~13 real
   columns instead of defaults. **hr_max for `hrr_pct`:** recommend reusing the existing
   max-to-date `hr_max_observed` already computed in `_activity_fact` (consistent with how
   zones/TRIMP use it), rather than `metrics.py`'s old all-time `max_heartrate()`. Document the choice.
4. **Add the missing boundary guard.** Extend the `test_read_modules_do_not_import_strava_or_refresh`
   family in `tests/test_security_guards.py` to ALSO forbid `mcp_strava.db` and
   `mcp_strava.adapters.duckdb` imports from the domain modules (`training`, `hr_zones`,
   `sports`, `cardiac_drift`, `metrics`). This was the blind spot that let the leak pass green.
5. **Update/replace coupled tests:** `test_smoke.py` (enrich_activity, calc_decoupling*,
   calc_efficiency_factor, _decoupling_invalid), `test_metric_services.py` (enrich_activity ref),
   `test_security_guards.py` (enrich_activity refs ~292/490/495). Add unit tests for the new pure
   functions + a materializer test asserting the columns are populated (not defaults).
6. **Delete dead `db.py::get_daily_trimp_history`** (unused in `src/`).
7. **LIVE OPS (operator-run, not code):** after deploy, re-materialize the read model so the
   columns populate. This **changes stored values from null → computed** on the live DuckDB
   (`/opt/docker/mcp-strava/data/strava.duckdb`). Verify via MCP (`get_workout_detail`,
   `compare_periods`) that the metrics now return real values.

## Success criteria

- Domain modules (`metrics`, `training`, `hr_zones`, `sports`, `cardiac_drift`) import no
  storage/adapter — **enforced by a boundary test**.
- The materializer computes & stores the previously-empty metrics by calling the pure functions.
- Live MCP returns real, non-null values for hr_recovery / vertical_speed / cardiac_drift /
  hrr_pct and the rolling medians.
- Full suite green; **no regression** in TRIMP / zones / cardiac_cost values.
- PROJECT.md core/domain-separation requirement → Validated.

## Constraints / hazards

- **Data preservation:** re-materialization rewrites stored fact values on the live DuckDB.
  The protected read-only backup at `~/backups/mcp-strava-safe/` is the safety net — must
  remain untouched. Confirm it's intact before the live re-materialize.
- **DuckDB single-writer:** admin/materialize ops require the owner stopped or owner-driven;
  don't contend with the live owner (see prior ART-corruption incident, now resolved).
- TDD mode is on for this project — write the failing test first for the pure functions and
  the materializer population.

## Key files

| File | Role |
|------|------|
| `src/mcp_strava/metrics.py` | the dead, storage-coupled module to purify (or partly delete) |
| `src/mcp_strava/adapters/duckdb/read_model_materializer.py` | `_activity_fact` ~117–218: where defaults become real compute |
| `src/mcp_strava/application/metric_registry.py` | the registered metrics + formula descriptions |
| `src/mcp_strava/application/metric_services.py` | reads the fact columns, serves them |
| `src/mcp_strava/training.py` | the clean pure-module ideal to mirror |
| `tests/test_security_guards.py` | boundary guards (~374–388) to extend |
| `src/mcp_strava/db.py` | dead `get_daily_trimp_history` to delete |

## References

- `.planning/quick/260525-jpo-clean-metric-registry-surface-and-remove/260525-jpo-PLAN.md`
  — the preserve-and-fix decision this phase completes.
- PROJECT.md → Active requirement: "Separate core/domain training logic from SQLite, Strava
  HTTP calls, CLI formatting, and MCP transport concerns."
