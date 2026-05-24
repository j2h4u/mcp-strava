---
phase: 07
slug: materialized-metrics-read-model
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-24
updated: 2026-05-24
---

# Phase 07 - Validation Strategy

> Per-phase validation contract for feedback sampling and Nyquist coverage.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest in Python 3.14 Docker test container + Docker MCP smoke/perf gates |
| **Config file** | `pyproject.toml`, `Justfile`, `deploy/docker-compose.yml` |
| **Quick run command** | `docker run --rm -v "$PWD":/src:ro -w /tmp/mcp-strava python:3.14-slim bash -lc 'cp -a /src/. /tmp/mcp-strava && python -m pip install --quiet --no-cache-dir ".[test]" && python -m pytest -q tests/test_read_model_materialization.py tests/test_read_model_queries.py tests/test_metric_services.py tests/test_mcp_surface.py tests/test_security_guards.py tests/test_refresh_runtime.py tests/test_mcp_latency_gate.py tests/test_docker_runtime.py'` |
| **Full suite command** | `docker run --rm -v "$PWD":/src:ro -v /opt/docker:/opt/docker:ro -w /tmp/mcp-strava python:3.14-slim bash -lc 'cp -a /src/. /tmp/mcp-strava && python -m pip install --quiet --no-cache-dir ".[test]" && python -m pytest -q'` |
| **Docker MCP smoke** | `just test` |
| **Explicit performance gate** | `just mcp-read-model-perf` |
| **Live DB readiness** | `docker compose -f deploy/docker-compose.yml exec -T mcp-strava python -m mcp_strava admin db-check --json` |
| **Estimated runtime** | quick ~45s; full ~75s; Docker smoke/perf depends on image/cache |

## Sampling Rate

- **After every task commit:** Run the narrow pytest command for the touched layer in a Docker Python 3.14 test container.
- **After every plan wave:** Run the full Docker test-container pytest suite plus `just test`.
- **Before `$gsd-verify-work 7`:** Full suite, Docker MCP smoke, explicit p95 gate, and live DB readiness must be green.
- **Max feedback latency:** 120 seconds for focused tests; Docker smoke/perf gates may be longer but must be explicit.

## Per-Requirement Verification Map

| Requirement | Required Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|-------------------|------------|-----------------|-----------|-------------------|-------------|--------|
| READMODEL-01 | Activity-level metric facts persist with source revision/hash, metric version, computed timestamp, completeness, missing reasons, and current synthetic metrics | T-07-01 | Derived facts are rebuildable and cannot masquerade as source data | migration/integration | `python -m pytest -q tests/test_read_model_materialization.py tests/test_metric_services.py tests/test_sqlite_safety.py` | yes | green |
| READMODEL-02 | Source writes atomically update source state and enqueue dirty rows for summaries, details, streams, channel metadata, and metric-version bumps | T-07-02 | No changed source row can commit without dirty invalidation | integration/failure | `python -m pytest -q tests/test_read_model_materialization.py tests/test_refresh_runtime.py tests/test_full_fidelity_mirror.py` | yes | green |
| READMODEL-03 | Refresh/backfill/migration materializes activity, daily, model, and rolling facts under lease/checkpoint control | T-07-03 | Dirty rows clear only after fact writes and run audit commit | integration/failure | `python -m pytest -q tests/test_read_model_materialization.py tests/test_refresh_runtime.py tests/test_docker_runtime.py` | yes | green |
| READMODEL-04 | MCP tools read materialized facts only and do not scan raw streams or call stream-heavy recompute helpers | T-07-04 | MCP remains read-only and cannot trigger recompute/admin/source writes | unit/guard | `python -m pytest -q tests/test_read_model_queries.py tests/test_metric_services.py tests/test_mcp_surface.py tests/test_security_guards.py` | yes | green |
| PERF-01 | Each MCP tool completes below 500 ms p95 for warm calls on the current local mirror/copy | T-07-05 | Slow raw-stream fallback is detected before acceptance | perf/smoke | `python -m pytest -q tests/test_mcp_latency_gate.py tests/test_mcp_test_client.py tests/test_read_model_queries.py && just mcp-read-model-perf` | yes | green |
| TEST-06 | Migration, dirty queue, materializer failure, MCP surface, Docker smoke, and live DB readiness are covered without live Strava calls | T-07-06 | Tests protect source data, secrets, and MCP boundary | suite/smoke | full Docker pytest suite, `just test`, `just mcp-read-model-perf`, live `db-check --json` | yes | green |

