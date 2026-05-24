# Phase 07: materialized-metrics-read-model - Research

**Researched:** 2026-05-24
**Domain:** SQLite materialized read models for MCP metric-serving
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Complex technical decisions in Phase 7 are delegated to an expert-panel lens. The user should be asked only for business/product decisions that cannot be resolved from prior project decisions.
- **D-02:** The Phase 7 expert panel found no blocking product questions. The safe defaults below are locked for planning unless implementation research disproves them.

- **D-03:** Use an in-DB SQLite read model beside the raw Strava mirror, not request-local Python caches, larger MCP timeouts, or a separate storage engine.
- **D-04:** Raw Strava mirror tables remain the source of truth. Materialized facts are replaceable derived projections that can be deleted and rebuilt from mirror data plus the metric algorithm version.
- **D-05:** Phase 7 should advance the runtime schema to a new version, expected as `user_version=5`, with schema inventory covering read-model tables, required columns, required indexes, and row-count reporting.
- **D-06:** Use wide fact tables for hot MCP metrics rather than EAV-only metric storage. EAV may be used only for secondary metadata if the planner proves it helps without slowing hot paths.

- **D-07:** `activity_source_state` stores one row per activity with `activity_id`, `activity_day`, semantic component hashes where useful, composite `source_hash`, `source_revision`, and change timestamp. Hashes must exclude non-semantic fields such as `synced_at` and `fetched_at`.
- **D-08:** `metric_dirty_activities` is a durable dirty queue keyed by affected activity/day/version, with reason, source revision, metric version, queued time, attempt count, and last error.
- **D-09:** `activity_metric_facts` stores per-activity derived metrics with provenance: source revision/hash, metric version, computed timestamp, completeness status, missing reasons, and current synthetic metrics such as TRIMP, HR zones, HR recovery, vertical speed, cardiac cost, adjusted cardiac cost, cardiac drift, HRR, Z5 seconds, anomaly counts, and volume fields.
- **D-10:** `daily_load_facts` stores per-day and per-scope aggregates: activity counts, stream/HR coverage, observed/effective TRIMP, distance, moving time, elevation, high-zone totals, anomaly totals, and status such as observed/partial/unknown/rest.
- **D-11:** `training_model_daily` stores recursive daily model state such as fitness, fatigue, form, ATL/CTL, ACWR, effective TRIMP, and related model inputs.
- **D-12:** `rolling_period_facts` stores fixed rolling windows such as 7/14/28/90 days for common fitness-state and weekly-context reads.
- **D-13:** `read_model_refresh_runs` is an audit/checkpoint table for materialization runs. It is not the source of truth and should not replace source-state or dirty-queue tables.

- **D-14:** Source writes must mark derived facts dirty in the same transaction as the source mutation. Dirty marking as a later best-effort call is not acceptable because it can leave changed source data with no recompute queued.
- **D-15:** Repository-level source-write APIs should compute semantic source hashes, bump source revisions, and enqueue dirty work atomically for summaries, details, stream replacement, stream-channel merge, unavailable-channel metadata, and metric-version changes.
- **D-16:** Dirty rows are cleared only after fact writes and refresh-run audit state commit successfully.
- **D-17:** Activity source changes recompute activity facts; changed activity facts recompute affected daily facts; changed effective load recomputes training model state from the earliest affected day forward; rolling facts are recomputed for windows whose range includes affected days.
- **D-18:** Metric algorithm/config changes bump `metric_version` and require historical recompute before Phase 7 is considered accepted. Mixed metric versions in a comparison must be degraded or suppressed with metadata; never silently compare old-formula and new-formula facts.
- **D-19:** Long materialization/backfill work must renew or otherwise safely hold the refresh/write lease. Lease expiry during recompute must not allow a second writer to create inconsistent source/fact state.

