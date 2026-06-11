# Phase 06 - Research: Full-Fidelity Strava Mirror

**Status:** Research complete
**Date:** 2026-05-22

## Research Question

What does the planner need to know to implement Phase 6 without losing Strava stream information, mutating live data unsafely, or expanding MCP beyond read-only training metrics?

## Findings

### Strava Stream Shape

Strava's activity stream endpoint is keyed by requested stream types and returns a stream set whose documented channels include `time`, `distance`, `latlng`, `altitude`, `velocity_smooth`, `heartrate`, `cadence`, `watts`, `temp`, `moving`, and `grade_smooth`. Each stream channel has its own values and metadata such as size/resolution/series type in the API model.

Planning implication: the current fixed `STREAM_KEYS` and `StravaStreams` parser are not enough. Phase 6 should preserve all returned channel keys in a normalized channel metadata table and keep point-level values that are not first-class hot columns in a JSON map.

### SQLite Remains The Operational Mirror

The existing repository already runs SQLite in WAL mode with busy timeout, and the current service is a single local mirror with short-lived readers and a refresh writer. SQLite WAL supports concurrent readers and a writer for this local deployment shape. This matches the Phase 6 requirement to preserve the existing mirror and avoid risky storage-engine changes.

Planning implication: extend the existing SQLite schema/migration/repository path. Do not introduce DuckDB into the write path in Phase 6.

### DuckDB Is Better Deferred

DuckDB's native concurrency model is primarily single-process for read/write access, while its SQLite extension can read or modify SQLite files using SQLite's locking rules. That is useful for future analytical reads or exports, but it does not reduce the migration/backfill risk of this phase.

Planning implication: DuckDB should remain a deferred read-model/export idea. Phase 6 plans should mention it only as rationale for staying on SQLite.

### Existing Code Patterns To Preserve

- `src/mcp_strava/adapters/sqlite/schema.py` owns required table/column inventory and should gain the Phase 6 required schema checks.
- `src/mcp_strava/adapters/sqlite/migrations.py` owns backup, preflight, migration, and parity discipline. Add a new target migration instead of ad hoc DDL.
- `src/mcp_strava/adapters/sqlite/repository.py` owns all SQLite access. Add stream metadata, coverage, and backfill candidate methods here.
- `src/mcp_strava/refresh/_sync_ops.py` currently drops unknown stream channels by parsing into fixed `StravaStreams`. Replace this with a stream payload builder that preserves raw returned keys into structured rows and metadata.
- `src/mcp_strava/refresh/runtime.py` and `src/mcp_strava/refresh/checkpoints.py` already support resumable stages and backoff; extend this instead of adding a separate sync loop.
- `src/mcp_strava/cli.py` already separates product commands from `admin` commands. Coverage and backfill controls belong under `admin`.
- `src/mcp_strava/interfaces/mcp_http.py` is an explicit read-only allowlist and must not gain coverage, raw, sync, SQL, status, or backfill tools.

## Validation Architecture

### Key Invariants

- Existing `activities`, `streams`, `athlete_zones`, `sync_log`, `kudos`, `refresh_state`, and `refresh_requests` rows remain present after migration.
- Stream point hot columns remain queryable for current analytics.
- Every returned stream channel key is represented in channel metadata.
- Unknown/future stream channel values are retained in `values_json` or an equivalent point-level structure.
- Canonical GPS is `lat` and `lng`; `latlng` is removed after local migration.
- Backfill candidates exclude activities with no stream rows and never trigger summary/detail/kudos account walks.
- MCP exposed tools remain exactly the read-only metric allowlist.

### Test Strategy

- Add temp-DB migration tests for stream metadata tables, `values_json`, GPS backfill from `latlng`, `latlng` removal, row-count parity, GPS-count parity, channel coverage parity, and analytics parity.
- Add repository tests for inserting/replacing mixed known and unknown stream channels in chunks.
- Add refresh tests with fake Strava transport that returns extra stream keys, unsupported/missing channels, rate-limit errors, and partial payloads.
- Add CLI tests for `admin mirror-coverage` and `admin backfill-streams` using temp or copied databases only.
- Add MCP/security guard tests proving no new admin, raw, sync, SQL, coverage, status, or backfill tools are exposed.
- Run `just test` before Phase 6 verification.

## Planning Recommendations

1. Start with schema and coverage inventory so later ingest/backfill work has durable tables and operator visibility.
2. Generalize stream parsing before GPS migration so future writes target the new model.
3. Run GPS migration after the projection contract exists, because it removes `latlng` and must preserve analytics parity.
4. Put historical stream-channel backfill last, because it depends on coverage queries and generalized ingestion.
5. Keep all live/runtime validation Docker-first under `/opt/docker/mcp-strava`; repo-local tests must use temp or copied databases.

## Sources

- Strava API reference: `https://developers.strava.com/docs/reference/#api-Streams-getActivityStreams`
- Strava OpenAPI: `https://developers.strava.com/swagger/swagger.json`
- SQLite WAL: `https://www.sqlite.org/wal.html`
- DuckDB concurrency: `https://duckdb.org/docs/current/connect/concurrency`
- DuckDB SQLite extension: `https://duckdb.org/docs/current/core_extensions/sqlite`

## Research Complete

