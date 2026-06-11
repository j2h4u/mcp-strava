---
phase: 7
slug: materialized-metrics-read-model
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-24
register_authored_at_plan_time: true
---

# Phase 7 - Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Strava mirror -> read model | Raw normalized SQLite mirror remains source of truth; read-model facts are replaceable derived projections. | Activity summaries/details, stream/channel-derived metrics, source hashes/revisions. |
| Source writes -> dirty queue | Repository source mutations update source state and enqueue metric dirties in the same transaction. | Activity ids, semantic hashes, source revisions, dirty reasons. |
| Refresh runtime -> materializer | Refresh/backfill stages materialize facts under checkpoint and lease control. | Dirty rows, derived fact writes, read-model run audit rows. |
| MCP surface -> application services | MCP exposes only five factual product tools and reads prepared facts. | Workouts, fitness facts, period comparisons, projections, freshness/completeness metadata. |
| Live Docker runtime -> local host data | Runtime reads/writes `/opt/docker/mcp-strava` via container volume and keeps DB/token paths out of MCP responses. | SQLite database, token file path, logs, MCP tool payloads. |

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-07-01 | Tampering | `run_migrations()` v5 | mitigate | Idempotent v5 DDL creates read-model inventory, seeds existing activities into dirty queue, and leaves source rows as source of truth; covered by migration/schema/initial queue tests. | closed |
| T-07-02 | Information Disclosure | Backup files | mitigate | v5 migration creates pinned pre-Phase-7 backup through backup helper; backup retention keeps pinned backups outside ordinary pruning. | closed |
| T-07-03 | Denial of Service | SQLite fact indexes | mitigate | v5 creates required read-model and activity lookup indexes; query-plan tests require hot reads to use fact indexes and avoid raw stream scans. | closed |
| T-07-SC | Tampering | Package installs | accept | Phase 7 introduced no new package-manager dependency; existing dependency set is unchanged. | closed |
| T-07-04 | Tampering | Repository source writes | mitigate | Source state update and dirty enqueue are transactionally coupled; failure injection proves source mutation rolls back if dirty enqueue fails. | closed |
| T-07-05 | Repudiation | Source revision history | mitigate | `activity_source_state` records source hash, source revision, activity day, and changed timestamp. | closed |
| T-07-06 | Information Integrity | Semantic hash computation | mitigate | Source hashes ignore non-semantic timestamp churn and only bump revisions on semantic source changes. | closed |
| T-07-07 | Tampering | Materializer dirty clear | mitigate | Materializer writes facts, records ok audit row, clears dirty rows, and commits in one transaction; failures roll back and keep dirty rows. | closed |
| T-07-08 | Information Integrity | Metric versioning | mitigate | Fact tables and dirty rows include metric version; materializer can write new versions without deleting old facts; MCP comparisons expose version status. | closed |
| T-07-09 | Denial of Service | Materializer computation | mitigate | Materializer supports bounded dirty batch limit and lease-renew callback; MCP request path does not trigger materialization. | closed |
| T-07-10 | Denial of Service | Refresh lease during materialization | mitigate | Runtime passes lease renewer into materialization and raises fail-closed error on lost lease. | closed |
| T-07-11 | Elevation of Privilege | MCP registry | mitigate | MCP registry is an allowlist of five read-only product tools; forbidden admin/sync/raw/recompute surfaces are guarded by tests. | closed |
| T-07-12 | Tampering | Admin materialization command | mitigate | Runtime-owned `admin mirror-refresh --force` performs materialization below MCP and reports structured status/count metadata. | closed |
| T-07-13 | Information Disclosure | Admin output | mitigate | Runtime checks and p95 output expose status, counts, and timings only; no tokens, raw stream rows, arbitrary SQL rows, or `.env` contents. | closed |
| T-07-14 | Elevation of Privilege | `metric_services.py` | mitigate | Static guards reject recompute/admin/sync/raw imports and calls; service code reads repository fact methods only. | closed |
| T-07-15 | Information Integrity | Read-model metadata | mitigate | MCP envelopes include read-model status, last materialized timestamp, dirty count, oldest dirty day, metric versions, and stale reason. | closed |
| T-07-16 | Tampering | Period comparison | mitigate | Period comparison uses read-model fact rows plus model facts and includes version/status metadata instead of silently mixing formulas. | closed |
| T-07-17 | Denial of Service | MCP read queries | mitigate | MCP services query indexed fact tables and never scan raw stream tables or call stream-heavy recompute helpers. | closed |
| T-07-18 | Denial of Service | MCP tool latency | mitigate | Warm p95 gate covers all five MCP tools and fails above 500 ms p95. Latest live max p95 was 34.867 ms. | closed |
| T-07-19 | Denial of Service | SQLite query shape | mitigate | EXPLAIN tests require fact-table indexes and half-open date filters; hot query tests reject `SUBSTR` date filters. | closed |
| T-07-20 | Tampering | Live runtime validation | mitigate | Live cutover followed pinned backup, migration, materialization, post-check, Docker smoke, and p95 validation. | closed |
| T-07-21 | Information Disclosure | Latency logs/output | mitigate | MCP/perf logs include tool names, status, and timing metrics only. | closed |

## Evidence