- **D-20:** Add a read-model materialization stage after source mirror writes and schema validation, before kudos/admin-adjacent work. Training facts do not depend on kudos.
- **D-21:** Daily refresh, full backfill, stream-channel backfill, and source-changing migrations must all use the same invalidation/materialization machinery.
- **D-22:** Refresh success and MCP freshness metadata must distinguish mirror freshness from read-model freshness. A mirror can be fresh while derived facts are stale or partially unavailable.
- **D-23:** MCP must not expose recompute, dirty queue, materialization, coverage, backfill, sync, SQL, raw, or admin controls. Operational recompute surfaces, if any, remain local admin/CLI/runtime only.

- **D-24:** After Phase 7, MCP tools must not scan raw `streams` rows or call stream-heavy computation helpers during request handling.
- **D-25:** MCP-facing service paths should be structurally incapable of fallback recompute from raw streams. Guardrails should block request-time use of `enrich_activity`, `daily_report_from_connection`, `weekly_digest`, `check_z5_minutes`, `check_hr_anomalies`, stream aggregate helpers, and raw `streams` reads in MCP read paths.
- **D-26:** Missing or stale read-model facts return fast partial data with explicit completeness/read-model metadata. They must not trigger inline recompute. A whole absent read model may make a tool unavailable, but partial/stale metrics should be represented factually wherever possible.
- **D-27:** Each metric exposed through MCP should carry or be joinable to: value, unit, status, missing reasons, coverage/sample counts, source revision, metric version, and materialized timestamp.
- **D-28:** MCP response metadata should include read-model status, last materialized timestamp, dirty count, oldest dirty date, metric versions present, and stale reason where applicable.
- **D-29:** Keep mirror freshness and read-model freshness separate in envelopes. Intelligent agents need both to decide how much to trust the data.
- **D-30:** `project_fitness_state` may keep a bounded request-time forward simulation, expected within the existing short horizon, if it starts from materialized baseline facts and does not recompute raw-stream metrics.

- **D-31:** The Phase 7 product SLO is each MCP tool completing below 500 ms p95 on the current local mirror for warm tool calls. MCP session startup can be measured separately and must not hide tool-call latency.
- **D-32:** Add an explicit performance gate separate from the fast Docker smoke. It should call every MCP tool repeatedly against a copy of the current live mirror or the canonical Docker runtime DB and fail if any tool exceeds the 500 ms p95 target.
- **D-33:** New MCP read queries should use indexed half-open ranges such as `date >= ? AND date < ?`. Avoid `SUBSTR(date,1,10)` in `WHERE` clauses on hot paths.
- **D-34:** Add indexes for activity date/sport lookups and read-model fact access, including at least activity date/id, activity sport/date/id, activity metric facts by day/sport/version, daily facts by day/scope/sport/version, model facts by day/scope/sport/version, rolling facts by as-of/window/scope/sport/version, and dirty queue lookup indexes.
- **D-35:** Planner should include `EXPLAIN QUERY PLAN` checks or equivalent query-shape tests for the main read-model queries. Hot MCP reads should not scan raw streams.

- **D-36:** Phase 7 migration must use the established preflight, backup, migration, post-check, and parity discipline. It must not mutate the live mirror without a backup.
- **D-37:** Pin the last known-good pre-Phase-7 backup outside normal retention until Phase 7 migration, materialization, parity, performance, and live Docker smoke are accepted.
- **D-38:** Migration v5 should create read-model tables/indexes idempotently without rewriting source rows unless strictly required. Initial materialization/backfill should be a separate, resumable step.
- **D-39:** Phase 7 parity checks must include key MCP outputs and read-model facts, not only row counts or existing low-level load snapshots.
- **D-40:** Tests must cover dirty queue behavior for summary/detail updates, full stream replace, channel merge, unavailable channel metadata, source hash stability, metric-version bumps, idempotent recompute, failure injection, rollback/restore, and stale facts not marked fresh.
- **D-41:** Runtime verification must remain Docker-first. Repo tests use temp or copied databases; live data under `/opt/docker/mcp-strava` is touched only through explicit backup/preflight/runtime validation.

