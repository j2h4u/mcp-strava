---
phase: 12-decouple-db-py-into-focused-modules
plan: "02"
subsystem: adapters/strava
tags: [strava-adapter, settings, clock, client-facade, d-06, d-07, d-08]
dependency_graph:
  requires: [12-01]
  provides: [SystemClock, SystemSleeper, StravaClient, _build_strava_transport, required_strava_client_creds]
  affects: [src/mcp_strava/adapters/strava, src/mcp_strava/settings.py, tests/test_strava_client.py]
tech_stack:
  added: []
  patterns: [protocol-implementation, facade, transport-injection-seam, token-file-credential-resolution]
key_files:
  created:
    - src/mcp_strava/adapters/strava/clock.py
    - src/mcp_strava/adapters/strava/client.py
    - tests/test_strava_client.py
  modified:
    - src/mcp_strava/settings.py
    - src/mcp_strava/adapters/strava/__init__.py
decisions:
  - "required_strava_client_creds lives in settings.py so load_settings() stays cred-free"
  - "Single _build_strava_transport helper eliminates a third parallel wiring path for 12-03"
  - "StravaClient.api_request drops token= param (GP-02: zero live callers)"
  - "Transport injection seam (transport=) avoids monkeypatching in tests"
metrics:
  duration: 7m
  completed: "2026-05-30T10:12:52Z"
  tasks_completed: 3
  files_changed: 5
---

# Phase 12 Plan 02: Strava Auth + HTTP Homes Summary

Landed SystemClock/SystemSleeper (D-07), StravaClient facade with shared transport helper (D-08), and token-file-sourced credential accessor in settings (D-06), keeping load_settings() credential-free for the read-only mirror path.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 (D-06) | Settings credential accessor | f843235 | settings.py |
| 2 (D-07) | SystemClock / SystemSleeper | f843235 | adapters/strava/clock.py, __init__.py |
| 3 (D-08) | StravaClient facade + transport helper | f843235 | adapters/strava/client.py, __init__.py, tests/test_strava_client.py |

## What Was Built

**settings.py — D-06 credential accessor**
- `_read_token_file_values(token_path)`: parses KEY=VALUE token file, skips comments/blanks
- `required_strava_client_creds(settings)`: returns `(client_id, client_secret)` from token file; raises RuntimeError naming missing keys + token_path; never called from `load_settings()` so the read-only mirror path stays credential-free; `STRAVA_CLIENT_ID`/`STRAVA_CLIENT_SECRET` not added to `_KEYS` (token-file values, not env vars)

**adapters/strava/clock.py — D-07**
- `SystemClock`: implements `Clock` protocol via `time.time()`
- `SystemSleeper`: implements `Sleeper` protocol via `time.sleep()`
- Both exported from `adapters/strava/__init__.py`
- `bootstrap.RealClock`/`RealSleeper` retained (renamed in 12-03/12-04)

**adapters/strava/client.py — D-08**
- `_build_strava_transport(settings, clock, sleeper)`: single canonical wiring path `FileTokenProvider -> TokenRefreshTransport -> StravaTransport`; used by both `StravaClient` and (in 12-03) `build_refresh_collaborators`
- `StravaClient`: facade with optional `transport` injection seam; `api_request(path)` returns `(data, rate_headers)` or rate-limited sentinel; `refresh_token()` returns new token; error messages surface only `exc.reason`, never client_secret

**tests/test_strava_client.py**
- 6 focused test cases via `_FakeTransport` injection — no real network calls or credentials
- Covers: happy-path data+rate_headers, rate-limited sentinel, non-rate-limit error, refresh success, refresh failure, no-secret-leak in error message

## Verification

```
329 passed in 141.05s
```

All existing tests pass. Ruff lint clean on modified/created files.

## Deviations from Plan

None — plan executed exactly as written. The plan already incorporated all RESEARCH and cross-AI review corrections (D-05 token-file relocation, D-06 fail-fast scope, token= param drop, transport helper, D-09 dead-code handling deferred to 12-05).

## Known Stubs

None — all three outputs are fully wired. `StravaClient` is a new facade (not replacing db.py yet — that is 12-03/12-04), so it has no callers at this point, which is expected for the additive approach.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced. `required_strava_client_creds` reads from the token file (existing path); no new credential surface.

## Self-Check: PASSED

- `src/mcp_strava/adapters/strava/clock.py` — EXISTS
- `src/mcp_strava/adapters/strava/client.py` — EXISTS
- `tests/test_strava_client.py` — EXISTS
- Commit f843235 — EXISTS
