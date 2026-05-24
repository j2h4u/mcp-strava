---
phase: 06-full-fidelity-strava-mirror
reviewed: 2026-05-24T08:22:09Z
depth: standard
files_reviewed: 24
files_reviewed_list:
  - src/mcp_strava/adapters/sqlite/migrations.py
  - src/mcp_strava/adapters/sqlite/repository.py
  - src/mcp_strava/adapters/sqlite/schema.py
  - src/mcp_strava/application/__init__.py
  - src/mcp_strava/application/mirror_coverage.py
  - src/mcp_strava/cli.py
  - src/mcp_strava/deploy/preflight.py
  - src/mcp_strava/interfaces/mcp_http.py
  - src/mcp_strava/refresh/__init__.py
  - src/mcp_strava/refresh/_sync_ops.py
  - src/mcp_strava/refresh/checkpoints.py
  - src/mcp_strava/refresh/runtime.py
  - src/mcp_strava/types.py
  - tests/test_application_reports.py
  - tests/test_application_workouts.py
  - tests/test_cli_surface.py
  - tests/test_docker_runtime.py
  - tests/test_full_fidelity_mirror.py
  - tests/test_load_status.py
  - tests/test_mcp_surface.py
  - tests/test_refresh_runtime.py
  - tests/test_repository_boundary.py
  - tests/test_smoke.py
  - tests/test_sqlite_safety.py
findings:
  critical: 0
  warning: 2
  info: 0
  total: 2
status: issues
---

# Phase 06: Code Review Report

**Reviewed:** 2026-05-24T08:22:09Z  
**Depth:** standard  
**Files Reviewed:** 24  
**Status:** issues

## Summary

Reviewed Phase 6 source, test, and deploy changes only. Planning artifacts and `.planning/config.json` were excluded from scope. The MCP HTTP surface remains read-only and the scoped MCP tests pass, but two admin/runtime defects remain in the Phase 6 code.

## Findings

### Warning: `admin mirror-coverage` crashes on the final v4 schema

**File:** `src/mcp_strava/application/mirror_coverage.py:20`  
**ID:** `CR-06-01`

`get_mirror_coverage_service()` unconditionally queries `latlng`:

```sql
SELECT COUNT(*) FROM streams WHERE (lat IS NOT NULL AND lng IS NOT NULL) OR latlng IS NOT NULL
```

Phase 6 v4 intentionally removes `streams.latlng`, so the new admin coverage command fails on the final schema that this phase creates. Reproduction against a temp migrated fixture returns `OperationalError: no such column: latlng`.

Fix direction: make GPS coverage version-aware by inspecting `PRAGMA table_info(streams)` before building the query, and add coverage for `admin mirror-coverage --db <v4.db> --json`.

### Warning: `admin backfill-streams --dry-run --db` requires Strava credentials before local estimation

**File:** `src/mcp_strava/cli.py:532`  
**ID:** `CR-06-02`

`cmd_backfill_streams()` calls `build_refresh_collaborators()` before it opens the selected database or checks `dry_run`. That function requires `STRAVA_CLIENT_ID` and `STRAVA_CLIENT_SECRET`, so a local dry-run estimate against a copied database fails before doing any local-only work. Reproduction with an empty temp project root returns `RuntimeError: Missing Strava client settings`.

This conflicts with the Phase 6 dry-run contract: estimating remaining stream-channel work should not require a Strava transport or token setup.

Fix direction: defer transport construction until non-dry-run execution, or use a dry-run path that opens the repo and calls the estimation logic without building Strava collaborators. Add a CLI regression test with no token file/env.

## Verification

- `uv run python -m pytest tests/test_full_fidelity_mirror.py tests/test_cli_surface.py tests/test_mcp_surface.py tests/test_refresh_runtime.py tests/test_repository_boundary.py tests/test_docker_runtime.py -q` -> 79 passed.
- Temp v4 coverage reproduction -> `OperationalError: no such column: latlng`.
- Temp dry-run/no-token reproduction -> `RuntimeError: Missing Strava client settings: STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET`.
- `just test` was not run during review because it starts Docker Compose with `/opt/docker/mcp-strava:/runtime`, and the review constraint says not to mutate live runtime data.

## MCP Boundary

No MCP surface violation found in the reviewed Phase 6 changes. `src/mcp_strava/interfaces/mcp_http.py` still exposes only:

- `get_fitness_state`
- `list_workouts`
- `get_workout_detail`
- `compare_periods`
- `project_fitness_state`

The scoped MCP tests passed and no sync/admin/debug/raw/SQL/backfill/status tool was exposed.

---

_Reviewed: 2026-05-24T08:22:09Z_  
_Reviewer: Codex inline reviewer for `gsd-code-reviewer` workflow_  
_Depth: standard_