- **D-42:** MCP remains factual and product-neutral. It exposes prepared metrics, units, directionality, comparison semantics, provenance, coverage, deltas, and warnings; it does not produce coaching advice, readiness judgments, motivation, or medical interpretation.
- **D-43:** Directionality metadata is allowed as registry/fact context, but the service must not turn it into claims such as "you improved" or "you should train/rest."
- **D-44:** For period comparisons, include values for both periods, delta, delta percentage where meaningful, sample sizes, coverage, missing reasons, metric version status, and whether comparison was global/per-sport.

### the agent's Discretion

Planner may choose exact table/column names, index names, batching size, p95 sample count, migration command names, read-model repository module names, and the detailed JSON shape of read-model metadata. These choices must preserve the locked constraints above: SQLite primary mirror, source-provenanced facts, atomic invalidation, no MCP recompute/admin controls, explicit partial/stale metadata, and sub-500ms warm MCP tool calls.

### Deferred Ideas (OUT OF SCOPE)

- DuckDB remains deferred as a possible future analytics/read-model layer. Phase 7 should use SQLite read-model tables first.
- Coaching/advice/recommendation interpretation remains outside MCP and belongs to the consuming intelligent agent.
- Public multi-user serving, hosted auth, and SaaS concerns remain out of scope.
- A future staged background recompute policy for very large history or multi-user deployments can be considered later; Phase 7 acceptance requires full recompute and validation.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| READMODEL-01 | Persist activity-level derived metrics with provenance/version metadata | Standard Stack, Architecture Patterns, Don’t Hand-Roll, Common Pitfalls |
| READMODEL-02 | Durable dirty invalidation contract (`source_hash`, `source_revision`, `metric_version`) | Architecture Patterns, Common Pitfalls, Security Domain |
| READMODEL-03 | Refresh runtime materializes all read-model tiers after sync/backfill | Architecture Patterns, Environment Availability, Validation Architecture |
| READMODEL-04 | MCP reads materialized facts only; no request-time stream recompute | Don’t Hand-Roll, Common Pitfalls, Validation Architecture |
| PERF-01 | Each MCP tool under 500ms p95 on local mirror with explicit gate | Standard Stack, Validation Architecture, Environment Availability |
| TEST-06 | Tests + Docker smoke validate correctness/latency/boundary guards | Validation Architecture, Security Domain, Common Pitfalls |
</phase_requirements>

## Summary

Phase 7 is a data-contract phase, not a feature-add phase: the existing runtime already has source sync staging, migration safety, and MCP allowlist controls, but MCP services still recompute stream-heavy metrics on request and read raw streams indirectly. Moving derived metrics into materialized SQLite read-model facts is the correct boundary move for both latency and trust metadata. [CITED: src/mcp_strava/refresh/runtime.py] [CITED: src/mcp_strava/application/metric_services.py] [CITED: src/mcp_strava/interfaces/mcp_http.py]

The strongest implementation strategy is: (1) schema v5 adds read-model fact tables + dirty queue + source state + refresh-run audit; (2) repository write methods atomically enqueue dirties inside the same transaction as source writes; (3) refresh runtime gains a materialization stage with lease renewal and resumable progress; (4) MCP services switch to read-model queries only and return explicit completeness/staleness metadata. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md] [CITED: src/mcp_strava/adapters/sqlite/repository.py] [CITED: src/mcp_strava/refresh/checkpoints.py]

