# Phase 1 Pattern Map: Package Foundation & Settings

**Phase:** 01 - Package Foundation & Settings
**Created:** 2026-05-20

## Source Layout Patterns

### Current CLI Dispatcher

- Source: `scripts/cli.py`
- Role: command registry plus thin command handlers.
- Pattern to preserve: `COMMANDS` dictionary maps command names to `cmd_*` functions; `main()` parses `sys.argv`, dispatches, prints JSON or text, and exits non-zero for bad commands.
- Phase 1 target: move this shape to `src/mcp_strava/cli.py` and call `main()` from `src/mcp_strava/__main__.py`.

### Current Runtime Modules

- Source: `scripts/strava_lib/*.py`
- Role: current analytics, sync, DB/auth, types, sports, and schema modules.
- Pattern to preserve: small module-level functions, dataclasses in `types.py`, and direct imports between modules.
- Phase 1 target: move modules under `src/mcp_strava/` and update imports from `strava_lib.*` to `mcp_strava.*`.
- Boundary note: do not do core/repository/adapter decomposition yet; that is planned for later phases.

### Current Settings-Like Values

- Source: `scripts/strava_lib/db.py`
- Existing identifiers: `BASE_DIR`, `DB_PATH`, `ENV_PATH`, `load_env()`, `save_env()`.
- Source: `scripts/strava_lib/constants.py`
- Existing identifier: `Config` for athlete/model/metric constants.
- Phase 1 target: keep `Config` for algorithm constants; add `mcp_strava.settings.Settings` for runtime paths/profile/bind/freshness values.

## Testing Patterns

### Current Smoke Runner

- Source: `scripts/run_tests.py`
- Pattern: discovers callables named `test_*` from `tests/test_smoke.py` and prints pass/fail status.
- Phase 1 target: remove this custom discovery path from the primary workflow and let pytest discover `tests/test_smoke.py`.

### Current Smoke Tests

- Source: `tests/test_smoke.py`
- Pattern: direct function tests with plain `assert`, mostly pure helpers plus a daily-report smoke path.
- Phase 1 target: retain plain asserts and test function names, update imports to `mcp_strava.*`, and keep report smoke read-only.

### Current Just Command

- Source: `Justfile`
- Current command: `python3 scripts/run_tests.py`
- Phase 1 target: `python3 -m pytest`; aliases `tests` and `smoke` should still route to `test`.

## Files Likely Created Or Modified By Plans

| File or path | Role |
|--------------|------|
| `pyproject.toml` | Package metadata, Python requirement, package discovery, pytest config. |
| `src/mcp_strava/__init__.py` | Package marker. |
| `src/mcp_strava/__main__.py` | `python -m mcp_strava` entrypoint. |
| `src/mcp_strava/cli.py` | Moved CLI dispatcher. |
| `src/mcp_strava/settings.py` | New typed settings boundary. |
| `src/mcp_strava/*.py` | Moved runtime modules from `scripts/strava_lib/*.py`. |
| `tests/test_smoke.py` | Pytest-compatible imports and settings smoke coverage. |
| `Justfile` | `just test` invokes pytest. |
| `scripts/` | Old primary runtime path removed or left non-primary only if the executor needs a short transition. |

## Non-Targets

- `data/strava.db` and all `data/*.db*` files.
- `.env` and `.planning/config.json`.
- Strava sync/backfill, OAuth refresh redesign, database migrations, repository ports, MCP HTTP server, Docker runtime.
