# Phase 7: Materialized Metrics Read Model - Context

**Gathered:** 2026-05-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 7 makes MCP training tools fast and trustworthy by adding versioned SQLite read-model facts beside the Strava mirror. Raw Strava mirror tables remain the source of truth. Derived activity metrics, daily load facts, training-model state, and rolling period summaries are materialized after source sync/backfill/migration work, then MCP tools read those prepared facts only.

This phase is not a training-model redesign, not a cache bolted onto MCP handlers, not a Strava/API refresh feature, and not an MCP admin surface. The goal is to remove request-time stream/model recomputation from MCP while preserving factual freshness, completeness, and metric provenance for intelligent agents.

</domain>

<decisions>
## Implementation Decisions

### Expert Panel Routing

- **D-01:** Complex technical decisions in Phase 7 are delegated to an expert-panel lens. The user should be asked only for business/product decisions that cannot be resolved from prior project decisions.
- **D-02:** The Phase 7 expert panel found no blocking product questions. The safe defaults below are locked for planning unless implementation research disproves them.

### Read Model Contract

- **D-03:** Use an in-DB SQLite read model beside the raw Strava mirror, not request-local Python caches, larger MCP timeouts, or a separate storage engine.
- **D-04:** Raw Strava mirror tables remain the source of truth. Materialized facts are replaceable derived projections that can be deleted and rebuilt from mirror data plus the metric algorithm version.
- **D-05:** Phase 7 should advance the runtime schema to a new version, expected as `user_version=5`, with schema inventory covering read-model tables, required columns, required indexes, and row-count reporting.
- **D-06:** Use wide fact tables for hot MCP metrics rather than EAV-only metric storage. EAV may be used only for secondary metadata if the planner proves it helps without slowing hot paths.

### Required Fact Tables

- **D-07:** `activity_source_state` stores one row per activity with `activity_id`, `activity_day`, semantic component hashes where useful, composite `source_hash`, `source_revision`, and change timestamp. Hashes must exclude non-semantic fields such as `synced_at` and `fetched_at`.
- **D-08:** `metric_dirty_activities` is a durable dirty queue keyed by affected activity/day/version, with reason, source revision, metric version, queued time, attempt count, and last error.
- **D-09:** `activity_metric_facts` stores per-activity derived metrics with provenance: source revision/hash, metric version, computed timestamp, completeness status, missing reasons, and current synthetic metrics such as TRIMP, HR zones, HR recovery, vertical speed, cardiac cost, adjusted cardiac cost, cardiac drift, HRR, Z5 seconds, anomaly counts, and volume fields.
- **D-10:** `daily_load_facts` stores per-day and per-scope aggregates: activity counts, stream/HR coverage, observed/effective TRIMP, distance, moving time, elevation, high-zone totals, anomaly totals, and status such as observed/partial/unknown/rest.
- **D-11:** `training_model_daily` stores recursive daily model state such as fitness, fatigue, form, ATL/CTL, ACWR, effective TRIMP, and related model inputs.
- **D-12:** `rolling_period_facts` stores fixed rolling windows such as 7/14/28/90 days for common fitness-state and weekly-context reads.
- **D-13:** `read_model_refresh_runs` is an audit/checkpoint table for materialization runs. It is not the source of truth and should not replace source-state or dirty-queue tables.

### Invalidation And Recompute

- **D-14:** Source writes must mark derived facts dirty in the same transaction as the source mutation. Dirty marking as a later best-effort call is not acceptable because it can leave changed source data with no recompute queued.
- **D-15:** Repository-level source-write APIs should compute semantic source hashes, bump source revisions, and enqueue dirty work atomically for summaries, details, stream replacement, stream-channel merge, unavailable-channel metadata, and metric-version changes.
- **D-16:** Dirty rows are cleared only after fact writes and refresh-run audit state commit successfully.
- **D-17:** Activity source changes recompute activity facts; changed activity facts recompute affected daily facts; changed effective load recomputes training model state from the earliest affected day forward; rolling facts are recomputed for windows whose range includes affected days.
- **D-18:** Metric algorithm/config changes bump `metric_version` and require historical recompute before Phase 7 is considered accepted. Mixed metric versions in a comparison must be degraded or suppressed with metadata; never silently compare old-formula and new-formula facts.
- **D-19:** Long materialization/backfill work must renew or otherwise safely hold the refresh/write lease. Lease expiry during recompute must not allow a second writer to create inconsistent source/fact state.

