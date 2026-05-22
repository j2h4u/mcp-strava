---
phase: 05-mcp-http-surface-docker-hardening
plan: 05-04
subsystem: api
tags: [mcp, http, sdk, settings, security, pytest]
requires:
  - phase: 05-01
    provides: metric registry contract
  - phase: 05-02
    provides: fitness/workout metric services
  - phase: 05-03
    provides: compare/projection metric services
provides:
  - read-only HTTP MCP surface with exact five-tool allowlist
  - pinned MCP SDK contract tests and feature probes
  - typed bind/origin settings and transport-security wiring
affects: [phase-05-mcp-surface, mcp-http-runtime, test-runtime]
tech-stack:
  added: [mcp>=1.27.1,<1.28]
  patterns: [sdk-feature-probing, strict-tool-allowlist, typed-http-security]
key-files:
  created:
    - src/mcp_strava/interfaces/__init__.py
    - src/mcp_strava/interfaces/mcp_http.py
    - tests/test_mcp_sdk_contract.py
    - tests/test_mcp_surface.py
  modified:
    - pyproject.toml
    - src/mcp_strava/settings.py
    - src/mcp_strava/application/metric_services.py
    - tests/test_settings.py
    - tests/test_security_guards.py
    - tests/test_smoke.py
    - Justfile
decisions:
  - "MCP tool surface is strictly limited to get_fitness_state, list_workouts, get_workout_detail, compare_periods, and project_fitness_state."
  - "HTTP bind/origin policy is enforced through typed settings plus FastMCP TransportSecuritySettings."
  - "Missing workout detail remains a factual unavailable response with workout_not_found warning metadata."
metrics:
  duration: "completed in-session"
  completed: 2026-05-22
requirements-completed: [MCP-01, MCP-02, MCP-03, MCP-04, TEST-03]
---

# Phase 05 Plan 04: MCP HTTP Surface Summary

Implemented the read-only FastMCP HTTP surface with five allowed metric tools, pinned SDK compatibility probes, typed transport-security settings, and full test coverage for forbidden/admin/sync exclusion.

## Task Commits

1. `c8cf1a5` — `test(05-04): add failing MCP SDK and HTTP settings contracts`
2. `c381707` — `feat(05-04): pin MCP SDK and extend typed HTTP settings`
3. `47c283d` — `test(05-04): add failing MCP HTTP surface contract coverage`
4. `1f5da1d` — `feat(05-04): add read-only MCP HTTP tool surface`
5. `9cd39be` — `fix(05-04): return workout_not_found warning for missing detail`
6. `94ac603` — `chore(05-04): run test suite via uv-managed python3`

## Verification

- `uv run python -m pytest tests/test_settings.py tests/test_mcp_sdk_contract.py -q` ✅
- `uv run python -m pytest tests/test_mcp_surface.py tests/test_metric_services.py tests/test_security_guards.py tests/test_smoke.py -q` ✅
- `just test` ✅ (155 passed)

## Deviations from Plan

### Auto-fixed Issues

1. **[Rule 3 - Blocking Issue] System python lacked `mcp` runtime for full-suite execution**
- **Found during:** Task 4 verification (`just test`)
- **Issue:** `just test` used system `python3 -m pytest` which could not import pinned `mcp` dependency.
- **Fix:** Updated `Justfile` test command to `uv run python3 -m pytest` so the managed environment resolves pinned dependencies.
- **Files modified:** `Justfile`
- **Commit:** `94ac603`

## Authentication Gates

None.

## Known Stubs

None.

## Self-Check: PASSED
