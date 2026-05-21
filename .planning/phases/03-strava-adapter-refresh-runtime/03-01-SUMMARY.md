---
phase: 03-strava-adapter-refresh-runtime
plan: 03-01
subsystem: api
tags: [strava, oauth, rate-limit, token-provider, transport, pytest]
requires: []
provides:
  - Strava adapter package with typed transport responses and failures
  - Atomic single-writer file token provider
  - Dedicated OAuth refresh transport with separate retry budget
  - Dual overall/read Strava rate-limit policy
affects: [phase-03-refresh-runtime, phase-03-integration, phase-04-application-services]
tech-stack:
  added: []
  patterns: [injectable-clock-sleeper, adapter-boundary, atomic-token-write]
key-files:
  created:
    - src/mcp_strava/adapters/strava/__init__.py
    - src/mcp_strava/adapters/strava/types.py
    - src/mcp_strava/adapters/strava/token_provider.py
    - src/mcp_strava/adapters/strava/token_refresh.py
    - src/mcp_strava/adapters/strava/rate_limit.py
    - src/mcp_strava/adapters/strava/transport.py
    - tests/test_strava_adapter.py
  modified: []
key-decisions:
  - "OAuth refresh has its own TokenRefreshTransport and retry budget, separate from data-fetch retries."
  - "Token persistence uses fcntl flock plus tempfile, fsync, os.replace, and chmod 0o600."
  - "Rate-limit policy tracks both X-RateLimit-* and X-ReadRateLimit-* windows."
patterns-established:
  - "Strava-facing code lives under src/mcp_strava/adapters/strava and is injectable for hermetic tests."
  - "Adapter failures use StravaUnavailable(reason) with product-safe reason codes."
requirements-completed: [STRAVA-01, STRAVA-02, TEST-02]
duration: 29min
completed: 2026-05-21
---

# Phase 3: Strava Adapter & Refresh Runtime Summary

**Dedicated Strava adapter with safe token refresh, dual quota tracking, typed failures, and hermetic fake-collaborator tests**

## Performance

- **Duration:** 29 min
- **Started:** 2026-05-21T15:05:45Z
- **Completed:** 2026-05-21T15:34:27Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Created `mcp_strava.adapters.strava` as the sole Strava OAuth/HTTP/rate-limit package.
- Added `FileTokenProvider` with exclusive lock, atomic write, and `0o600` token file mode.
- Added `TokenRefreshTransport` so OAuth refresh retries do not consume data-fetch retry budget.
- Added `RateLimitPolicy` parsing overall and read/non-upload Strava quota headers.
- Added hermetic tests with fake HTTP, fake token refresh, fake clock/sleeper, and live-network guard.

## Task Commits

1. **Task 1: Write failing Strava adapter tests with fake collaborators** - `58e3665` (test)
2. **Task 2: Implement Strava adapter package** - `a3842cb` (feat)

**Plan metadata:** this summary

## Files Created/Modified

- `tests/test_strava_adapter.py` - Adapter RED/GREEN coverage for tokens, retries, rate limits, typed responses, and network isolation.
- `src/mcp_strava/adapters/strava/types.py` - Shared adapter dataclasses, protocols, and typed failure.
- `src/mcp_strava/adapters/strava/token_refresh.py` - OAuth POST transport with independent retry budget.
- `src/mcp_strava/adapters/strava/token_provider.py` - Atomic file token provider with single-writer lock.
- `src/mcp_strava/adapters/strava/rate_limit.py` - Dual-window quota policy.
- `src/mcp_strava/adapters/strava/transport.py` - Data-fetch transport using injected collaborators.
- `src/mcp_strava/adapters/strava/__init__.py` - Public adapter exports.

## Decisions Made

- Used the existing `.env` token format for now, but moved read/write/refresh behavior behind `FileTokenProvider`.
- Kept transport dependencies injectable so later refresh-runtime tests can avoid live Strava and real sleeps.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Verification

- `python3 -m pytest tests/test_strava_adapter.py -q` -> 10 passed.
- `just test` -> 63 passed.
- Grep guard for direct SQLite in adapter -> no matches.
- Grep guard for refresh imports in adapter -> no matches.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The adapter package is ready for the SQLite refresh-state repository work and refresh-runtime orchestration. Plan 03-03 can now add persistent leases/checkpoints; Plan 03-02 can inject this adapter into runtime tests after repository support exists.

---
*Phase: 03-strava-adapter-refresh-runtime*
*Completed: 2026-05-21*
