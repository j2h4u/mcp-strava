---
phase: 07-materialized-metrics-read-model
plan: 07-05
subsystem: api
tags: [mcp, read-model, sqlite, services, pytest]
requires:
  - phase: 07-materialized-metrics-read-model
    plan: 07-04
    provides: runtime materialization wiring below MCP
provides:
  - read-model repository query methods for MCP service needs
  - fact-only MCP metric services with no request-time raw recompute
  - read-model metadata carried in service completeness coverage
  - pre-v5 runtime fail-soft behavior for absent read-model schema
affects: [phase-07-06, mcp-surface, read-model-performance, docker-runtime]
tech-stack:
  added: []
  patterns: [read-model-only-mcp, fail-soft-pre-v5, half-open-fact-queries]
key-files:
  created:
    - tests/test_read_model_queries.py
  modified:
    - src/mcp_strava/types.py
    - src/mcp_strava/adapters/sqlite/repository.py
    - src/mcp_strava/application/metric_services.py
    - tests/test_metric_services.py
    - tests/test_mcp_surface.py
    - tests/test_security_guards.py
key-decisions:
  - "MCP read-model metadata is carried in `completeness.coverage.read_model` to preserve the existing ServiceEnvelope top-level shape."
  - "Pre-v5 runtime databases return unavailable read-model metadata instead of MCP errors."
patterns-established:
  - "MCP service functions assemble payloads from materialized facts and registry metadata only."
  - "Read-model repository methods use parameterized SQL and half-open date ranges for hot fact reads."
  - "Absent read-model schema is represented as unavailable metadata while the runtime DB is still pre-v5."
requirements-completed: [READMODEL-01, READMODEL-04, TEST-06]
duration: 45min
completed: 2026-05-24
---

# Phase 7 Plan 5: MCP Service Read-Model Cutover Summary

**MCP metric services now read materialized facts instead of recomputing from raw mirror data**

## Performance

- **Duration:** 45 min
- **Started:** 2026-05-24T18:00:00+05:00
- **Completed:** 2026-05-24T18:45:00+05:00
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Added RED coverage for read-model query methods, all five MCP service functions, service-envelope metadata, and static guards against request-time recompute.
- Added `ReadModelMetadata` and SQLite repository methods for activity facts, daily load facts, training model facts, rolling period facts, workout detail facts, and read-model status.
- Reworked `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, and `project_fitness_state` service paths to assemble responses from materialized read-model facts.
- Preserved separate mirror freshness and read-model status by placing read-model metadata in `completeness.coverage.read_model`.
- Added a pre-v5 fail-soft path so Docker/runtime databases without read-model tables return unavailable metadata rather than MCP tool errors.

## Task Commits

1. **Task 1: Add read-model-only MCP service contract tests** - `6c46737` (`test`)
2. **Task 2: Serve MCP metrics from read-model facts** - `65f840d` (`feat`)
3. **Fix: Return unavailable when read-model schema is absent** - `dc3a5f5` (`fix`)

## Verification

- `uv run pytest -q tests/test_read_model_queries.py tests/test_metric_services.py tests/test_mcp_surface.py tests/test_security_guards.py` - passed, 40 tests
- `uv run pytest -q tests/test_mcp_test_client.py` - passed, 5 tests
- `uv run python -m compileall -q src/mcp_strava/application/metric_services.py src/mcp_strava/adapters/sqlite/repository.py src/mcp_strava/types.py` - passed
- `just test` - passed; Docker MCP smoke-basic returned status ok and `list_workouts` handled a pre-v5 runtime DB without tool error

## Files Created/Modified

- `tests/test_read_model_queries.py` - read-model metadata, query behavior, and pre-v5 fail-soft contract tests.
- `src/mcp_strava/types.py` - `ReadModelMetadata`.
- `src/mcp_strava/adapters/sqlite/repository.py` - read-model status and fact query methods.
- `src/mcp_strava/application/metric_services.py` - fact-only service assembly for the five MCP tools.
- `tests/test_metric_services.py` - service-level read-model fixtures, metadata checks, and recompute blockers.
- `tests/test_mcp_surface.py` - structured MCP payload metadata coverage.
- `tests/test_security_guards.py` - forbidden recompute and raw stream request-path guards.

## Decisions Made

- The service envelope top-level shape stays unchanged; read-model details live under completeness coverage so existing MCP response framing remains stable.
- Pre-v5 database state is not treated as a request failure. It is reported as `read_model_schema_missing` so MCP surfaces remain factual while Phase 7 validation finishes migration/materialization.
- `project_fitness_state` may project forward only from materialized `training_model_daily` baseline facts; it does not recompute from raw streams at request time.

## Deviations from Plan

### Auto-fixed Issues

**1. [Runtime Compatibility] Pre-v5 Docker DB lacked read-model tables**
- **Found during:** `just test`
- **Issue:** Docker smoke hit `no such table: activity_metric_facts` because the runtime database was still at `user_version=4`.
- **Fix:** Read-model repository methods now return unavailable/empty facts when the read-model schema is absent.
- **Files modified:** `src/mcp_strava/adapters/sqlite/repository.py`, `tests/test_read_model_queries.py`
- **Verification:** targeted read-model/service/security tests and Docker smoke passed.
- **Committed in:** `dc3a5f5`

---

**Total deviations:** 1 auto-fixed runtime compatibility issue.
**Impact on plan:** Strengthens D-26/D-27/D-28 by making missing read-model facts explicit metadata instead of a failed MCP request.

## Issues Encountered

- Current Docker runtime DB observed during smoke is still pre-v5, so Phase 7 acceptance still needs the 07-06 migration/materialization/performance gate before treating the live read-model path as complete.

## User Setup Required

None.

## Next Phase Readiness

Ready for Plan 07-06: add query-plan checks, Docker-first runtime validation docs, and the explicit warm p95 performance gate.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: request-time-recompute | src/mcp_strava/application/metric_services.py | MCP services must continue to avoid raw stream scans and recompute helpers. |
| threat_flag: pre-v5-runtime | src/mcp_strava/adapters/sqlite/repository.py | Missing read-model schema must remain metadata, not a tool-call failure. |

## Self-Check: PASSED
