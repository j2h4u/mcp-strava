---
quick_id: 260522-ra3
status: complete
completed: 2026-05-22
---

# Quick Task 260522-ra3 Summary

Set the automatic Strava mirror refresh cadence to a fixed one-hour interval by default.

## Changed

- Added `MCP_STRAVA_REFRESH_INTERVAL_SECONDS` with default `3600`.
- Replaced same-calendar-day refresh skipping with interval-based refresh skipping.
- Kept MCP read-only; refresh remains owned by the background worker.
- Added tests for hourly interval behavior and Docker runtime settings.

## Verified

- `just test`
- `just gateway-smoke`
- Docker targeted pytest: `tests/test_refresh_runtime.py tests/test_settings.py tests/test_security_guards.py`