SQLite performance guardrails should be made testable and deterministic: hot queries must use range predicates on indexed date columns and be checked with `EXPLAIN QUERY PLAN` assertions; avoid `SUBSTR(date,1,10)` on hot paths because it blocks straightforward index use in this codebase. [CITED: https://sqlite.org/eqp.html] [CITED: https://www.sqlite.org/queryplanner.html] [CITED: src/mcp_strava/adapters/sqlite/repository.py]

**Primary recommendation:** Implement read-model v5 as an internal SQLite projection pipeline behind repository + refresh runtime boundaries, then cut MCP services to read-only fact queries with explicit stale/partial metadata. [HIGH]

## Project Constraints (from AGENTS.md)

- Never delete/overwrite `data/strava.db`; migration requires backup + preflight + verification. [CITED: AGENTS.md]
- Avoid designs that force full Strava resync due to API rate limits. [CITED: AGENTS.md]
- MCP must expose only workouts/analytics/reports/recommendations; no sync/admin/debug operations. [CITED: AGENTS.md]
- Freshness policy belongs in core/application logic, not MCP tool design. [CITED: AGENTS.md]
- Keep `just test` as baseline verification and add targeted tests for migrations/freshness/MCP tooling. [CITED: AGENTS.md]
- No project skill rules are present in `.codex/skills` or `.agents/skills`. [CITED: AGENTS.md]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Source write + dirty invalidation | Database/Storage | API/Backend | Must be atomic with source write transaction. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md] |
| Fact materialization orchestration | API/Backend | Database/Storage | Runtime controls lease/checkpoint flow and commits facts. [CITED: src/mcp_strava/refresh/runtime.py] |
| Derived fact persistence/indexes | Database/Storage | — | Read model is SQLite-resident by locked decision. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md] |
| MCP tool response assembly | API/Backend | — | MCP tools should consume prepared facts only. [CITED: src/mcp_strava/interfaces/mcp_http.py] |
| Latency/perf gating | API/Backend | Database/Storage | p95 is measured at tool-call level; query plans determine backend cost. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md] [CITED: https://sqlite.org/eqp.html] |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.13.5 | Runtime for repository/refresh/MCP services | Already active runtime in project and tests. [CITED: local env `python3 --version`] |
| SQLite | user_version 4 -> 5 target | Source mirror + new read model | Existing migration/inventory discipline already centered on SQLite. [CITED: src/mcp_strava/adapters/sqlite/schema.py] |
| `mcp` | 1.27.1 (PyPI latest on 2026-05-08) | MCP server transport/tool contracts | Current dependency and current registry release. [CITED: pyproject.toml] [CITED: https://pypi.org/pypi/mcp/json] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `PyYAML` | 6.0.3 (PyPI latest on 2025-09-25) | Existing config/document parsing dependency | Keep as-is; not central to read-model logic. [CITED: pyproject.toml] [CITED: https://pypi.org/pypi/PyYAML/json] |
| Docker Compose | 29.3.1 engine present | Runtime smoke and p95 gate execution | Use for required Docker-first live validation. [CITED: local env `docker --version`] [CITED: Justfile] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQLite read-model tables | DuckDB sidecar | Explicitly deferred by locked decisions; adds split-store complexity now. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md] |
| Wide fact tables | EAV-first schema | Higher read/query complexity on hot MCP paths; conflicts with locked D-06. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md] |

**Installation:**
```bash
# No new package required for Phase 7 baseline.
# Existing environment uses project deps from pyproject.toml.
```

## Package Legitimacy Audit

No new external package installation is required by this phase baseline. [CITED: pyproject.toml]

## Architecture Patterns

### System Architecture Diagram

```text
Strava Sync/Backfill Source Writes
          |
          v
  SQLiteRepository write methods
  (summary/detail/streams/channel metadata)
          |
          | same transaction
          v
activity_source_state + metric_dirty_activities enqueue
          |
          v
refresh.runtime materialization stage (lease + checkpoint + retries)
          |
          +--> activity_metric_facts
          +--> daily_load_facts
          +--> training_model_daily
          +--> rolling_period_facts
          +--> read_model_refresh_runs
          |
          v
application.metric_services (fact-only queries)
          |
          v
interfaces.mcp_http (5-tool allowlist, no admin/recompute)
```