*Status values: pending, green, red, flaky.*

## Coverage Evidence

| Requirement | Primary Evidence |
|-------------|------------------|
| READMODEL-01 | `tests/test_read_model_materialization.py` verifies v5 tables, required columns/indexes, initial dirty queue seeding, fact provenance, fact tiers, idempotency, metric versions, and failure behavior. |
| READMODEL-02 | `tests/test_read_model_materialization.py` verifies source hash stability, semantic revision bumps, dirty queue dedupe/reset, stream/detail/channel dirty enqueue, metric-version recompute, and rollback on dirty enqueue failure. |
| READMODEL-03 | `tests/test_refresh_runtime.py` verifies materialization after schema validation, resume from materialization checkpoint, fail-closed lost lease behavior, backfill materialization, and stream-channel backfill materialization. |
| READMODEL-04 | `tests/test_metric_services.py`, `tests/test_mcp_surface.py`, and `tests/test_security_guards.py` verify all five MCP service paths use read-model metadata, keep structured envelopes, expose only product tools, and do not import/call raw recompute helpers or raw stream SQL. |
| PERF-01 | `tests/test_mcp_latency_gate.py` verifies warm latency measurement, startup separation, p95 threshold failure, all-tool coverage, and fallback behavior; `tests/test_read_model_queries.py` verifies indexed query plans and no hot `SUBSTR` filters. |
| TEST-06 | Full pytest, Docker smoke, p95 gate, and live DB readiness passed against the current Python 3.14 Docker runtime. |

## Wave 0 Requirements

- [x] Phase 7 schema/migration tests for v5 read-model tables, indexes, idempotency, pinned backup retention, and source row preservation.
- [x] Dirty queue tests for summary/detail writes, full stream replace, stream-channel merge, unavailable channel metadata, and metric-version bumps.
- [x] Materializer failure-injection tests for failed fact writes/run audit paths, retained dirty rows, retry/idempotency, and metric-version coexistence.
- [x] MCP guard tests proving request paths cannot call `enrich_activity`, `daily_report_from_connection`, `weekly_digest`, raw stream aggregate helpers, or recompute/admin surfaces.
- [x] Explicit MCP performance script support for p50/p95/max per warm tool call.
- [x] Query-shape tests using `EXPLAIN QUERY PLAN` for main read-model queries.

## Manual-Only Verifications

All Phase 7 behaviors have automated verification or recorded live runtime command evidence. No manual-only validation remains.

## Validation Audit 2026-05-24

| Metric | Count |
|--------|-------|
| Requirements audited | 6 |
| Covered automated/live command evidence | 6 |
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| Stale pending rows updated | 6 |

## Verification Run 2026-05-24

| Command | Result |
|---------|--------|
| Docker Python 3.14 full pytest with `/opt/docker` mounted read-only | `Python 3.14.5`; `262 passed, 1 skipped in 70.38s` |
| `just test` | Passed; rebuilt `python:3.14-slim` image, recreated healthy `mcp-strava`, MCP smoke returned the five product tools and called `list_workouts`. |
| `just mcp-read-model-perf` | Passed; p95 ms: `get_fitness_state=14.568`, `list_workouts=21.625`, `get_workout_detail=16.764`, `compare_periods=30.171`, `project_fitness_state=13.986`. |
| `docker compose -f deploy/docker-compose.yml exec -T mcp-strava python -m mcp_strava admin db-check --json` | Passed; `user_version=5`, `integrity_result=ok`, `metric_dirty_activities=0`, `activity_metric_facts=599`, `daily_load_facts=515`, `training_model_daily=515`, `rolling_period_facts=4`. |
| `docker compose -f deploy/docker-compose.yml exec -T mcp-strava python --version` | `Python 3.14.5` |

## Validation Sign-Off

- [x] All plans include automated verify commands or completed Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive task commits without an automated check.
- [x] Wave 0 covers all missing Phase 7 validation references.
- [x] No watch-mode flags in verification commands.
- [x] Full Docker pytest suite is green.
- [x] Docker MCP smoke is green.
- [x] Explicit p95 performance gate proves all warm MCP tool calls are below 500 ms.
- [x] Live/runtime migration uses backup, preflight, post-check, parity, and restore instructions; current live DB readiness check is green.
- [x] `nyquist_compliant: true` remains set in frontmatter.

**Approval:** approved 2026-05-24
