---
phase: 07-materialized-metrics-read-model
plan: 07-06
subsystem: validation
tags: [mcp, read-model, performance, docker, query-plan, pytest]
requires:
  - phase: 07-materialized-metrics-read-model
    plan: 07-05
    provides: fact-only MCP service paths
provides:
  - explicit warm MCP p95 performance gate
  - query-plan checks for hot read-model fact reads
  - Docker-first Phase 7 validation runbook
  - fail-soft performance-gate fallback for pre-v5 runtime DBs
affects: [mcp-surface, docker-runtime, deployment-runbook, read-model-performance]
tech-stack:
  added: []
  patterns: [warm-session-latency-gate, explain-query-plan-guard, docker-first-validation]
key-files:
  created:
    - tests/test_mcp_latency_gate.py
  modified:
    - Justfile
    - src/mcp_strava/devtools/mcp_client/client.py
    - src/mcp_strava/devtools/mcp_client/cli.py
    - src/mcp_strava/deploy/smoke.py
    - src/mcp_strava/application/metric_services.py
    - tests/test_mcp_test_client.py
    - tests/test_read_model_queries.py
    - tests/test_security_guards.py
    - tests/test_docker_runtime.py
    - docs/deployment.md
key-decisions:
  - "Performance validation is an explicit `just mcp-read-model-perf` gate and remains separate from `just test`."
  - "Warm latency measurement separates startup time from per-tool samples in one MCP session."
  - "Live Phase 7 acceptance requires pinned backup, v5 migration, runtime-owned materialization, parity checks, Docker smoke, and p95 gate before backup cleanup."
patterns-established:
  - "Reusable MCP client supports scripted repeated warm samples for all five product tools."
  - "Read-model hot query plans are guarded with EXPLAIN QUERY PLAN checks and no raw streams scans."
  - "Pre-v5 runtime DBs can run the p95 gate through missing-workout fail-soft detail calls, but this is not full live read-model acceptance."
requirements-completed: [READMODEL-04, PERF-01, TEST-06]
duration: 62min
completed: 2026-05-24
---

# Phase 7 Plan 6: Read-Model Performance and Docker Validation Summary

**The read-model MCP path now has explicit latency, query-shape, and Docker validation gates**

## Performance

- **Duration:** 62 min
- **Started:** 2026-05-24T18:45:00+05:00
- **Completed:** 2026-05-24T19:47:00+05:00
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments

- Added RED tests for warm MCP latency measurement, repeated script samples, query-plan guards, and MCP request-path stream-scan guards.
- Added `measure_warm_tool_latency`, default five-tool call generation, script support, and a `perf-read-model` reusable MCP client command.
- Added `just mcp-read-model-perf` as a separate explicit gate, not part of `just test`.
- Extended Docker smoke wrapper with optional performance-gate support.
- Added EXPLAIN QUERY PLAN tests proving hot read-model queries use fact-table indexes and do not scan `streams`.
- Added deployment runbook coverage for pinned backup, `user_version=5`, runtime-owned materialization, post-check/parity, Docker smoke, and the 500 ms p95 threshold.
- Restored the `compare_periods` mapped/skipped registry contract after full pytest caught the missing export.

## Task Commits

1. **Task 1: Add MCP read-model latency and query-plan gates** - `6c97279` (`test`)
2. **Task 2: Add warm MCP read-model latency gate** - `c3983f5` (`feat`)
3. **Task 3: Document Docker performance validation** - `c1205b8` (`docs`)

## Verification

- RED check: `uv run pytest -q tests/test_mcp_latency_gate.py tests/test_mcp_test_client.py tests/test_read_model_queries.py tests/test_security_guards.py` failed on missing `measure_warm_tool_latency`.
- `uv run pytest -q tests/test_mcp_latency_gate.py tests/test_mcp_test_client.py tests/test_read_model_queries.py tests/test_security_guards.py && just --list` - passed, 39 tests; `mcp-read-model-perf` listed.
- `uv run python -m compileall -q src/mcp_strava/devtools/mcp_client/client.py src/mcp_strava/devtools/mcp_client/cli.py src/mcp_strava/deploy/smoke.py` - passed.
- `uv run pytest -q tests/test_docker_runtime.py tests/test_read_model_queries.py tests/test_mcp_latency_gate.py` - passed, 27 tests.
- `uv run pytest -q` - passed, 260 passed, 1 skipped.
- `just test` - passed; Docker MCP smoke-basic returned status ok with the five product tools.
- `just mcp-read-model-perf` - passed against Docker MCP with warm p95 below 500 ms for all five tools:
  - `get_fitness_state`: p95 14.353 ms
  - `list_workouts`: p95 12.806 ms
  - `get_workout_detail`: p95 10.854 ms
  - `compare_periods`: p95 13.748 ms
  - `project_fitness_state`: p95 15.511 ms

