# Phase 06 Pattern Map

**Phase:** 06 - Full-Fidelity Strava Mirror
**Status:** Ready for planner use

## Existing Patterns To Reuse

| Role | Existing Pattern | Files | Phase 6 Use |
|------|------------------|-------|-------------|
| SQLite inventory | Required tables/columns plus preflight report | `src/mcp_strava/adapters/sqlite/schema.py` | Add Phase 6 stream metadata, `values_json`, canonical GPS, and coverage inventory checks. |
| Migration gate | `run_preflight` -> backup -> migration -> post-check -> row parity | `src/mcp_strava/adapters/sqlite/migrations.py` | Add target migration for lossless streams and GPS canonicalization with parity snapshots. |
| Repository write boundary | Chunked stream insert/replace methods | `src/mcp_strava/adapters/sqlite/repository.py` | Extend stream writes to scalar hot columns plus extra-channel JSON and metadata rows. |
| Refresh checkpointing | Stage enum, refresh state row, backoff handling | `src/mcp_strava/refresh/checkpoints.py`, `src/mcp_strava/refresh/runtime.py` | Add stream-channel backfill stages and preserve resumability under rate limits. |
| Strava transport seam | Fakeable `transport.fetch()` returning `StravaResponse` | `tests/test_refresh_runtime.py`, `src/mcp_strava/adapters/strava/transport.py` | Test all-channel ingestion and backfill without live Strava calls. |
| Product/admin CLI split | Product commands in `COMMANDS`, operational commands in `ADMIN_COMMANDS` | `src/mcp_strava/cli.py` | Add `admin mirror-coverage` and `admin backfill-streams`; do not expose these as product commands. |
| MCP allowlist | Exact `MCP_TOOL_NAMES` and `FORBIDDEN_TOOL_NAMES` | `src/mcp_strava/interfaces/mcp_http.py` | Preserve read-only metric-only surface and extend forbidden list/tests if needed. |
| Runtime path discipline | Live state under `/opt/docker/mcp-strava` | `src/mcp_strava/deploy/prepare_runtime.py`, `src/mcp_strava/deploy/preflight.py` | Docker/live smoke should inspect runtime DB safely; repo tests use temp or copied DBs. |

## Files Likely Modified

- `src/mcp_strava/types.py`
- `src/mcp_strava/adapters/sqlite/schema.py`
- `src/mcp_strava/adapters/sqlite/migrations.py`
- `src/mcp_strava/adapters/sqlite/repository.py`
- `src/mcp_strava/refresh/_sync_ops.py`
- `src/mcp_strava/refresh/checkpoints.py`
- `src/mcp_strava/refresh/runtime.py`
- `src/mcp_strava/cli.py`
- `src/mcp_strava/interfaces/mcp_http.py`
- `src/mcp_strava/deploy/preflight.py`
- `tests/test_sqlite_safety.py`
- `tests/test_repository_boundary.py`
- `tests/test_refresh_runtime.py`
- `tests/test_cli_surface.py`
- `tests/test_mcp_surface.py`
- `tests/test_security_guards.py`
- `tests/test_docker_runtime.py`
- `tests/test_smoke.py`

## New Files Likely Created

- `src/mcp_strava/application/mirror_coverage.py`
- `tests/test_full_fidelity_mirror.py`

## Data Flow

```text
Strava stream response
  -> generalized stream payload builder
  -> repository writes scalar hot columns + values_json + channel metadata
  -> analytics reads existing hot columns
  -> admin coverage/backfill reads mirror coverage
```

MCP remains outside this flow except for existing read-only metric services that read analytics projections.

## Risk Patterns

- Removing `latlng` is a schema-breaking migration; do it only after backup, preflight, local coordinate fill, and analytics parity checks exist.
- `INSERT OR REPLACE` can accidentally drop newly added nullable columns if bindings are incomplete. Update all stream insert/replace bind lists in one plan.
- Stream channels can have unequal lengths or be absent. Use `time` as the canonical point index and store per-channel metadata/status instead of failing the activity.
- Backfill can accidentally become a full resync. Candidate queries must require existing stream rows and missing channel metadata or missing channel values.
- CLI coverage output can leak too much mirror detail. Keep output aggregated by activity/date/sport/channel/status and avoid raw payloads.

