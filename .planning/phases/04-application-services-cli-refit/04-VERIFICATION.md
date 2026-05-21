---
phase: 04-application-services-cli-refit
verified: 2026-05-21T17:56:00Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
---

# Phase 4: Application Services & CLI Refit Verification Report

**Phase Goal:** User-facing analytics/report capabilities are delivered by application services and consumed by a clean CLI surface.
**Verified:** 2026-05-21T17:56:00Z
**Status:** passed
**Re-verification:** No - initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Daily report is available through an application service envelope | VERIFIED | `get_daily_report_service()` wraps `daily_report_from_connection()` with freshness/completeness/warnings/rationale (`application/reports.py`) and is covered by `tests/test_application_reports.py` |
| 2 | Weekly summary is available through an application service envelope | VERIFIED | `get_weekly_summary_service()` wraps `weekly_digest()` with injected connection/date support and metadata (`application/reports.py`) |
| 3 | Recent workouts and per-workout analytics read from the local mirror only | VERIFIED | `get_recent_workouts_service()` and `get_workout_analytics_service()` use `SQLiteRepository` and `enrich_activity()`; tests forbid live network and cover missing HR/streams |
| 4 | Freshness metadata and lazy first-use signaling live in application logic | VERIFIED | `build_freshness_metadata()` computes refresh/activity age and enqueues first-use requests without exposing sync to product commands (`application/freshness.py`) |
| 5 | Product registry is safe for future MCP discovery | VERIFIED | `PRODUCT_SERVICES` contains only `daily_report`, `weekly_summary`, `recent_workouts`, `workout_analytics`, and `freshness`; guards exclude admin/debug names |
| 6 | CLI has a product/admin split | VERIFIED | `COMMANDS` exposes product commands plus `admin`; `ADMIN_COMMANDS` contains mirror refresh, token refresh, backfill, SQL, raw, log, and DB safety commands |
| 7 | Product CLI handlers call services and preserve metadata in JSON/human output | VERIFIED | `cmd_report`, `cmd_weekly`, `cmd_workouts`, `cmd_workout`, and `cmd_freshness` call application services and render full `ServiceEnvelope` JSON with `--json`; CLI tests monkeypatch legacy internals to prove they are not called |
| 8 | Replacement mapping documents all old CLI command keys | VERIFIED | `docs/cli.md` maps all 18 old top-level commands to new command/status rows and states admin/debug commands are not part of MCP |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mcp_strava/application/freshness.py` | Shared freshness service | VERIFIED | Produces `FreshnessMetadata` and `get_freshness_service()` envelope |
| `src/mcp_strava/application/reports.py` | Daily/weekly application services | VERIFIED | Provides report and weekly services over existing calculations |
| `src/mcp_strava/application/workouts.py` | Recent/workout analytics services | VERIFIED | Provides recent workout list and per-workout analytics |
| `src/mcp_strava/application/registry.py` | Product service registry | VERIFIED | Callable registry with no admin/debug entries |
| `src/mcp_strava/cli.py` | Product/admin command dispatcher | VERIFIED | Product commands route through services; admin namespace retains operator workflows |
| `docs/cli.md` | CLI replacement mapping | VERIFIED | Accounts for old command keys and explains product/admin split |
| `tests/test_cli_surface.py` | CLI surface tests | VERIFIED | Covers product commands, JSON envelope output, admin namespace, docs mapping, and AST guard |
| `tests/test_phase4_e2e.py` | Fixture-backed CLI integration | VERIFIED | Exercises CLI -> service -> repository -> SQLite using temp DB |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| APP-01 | SATISFIED | Daily report service returns `ServiceEnvelope` with metadata; report service tests pass |
| APP-02 | SATISFIED | Weekly service wraps weekly digest with metadata and insufficient-history handling |
| APP-03 | SATISFIED | Workout services expose recent workouts and per-workout analytics from local DB rows |
| APP-04 | SATISFIED | Freshness service returns factual refresh/activity metadata and first-use refresh request signaling |
| CLI-01 | SATISFIED | Product commands plus `admin` namespace cover retained report, weekly, workouts, freshness, refresh, backfill, SQL, raw/debug, log, and DB safety workflows |
| CLI-02 | SATISFIED | CLI product handlers call application services; AST and monkeypatch tests prevent legacy calculation/sync/API calls |
| CLI-03 | SATISFIED | `docs/cli.md` maps all old command keys and distinguishes token refresh from mirror refresh |
| TEST-04 | SATISFIED | Tests cover freshness metadata, missing HR/stream completeness, report/weekly parity, CLI surface, and fixture-backed E2E |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| CLI product/admin surface | `PYTHONPATH=src python3 -m pytest tests/test_cli_surface.py tests/test_phase4_e2e.py tests/test_security_guards.py tests/test_smoke.py -q` | `44 passed` | PASS |
| CLI freshness envelope | `PYTHONPATH=src python3 -m mcp_strava freshness --json` | Full `ServiceEnvelope` JSON printed | PASS |
| Full regression | `just test` | `123 passed` | PASS |
| Schema drift | `gsd-sdk query verify.schema-drift 04` | `drift_detected=false` | PASS |

### Code Review

| Gate | Result | Details |
|------|--------|---------|
| Code review | clean | `04-REVIEW.md` records no remaining findings |

### Human Verification Required

None.

### Gaps Summary

No blocking implementation gaps found for Phase 4. Phase 5 can build the MCP HTTP surface against the product service registry while keeping admin/debug workflows out of MCP discovery.

---
_Verified: 2026-05-21T17:56:00Z_
_Verifier: inline GSD verifier (Codex runtime; no subagent spawn)_
