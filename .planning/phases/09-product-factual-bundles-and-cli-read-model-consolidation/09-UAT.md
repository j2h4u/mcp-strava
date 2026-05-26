---
status: complete
phase: 09-product-factual-bundles-and-cli-read-model-consolidation
source:
  - 09-01-SUMMARY.md
  - 09-02-SUMMARY.md
  - 09-03-SUMMARY.md
  - 09-04-SUMMARY.md
started: 2026-05-26T16:17:41Z
updated: 2026-05-26T16:35:00Z
---

## Current Test

[testing complete]

## Tests

### 1. MCP Product Tool Surface
expected: A direct MCP smoke against the Strava server shows exactly the six product tools: get_fitness_state, list_workouts, get_workout_detail, compare_periods, project_fitness_state, and get_training_aggregates. It does not expose sync, backfill, raw, SQL, token, admin, log, migration, or gateway-only controls.
result: pass

### 2. Daily Brief Facts
expected: Calling get_training_aggregates for the daily_brief bundle returns factual read-model-backed rows plus a bundle payload with daily sections, status facts, freshness, completeness, calculation metadata, and no coaching advice or interpretation text.
result: pass

### 3. Weekly And Historical Bundles
expected: Calling get_training_aggregates for weekly_digest and historical_facts returns factual weekly trend and historical context sections through the same MCP tool, with explicit bundle completeness and no extra MCP tool ids.
result: pass

### 4. Workout Kudos And Gear Facts
expected: Recent workout and workout-detail reads show local read-model facts, including kudos count and detail-only kudos names when available, plus mirrored gear facts where Strava data is present. Missing gear is reported as an explicit completeness condition, not hidden or fetched live.
result: pass

### 5. CLI Read-Model Surface
expected: The CLI product surface exposes report daily, weekly, workouts recent, workout analyze, and freshness as thin read-model/application-service reads. Legacy activities, gear, stats, trend, backtest, kudos, sync, raw, SQL, token, and migration operations are not root product commands; local operations stay under admin.
result: pass

### 6. Direct Smoke And Performance Readiness
expected: The Phase 9 verification commands run against the product itself, not the gateway: targeted pytest passes, just phase9-bundle-smoke passes direct server bundle smoke, just test passes Docker smoke/basic, and warm MCP p95 stays below the Phase 9 500 ms gate.
result: pass

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

none

## Self-Verification Evidence

| Check | Result |
|-------|--------|
| `just mcp-list-tools` | Passed: exactly six product tools; no sync/backfill/raw/SQL/token/admin/log/migration/gateway controls. |
| `just phase9-bundle-smoke` | Passed: 19 targeted MCP tests plus direct live smoke for `daily_brief`, `weekly_digest`, and `historical_facts`. |
| `just mcp-read-model-perf 20 2 500` | Passed: all product tools under the 500 ms Phase 9 p95 gate; worst p95 `list_workouts` at 102.825 ms. |
| `just test` | Passed: Docker build/recreate healthy and smoke-basic returned the six product tools. |
| Container CLI product commands | Passed: `report daily --json`, `weekly --json`, `workouts recent --limit 2 --json`, `workout analyze latest --json`, and `freshness --json` all returned service envelopes. |
| Full pytest | Passed: `354 passed, 1 skipped`. |

## Fix Applied During Verification

Self-verification initially found that `python -m mcp_strava freshness --json` crashed in the Docker runtime because `get_freshness_service()` wrapped the primary DuckDB connection with `SQLiteRepository`. The fix routes freshness through `repository_from_connection()` like the other product read services and adds a regression test for primary repository factory routing.
