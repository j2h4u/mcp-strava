---
phase: 06-full-fidelity-strava-mirror
plan: 01
subsystem: database
tags: [sqlite, migrations, repository, cli, mirror-coverage]
requires:
  - phase: 05-mcp-http-surface-docker-hardening
    provides: read-only MCP metric surface and admin/product boundary
provides:
  - Version 3 migration for lossless stream storage (`values_json` + `stream_channels`)
  - Version-aware schema inventory contracts for v1/v2/v3/v4
  - Atomic repository API for replacing stream rows and channel metadata in one transaction
  - Admin-only aggregate mirror coverage command (`admin mirror-coverage`)
affects: [phase-06-02, phase-06-03, stream-ingestion, backfill]
tech-stack:
  added: []
  patterns: [version-aware sqlite schema validation, atomic stream+metadata replacement]
key-files:
  created: [src/mcp_strava/application/mirror_coverage.py, tests/test_full_fidelity_mirror.py]
  modified:
    [
      src/mcp_strava/adapters/sqlite/schema.py,
      src/mcp_strava/adapters/sqlite/migrations.py,
      src/mcp_strava/adapters/sqlite/repository.py,
      src/mcp_strava/cli.py,
      src/mcp_strava/types.py,
      tests/test_repository_boundary.py,
      tests/test_cli_surface.py,
      tests/test_smoke.py,
      tests/test_sqlite_safety.py,
    ]
key-decisions:
  - "Migration target advanced to user_version=3 for Phase 06-01 lossless stream foundation."
  - "Schema inventory is keyed by `PRAGMA user_version` to keep v3 (`latlng` retained) separate from reserved v4 contract."
  - "Admin mirror coverage stays local-only under `admin` namespace and is not exposed in product or MCP surfaces."
patterns-established:
  - "Repository stream writes must tolerate both pre-v3 and v3 schemas during fixture/runtime transitions."
  - "Channel metadata persistence uses upsert semantics keyed by `(activity_id, channel_key)`."
requirements-completed: [MIRROR-01, MIRROR-02, STREAM-02, STREAM-03, COVERAGE-01, TEST-05]
duration: 55min
completed: 2026-05-24
---

# Phase 6 Plan 1: Lossless Stream Foundation Summary

**SQLite v3 mirror foundation now stores stream extra channels losslessly with atomic stream+metadata replacement and admin aggregate coverage reporting.**

## Performance

- **Duration:** 55 min
- **Started:** 2026-05-24T12:34:00Z
- **Completed:** 2026-05-24T13:29:00Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments

- Added RED tests for v3 migration inventory, version-aware schema contracts, stream metadata APIs, and admin mirror coverage output.
- Implemented migration `2 -> 3` with `streams.values_json`, `stream_channels`, and required index `idx_stream_channels_activity`.
- Added repository APIs for channel metadata upsert, atomic replace of rows+metadata, merge helper, and coverage stats.
- Added admin-only `mirror-coverage` command with `--json` and optional `--db <path>` for fixture/copy inspection.

## Task Commits

1. **Task 1: Add failing lossless stream schema and coverage tests** - `ffeaa9d` (`test`)
2. **Task 2: Add SQLite schema, migration, and repository support for lossless stream metadata** - `28cdb26` (`feat`)
3. **Task 3: Add aggregate mirror coverage service and admin command** - `2632a5e` (`feat`)

## Files Created/Modified

- `src/mcp_strava/adapters/sqlite/schema.py` - version-aware required inventory by schema version.
- `src/mcp_strava/adapters/sqlite/migrations.py` - new migration target v3 for lossless stream inventory.
- `src/mcp_strava/adapters/sqlite/repository.py` - stream `values_json` support and channel metadata transactional APIs.
- `src/mcp_strava/application/mirror_coverage.py` - aggregate mirror coverage service for admin CLI.
- `src/mcp_strava/cli.py` - `admin mirror-coverage` command integration.
- `tests/test_full_fidelity_mirror.py` - new phase-specific RED/GREEN tests for v3 foundation.

## Decisions Made

- Keep `latlng` required for v3 inventory; reserve `latlng` removal semantics for v4 (Plan 06-03).
- Keep `batch_id` nullable on `stream_channels` pending runtime sync-log identity threading.
- Keep coverage output aggregate-only and status-focused to avoid payload/secret disclosure.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserve compatibility with pre-v3 stream fixtures**
- **Found during:** Task 2 verification
- **Issue:** Repository inserts/selects assumed `values_json` always exists, breaking v1/v2 fixtures.
- **Fix:** Added runtime schema detection in repository stream read/write paths and fallback SQL without `values_json`.
- **Files modified:** `src/mcp_strava/adapters/sqlite/repository.py`
- **Verification:** `uv run python -m pytest tests/test_full_fidelity_mirror.py tests/test_repository_boundary.py tests/test_sqlite_safety.py -q`
- **Committed in:** `28cdb26`

**2. [Rule 1 - Bug] Make mirror coverage resilient on pre-migration DBs**
- **Found during:** Task 3 verification
- **Issue:** Coverage queries assumed `stream_channels` and `values_json` existed, failing on v2 fixtures.
- **Fix:** Added table/column presence guards and aggregate fallbacks.
- **Files modified:** `src/mcp_strava/adapters/sqlite/repository.py`, `src/mcp_strava/application/mirror_coverage.py`
- **Verification:** `uv run python -m pytest tests/test_full_fidelity_mirror.py tests/test_cli_surface.py tests/test_mcp_surface.py -q`
- **Committed in:** `2632a5e`

---

**Total deviations:** 2 auto-fixed (2 rule-1 bugs)
**Impact on plan:** Both fixes were required for correctness and deterministic verification across fixture schema versions.

## Issues Encountered

- Local `python3 -m pytest` runtime lacked MCP dependency import path for `tests/test_mcp_surface.py`; verification was run via `uv run python -m pytest ...` (project-managed environment) and passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Plan 06-02 ingestion wiring to populate channel metadata and `values_json` from Strava streams.
- v3 schema guards and admin coverage reporting are in place to measure backfill needs before runtime channel expansion.

## Self-Check: PASSED

