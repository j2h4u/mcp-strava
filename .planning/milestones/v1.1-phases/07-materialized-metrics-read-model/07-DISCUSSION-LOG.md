# Phase 7: Materialized Metrics Read Model - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-24
**Phase:** 07-materialized-metrics-read-model
**Areas discussed:** expert panel routing, read-model architecture, MCP partial/stale behavior, refresh integration, migration and performance gates

---

## Expert Panel Routing

| Option | Description | Selected |
|--------|-------------|----------|
| Ask the user every technical gray area | Interactive but too noisy for architecture/storage internals | |
| Expert panel handles technical complexity | Technical experts resolve architecture/database/MCP/QA tradeoffs; user is asked only for true business decisions | ✓ |
| Agent decides alone | Fast, but weaker for subtle architecture and data-safety questions | |

**User's choice:** Use an expert panel for all complex questions and ask the user only about business/product decisions.
**Notes:** The panel covered SQLite/read-model design, MCP/performance, refresh/runtime, QA/data safety, and product/agent-user needs.

---

## MCP Partial Or Stale Facts

| Option | Description | Selected |
|--------|-------------|----------|
| Return partial/stale metadata | Return available facts quickly and mark stale/missing metrics explicitly | ✓ |
| Fail the whole tool | Strict but less useful for intelligent agents and brittle during backfill | |
| Compute inline | Hides staleness but recreates the current 20-50 second request path | |

**User's choice:** Delegated to expert panel and prior product decisions.
**Notes:** Panel consensus: return fast partial/stale factual metadata; never trigger raw-stream recompute from MCP. A wholly absent read model may make a tool unavailable, but stale or missing individual metrics should be represented in completeness/read-model metadata.

---

## Read Model Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| SQLite read model beside mirror | Source mirror remains canonical; derived facts are materialized and rebuildable | ✓ |
| Request-local Python cache | Lower effort but does not solve invalidation, process restarts, or cold requests | |
| Separate database/storage engine now | Potential future analytics path, but extra complexity before SQLite read-model proof | |

**User's choice:** Delegated to expert panel.
**Notes:** Panel consensus: use SQLite read-model tables with source revision/hash, metric version, durable dirty queue, activity/day/model/rolling facts, and read-model run audit.

---

## Refresh And Recompute Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Source writes atomically enqueue dirty work | Prevents changed source rows from escaping recompute tracking | ✓ |
| Best-effort dirty enqueue after writes | Simpler but can leave silently stale facts after crash | |
| MCP recomputes when facts missing | Violates Phase 7 latency and MCP boundary | |

**User's choice:** Delegated to expert panel.
**Notes:** Materialization belongs after source mirror writes and schema validation, before kudos/admin-adjacent work. Dirty rows clear only after fact writes and refresh-run audit commit.

---

## Performance Gate

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit 500 ms p95 gate | Measures every MCP tool repeatedly and fails slow read-model paths | ✓ |
| Keep smoke-only testing | Verifies transport but misses slow-tool regressions | |
| Use large timeout as acceptance | Masks the actual product problem | |

**User's choice:** Prior user feedback set the target: any MCP tool should complete under about 500 ms.
**Notes:** The locked target is `<500ms p95` for warm tool calls. Session startup should be measured separately.

---

## Migration And Backup Discipline

| Option | Description | Selected |
|--------|-------------|----------|
| Pin pre-Phase-7 backup until acceptance | Safest while adding schema/read-model materialization | ✓ |
| Rely on default retention only | Can rotate away the last known-good restore point during repeated attempts | |
| Delete backups before migration | Not acceptable while Phase 7 changes live DB shape | |

**User's choice:** Delegated to expert panel and prior data-preservation constraints.
**Notes:** Phase 7 should keep a pinned last known-good backup until migration, materialization, parity, performance, and Docker smoke pass.

---

## the agent's Discretion

- Exact table/column names, index names, batching size, p95 sample count, migration command names, read-model repository module names, and JSON metadata shape remain planner discretion.
- Planner must preserve the locked constraints: SQLite primary mirror, source-provenanced facts, atomic invalidation, no MCP recompute/admin controls, explicit partial/stale metadata, and sub-500ms warm MCP tool calls.

## Deferred Ideas

- DuckDB as a future analytics/read-model layer.
- Coaching/advice/recommendation interpretation in the MCP server.
- Public multi-user or hosted SaaS concerns.
- Staged background recompute policy for future much larger deployments.
