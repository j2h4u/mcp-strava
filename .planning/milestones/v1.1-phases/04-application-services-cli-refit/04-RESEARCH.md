# Phase 4: Application Services & CLI Refit - Research

**Researched:** 2026-05-21
**Domain:** Python application service layer, CLI refit, local-mirror analytics contracts
**Confidence:** HIGH (based on live codebase and Phase 4 decisions)

## Summary

Phase 4 should introduce a thin application/use-case layer between interfaces and existing domain/repository code. The work is a contract refactor, not a new analytics product: preserve current daily, weekly, recent-workout, and per-workout analytics behavior while adding a shared factual metadata envelope for freshness, completeness, warnings, and rationale.

The application layer must stay Strava-free. Product read services read SQLite through `SQLiteRepository` and existing domain functions; they may inspect `refresh_state` and create idempotent local refresh requests for lazy first-use refresh, but they must not call Strava, refresh tokens, run sync/backfill, inspect sync logs, or expose admin controls. CLI then becomes a renderer/argument adapter over these services, split into product commands and admin/debug commands.

## Phase Requirements

| ID | Research Support |
|----|------------------|
| APP-01 | Wrap current `daily_report()` output in a service envelope with freshness/completeness/warnings/rationale. |
| APP-02 | Wrap current `weekly_digest()` output in the same envelope without changing calculations. |
| APP-03 | Expose recent workouts and per-workout analytics from local rows and `enrich_activity()` only. |
| APP-04 | Centralize freshness metadata and lazy first-use refresh signaling in application services. |
| CLI-01 | Refit CLI into product/admin command groups while retaining local operator capabilities. |
| CLI-02 | CLI handlers call application services/adapters rather than owning calculations. |
| CLI-03 | New command names and JSON shapes are allowed, but retained workflows need replacement mapping. |
| TEST-04 | Tests must cover metadata, missing-HR/stream handling, and report/weekly parity. |

## Current Code Findings

- `src/mcp_strava/cli.py` is still the fat command dispatcher. It directly queries SQL for `activities`, calls `daily_report()`, calls `weekly_digest(conn)`, calls Strava-backed `api_request()` for `gear/stats/raw`, and calls sync/backfill wrappers.
- `src/mcp_strava/report.py::daily_report()` opens `DbConn()` internally and returns `DailyReport`.
- `src/mcp_strava/analytics.py::weekly_digest(conn)` accepts a connection and returns `WeeklyDigest | None`.
- `src/mcp_strava/metrics.py::enrich_activity(conn, row)` computes the existing per-workout analytics surface.
- `src/mcp_strava/types.py` owns current dataclass contracts and should host shared service-envelope dataclasses unless the implementation creates a clearly local application contract module.
- `src/mcp_strava/refresh/freshness.py` already has pure `evaluate_freshness()` and `enqueue_refresh_request_if_stale()`, but Phase 4 must use them as factual metadata/signaling, not as a hidden coaching policy.
- `SQLiteRepository` already exposes `recent_activities()`, `activity_by_id()`, load helpers, `get_refresh_state()`, and `enqueue_refresh_request()`. It may need a small `latest_activity_at()` helper for efficient last-activity metadata.

## Recommended Architecture

```
CLI product commands
        |
        v
src/mcp_strava/application/
  contracts.py or types.py additions
  freshness.py
  reports.py
  workouts.py
  registry.py
        |
        v
SQLiteRepository + existing domain analytics
        |
        v
data/strava.db
```

Admin/debug CLI commands remain separate and may call refresh runtime, SQL, raw Strava shims, or local operator tooling. MCP Phase 5 must consume only the product service registry, not the CLI command registry.

## Contract Recommendation

Use a shared envelope:

- `data`: typed service-specific payload.
- `freshness`: `state`, `checked_at`, `last_successful_refresh_at`, `refresh_age_seconds`, `last_activity_at`, `last_activity_age_seconds`, `refresh_requested`, `refresh_request_reason`, `last_error_code`, `backoff_until`.
- `completeness`: `status` (`complete`, `partial`, `insufficient`, `unavailable`), `missing` reason codes, and optional coverage counts.
- `warnings`: factual warning objects with `code`, `severity`, `message`, and optional `field`.
- `rationale`: short calculation/rule explanations from the analytics result, not refresh-runtime debug output.

Do not encode "if stale N days then train easy" rules. Return facts and let the consumer decide.

## CLI Recommendation

Product commands should support human-readable output by default and `--json` for the full envelope. Admin/debug commands can keep pragmatic text/JSON.

Suggested shape for planning (exact spelling may change):

- `report daily [--json]`
- `weekly [--json]`
- `workouts recent [--limit N] [--json]`
- `workout analyze <activity_id|latest> [--json]`
- `freshness [--json]`
- `admin refresh [--force]`
- `admin backfill [since]`
- `admin sql "..."`
- `admin raw <path>`
- `admin log [limit]`

## Validation Architecture

Tests should use fixture SQLite databases, fake refresh state rows, and monkeypatched clocks. The minimum test suite should prove:

- service envelopes are present on daily/weekly/workout/freshness responses;
- `last_successful_refresh_at` and `last_activity_at` are distinct fields;
- first-use freshness signaling creates at most one refresh request for a day;
- product read services do not import Strava adapter, sync, or refresh runtime execution functions;
- daily and weekly `data` output preserves key fields from the current functions;
- missing HR/streams results in `null`/unavailable metrics plus factual warnings;
- CLI product handlers call services and render human text or full JSON envelope;
- admin/debug commands are not in the product service registry.

## Risks

- Silent parity regression: formulas remain plausible but differ from current output.
- Boundary regression: CLI or services accidentally call Strava or sync from read paths.
- Metadata bloat: every service invents a different envelope shape.
- Refresh policy drift: lazy first-use becomes an actual API call on every MCP request instead of a deduped local signal.
- Admin leakage: MCP Phase 5 accidentally wraps CLI commands instead of a product-only service registry.

## Planning Implications

Plan in dependency order:

1. Shared service envelope, factual freshness metadata, and product service registry skeleton.
2. Daily/weekly application services preserving current analytics.
3. Recent/per-workout services preserving current `EnrichedActivity` metrics.
4. CLI refit and boundary guards.