### Refresh Runtime Integration

- **D-20:** Add a read-model materialization stage after source mirror writes and schema validation, before kudos/admin-adjacent work. Training facts do not depend on kudos.
- **D-21:** Daily refresh, full backfill, stream-channel backfill, and source-changing migrations must all use the same invalidation/materialization machinery.
- **D-22:** Refresh success and MCP freshness metadata must distinguish mirror freshness from read-model freshness. A mirror can be fresh while derived facts are stale or partially unavailable.
- **D-23:** MCP must not expose recompute, dirty queue, materialization, coverage, backfill, sync, SQL, raw, or admin controls. Operational recompute surfaces, if any, remain local admin/CLI/runtime only.

### MCP Request Path

- **D-24:** After Phase 7, MCP tools must not scan raw `streams` rows or call stream-heavy computation helpers during request handling.
- **D-25:** MCP-facing service paths should be structurally incapable of fallback recompute from raw streams. Guardrails should block request-time use of `enrich_activity`, `daily_report_from_connection`, `weekly_digest`, `check_z5_minutes`, `check_hr_anomalies`, stream aggregate helpers, and raw `streams` reads in MCP read paths.
- **D-26:** Missing or stale read-model facts return fast partial data with explicit completeness/read-model metadata. They must not trigger inline recompute. A whole absent read model may make a tool unavailable, but partial/stale metrics should be represented factually wherever possible.
- **D-27:** Each metric exposed through MCP should carry or be joinable to: value, unit, status, missing reasons, coverage/sample counts, source revision, metric version, and materialized timestamp.
- **D-28:** MCP response metadata should include read-model status, last materialized timestamp, dirty count, oldest dirty date, metric versions present, and stale reason where applicable.
- **D-29:** Keep mirror freshness and read-model freshness separate in envelopes. Intelligent agents need both to decide how much to trust the data.
- **D-30:** `project_fitness_state` may keep a bounded request-time forward simulation, expected within the existing short horizon, if it starts from materialized baseline facts and does not recompute raw-stream metrics.

### Performance And Query Shape

- **D-31:** The Phase 7 product SLO is each MCP tool completing below 500 ms p95 on the current local mirror for warm tool calls. MCP session startup can be measured separately and must not hide tool-call latency.
- **D-32:** Add an explicit performance gate separate from the fast Docker smoke. It should call every MCP tool repeatedly against a copy of the current live mirror or the canonical Docker runtime DB and fail if any tool exceeds the 500 ms p95 target.
- **D-33:** New MCP read queries should use indexed half-open ranges such as `date >= ? AND date < ?`. Avoid `SUBSTR(date,1,10)` in `WHERE` clauses on hot paths.
- **D-34:** Add indexes for activity date/sport lookups and read-model fact access, including at least activity date/id, activity sport/date/id, activity metric facts by day/sport/version, daily facts by day/scope/sport/version, model facts by day/scope/sport/version, rolling facts by as-of/window/scope/sport/version, and dirty queue lookup indexes.
- **D-35:** Planner should include `EXPLAIN QUERY PLAN` checks or equivalent query-shape tests for the main read-model queries. Hot MCP reads should not scan raw streams.

### Migration, Backup, And QA Gates

- **D-36:** Phase 7 migration must use the established preflight, backup, migration, post-check, and parity discipline. It must not mutate the live mirror without a backup.
- **D-37:** Pin the last known-good pre-Phase-7 backup outside normal retention until Phase 7 migration, materialization, parity, performance, and live Docker smoke are accepted.
- **D-38:** Migration v5 should create read-model tables/indexes idempotently without rewriting source rows unless strictly required. Initial materialization/backfill should be a separate, resumable step.
- **D-39:** Phase 7 parity checks must include key MCP outputs and read-model facts, not only row counts or existing low-level load snapshots.
- **D-40:** Tests must cover dirty queue behavior for summary/detail updates, full stream replace, channel merge, unavailable channel metadata, source hash stability, metric-version bumps, idempotent recompute, failure injection, rollback/restore, and stale facts not marked fresh.
- **D-41:** Runtime verification must remain Docker-first. Repo tests use temp or copied databases; live data under `/opt/docker/mcp-strava` is touched only through explicit backup/preflight/runtime validation.

### Product-Neutral Agent Contract

