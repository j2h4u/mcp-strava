# Phase 1: Package Foundation & Settings - Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 establishes the development foundation for the refactor: an installable Python package, a typed settings boundary, and a pytest/pyproject test workflow. It does not need to keep the old `scripts/` execution path operational while the refactor is in progress.

This phase must not implement SQLite migration safety, Strava adapter isolation, MCP tools, background refresh, or Docker runtime behavior. Those are later phases. The only persistent data rule that applies now is: do not delete or overwrite `data/strava.db`.

</domain>

<decisions>
## Implementation Decisions

### Code Move Strategy
- **D-01:** Move existing runtime code into the package layout immediately. Do not spend Phase 1 preserving the old `scripts/strava_lib` path as the primary runtime path.
- **D-02:** Intermediate product operability is not required during this refactor phase; optimize for clean development sequencing.

### Settings Boundary
- **D-03:** Introduce a typed settings layer with separate configuration for database path, token path, runtime profile, HTTP bind settings, and freshness thresholds.
- **D-04:** Existing `.env` compatibility may be used as an input source, but the target boundary should not treat `.env` as the only settings model.
- **D-05:** `.planning/config.json` is intentionally ignored and must not be committed; it can contain local API keys or tokens.

### Package Entrypoint
- **D-06:** A module entrypoint is sufficient for Phase 1: `python -m mcp_strava`.
- **D-07:** A dedicated `mcp-strava` console executable can wait until later CLI/API surface decisions are made.

### Test Workflow
- **D-08:** Move directly to a normal `pytest` + `pyproject.toml` workflow.
- **D-09:** `just test` remains the developer-facing command, but it should call the new pytest workflow rather than preserving `scripts/run_tests.py` as the primary test runner.

### Agent Discretion
- Planner may decide the exact package manager/tooling details, provided the result is simple, local-first, and compatible with Python 3.13.
- Planner may decide whether old files remain temporarily as shims during the code move, but shims are not required for compatibility.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope
- `.planning/PROJECT.md` — core value, constraints, and decisions for the Strava mirror refactor.
- `.planning/REQUIREMENTS.md` — v1 requirements; Phase 1 maps to `FOUND-01`, `FOUND-02`, and `FOUND-03`.
- `.planning/ROADMAP.md` — phase boundary and success criteria for Phase 1.
- `.planning/STATE.md` — current workflow position: Phase 1 ready to plan.

### Codebase Maps
- `.planning/codebase/STACK.md` — current Python 3.13, stdlib-only, no package manifest state.
- `.planning/codebase/STRUCTURE.md` — current `scripts/`, `tests/`, `references/`, `data/` layout and key file locations.
- `.planning/codebase/TESTING.md` — current custom smoke runner and test coverage shape.

### Research
- `.planning/research/SUMMARY.md` — recommended high-level phase ordering and stack implications.
- `.planning/research/STACK.md` — package/tooling and MCP stack recommendations, useful for planner tradeoffs.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/strava_lib/` — existing modules to move or adapt into the new package layout.
- `scripts/cli.py` — current command registry and entrypoint shape; useful for identifying runtime capabilities but not a compatibility contract.
- `scripts/run_tests.py` and `tests/test_smoke.py` — current smoke suite; use as migration source for pytest tests.
- `Justfile` — current developer command surface; should continue to expose `just test`.

### Established Patterns
- Runtime code currently assumes `scripts/` is on `sys.path`; Phase 1 should remove that path hack by creating a real package.
- Test discovery currently happens through a custom importlib runner; Phase 1 should replace this with pytest discovery.
- Configuration currently mixes `.env`, constants, and module-level path globals; Phase 1 should centralize settings without yet solving token persistence or database migrations.

### Integration Points
- `data/strava.db` is runtime state and must be preserved. Do not move, rewrite, delete, or recreate it in Phase 1.
- `.env` is ignored and stores Strava credentials; do not commit or expose it.
- `.planning/config.json` is ignored and must stay out of commits.
- Source files (`scripts/`, `tests/`, `references/`, `Justfile`, `.gitignore`, `SKILL.md`) are currently untracked in git. Planning/execution should account for this baseline before large file moves.

</code_context>

<specifics>
## Specific Ideas

- User explicitly chose development efficiency over keeping the product operational during the refactor.
- User explicitly approved a direct move to package layout and pytest instead of gradual compatibility preservation.
- User explicitly said preserving exact old CLI command names and JSON formats is not important.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 1 scope.

</deferred>

---

*Phase: 1-Package Foundation & Settings*
*Context gathered: 2026-05-20*
