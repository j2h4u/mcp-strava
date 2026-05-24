---
phase: 07
slug: materialized-metrics-read-model
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-24
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + Docker MCP smoke |
| **Config file** | `pyproject.toml`, `Justfile`, `deploy/docker-compose.yml` |
| **Quick run command** | `uv run pytest -q tests/test_metric_services.py tests/test_refresh_runtime.py tests/test_mcp_surface.py tests/test_security_guards.py` |
| **Full suite command** | `uv run pytest -q && just test` |
| **Explicit performance gate** | new Phase 7 MCP warm p95 gate, expected to run outside `just test` until read-model work lands |
| **Estimated runtime** | quick ~30s, full + Docker smoke depends on local image/cache |

---

## Sampling Rate

- **After every task commit:** Run the quick pytest command relevant to the touched layer.
- **After every plan wave:** Run `uv run pytest -q && just test`.
- **Before `$gsd-validate-phase 7`:** Full suite and explicit MCP p95 gate must be green.
- **Max feedback latency:** 120 seconds for quick local tests; Docker/perf gates may be longer but must be explicit.

---

## Per-Requirement Verification Map

| Requirement | Required Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|-------------------|------------|-----------------|-----------|-------------------|-------------|--------|
| READMODEL-01 | Activity-level metric facts persist with source revision/hash, metric version, computed timestamp, completeness, missing reasons, and current synthetic metrics | T-07-01 | Derived facts are rebuildable and cannot masquerade as source data | migration/integration | `uv run pytest -q tests/test_metric_services.py tests/test_sqlite_safety.py` | W0 | pending |
| READMODEL-02 | Source writes atomically update source state and enqueue dirty rows for summaries, details, streams, channel metadata, and metric-version bumps | T-07-02 | No changed source row can commit without dirty invalidation | integration/failure | `uv run pytest -q tests/test_refresh_runtime.py tests/test_sqlite_safety.py` | W0 | pending |
| READMODEL-03 | Refresh/backfill/migration materializes activity, daily, model, and rolling facts under lease/checkpoint control | T-07-03 | Dirty rows clear only after fact writes and run audit commit | integration/failure | `uv run pytest -q tests/test_refresh_runtime.py` | W0 | pending |
| READMODEL-04 | MCP tools read materialized facts only and do not scan raw streams or call stream-heavy recompute helpers | T-07-04 | MCP remains read-only and cannot trigger recompute/admin/source writes | unit/guard | `uv run pytest -q tests/test_metric_services.py tests/test_mcp_surface.py tests/test_security_guards.py` | W0 | pending |
| PERF-01 | Each MCP tool completes below 500 ms p95 for warm calls on the current local mirror/copy | T-07-05 | Slow raw-stream fallback is detected before acceptance | perf/smoke | new p95 gate via `src/mcp_strava/devtools/mcp_client` plus `EXPLAIN QUERY PLAN` checks | W0 | pending |
| TEST-06 | Migration, dirty queue, materializer failure, MCP surface, and Docker smoke are covered without live Strava calls | T-07-06 | Tests protect source data, secrets, and MCP boundary | suite/smoke | `uv run pytest -q && just test` | W0 | pending |

*Status values: pending, green, red, flaky.*

---

## Wave 0 Requirements

- [ ] Add Phase 7 schema/migration tests for v5 read-model tables, indexes, idempotency, backup creation, and source row-count preservation.
- [ ] Add dirty queue tests for summary/detail writes, full stream replace, stream-channel merge, unavailable channel metadata, and metric-version bumps.
- [ ] Add materializer failure-injection tests for crash after fact write, crash before dirty clear, failed run audit, and retry/idempotency.
- [ ] Add MCP guard tests proving request paths cannot call `enrich_activity`, `daily_report_from_connection`, `weekly_digest`, raw stream aggregate helpers, or recompute/admin surfaces.
- [ ] Add explicit MCP performance script support for p50/p95/max per warm tool call.
- [ ] Add query-shape tests or admin checks using `EXPLAIN QUERY PLAN` for main read-model queries.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live backup pin before Phase 7 migration | READMODEL-01, TEST-06 | Live runtime backup retention is operator-visible and must protect `/opt/docker/mcp-strava` data | Confirm the pre-Phase-7 backup exists outside normal retention before live migration; do not delete it until Phase 7 acceptance. |
| Live Docker MCP p95 smoke on current mirror | PERF-01, TEST-06 | Uses the real runtime volume and local MCP container path | After migration/materialization on a backed-up runtime DB, run the explicit p95 gate against Docker MCP and record p50/p95/max for all five tools. |

---

## Validation Sign-Off

- [ ] All plans include automated verify commands or Wave 0 dependencies.
- [ ] Sampling continuity: no 3 consecutive task commits without an automated check.
- [ ] Wave 0 covers all missing Phase 7 validation references.
- [ ] No watch-mode flags in verification commands.
- [ ] Full suite is green: `uv run pytest -q && just test`.
- [ ] Explicit p95 performance gate proves all warm MCP tool calls are below 500 ms.
- [ ] Live/runtime migration uses backup, preflight, post-check, parity, and restore instructions.
- [ ] `nyquist_compliant: true` remains set in frontmatter.

**Approval:** pending