- **D-42:** MCP remains factual and product-neutral. It exposes prepared metrics, units, directionality, comparison semantics, provenance, coverage, deltas, and warnings; it does not produce coaching advice, readiness judgments, motivation, or medical interpretation.
- **D-43:** Directionality metadata is allowed as registry/fact context, but the service must not turn it into claims such as "you improved" or "you should train/rest."
- **D-44:** For period comparisons, include values for both periods, delta, delta percentage where meaningful, sample sizes, coverage, missing reasons, metric version status, and whether comparison was global/per-sport.

### the agent's Discretion

Planner may choose exact table/column names, index names, batching size, p95 sample count, migration command names, read-model repository module names, and the detailed JSON shape of read-model metadata. These choices must preserve the locked constraints above: SQLite primary mirror, source-provenanced facts, atomic invalidation, no MCP recompute/admin controls, explicit partial/stale metadata, and sub-500ms warm MCP tool calls.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project And Phase Scope

- `.planning/PROJECT.md` - Project goals, durable mirror constraint, MCP boundary, Docker runtime location, and current refresh policy.
- `.planning/REQUIREMENTS.md` - Validated v1/v1.1 requirements, MCP/admin exclusions, and data-preservation constraints.
- `.planning/ROADMAP.md` - Phase 7 goal, success criteria, and cross-cutting constraints.
- `.planning/STATE.md` - Current phase routing and project status.
- `.planning/phases/07-materialized-metrics-read-model/07-PANEL.md` - Initial expert panel synthesis for read-model architecture, invalidation, SQL, QA, and acceptance criteria.

### Prior Phase Context

- `.planning/phases/06-full-fidelity-strava-mirror/06-CONTEXT.md` - Lossless normalized mirror, SQLite primary, stream/channel/GPS storage, and no-MCP-admin boundary.
- `.planning/phases/05-mcp-http-surface-docker-hardening/05-CONTEXT.md` - MCP five-tool surface, metric registry contract, no coaching/admin/raw/sync tools, Docker runtime path, and gateway boundary.
- `.planning/phases/04-application-services-cli-refit/04-CONTEXT.md` - Product service envelopes, product/admin split, factual freshness/completeness metadata, and Strava-free read paths.
- `.planning/phases/03-strava-adapter-refresh-runtime/03-CONTEXT.md` - Refresh runtime, leases, checkpoints, rate limits, and no-sync MCP boundary.
- `.planning/phases/02-sqlite-safety-repository-layer/02-CONTEXT.md` - Durable SQLite mirror, migration backup/preflight/parity discipline, fail-closed DB behavior, and missing-data semantics.

### Current Code

- `src/mcp_strava/application/metric_services.py` - Current MCP service implementation that still performs request-time daily report, weekly digest, enrichment, and comparison recomputation.
- `src/mcp_strava/application/metric_registry.py` - Metric registry with units, scope, comparison mode, directionality, missing reasons, and tool exposure.
- `src/mcp_strava/interfaces/mcp_http.py` - MCP allowlist, read-only tool registration, forbidden admin names, and tool-call logging.
- `src/mcp_strava/devtools/mcp_client/client.py` - Reusable MCP SDK client and smoke harness to extend with latency gates.
- `src/mcp_strava/adapters/sqlite/repository.py` - Source write/read boundary, stream replacement/merge methods, existing hot stream aggregate helpers, refresh state, and current SQL shape.
- `src/mcp_strava/adapters/sqlite/schema.py` - Schema inventory, required tables/columns/indexes, and row-count helpers to extend for read-model v5.
- `src/mcp_strava/adapters/sqlite/migrations.py` - Existing backup/preflight/migration/post-check/parity style to extend for Phase 7.
- `src/mcp_strava/adapters/sqlite/backup.py` - Backup retention behavior; Phase 7 must pin the pre-Phase-7 backup outside normal retention.
- `src/mcp_strava/refresh/runtime.py` - Daily refresh/backfill/stream-channel backfill sequencing, lease behavior, and checkpoint handling.
- `src/mcp_strava/refresh/_sync_ops.py` - Source mirror write orchestration for summaries, streams, details, schema validation, kudos, and stream-channel backfill.
- `src/mcp_strava/refresh/checkpoints.py` - Existing stage enum to extend with read-model materialization.
- `src/mcp_strava/metrics.py` - Expensive per-activity enrichment and stream-derived metric helpers that must move out of MCP request paths.
- `src/mcp_strava/report.py` - Current daily report path used by MCP services today; should not remain in hot MCP reads after Phase 7.
- `src/mcp_strava/analytics.py` - Current weekly digest and activity metric aggregation path; should be replaced by read-model facts for MCP.
- `src/mcp_strava/training.py` - Banister/model calculations; use existing formulas for materialization and bounded projection from materialized baselines.

