# Phase 1 Research: Package Foundation & Settings

**Phase:** 01 - Package Foundation & Settings
**Researched:** 2026-05-20
**Status:** Ready for planning

## Planning Question

What needs to be true to move this repo from a `scripts/`-driven Python layout to an installable package with one typed settings surface, while preserving the local Strava mirror and keeping `just test` useful?

## Findings

### Package Layout

- Use a `src/mcp_strava/` package layout so imports no longer depend on `scripts/` being inserted into `sys.path`.
- Move the existing CLI dispatcher into `src/mcp_strava/cli.py` and expose `python -m mcp_strava` through `src/mcp_strava/__main__.py`.
- Move the current `scripts/strava_lib/*.py` modules into the package and update imports from `strava_lib.*` to `mcp_strava.*`.
- Do not preserve `scripts/cli.py` or `scripts/strava_lib` as the primary runtime path. Phase 1 context explicitly allows temporary breakage of old script commands.
- Keep the move mechanical where possible. Core/repository/adapter restructuring belongs to later phases.

### Packaging Tooling

- Add `pyproject.toml` with `requires-python = ">=3.13"` and setuptools package discovery under `src/`.
- Runtime can remain stdlib-only in Phase 1. Do not add MCP, SQLAlchemy, Alembic, Typer, or Strava adapter dependencies yet; those belong to later phases.
- Add `pytest` as a dev/test dependency in project metadata or an optional dependency group so `just test` has a normal test runner target.
- A console executable is explicitly deferred by context decision D-07. Do not add `[project.scripts]` for `mcp-strava` in Phase 1.

### Settings Boundary

- Add `src/mcp_strava/settings.py` as the one typed settings surface for development/runtime configuration.
- Keep algorithm constants in `Config`; settings should cover runtime inputs:
  - database path
  - token/env path
  - runtime profile
  - HTTP host and port
  - freshness thresholds
- Use stdlib dataclasses and `os.environ` parsing for Phase 1 simplicity. A future pydantic-settings migration can happen when external dependencies are introduced.
- Preserve `.env` compatibility as an input source, but do not make `.env` the only configuration model.
- Avoid token persistence changes in Phase 1. Existing token rewrite behavior remains a later adapter/runtime concern.

### Test Workflow

- Convert `tests/test_smoke.py` to normal pytest discovery by importing `mcp_strava.*`.
- Update `Justfile` so `just test` runs `python3 -m pytest`.
- Remove or stop relying on `scripts/run_tests.py`; the primary runner after Phase 1 is pytest.
- Preserve the existing smoke behavior: import checks, daily report path, pure training/model helpers, metric gates, analytics helpers, and sport registry behavior.
- Baseline before planning: `just test` passed with 11/11 smoke tests using the current custom runner.

### Safety Constraints

- Do not delete, move, overwrite, or recreate `data/strava.db`.
- Do not run sync, backfill, token refresh, raw Strava API calls, or any full resync as part of Phase 1.
- Do not commit `.env`, `.planning/config.json`, database files, WAL/SHM sidecars, caches, or virtual environments.
- Startup behavior that accidentally creates `data/strava.db` is a Phase 2 safety concern, but Phase 1 should not make it worse.

## Recommended Plan Split

1. Package manifest, source layout, import migration, and `python -m mcp_strava`.
2. TDD plan for typed settings parsing/defaults because it has clear input/output behavior.
3. Pytest and `just test` migration to prove the packaged code still supports baseline smoke behavior.

## Risks

| Risk | Mitigation |
|------|------------|
| Large move loses imports | Keep package move mechanical; verify import suite under pytest after the move. |
| Settings boundary mutates secret handling too early | Settings reads paths and values only; token persistence remains out of scope. |
| Pytest accidentally imports local `types.py` as stdlib `types` | Use `src/` package layout and import `mcp_strava.types`, not a top-level `types.py`. |
| Data loss during refactor | Plans must explicitly avoid all `data/` writes except existing read-only report smoke behavior. |

## Research Complete

Phase 1 can be planned without external dependency research. The work is a package/test/settings foundation over existing local code, with data safety and scope boundaries enforced by plan acceptance criteria.
