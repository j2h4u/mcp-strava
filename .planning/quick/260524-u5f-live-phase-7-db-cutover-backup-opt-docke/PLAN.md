---
quick_id: 260524-u5f
slug: live-phase-7-db-cutover-backup-opt-docke
status: in_progress
created: 2026-05-24
---

# Live Phase 7 DB Cutover

## Goal

Back up the live `/opt/docker/mcp-strava` runtime database, migrate it to read-model schema `user_version=5`, materialize read-model facts, and verify Docker MCP smoke and p95 gates.

## Safety Rules

- Stop the running Docker service before mutating the live SQLite file.
- Create a separately named pinned backup before migration.
- Do not delete any existing backup during this task.
- If migration does not seed existing activities for materialization, fix that in code and tests before live mutation.
- Verify row counts and MCP behavior after the cutover.

## Steps

1. Inspect current live DB version/counts.
2. Ensure v5 migration seeds existing source rows into `activity_source_state` and `metric_dirty_activities`.
3. Run tests for migration/materialization behavior.
4. Stop Docker service and create a pinned backup.
5. Run migration to v5 using the Docker image/runtime env.
6. Run runtime-owned materialization via `admin mirror-refresh --force`.
7. Verify counts, `just test`, and `just mcp-read-model-perf`.
8. Record summary and commit GSD artifacts/code changes.