| Control Area | Evidence |
|--------------|----------|
| v5 schema and initial dirty queue | `src/mcp_strava/adapters/sqlite/migrations.py:371` creates `activity_source_state`, `metric_dirty_activities`, fact tables, indexes, `read_model_refresh_runs`; `src/mcp_strava/adapters/sqlite/migrations.py:562` seeds existing activities for first materialization. |
| Backup and migration gate | `src/mcp_strava/adapters/sqlite/migrations.py:603` runs preflight, creates backup, creates pinned pre-Phase-7 backup before v5, then runs post-check/parity. |
| Atomic source invalidation | `src/mcp_strava/adapters/sqlite/repository.py:183` updates source state and enqueues dirty rows; `src/mcp_strava/adapters/sqlite/repository.py:248` dedupes dirty rows and resets failure metadata. |
| Read-model metadata | `src/mcp_strava/adapters/sqlite/repository.py:430` returns current/stale/unavailable status, last materialized time, dirty count, oldest dirty day, versions, and stale reason. |
| Fact-only indexed reads | `src/mcp_strava/adapters/sqlite/repository.py:516` through `src/mcp_strava/adapters/sqlite/repository.py:650` read `training_model_daily`, `activity_metric_facts`, `daily_load_facts`, and `rolling_period_facts` with indexed predicates. |
| Materializer transaction | `src/mcp_strava/adapters/sqlite/read_model_materializer.py:360` begins the materialization transaction; `src/mcp_strava/adapters/sqlite/read_model_materializer.py:391` records ok audit metadata; `src/mcp_strava/adapters/sqlite/read_model_materializer.py:409` clears dirty rows; `src/mcp_strava/adapters/sqlite/read_model_materializer.py:410` rolls back on failure. |
| Refresh lease and checkpoints | `src/mcp_strava/refresh/runtime.py:100`, `src/mcp_strava/refresh/runtime.py:162`, and `src/mcp_strava/refresh/runtime.py:252` materialize after daily refresh, backfill, and stream-channel backfill; `src/mcp_strava/refresh/runtime.py:324` fails closed on lost lease renewal. |
| MCP allowlist | `src/mcp_strava/interfaces/mcp_http.py:24` defines exactly five product tools; `src/mcp_strava/interfaces/mcp_http.py:137` through `src/mcp_strava/interfaces/mcp_http.py:222` registers those tools as read-only structured outputs. |
| MCP service boundary | `src/mcp_strava/application/metric_services.py:298`, `src/mcp_strava/application/metric_services.py:334`, `src/mcp_strava/application/metric_services.py:401`, `src/mcp_strava/application/metric_services.py:626`, and `src/mcp_strava/application/metric_services.py:782` assemble responses from read-model repository queries. |
| Runtime security guards | `tests/test_security_guards.py:358` rejects request-time recompute helper imports/calls; `tests/test_security_guards.py:402` rejects raw stream SQL in metric services; `tests/test_security_guards.py:409` rejects raw stream/channel SQL in MCP request modules; `tests/test_security_guards.py:432` rejects admin/sync/Strava adapter imports in MCP HTTP. |
| Query/perf tests | `tests/test_read_model_queries.py:412` checks hot query plans use fact indexes and never scan streams; `tests/test_read_model_queries.py:490` checks hot methods avoid `SUBSTR` date filters; `tests/test_mcp_latency_gate.py:34` verifies startup is measured separately; `tests/test_mcp_latency_gate.py:75` fails above p95 threshold; `tests/test_mcp_latency_gate.py:90` covers all product tools. |
| Repo-hygiene test isolation | Git-dependent local-state checks were removed from `tests/test_security_guards.py`; `tests/test_repo_hygiene.py` now checks local-state policy statically without invoking Git. |

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-07-SC | T-07-SC | No new package-manager dependency was introduced in Phase 7; supply-chain posture remains unchanged from the existing project baseline. | Plan 07-01 / Codex security audit | 2026-05-24 |

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-24 | 22 | 22 | 0 | Codex |

### Verification Commands

| Command | Result |
|---------|--------|
| `docker run --rm -v "$PWD":/src:ro -w /tmp/mcp-strava python:3.13-slim ... python -m pytest -q tests/test_repo_hygiene.py tests/test_read_model_materialization.py tests/test_read_model_queries.py tests/test_metric_services.py tests/test_mcp_surface.py tests/test_security_guards.py tests/test_refresh_runtime.py tests/test_mcp_latency_gate.py tests/test_docker_runtime.py` | `110 passed in 42.18s` |
| `just test` | Passed; Docker MCP smoke returned exactly `compare_periods`, `get_fitness_state`, `get_workout_detail`, `list_workouts`, `project_fitness_state`, and successfully called `list_workouts`. |
| `docker compose -f deploy/docker-compose.yml exec -T mcp-strava python -m mcp_strava admin db-check --json` | Passed; `user_version=5`, `integrity_result=ok`, `metric_dirty_activities=0`, `activity_metric_facts=599`, `daily_load_facts=515`, `training_model_daily=515`, `rolling_period_facts=4`. |
| `just mcp-read-model-perf` | Passed; p95 ms: `get_fitness_state=16.406`, `list_workouts=16.609`, `get_workout_detail=13.803`, `compare_periods=34.867`, `project_fitness_state=18.657`. |

## Live Runtime State

| Metric | Value |
|--------|-------|
| Database | `/opt/docker/mcp-strava/data/strava.db` mounted as `/runtime/data/strava.db` |
| `PRAGMA user_version` | `5` |
| Integrity | `ok` |
| Activities | `599` |
| Streams | `2,665,424` |
| Stream channels | `7,787` |
| Activity source state rows | `599` |
| Dirty rows | `0` |
| Activity metric facts | `599` |
| Daily load facts | `515` |
| Training model daily rows | `515` |
| Rolling period facts | `4` |
| Latest read-model run | `status=ok`, `activities_materialized=599`, `dirty_rows_claimed=599`, `dirty_rows_cleared=599`, `last_error=null` |

## Sign-Off

- [x] All threats have a disposition: mitigate / accept / transfer.
- [x] Accepted risks are documented in Accepted Risks Log.
- [x] `threats_open: 0` confirmed.
- [x] `status: verified` set in frontmatter.

**Approval:** verified 2026-05-24