## Files Created/Modified

- `tests/test_mcp_latency_gate.py` - warm latency helper, threshold failure, default call set, and empty-workout fallback tests.
- `src/mcp_strava/devtools/mcp_client/client.py` - latency measurement helpers, default call generation, script support.
- `src/mcp_strava/devtools/mcp_client/cli.py` - `perf-read-model` command.
- `src/mcp_strava/deploy/smoke.py` - optional HTTP MCP performance gate.
- `Justfile` - `mcp-read-model-perf` target.
- `tests/test_mcp_test_client.py` - repeated warm script samples for all five product tools.
- `tests/test_read_model_queries.py` - EXPLAIN QUERY PLAN and no-`SUBSTR` hot-query guards.
- `tests/test_security_guards.py` - request-path raw stream table guard.
- `tests/test_docker_runtime.py` - deployment runbook contract test.
- `docs/deployment.md` - Phase 7 validation sequence.
- `src/mcp_strava/application/metric_services.py` - `compare_periods` mapped/skipped registry contract.

## Decisions Made

- The normal `just test` target remains a fast Docker transport smoke; the p95 performance gate is explicit and opt-in through `just mcp-read-model-perf`.
- The performance gate measures startup separately from warm tool calls so slow startup cannot be hidden inside per-tool samples.
- Empty or pre-v5 runtime DBs do not block the gate from measuring all five tools; `get_workout_detail` uses a missing-id fail-soft path in that case.

## Deviations from Plan

### Auto-fixed Issues

**1. [Registry Contract] `compare_periods` mapping exports were missing after read-model cutover**
- **Found during:** Full pytest.
- **Issue:** `tests/test_metric_registry.py` expected mapped/skipped registries for comparable metrics.
- **Fix:** Restored `COMPARE_PERIODS_HANDLERS` and `COMPARE_PERIODS_SKIP_REASONS` without adding request-time recompute.
- **Files modified:** `src/mcp_strava/application/metric_services.py`
- **Verification:** full pytest passed.
- **Committed in:** `c1205b8`

**2. [Docker Runtime] Performance gate could not resolve a workout id on a pre-v5 DB**
- **Found during:** `just mcp-read-model-perf`.
- **Issue:** Docker runtime DB was `user_version=4` and had no read-model facts, so `list_workouts` returned no rows.
- **Fix:** Default gate falls back to `workout_id=0`, which measures the MCP `get_workout_detail` fail-soft path without throwing protocol errors.
- **Files modified:** `src/mcp_strava/devtools/mcp_client/client.py`, `tests/test_mcp_latency_gate.py`
- **Verification:** `just mcp-read-model-perf` passed.
- **Committed in:** `c1205b8`

---

**Total deviations:** 2 auto-fixed validation issues.
**Impact on plan:** Strengthens TEST-06 by keeping registry coverage and allowing the Docker gate to run before live v5 migration.

## Issues Encountered

- Current Docker runtime DB still reports `user_version=4`; read-model tables are missing, while raw mirror tables are populated (`activities=599`, `streams=2665424`, `stream_channels=7787`). This execution did not mutate the live DB to v5.
- The p95 numbers above prove the MCP transport and fail-soft request paths are fast. Full live read-model acceptance still requires the documented backup, migration, runtime materialization, parity, and p95 sequence on the live DB.

## User Setup Required

None for code execution. Before deleting any pinned pre-Phase-7 backup, run the Phase 7 read-model validation sequence in `docs/deployment.md` against the live `/opt/docker/mcp-strava` runtime state.

## Next Phase Readiness

Phase 7 implementation is complete. The next operational step is live read-model migration/materialization acceptance, not another code phase in the current roadmap.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: latency-gate | src/mcp_strava/devtools/mcp_client/client.py | Warm p95 must continue to measure tool calls separately from startup. |
| threat_flag: query-plan | tests/test_read_model_queries.py | Hot MCP read-model queries must keep using fact indexes and avoid raw stream scans. |
| threat_flag: live-migration | docs/deployment.md | Live backup must remain until v5 migration, materialization, parity, Docker smoke, and p95 acceptance pass. |

## Self-Check: PASSED