### Recommended Project Structure
```text
src/mcp_strava/
├── adapters/sqlite/
│   ├── repository.py          # source writes + dirty enqueue + fact reads
│   ├── schema.py              # v5 required tables/columns/indexes
│   └── migrations.py          # backup/preflight/migrate/post-check/parity
├── refresh/
│   ├── runtime.py             # add materialization checkpoint stage
│   └── checkpoints.py         # extend stage enum for read-model materialize
├── application/
│   └── metric_services.py     # read-model-only MCP payload assembly
└── interfaces/mcp_http.py     # unchanged tool allowlist boundary
```

### Pattern 1: Atomic Source-Write Invalidation
**What:** repository write APIs perform source mutation + source hash/revision update + dirty queue enqueue in one transaction. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md]  
**When to use:** every source mutation path (`upsert_activity_summary`, detail update, stream replace/merge, unavailable metadata). [CITED: src/mcp_strava/adapters/sqlite/repository.py]  
**Example:**
```python
# Source: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md (D-14/D-15)
with conn:
    upsert_activity_summary(...)
    update_activity_source_state(...)
    enqueue_metric_dirty(activity_id=..., reason="summary_upsert", metric_version=...)
```

### Pattern 2: Staged Materialization Under Lease
**What:** refresh runtime extends stage graph to include read-model materialization with lease renewal for long work. [CITED: src/mcp_strava/refresh/runtime.py]  
**When to use:** daily refresh, backfill, stream-channel backfill, migration-triggered recompute. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md]  
**Example:**
```python
# Source: src/mcp_strava/refresh/runtime.py + context D-19/D-20/D-21
repo.set_checkpoint("read_model_materialize", cursor)
renewed = repo.renew_refresh_lease(owner, expires_at)
if not renewed:
    raise RuntimeError("refresh lease lost during read-model materialization")
materialize_dirty_queue(...)
repo.set_checkpoint("complete", None)
```

