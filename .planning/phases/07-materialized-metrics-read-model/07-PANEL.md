# Phase 7 Expert Panel: Materialized Metrics Read Model

## Context

Live MCP E2E revealed that the current MCP services are functionally wired but architecturally too expensive:

- `get_fitness_state` measured about 26 seconds on the live mirror.
- `compare_periods` timed out under a 90 second full smoke in one run, and a 30-day comparison measured about 52.7 seconds in SQLite expert profiling.
- The live mirror has roughly 599 activities and 2.6M stream rows, which is not large enough to justify multi-second MCP calls.

The target contract is stricter: any individual MCP tool should be below 500 ms p95 on the current local mirror.

## Panel Consensus

Do not solve this with request-local Python caches or larger MCP timeouts.

The correct architecture is an in-DB read model beside the Strava mirror:

- Raw Strava mirror tables remain the source of truth.
- Derived facts are materialized in SQLite tables.
- Source writes mark affected activities and days dirty.
- Refresh/runtime recomputes derived facts after source sync/backfill.
- MCP tools read prepared facts and aggregate them, without scanning raw streams or recomputing stream-derived metrics at request time.

## Proposed Tables

| Table | Purpose |
|-------|---------|
| `activity_source_state` | Per-activity source fingerprints, source revision, and changed timestamp. |
| `metric_dirty_activities` | Durable queue of activities/days requiring derived metric recomputation. |
| `activity_metric_facts` | Per-activity metrics: volume, TRIMP, HR, zones, HR recovery, vertical speed, cardiac cost, cardiac drift, HRR, Z5, anomalies, completeness. |
| `daily_load_facts` | Per-day and per-sport aggregates: counts, coverage, TRIMP, distance, time, elevation, high-zone/anomaly totals. |
| `training_model_daily` | Daily fitness/fatigue/form/ATL/CTL/ACWR/model state. |
| `rolling_period_facts` | Fixed rolling windows such as 7/14/28/90 days for fitness state and weekly context. |
| `read_model_refresh_runs` | Audit/checkpoint table for read-model recomputation. |

## Invalidation Contract

- Use source hashes/revisions, not timestamps alone.
- Exclude non-semantic fields such as `synced_at` and `fetched_at` from source fingerprints.
- If source data changes, increment `source_revision` and enqueue dirty work.
- If metric formulas or config change, bump `metric_version` and enqueue affected facts.
- Clear dirty rows only after recomputation commits successfully.

## Refresh Integration

Add a read-model materialization step after source mirror update and schema validation, before optional kudos/admin-adjacent work.

Backfill and stream-channel merge paths must call the same invalidation/materialization machinery. MCP must not expose recompute controls.

## SQL And Indexing Notes

- Add activity indexes such as `(date, id)` and `(sport_type, date, id)`.
- Avoid `SUBSTR(date,1,10)` in `WHERE` clauses; use half-open indexed ranges.
- Replace repeated stream scans with selected-activity joins or materialized daily facts.
- Run `ANALYZE` or `PRAGMA optimize` after migration/index changes in a write-capable admin path.

## QA Requirements

- Source-change invalidation tests for summary/detail/stream/channel updates.
- Idempotent recompute tests.
- Failure injection around stream merge plus dirty marking.
- Migration parity snapshots for key MCP and CLI outputs.
- Rate-limit/backoff tests ensuring changed facts are not marked fresh before recomputation.
- Backup and restore drill for live DB migration.

## Acceptance Criteria

- MCP stays read-only and operational controls remain admin/CLI only.
- Raw streams are never scanned during MCP request handling.
- `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, and `project_fitness_state` complete below 500 ms p95 on the current live mirror.
- Missing/stale derived facts appear as completeness metadata instead of triggering expensive request-time recomputation.
