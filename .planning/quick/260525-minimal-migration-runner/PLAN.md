---
quick_id: 260525-minimal-migration-runner
status: completed
---

# Minimal Migration Runner Cleanup

## Goal

Improve the existing SQLite migration runner without adopting a new migration framework.

## Scope

- Keep existing inline migrations v1-v6 unchanged.
- Add support for separate versioned migration modules starting with v7.
- Add a small applied-migration log table for auditability.
- Keep backup, preflight, post-check, and automatic container-start migration behavior.

## Out Of Scope

- Alembic, yoyo, dbmate, or other migration framework adoption.
- Rollback mechanics.
- Rewriting old migrations for aesthetics.

## Result

- Existing inline migrations v1-v6 remain unchanged.
- New migration modules are loaded from `src/mcp_strava/adapters/sqlite/migration_versions/`.
- v7 creates `schema_migration_log` and records legacy v1-v6 plus v7 with checksum.
- `latest_migration_version()` drives container startup migration checks.
- Verified with focused migration tests, full pytest, and Docker MCP smoke.