### Pattern 3: MCP Fact-Only Read Path
**What:** MCP services query fact tables and emit completeness metadata, never inline recompute from raw streams. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md]  
**When to use:** all five MCP tools (`get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, `project_fitness_state`). [CITED: src/mcp_strava/interfaces/mcp_http.py]  
**Example:**
```python
# Source: src/mcp_strava/interfaces/mcp_http.py + context D-24..D-29
facts = repo.fetch_activity_metric_facts(...)
if facts_missing:
    completeness.status = "partial"
    completeness.missing.append("read_model_stale")
return ServiceEnvelope(data=..., completeness=completeness, freshness=freshness, ...)
```

### Anti-Patterns to Avoid
- **Request-time stream recompute in MCP:** currently present via `enrich_activity` path; must be removed from MCP service flows. [CITED: src/mcp_strava/application/metric_services.py]
- **Date filtering with `SUBSTR` on hot paths:** hinders index-friendly range scans in this repo query style; switch to half-open raw date comparisons where possible. [CITED: src/mcp_strava/adapters/sqlite/repository.py] [CITED: https://www.sqlite.org/queryplanner.html]
- **Best-effort async dirty marking:** violates atomic invalidation contract and can silently desync source/facts. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Query planner introspection | Custom SQL parser | SQLite `EXPLAIN QUERY PLAN` assertions | Native planner output is purpose-built for index strategy checks. [CITED: https://sqlite.org/eqp.html] |
| Transaction semantics layer | Custom lock manager | Python `sqlite3` transaction control + existing lease rows | Existing runtime already uses DB lease/checkpoint model. [CITED: src/mcp_strava/refresh/runtime.py] [CITED: https://docs.python.org/3/library/sqlite3.html] |
| Parallel analytical cache store | New DB/cache product in Phase 7 | SQLite read-model tables in same DB | Locked decisions require single SQLite mirror/read-model plane now. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md] |

**Key insight:** This phase is correctness-through-boundaries; adding new infrastructure would increase failure modes before the core invariant (atomic invalidation + fact-only MCP) is secured.

## Common Pitfalls

### Pitfall 1: Mixed Metric Versions in Comparisons
**What goes wrong:** comparisons silently combine old and new formula outputs. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md]  
**Why it happens:** missing `metric_version` filters and metadata in fact queries.  
**How to avoid:** enforce version scoping in read queries + explicit “degraded/incomparable” metadata.  
**Warning signs:** delta fields present while period facts come from different versions.

### Pitfall 2: Dirty Queue Not Truly Durable
**What goes wrong:** changed source rows never get recomputed. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md]  
**Why it happens:** dirty enqueue outside transaction or cleared before fact commit.  
**How to avoid:** enqueue in same transaction and clear only after successful fact + run-audit commit.  
**Warning signs:** source revision increments without corresponding dirty record.

### Pitfall 3: Latency Regression Hidden by Session Startup
**What goes wrong:** tool p95 looks acceptable only because startup latency dominates measurement method. [CITED: .planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md]  
**Why it happens:** one-shot smoke without per-tool repeated sampling.  
**How to avoid:** repeated warm tool calls per endpoint and per-call duration tracking.  
**Warning signs:** low sample counts, only end-to-end startup timing reported.

## Code Examples

### Existing MCP Tool Timing Hook (Reuse for PERF-01 gate)
```python
# Source: src/mcp_strava/interfaces/mcp_http.py
started = time.perf_counter()
payload = _envelope_payload(operation())
_emit_log("mcp_tool_call_finished", tool=name, duration_ms=round((time.perf_counter() - started) * 1000, 3))
```

### Existing Refresh Lease Pattern (Extend for Materialization)
```python
# Source: src/mcp_strava/refresh/runtime.py
if not repo.acquire_refresh_lease(owner, expires_at, now_iso):
    return RefreshSkipped("refresh_in_progress")
try:
    ...
finally:
    repo.release_refresh_lease(owner)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Request-time metric recompute from raw streams in service layer | Materialized read-model facts with provenance and completeness metadata | Planned for Phase 7 | Predictable latency and explicit trust semantics |
| Broad date filtering with `SUBSTR` on hot reads | Index-friendly range predicates and query-plan verification | Planned for Phase 7 | Lower p95 and less scan risk |
| “Fresh mirror implies fresh metrics” | Separate mirror freshness and read-model freshness metadata | Planned for Phase 7 | Prevents false confidence in stale derived facts |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No new third-party package is required for Phase 7 implementation | Standard Stack / Package Legitimacy Audit | Low; planner might miss needed dependency task if later design changes |

## Open Questions

1. **Should fact-table partitioning by scope use separate tables or one table with `scope_type/scope_id`?**
   - What we know: locked decisions permit naming/layout discretion but require indexed hot paths.
   - What's unclear: best shape for query simplicity vs index fanout on current mirror size.
   - Recommendation: benchmark both with `EXPLAIN QUERY PLAN` + warm p95 smoke before locking schema.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `python3` | runtime/tests/migrations | ✓ | 3.13.5 | — |
| `just` | baseline smoke gate | ✓ | 1.40.0 | run equivalent Docker commands directly |
| `docker` | Docker-first verification + perf smoke | ✓ | 29.3.1 | none (blocking for live gate) |
| `uv` | project command environment | ✓ | 0.11.3 | use direct python invocation where already supported |
| `pip` | package index probing in this environment | ✗ | — | use PyPI JSON API for version verification |

**Missing dependencies with no fallback:**
- None for planning and code implementation.

**Missing dependencies with fallback:**
- `pip` CLI absent; use `https://pypi.org/pypi/<pkg>/json` for version/date checks.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 8.3.5 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `just test` |
| Full suite command | `PYTHONPATH=src python3 -m pytest tests -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| READMODEL-01 | Activity facts persisted with provenance | unit/integration | `python3 -m pytest tests/test_metric_services.py -q` | ✅ |
| READMODEL-02 | Dirty queue atomic contract | integration | `python3 -m pytest tests/test_refresh_runtime.py -q` | ✅ (needs expansion) |
| READMODEL-03 | Runtime materialization after sync/backfill | integration | `python3 -m pytest tests/test_refresh_runtime.py -q` | ✅ (needs expansion) |
| READMODEL-04 | MCP reads fact tables only | unit/guard | `python3 -m pytest tests/test_security_guards.py tests/test_mcp_surface.py -q` | ✅ (needs expansion) |
| PERF-01 | <500ms p95 per MCP tool | smoke/perf | `just mcp-smoke-full` + new repeated-call perf script | ❌ Wave 0 |
| TEST-06 | End-to-end correctness + Docker smoke | integration/smoke | `just test` | ✅ |

### Sampling Rate
- **Per task commit:** targeted pytest for touched module + boundary guard tests.
- **Per wave merge:** `PYTHONPATH=src python3 -m pytest tests -q`.
- **Phase gate:** `just test` and explicit warm-call p95 perf script across all five MCP tools.

### Wave 0 Gaps
- [ ] `tests/test_read_model_materialization.py` — dirty queue, idempotent recompute, version bump behavior.
- [ ] `tests/test_read_model_queries.py` — query-shape and completeness metadata checks.
- [ ] `tests/test_mcp_latency_gate.py` or devtool script assertions — repeated call p95 per tool.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Local trusted network profile; no new auth in this phase |
| V3 Session Management | no | Stateless MCP HTTP in current design |
| V4 Access Control | yes | MCP allowlist + forbidden tool names + read-only tool annotations |
| V5 Input Validation | yes | strict typed tool args + date range validation in services |
| V6 Cryptography | no | No new crypto in Phase 7 |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Raw/admin MCP capability leakage | Elevation of Privilege | Preserve allowlist and forbidden-name tests in MCP surface |
| Stale fact misrepresentation as fresh | Tampering | Separate mirror freshness from read-model freshness and expose stale reasons |
| Transaction split between source write and dirty mark | Integrity | Single transaction for source mutation + dirty enqueue |
| SQL performance DoS by table scans | Denial of Service | Indexed predicates + `EXPLAIN QUERY PLAN` checks |

## Sources

### Primary (HIGH confidence)
- `.planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md` - locked decisions D-01..D-44
- `src/mcp_strava/adapters/sqlite/repository.py` - current source write/read SQL patterns and `SUBSTR` hotspots
- `src/mcp_strava/refresh/runtime.py` and `src/mcp_strava/refresh/checkpoints.py` - lease/checkpoint orchestration
- `src/mcp_strava/interfaces/mcp_http.py` - MCP allowlist, forbidden names, tool timing logs
- `src/mcp_strava/adapters/sqlite/schema.py` and `src/mcp_strava/adapters/sqlite/migrations.py` - schema inventory and migration discipline
- `tests/test_metric_services.py`, `tests/test_refresh_runtime.py`, `tests/test_mcp_surface.py`, `tests/test_security_guards.py`, `tests/test_sqlite_safety.py` - present validation posture
- https://sqlite.org/eqp.html - EXPLAIN QUERY PLAN usage/warnings
- https://www.sqlite.org/queryplanner.html - planner/index behavior
- https://www.sqlite.org/partialindex.html - partial index behavior and applicability rules
- https://docs.python.org/3/library/sqlite3.html - transaction control guidance
- https://modelcontextprotocol.io/specification/2025-06-18/server/tools - tool `outputSchema` and tool result structure
- https://modelcontextprotocol.io/specification/2025-11-25/schema - schema surface includes `readOnlyHint`
- https://pypi.org/pypi/mcp/json - latest package version/date
- https://pypi.org/pypi/PyYAML/json - latest package version/date

### Secondary (MEDIUM confidence)
- None.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - runtime/dependency/version validated from repo + local env + PyPI API.
- Architecture: HIGH - directly constrained by locked context decisions and current code boundaries.
- Pitfalls: HIGH - derived from observed current codepaths and SQLite official planner docs.

**Research date:** 2026-05-24  
**Valid until:** 2026-06-23
