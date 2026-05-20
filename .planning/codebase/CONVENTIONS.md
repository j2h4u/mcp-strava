# Coding Conventions

**Analysis Date:** 2026-05-20

## Naming Patterns

**Files:**
- Module files are lower-case with underscores, for example `scripts/strava_lib/constants.py`, `scripts/strava_lib/training.py`, `scripts/strava_lib/report.py`, and `tests/test_smoke.py`.
- The only top-level executable entrypoints in this repo are plain Python scripts such as `scripts/cli.py` and `scripts/run_tests.py`.

**Functions:**
- Use `snake_case` for all functions and helpers, for example `calc_banister()`, `calc_weekly_plan()`, `refresh_token()`, and `load_tests()`.
- Command handlers in `scripts/cli.py` follow the `cmd_*` prefix, for example `cmd_activities()`, `cmd_sync()`, and `cmd_report()`.
- Private helpers use a leading underscore, for example `_fetch_with_retry()`, `_form_zone()`, `_sim_one_day()`, and `_decoupling_invalid()`.

**Variables:**
- Use `snake_case` for locals and module variables, for example `daily_trimp`, `alpha_fitness`, `after_param`, and `_hr_max_cache`.
- Module-level constants use `UPPER_CASE`, for example `DB_PATH`, `ENV_PATH`, `STREAM_KEYS`, and `COMMANDS`.

**Types:**
- Use `PascalCase` for dataclasses and classes, for example `Config`, `DbConn`, `StravaActivity`, `WeeklyPlan`, and `DailyReport`.
- Type names live in `scripts/strava_lib/types.py` and are used as the shared data contract between modules.

## Code Style

**Formatting:**
- The codebase uses standard Python formatting with no repo-local formatter config detected.
- Imports are grouped by standard library first, then local `strava_lib` imports, as seen in `scripts/cli.py`, `scripts/strava_lib/report.py`, and `scripts/strava_lib/metrics.py`.
- Section dividers and docstrings are used heavily to separate CLI, model, analytics, and sync responsibilities.

**Structure:**
- Prefer small, domain-named functions over deep class hierarchies.
- Keep orchestration thin at the edge and push computation into `scripts/strava_lib/*.py`.
- Use dataclasses for structured results instead of raw dicts once data crosses a module boundary.

## Import Organization

**Order:**
1. Standard library imports.
2. Local project imports from `strava_lib`.
3. In-module imports inside functions only when needed for optional or circular dependencies.

**Path Aliases:**
- Not detected. Imports use direct package paths such as `from strava_lib.constants import Config`.

## Error Handling

**Patterns:**
- Hard failures raise `RuntimeError` with actionable messages in auth and API code, for example `scripts/strava_lib/db.py` in `refresh_token()` and `api_request()`.
- Missing or insufficient data usually returns `None` instead of throwing, especially in metric functions such as `calc_efficiency_factor()`, `calc_hr_recovery()`, and `calc_vertical_speed()`.
- CLI commands print user-facing errors to `stderr` and exit non-zero on failure, as in `scripts/cli.py` and `scripts/strava_lib/sync.py`.
- Sync code catches transient network and HTTP problems, retries, and logs failures to `sync_log` in `data/strava.db` through `scripts/strava_lib/sync.py`.

## Logging

**Framework:** `print()` to stdout/stderr.

**Patterns:**
- Command output is usually JSON on stdout.
- Progress, retries, and sync status go to stderr in `scripts/strava_lib/sync.py`.
- Success and failure indicators are text-based and intentionally minimal, for example `✓` and `✗` in `cmd_log()` in `scripts/cli.py`.

## Comments

**When to Comment:**
- Comments explain domain decisions, thresholds, and rationale, not trivial syntax.
- Section headers and inline notes are used to explain why metrics were removed, why thresholds exist, and why particular data gates are applied.
- Comments often mention the business reason for a rule, for example the steady-state requirement in `scripts/strava_lib/metrics.py` or the training-signal rationale in `scripts/strava_lib/report.py`.

**JSDoc/TSDoc:**
- Not used. Python docstrings are the primary documentation style.

## Function Design

**Size:**
- Functions are generally small and single-purpose.
- CLI handlers in `scripts/cli.py` are thin wrappers around one query or one library call.
- Core analytics functions in `scripts/strava_lib/*.py` are pure where possible and return typed records instead of mutating shared state.

**Parameters:**
- Prefer explicit positional or keyword parameters with simple data structures.
- `conn` is the standard database handle name.
- Dates are usually passed as `YYYY-MM-DD` strings or `datetime.date` objects depending on the module.

**Return Values:**
- Structured results use dataclasses from `scripts/strava_lib/types.py`.
- Optional computations return `None` when data is missing or invalid rather than sentinel numeric values.
- CLI handlers print their output instead of returning it.

## Module Design

**Exports:**
- Modules expose functions and dataclasses directly; `scripts/strava_lib/__init__.py` is empty and does not act as a barrel file.
- Shared constants live in `scripts/strava_lib/constants.py`, and shared types live in `scripts/strava_lib/types.py`.

**Barrel Files:**
- Not used.

## Practical Rules

- Keep new business logic in `scripts/strava_lib/`, not in `scripts/cli.py`.
- Keep new result shapes in `scripts/strava_lib/types.py` so downstream code stays typed and consistent.
- Keep validation gates close to the metric they protect, as in `scripts/strava_lib/metrics.py` and `scripts/strava_lib/training.py`.
- Prefer explicit, readable thresholds in `Config` over inline magic numbers.

---

*Convention analysis: 2026-05-20*
