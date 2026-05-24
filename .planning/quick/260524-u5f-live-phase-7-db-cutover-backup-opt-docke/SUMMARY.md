---
quick_id: 260524-u5f
slug: live-phase-7-db-cutover-backup-opt-docke
status: complete
completed: 2026-05-24
---

# Live Phase 7 DB Cutover Summary

## Result

Live `/opt/docker/mcp-strava/data/strava.db` was backed up, migrated from `user_version=4` to `user_version=5`, materialized through the runtime refresh path, and verified through Docker MCP smoke and warm p95 gate.

## Code Fix Before Cutover

The initial live plan exposed a real blocker: v5 migration created read-model tables but did not queue existing activities for initial materialization. Fixed before mutating live DB.

- `89ef97e` - RED test requiring v5 migration to queue existing activities.
- `e67ea0e` - v5 migration now seeds `activity_source_state` and `metric_dirty_activities` for existing activities.

## Backup

- Manual pinned backup: `/opt/docker/mcp-strava/data/backups/pre-phase7-live-cutover-20260524-214908.db`
- Migration-created pinned backup: `/opt/docker/mcp-strava/data/backups/strava-pre-phase-7-20260524T164932Z.db`
- Backup integrity: `ok`
- Backup version: `user_version=4`
- Backup counts: `activities=599`, `streams=2665424`, `stream_channels=7787`, `sync_log=51`

## Final Live DB State

- `user_version=5`
- `activities=599`
- `streams=2665424`
- `stream_channels=7787`
- `activity_source_state=599`
- `metric_dirty_activities=0`
- `activity_metric_facts=599`
- `daily_load_facts=515`
- `training_model_daily=515`
- `rolling_period_facts=4`
- `read_model_refresh_runs=1`
- `sync_log=52`
- latest read-model run: `status=ok`, `activities_materialized=599`, `daily_facts_materialized=515`, `model_facts_materialized=515`, `rolling_facts_materialized=4`, `dirty_rows_claimed=599`, `dirty_rows_cleared=599`
- final integrity: `ok`

## Verification

- `uv run pytest -q` - passed, 262 passed, 1 skipped
- live preflight before migration - passed, `user_version=4`, integrity `ok`
- `docker compose -f deploy/docker-compose.yml build` - passed
- `docker compose -f deploy/docker-compose.yml stop mcp-strava` - stopped service before mutation
- one-off `admin db-migrate --apply` - passed, `user_version=5`
- one-off `admin mirror-refresh --force` - passed, checkpoint `complete`
- `just test` - passed; Docker MCP smoke returned one workout from read-model facts
- `just mcp-read-model-perf` - passed:
  - `get_fitness_state`: p95 19.04 ms
  - `list_workouts`: p95 16.104 ms
  - `get_workout_detail`: p95 15.12 ms
  - `compare_periods`: p95 29.929 ms
  - `project_fitness_state`: p95 12.753 ms

## Notes

- No backup was deleted.
- Main `mcp-strava` container is running and healthy.
- Recent Docker logs show MCP tool timing entries and no `refresh_worker_error` in the checked window.
