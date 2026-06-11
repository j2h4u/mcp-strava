---
phase: 06-full-fidelity-strava-mirror
plan: 02
subsystem: database
tags: [sqlite, streams, refresh-runtime, metadata, tdd]
requires:
  - phase: 06-full-fidelity-strava-mirror
    provides: v3 lossless stream schema and repository stream+metadata contracts
provides:
  - Generalized all-channel stream request and parser for refresh ingestion
  - Hot-path scalar projections plus retained non-hot-path `values_json` channel values
  - Atomic stream row + channel metadata replacement path in refresh runtime
affects: [phase-06-03, phase-06-04, stream-backfill, mirror-coverage]
tech-stack:
  added: []
  patterns: [channel-key projection map, requested-vs-returned metadata status tracking]
key-files:
  created: []
  modified:
    [
      src/mcp_strava/types.py,
      src/mcp_strava/refresh/_sync_ops.py,
      tests/test_refresh_runtime.py,
      tests/test_repository_boundary.py,
      tests/test_full_fidelity_mirror.py,
    ]
key-decisions:
  - "Use `time` as canonical point index and tolerate uneven channel lengths by skipping out-of-range values."
  - "Project only analytics hot columns; retain `distance`, `watts`, `temp`, and unknown channels in `values_json`."
  - "Persist requested-but-absent channels as `status='unavailable'` metadata rather than failing activity ingestion."
patterns-established:
  - "Strava channel names remain canonical in metadata (`stream_channels.channel_key`)."
  - "Refresh ingestion writes stream rows and metadata through one repository transaction."
requirements-completed: [MIRROR-01, MIRROR-02, STREAM-01, STREAM-02, STREAM-03, TEST-05]
duration: 35min
completed: 2026-05-24
---

# Phase 6 Plan 2: All-Channel Stream Ingestion Summary

**Refresh ingestion now requests all configured Strava stream channels, preserves unknown channel content in SQLite, and maintains hot-path analytics projections with atomic row+metadata writes.**

## Performance

- **Duration:** 35 min
- **Started:** 2026-05-24T14:05:00Z
- **Completed:** 2026-05-24T14:40:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Added RED tests for all-channel stream requests, scalar projection parity, `lat/lng` extraction, `values_json` retention/exclusion rules, and unavailable-channel metadata.
- Replaced fixed stream parsing with generalized channel parsing and a projection map from Strava channel names to analytics scalar columns.
- Updated refresh stream writes to atomically replace stream rows and channel metadata in one repository transaction.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add failing all-channel ingestion tests** - `8fdda60` (test)
2. **Task 2: Generalize stream response parsing and projection building** - `966dca5` (feat)
3. **Task 3: Write all-channel rows and metadata through repository methods** - `a7dddb1` (feat)

## Files Created/Modified

- `src/mcp_strava/types.py` - added raw keyed stream parser preserving all returned channels.
- `src/mcp_strava/refresh/_sync_ops.py` - expanded channel request set, generalized projection builder, metadata synthesis, and atomic write path.
- `tests/test_refresh_runtime.py` - RED/GREEN tests for all-channel refresh behavior and missing-channel metadata.
- `tests/test_repository_boundary.py` - null `values_json` assertion for rows without extra channel values.
- `tests/test_full_fidelity_mirror.py` - explicit unavailable-channel metadata persistence assertion.

## Decisions Made

- Keep scalar projection scope unchanged for this phase (`heartrate`, `velocity`, `altitude`, `cadence`, `grade`, GAP, movement, and canonical `lat`/`lng`).
- Preserve non-projected channel keys in `values_json` for forward compatibility and queryability.
- Keep missing-channel behavior non-fatal and observable via channel metadata status.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Plan 06-03 canonical GPS migration and projection cleanup using the new all-channel storage path.
- Ready for Plan 06-04 metadata/channel backfill without needing a full activity stream replacement run.

## Self-Check: PASSED

