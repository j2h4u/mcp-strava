---
phase: 07-materialized-metrics-read-model
plan: 04
subsystem: refresh-runtime
tags: [refresh, backfill, read-model, cli-admin, mcp-boundary, docker]
requires:
  - phase: 07-materialized-metrics-read-model
    provides: offline read-model materializer for dirty activity rows
provides:
  - read-model materialization stage in daily refresh and backfill flows
  - lease-aware materialization wrapper below MCP
  - local admin read-model materialization command
  - MCP forbidden-name guard for recompute/materialization controls
affects: [phase-07-05, phase-07-06, refresh-runtime, docker-runtime, mcp-surface]
tech-stack:
  added: []
  patterns: [checkpointed materialization stage, admin-only recompute control, Docker-first runtime validation]
key-files:
  created: []
  modified:
    - src/mcp_strava/refresh/checkpoints.py
    - src/mcp_strava/refresh/runtime.py
    - src/mcp_strava/refresh/_sync_ops.py
    - src/mcp_strava/deploy/preflight.py
    - src/mcp_strava/cli.py
    - src/mcp_strava/interfaces/mcp_http.py
    - src/mcp_strava/adapters/sqlite/repository.py
    - tests/test_refresh_runtime.py
    - tests/test_cli_surface.py
    - tests/test_docker_runtime.py
    - tests/test_mcp_surface.py
    - tests/test_read_model_materialization.py
key-decisions:
  - "Refresh, legacy backfill, and stream-channel backfill use the same read-model materialization helper below MCP."
  - "Read-model materialization lease renewal must not commit an already-active materializer transaction."
  - "Read-model materialization is local admin/runtime only; MCP keeps the five-tool product allowlist."
patterns-established:
  - "Daily refresh checkpoints `read_model_materialize` after schema validation and before kudos."
  - "Backfill checkpoints `read_model_materialize_backfill` after source-changing stream/detail work."
  - "Runtime DB preflight reports read-model readiness metadata without triggering recompute."
requirements-completed: [READMODEL-03, TEST-06]
duration: 78min
completed: 2026-05-24
---

# Phase 7 Plan 4: Runtime Materialization Wiring Summary

**Refresh and backfill now materialize read-model facts below the MCP surface, with local admin controls only**

## Performance

- **Duration:** 78 min
- **Started:** 2026-05-24T16:38:00+05:00
- **Completed:** 2026-05-24T17:56:00+05:00
- **Tasks:** 4
- **Files modified:** 12

## Accomplishments

- Added RED coverage for refresh-stage ordering, backfill materialization, lease-loss fail-closed behavior, admin CLI output, Docker v5 readiness, and MCP forbidden operational names.
- Added `Stage.READ_MODEL_MATERIALIZE` and `Stage.READ_MODEL_MATERIALIZE_BACKFILL`, then wired materialization after schema validation and before kudos in daily refresh.
- Wired legacy backfill and stream-channel backfill through the same `_sync_ops.materialize_read_model_stage(...)` helper.
- Added `python -m mcp_strava admin read-model-materialize` with `--db`, `--json`, `--dry-run`, `--limit`, and `--metric-version`.
- Extended runtime DB preflight to return read-model readiness metadata while still allowing startup when facts are not current.
- Preserved the MCP boundary by keeping the product allowlist unchanged and blocking materialize/recompute/dirty/status/admin names.
- Fixed a transaction safety issue so lease renewal during materialization does not commit partial fact writes.

## Task Commits

1. **Task 1: Add failing runtime/admin/MCP/preflight tests** - `6434afb` (`test`)
2. **Task 2: Implement refresh/backfill materialization stages** - `8e31f38` (`feat`)
3. **Task 3: Add admin command and MCP forbidden names** - `28496c9` (`feat`)
4. **Fix: Preserve materializer transaction on lease renewal** - `8b67883` (`fix`)

## Verification

- `uv run pytest -q tests/test_refresh_runtime.py tests/test_docker_runtime.py` - passed, 46 tests
- `uv run pytest -q tests/test_cli_surface.py tests/test_mcp_surface.py tests/test_security_guards.py` - passed, 43 tests
- `uv run pytest -q tests/test_read_model_materialization.py tests/test_refresh_runtime.py tests/test_docker_runtime.py tests/test_cli_surface.py tests/test_mcp_surface.py tests/test_security_guards.py` - passed, 103 tests
- `uv run pytest -q` - passed, 248 passed, 1 skipped
- `just test` - passed; Docker MCP smoke-basic returned status ok with the five product tools and `list_workouts` call

## Files Created/Modified

- `src/mcp_strava/refresh/checkpoints.py` - read-model checkpoint stages and daily/backfill progression.
- `src/mcp_strava/refresh/runtime.py` - materialization calls in daily refresh, backfill, and stream-channel backfill.
- `src/mcp_strava/refresh/_sync_ops.py` - shared materialization stage helper.
- `src/mcp_strava/deploy/preflight.py` - v5 read-model readiness metadata for runtime preflight.
- `src/mcp_strava/cli.py` - local admin `read-model-materialize` command.
- `src/mcp_strava/interfaces/mcp_http.py` - forbidden operational names for read-model/recompute controls.
- `src/mcp_strava/adapters/sqlite/repository.py` - transaction-aware lease renewal behavior.
- Tests covering runtime, CLI, Docker preflight, MCP boundary, and materializer transaction safety.

## Decisions Made

- Stream-channel backfill keeps its existing source-work checkpoint until materialization completes; if materialization fails, rerunning stream-channel backfill is idempotent and safely retries materialization.
- Docker startup preflight treats missing/current facts as readiness metadata, not a startup blocker and not a recompute trigger.
- Admin output reports counts/status/run id only; it does not expose raw streams, arbitrary SQL, or token material.

## Deviations from Plan

### Auto-fixed Issues

**1. [Transaction Safety] Prevented lease renewal from committing materializer work**
- **Found during:** Post-Task 3 verification review
- **Issue:** `renew_refresh_lease()` always committed; when called from materializer transaction it could commit activity facts before a later materializer failure.
- **Fix:** `renew_refresh_lease()` now commits only if the connection was not already in a transaction before the lease update.
- **Files modified:** `src/mcp_strava/adapters/sqlite/repository.py`, `tests/test_read_model_materialization.py`
- **Verification:** regression test proves a failed materializer with lease renewal leaves dirty rows and no committed activity facts.
- **Committed in:** `8b67883`

---

**Total deviations:** 1 auto-fixed correctness issue.
**Impact on plan:** Strengthens D-19 and D-20 by preserving both lease renewal behavior and materializer atomicity.

## Issues Encountered

None remaining.

## User Setup Required

None.

## Next Phase Readiness

Ready for Plan 07-05: cut MCP services over to materialized fact-only read queries and add read-model metadata to service envelopes.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: materialization-lease | src/mcp_strava/refresh/runtime.py | Long materialization renews the refresh lease and fails closed if lease ownership is lost. |
| threat_flag: admin-read-model | src/mcp_strava/cli.py | Local admin can materialize facts; this must remain outside MCP. |
| threat_flag: mcp-boundary | src/mcp_strava/interfaces/mcp_http.py | MCP forbidden-name set blocks operational read-model/recompute controls. |

## Self-Check: PASSED