### Tests And Verification

- `tests/test_metric_services.py` - Existing MCP service behavior tests to update for read-model-backed responses and no raw recompute fallback.
- `tests/test_mcp_surface.py` - MCP allowlist/forbidden surface tests to preserve and extend with recompute/admin forbidden names.
- `tests/test_mcp_test_client.py` - MCP SDK client tests to extend for latency and script assertions.
- `tests/test_sqlite_safety.py` - Existing backup/preflight/parity tests to extend for v5 read-model migration and pinned backups.
- `tests/test_full_fidelity_mirror.py` - Phase 6 stream/GPS/channel safety tests that protect source mirror semantics while adding derived facts.
- `tests/test_refresh_runtime.py` - Refresh/backfill/rate-limit tests to extend for read-model materialization and dirty queue behavior.
- `tests/test_security_guards.py` - Import/boundary guard tests to extend so MCP paths cannot depend on raw sync/admin/recompute/stream-heavy helpers.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- Existing SQLite migration tooling already performs backup, preflight, migration, post-check, and parity validation. Phase 7 should extend this path rather than adding ad hoc live DB edits.
- Existing refresh runtime has stages, leases, checkpoints, and backfill flows. Phase 7 should add materialization as a runtime stage instead of making MCP aware of recompute.
- Existing metric registry is the right source for metric units, scope, comparison mode, directionality, requirements, missing reasons, and tool exposure.
- Existing MCP SDK devtools client is the right place to add performance smoke scripts and latency assertions.
- Existing service envelope concept already carries freshness/completeness/warnings/rationale. Phase 7 should add read-model provenance/freshness metadata to that contract.

### Established Patterns

- Product/MCP read paths must remain Strava-free and sync-free.
- MCP is an explicit read-only allowlist and must not grow admin/debug/recompute tools.
- Missing HR/streams/details/facts are represented as partial/unavailable/stale metadata, not zeros or silent fallbacks.
- Runtime data lives under `/opt/docker/mcp-strava`; tests should use temp/copied DBs and live validation should be Docker-first.
- The service may change internal schema/API shapes freely because there are no backward-compatibility obligations, but source data must be preserved.

### Integration Points

- Read-model schema and indexes connect through `adapters/sqlite/schema.py` and `adapters/sqlite/migrations.py`.
- Source-write invalidation connects through repository write methods, not through MCP handlers.
- Materialization connects through `refresh/runtime.py` after source mirror stability and schema validation.
- MCP services connect to read-model repository methods and should no longer call raw enrichment/report/digest paths.
- Performance validation connects through `devtools/mcp_client` and Docker runtime smoke.

</code_context>

<specifics>
## Specific Ideas

- Treat Phase 7 as a trust-contract phase as much as a latency phase: intelligent agents need to know whether each metric is complete, partial, stale, unavailable, or computed under a different metric version.
- Return partial/stale facts with explicit metadata by default. Do not fail a whole tool merely because one metric is stale or missing, and do not recompute inline to hide read-model lag.
- Warm tool-call latency is the product SLO for `<500ms p95`; MCP session startup should be measured separately.
- Pin the pre-Phase-7 backup until migration, materialization, parity, performance, and Docker smoke are accepted.
- During Phase 7 implementation, full historical recompute is required before the phase is accepted. Later background/staged recompute policies can be revisited only if needed.
- Kudos are not part of training metric freshness for Phase 7.

</specifics>

<deferred>
## Deferred Ideas

- DuckDB remains deferred as a possible future analytics/read-model layer. Phase 7 should use SQLite read-model tables first.
- Coaching/advice/recommendation interpretation remains outside MCP and belongs to the consuming intelligent agent.
- Public multi-user serving, hosted auth, and SaaS concerns remain out of scope.
- A future staged background recompute policy for very large history or multi-user deployments can be considered later; Phase 7 acceptance requires full recompute and validation.

</deferred>

---

*Phase: 07-Materialized Metrics Read Model*
*Context gathered: 2026-05-24*
