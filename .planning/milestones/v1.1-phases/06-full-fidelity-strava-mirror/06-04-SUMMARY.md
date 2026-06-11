---
phase: 06-full-fidelity-strava-mirror
plan: 04
subsystem: refresh-runtime
tags: [sqlite, backfill, cli, mcp, docker]
requires:
  - phase: 06-full-fidelity-strava-mirror
    provides: v4 canonical gps schema and all-channel stream ingestion
provides:
  - Resumable stream-channel backfill with dry-run estimation and checkpoint routing
  - Admin-only `backfill-streams` CLI command surface
  - Version-aware runtime preflight checks for Phase 6 v3/v4 stream schemas
affects: [refresh-runtime, mirror-coverage, admin-cli, mcp-boundary, docker-runtime]
tech-stack:
  added: []
  patterns: [merge-only stream channel backfill, explicit checkpoint stage routing]
key-files:
  created: []
  modified:
    - src/mcp_strava/refresh/checkpoints.py
    - src/mcp_strava/refresh/runtime.py
    - src/mcp_strava/refresh/_sync_ops.py
    - src/mcp_strava/adapters/sqlite/repository.py
    - src/mcp_strava/cli.py
    - src/mcp_strava/interfaces/mcp_http.py
    - src/mcp_strava/deploy/preflight.py
    - tests/test_refresh_runtime.py
    - tests/test_cli_surface.py
    - tests/test_mcp_surface.py
    - tests/test_docker_runtime.py
    - tests/test_full_fidelity_mirror.py
key-decisions:
  - "Stream-channel backfill runs only against activities that already have stream rows and uses streams endpoint only."
  - "Daily refresh and legacy backfill explicitly reject stream-channel backfill checkpoints."
  - "Runtime preflight treats v3 as intermediate and v4 as final post-latlng schema."
patterns-established:
  - "Backfill dry-run returns structured remaining-work estimation without transport calls."
  - "Channel merge preserves existing values_json keys and avoids downgrading available channel metadata."
requirements-completed: [MIRROR-01, STREAM-01, STREAM-02, COVERAGE-01, BACKFILL-01, TEST-05]
duration: 6min
completed: 2026-05-24
---

# Phase 6 Plan 4: Stream-Channel Backfill Summary

**Admin-only stream-channel backfill now supports resumable, rate-limit-aware merge updates with dry-run coverage estimates while MCP remains read-only.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-24T08:04:32Z
- **Completed:** 2026-05-24T08:10:27Z
- **Tasks:** 4
- **Files modified:** 12

## Accomplishments
- Added RED tests for stream-channel backfill dry-run output, checkpoint routing, merge-only writes, and admin command surface.
- Implemented stream-channel checkpoint stages, candidate estimation, and merge-only backfill execution with rate-limit-safe failure behavior.
- Added `admin backfill-streams` with `--dry-run`, `--since`, `--limit`, `--db`, and `--json`.
- Kept MCP tool allowlist unchanged and extended forbidden-name checks for admin/raw/sql/backfill/coverage/status names.
- Added runtime preflight checks for Phase 6 v3/v4 schema expectations and Docker-safe runtime path tests.

## Task Commits

1. **Task 1: Add failing stream-channel backfill candidate and rate-limit tests** - `613cdf2` (test)
2. **Task 2: Implement resumable stream-channel backfill runtime** - `7aff23b` (feat)
3. **Task 3: Add admin backfill command and preserve MCP allowlist** - `82ef3aa` (feat)
4. **Task 4: Add Docker/runtime-safe verification hooks** - `1a92236` (feat)
5. **Post-task fix:** `b62fe42` (fix) for legacy-schema stream_channel table guard

## Files Created/Modified
- `src/mcp_strava/refresh/runtime.py` - new `run_backfill_stream_channels` and routing guards.
- `src/mcp_strava/refresh/_sync_ops.py` - estimation + streams-only backfill merge flow.
- `src/mcp_strava/adapters/sqlite/repository.py` - merge safety and missing-channel candidate queries.
- `src/mcp_strava/cli.py` - admin `backfill-streams` command and help text updates.
- `src/mcp_strava/interfaces/mcp_http.py` - expanded forbidden tool names, unchanged allowlist.
- `src/mcp_strava/deploy/preflight.py` - Phase 6 v3/v4 schema validation.
- `tests/test_refresh_runtime.py` - stream-channel backfill RED/GREEN coverage.
- `tests/test_cli_surface.py`, `tests/test_mcp_surface.py`, `tests/test_docker_runtime.py` - admin/MCP/runtime safety checks.

## Decisions Made
- Preserve legacy `admin backfill` while introducing explicit Phase 6 `admin backfill-streams`.
- Keep stream backfill write path strictly merge/update-only and avoid row replacement APIs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Legacy fixtures without `stream_channels` table crashed candidate scan**
- **Found during:** Task 3 verification
- **Issue:** Candidate discovery assumed `stream_channels` always exists.
- **Fix:** Added table-existence guard before metadata lookups.
- **Files modified:** `src/mcp_strava/adapters/sqlite/repository.py`
- **Verification:** `uv run python -m pytest tests/test_cli_surface.py tests/test_mcp_surface.py tests/test_security_guards.py -q`
- **Committed in:** `b62fe42`

---

**Total deviations:** 1 auto-fixed (1 rule-1 bug)
**Impact on plan:** Required for compatibility with older fixtures and non-destructive runtime verification.

## Issues Encountered
- `python3 -m pytest` for MCP surface failed in local shell due missing `mcp` package; verification was run via `uv run` and passed.
- `just test` still fails because container healthcheck remains unhealthy after compose startup.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 06 plan set is complete with stream-channel backfill and Docker-safe preflight checks in place.
- Remaining follow-up is container healthcheck debugging in Docker runtime path (`just test` currently unhealthy).

## Self-Check: PASSED

