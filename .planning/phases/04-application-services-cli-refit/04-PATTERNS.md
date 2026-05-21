# Phase 4: Application Services & CLI Refit - Patterns

**Generated:** 2026-05-21

## Target Files And Closest Analogs

| Target | Role | Closest Analog | Pattern To Reuse |
|--------|------|----------------|------------------|
| `src/mcp_strava/application/__init__.py` | Product service package | `src/mcp_strava/adapters/strava/__init__.py`, `src/mcp_strava/refresh/__init__.py` | Re-export explicit public service functions/classes. |
| `src/mcp_strava/application/freshness.py` | Freshness metadata and first-use signal | `src/mcp_strava/refresh/freshness.py` | Keep pure state evaluation separate from side-effecting enqueue helper. |
| `src/mcp_strava/application/reports.py` | Daily/weekly service use cases | `src/mcp_strava/report.py`, `src/mcp_strava/analytics.py` | Wrap existing domain functions without changing formulas. |
| `src/mcp_strava/application/workouts.py` | Recent and per-workout service use cases | `src/mcp_strava/metrics.py::enrich_activity`, `SQLiteRepository.recent_activities()` | Convert repository rows to existing enriched dataclasses. |
| `src/mcp_strava/application/registry.py` | Product-only service registry for future MCP | `src/mcp_strava/cli.py::COMMANDS` | Registry as explicit allowlist, but never include admin/debug commands. |
| `src/mcp_strava/types.py` | Shared dataclass contracts | Existing `DailyReport`, `WeeklyDigest`, `EnrichedActivity` | Add dataclasses rather than raw dict leakage across module boundaries. |
| `src/mcp_strava/cli.py` | Thin CLI renderer and admin/product split | Existing `cmd_*` handlers | Keep dispatch simple; move calculations into services. |
| `tests/test_application_services.py` | Service contract tests | `tests/test_refresh_runtime.py`, `tests/test_load_status.py` | Use fixture DBs, fake clocks, no live network. |
| `tests/test_cli_surface.py` | CLI behavior tests | `tests/test_security_guards.py` | Inspect command registry and monkeypatch service calls. |
| `docs/cli.md` | Replacement mapping | No current docs | Short, factual command map; no long narrative. |

## Existing Metric Surface To Preserve

`EnrichedActivity` currently exposes:

- `id`, `date`, `name`, `sport_type`
- `distance_km`, `moving_time_min`, `elapsed_time_min`, `elevation_m`
- `trimp`, `avg_hr`, `max_hr`
- `zone_minutes`
- `hr_recovery`
- `vertical_speed`
- `cc`
- `cardiac_drift`
- `hrr_pct`
- `start_time`

Phase 4 workout analytics should expose these fields plus factual completeness/availability metadata. Do not add similar-workout comparison unless it is already present.

## Guardrail Patterns

- AST guard style: use the helper approach in `tests/test_security_guards.py` to reject forbidden imports.
- Hermetic DB style: copy or create SQLite fixtures in `tmp_path`; do not mutate `data/strava.db`.
- No-live-network style: product service tests should monkeypatch `urllib.request.urlopen` to fail if any hidden Strava path is reached.
- CLI monkeypatch style: replace service calls with fake envelopes and assert rendering/dispatch behavior.

## Source-Of-Truth Decisions

- `04-CONTEXT.md` D-01..D-20 are binding for all plans.
- Product services are read/use-case boundaries.
- Product services may create local refresh requests; they do not run refresh runtime or Strava transport.
- Product service registry is the future MCP allowlist.
- CLI product commands support human-readable default and `--json`.
- Admin/debug commands stay separate from product services.

