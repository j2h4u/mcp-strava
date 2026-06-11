# Phase 8: DuckDB Primary Storage & Aggregate Analytics Surface - Context

**Gathered:** 2026-05-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 8 moves the local Strava mirror from SQLite-primary storage to DuckDB-primary storage and adds an aggregate analytics layer for agent-facing MCP metrics. The result should preserve source mirror data, stream/channel coverage, kudos, refresh state, and derived metric facts while making bucketed period queries natural: day, week, month, year, rolling windows, and all-time.

This phase is a storage and aggregate-query cutover, not a training-model redesign, not a raw SQL MCP surface, not a gateway/infrastructure test phase, and not a permanent SQLite plus DuckDB dual-primary design. SQLite remains only migration input, backup, or rollback material after cutover.

</domain>

<decisions>
## Implementation Decisions

### Cutover Policy

- **D-01:** Use a fast one-shot cutover from SQLite to DuckDB, not a long-running dual-primary or shadow-write architecture.
- **D-02:** Fast cutover still requires a pinned verified SQLite backup, a migration from a stable copy or backup, DuckDB post-checks, parity checks, Docker smoke, MCP smoke, and the current 100 ms p95 MCP latency gate before acceptance.
- **D-03:** Stop or quiesce runtime writers before live cutover and prove there is no active refresh lease. An active lease blocks cutover until resolved.
- **D-04:** After cutover, runtime repository, refresh, preflight, healthcheck, Docker, and CLI paths must use DuckDB primary storage. Runtime code must not keep writing SQLite.
- **D-05:** Keep the pre-Phase-8 SQLite backup pinned outside normal retention until migration parity, Docker smoke, MCP smoke, latency gate, and the first accepted post-cutover refresh pass.
- **D-06:** Rollback means stop the DuckDB runtime, restore or repoint to the pinned SQLite DB plus previous runtime config/image, run preflight, then Docker smoke/perf validation. A full Strava resync is not an acceptable rollback or validation mechanism.

### DuckDB Storage And Query Layer

- **D-07:** DuckDB is the primary runtime database. Avoid a permanent SQLite bridge, bidirectional sync, CDC, or dual-primary system.
- **D-08:** Preserve physical DuckDB tables for mirrored Strava data and explicit derived facts: activities, streams, stream channels, kudos, refresh metadata, activity metric facts, daily load facts, training model facts, and read-model metadata.
- **D-09:** Do not add new permanent period aggregate tables initially. Use DuckDB views plus whitelisted repository query builders for aggregate queries; treat physical aggregate tables as a fallback only if live Docker benchmarks prove they are needed.
- **D-10:** DuckDB views are acceptable for normalizing typed dates, metric columns, completeness metadata, sport/scope fields, and aggregate-ready fact rows. Macros may be used only for small reusable SQL primitives if they remain simple.
- **D-11:** Domain-heavy computation still belongs below the request path. DuckDB aggregates prepared facts; it does not recompute expensive stream-derived metrics inside MCP calls.
- **D-12:** Store and query canonical activity days as `DATE`, not text slicing. Date ranges use half-open intervals `[start_day, end_day_exclusive)`.
- **D-13:** DuckDB runtime must respect native concurrency constraints: one read-write process owns the DB file. Separate healthcheck or smoke processes must not open the same DB read-write while the service owns it.
- **D-14:** SQLite import is migration-only. Because SQLite is weakly typed and DuckDB is strongly typed, migration must use controlled casts and parity checks for dates, JSON/text, numeric fields, and nullable columns.

### MCP Aggregate Surface

- **D-15:** Add one constrained generic MCP tool named `get_training_aggregates`.
- **D-16:** Keep the existing product tools: `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, and `project_fitness_state`.
- **D-17:** `get_training_aggregates` should be designed from agent/user scenarios, not from the old CLI. Primary scenarios are daily briefs, weekly/monthly digests, period comparisons, sport-specific efficiency trends, and historical factual exploration.
- **D-18:** `get_training_aggregates` should accept product-level parameters, not SQL: date range, bucket, metric ids or registry-defined metric bundle, grouping scope, sport filters, registry-default aggregation mode, and whether empty buckets are included.
- **D-19:** Support both explicit metric ids and predefined metric bundles. Bundles must be defined from the metric registry, not hand-built in the MCP handler.
- **D-20:** Do not expose gear/equipment filtering or grouping in Phase 8 aggregate queries.
- **D-21:** Do not expose raw SQL, DuckDB table names, query plans, migrations, preflight, sync, backfill, recompute, dirty queues, token state, raw Strava payloads, raw streams, or debug/admin controls through MCP.
- **D-22:** Aggregate responses remain factual. They include values, units, aggregation mode, denominator, sample size, coverage, missing reasons, freshness, and metric version metadata. They must not say whether the athlete should train, rest, improve, or worry.

### Period Comparison

- **D-23:** Rewrite `compare_periods` over the same aggregate query layer as `get_training_aggregates`.
- **D-24:** `compare_periods` should call the aggregate layer twice with `bucket=all_time` for period A and period B, then format deltas, percentages, trend direction, sample sizes, coverage, missing reasons, and metric version status.
- **D-25:** Do not keep a separate Python row-scanning or per-metric recomputation path for period comparison once the aggregate layer exists.

### Bucket And Filter Contract

- **D-26:** Supported buckets for Phase 8 are `day`, `week`, `month`, `year`, and `all_time`.
- **D-27:** Week buckets use Monday start, matching DuckDB `time_bucket` behavior for week-width date buckets.
- **D-28:** All-time starts at the earliest activity date in the local mirror unless the caller supplies an explicit start date.
- **D-29:** Supported scopes are global and per-sport, controlled by metric registry metadata. Metrics with sport-sensitive semantics default to per-sport comparison unless explicitly marked `global` or `both`.
- **D-30:** Rolling windows use `as_of_day` plus whitelisted `window_days`, with initial windows `7`, `14`, `28`, `42`, and `90`.
- **D-31:** Gear/equipment is not a supported aggregate filter or grouping dimension in Phase 8.

### Aggregation Semantics

- **D-32:** Aggregation semantics belong in the metric registry. Do not mint duplicate metric ids just to represent alternative aggregation math.
- **D-33:** Volume and load metrics aggregate by sum unless the registry defines a different mode. Examples: distance, moving time, elevation, TRIMP, HR-zone seconds, active days, workout count.
- **D-34:** Named daily averages divide by calendar bucket days by default. Active-day averages require an explicit registry metric or explicit denominator metadata.
- **D-35:** Heart-rate and power averages must be weighted averages, not naive averages of activity averages. HR should be weighted by HR sample count or sample seconds; watts should be weighted by watts sample count or sample seconds when available.
- **D-36:** Pace/speed-style aggregate facts should be computed from distance/time ratios, not averages of per-activity pace/speed, unless the registry explicitly defines another denominator.
- **D-37:** Efficiency and skewed metrics should use median plus distribution context by default. Examples include cardiac cost, adjusted cardiac cost, cardiac drift, HR recovery, HRR percentage, vertical speed, elevation density, and kudos-per-activity.
- **D-38:** Default quantiles for distribution context are p25, median, and p75. Responses must include sample size so agents can judge low-N results.
- **D-39:** Model-state metrics such as fitness, fatigue, form, ACWR, ATL, and CTL aggregate as last-known state for the bucket unless the registry explicitly defines another mode.
- **D-40:** Categorical facts such as form zone, ACWR zone, drift severity, completeness status, and warning/status codes aggregate as distributions/counts, not numeric averages.
- **D-41:** Kudos are social/context facts. `kudos_count` may be aggregated as count/sum or distribution where useful; kudos names remain per-workout detail context and should not be emitted as aggregate bucket payloads.

### Completeness And Provenance

- **D-42:** Every aggregate row must include bucket start/end, bucket width, metric id, unit, calculation description or registry reference, aggregation mode, denominator, value, sample size, activity count, null/excluded count, completeness status, missing reasons, metric version status, materialized timestamp, mirror freshness, and read-model freshness.
- **D-43:** HR, watts, stream, and GPS coverage must be explicit where relevant. Missing denominators suppress weighted values or mark them unavailable/partial; they must not silently degrade to naive averages.
- **D-44:** Mixed metric versions in a bucket or comparison must be reported as mixed/degraded and must not be silently compared as if formulas were identical.

### Expert Panel Routing

- **D-45:** Planner should use expert-panel or research lenses for hard technical choices that remain after this context, especially DuckDB cutover mechanics, healthcheck concurrency, and whether any physical aggregate table is justified by benchmark data.
- **D-46:** The user should only be asked product/business questions not answerable from this context. Technical defaults above are locked unless research finds they are unsafe or impossible.

### the agent's Discretion

Planner may choose exact DuckDB table names, view names, repository class names, migration command names, JSON field spelling, metric-bundle names, and test fixture shapes. These choices must preserve the locked constraints above: DuckDB primary, fast-but-backed-up cutover, no permanent dual-primary, no raw/admin MCP surface, metric-registry-driven aggregation semantics, and sub-100 ms p95 MCP acceptance unless explicitly changed.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project And Phase Scope

- `.planning/PROJECT.md` - Project goals, durable mirror constraint, MCP boundary, Docker runtime, and current storage/read-model state.
- `.planning/REQUIREMENTS.md` - Validated v1/v1.1 requirements, MCP exclusions, data preservation, read-model facts, and performance gates.
- `.planning/ROADMAP.md` - Phase 8 goal, success criteria, and cross-cutting constraints.
- `.planning/STATE.md` - Current phase routing and recent Phase 7/quick-task decisions.

### Prior Phase Context

- `.planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md` - Current read-model fact contract, dirty queue, materialization, MCP no-recompute boundary, and p95 gate.
- `.planning/phases/06-full-fidelity-strava-mirror/06-CONTEXT.md` - Lossless normalized mirror, stream/channel/GPS storage, SQLite primary decision being superseded in Phase 8, and no-MCP-admin boundary.
- `.planning/phases/05-mcp-http-surface-docker-hardening/05-CONTEXT.md` - MCP five-tool surface, metric registry, no coaching/admin/raw/sync tools, Docker runtime path, and gateway boundary.
- `.planning/phases/02-sqlite-safety-repository-layer/02-CONTEXT.md` - Backup, preflight, parity, fail-closed DB behavior, and missing-data semantics to preserve through migration.

### Codebase Maps

- `.planning/codebase/ARCHITECTURE.md` - Current SQLite repository/application/MCP/refresh architecture and anti-patterns.
- `.planning/codebase/STACK.md` - Current Python 3.14, MCP SDK, PyYAML, SQLite, Docker stack.
- `.planning/codebase/INTEGRATIONS.md` - Strava API, local MCP gateway, runtime DB paths, token files, and Docker integration.
- `.planning/codebase/CONCERNS.md` - Repository concentration, compare-periods fanout, schema-validation gap, and performance bottlenecks.

### Current Code

- `pyproject.toml` - Python and dependency baseline; DuckDB dependency is not yet present.
- `deploy/Dockerfile` - Current Python 3.14 image and runtime DB path still pointing at `strava.db`.
- `Justfile` - Docker-first test entrypoint and current `mcp-read-model-perf` 100 ms p95 gate.
- `src/mcp_strava/adapters/sqlite/schema.py` - Current SQLite schema inventory and read-model tables to migrate.
- `src/mcp_strava/adapters/sqlite/migrations.py` - Existing backup/preflight/migration/post-check/parity pattern and versioned migration runner.
- `src/mcp_strava/adapters/sqlite/repository.py` - Current persistence boundary to replace/refit for DuckDB primary.
- `src/mcp_strava/adapters/sqlite/read_model_materializer.py` - Current materialized fact creation logic and aggregation assumptions.
- `src/mcp_strava/application/metric_registry.py` - Metric registry to extend with aggregation semantics.
- `src/mcp_strava/application/metric_services.py` - Current MCP service implementation and `compare_periods` logic to refit over aggregate layer.
- `src/mcp_strava/interfaces/mcp_http.py` - MCP allowlist and tool registration; Phase 8 adds `get_training_aggregates`.
- `src/mcp_strava/deploy/preflight.py` - Fail-closed runtime DB validation to refit for DuckDB.
- `tests/test_read_model_queries.py` - Existing read-model query expectations and fixture data.
- `tests/test_mcp_latency_gate.py` - Current MCP p95 gate behavior.

### External References

- `https://duckdb.org/docs/current/sql/functions/date.html` - DuckDB date functions and `time_bucket` behavior.
- `https://duckdb.org/docs/current/sql/functions/aggregates` - DuckDB aggregate functions including `weighted_avg`, `median`, and `quantile_cont`.
- `https://duckdb.org/docs/stable/sql/statements/create_view` - DuckDB view behavior; views are not physically materialized.
- `https://duckdb.org/docs/current/connect/concurrency.html` - DuckDB native DB concurrency model and single read-write process constraint.
- `https://duckdb.org/docs/stable/guides/database_integration/sqlite.html` - SQLite import/attach path and weak-typing caveats.
- `https://duckdb.org/docs/stable/core_extensions/sqlite` - SQLite extension behavior for direct SQLite reads during migration.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- Existing migration tooling already has backup, preflight, post-check, parity, and migration logging behavior that should be reused conceptually for DuckDB cutover.
- Phase 7 read-model tables already separate expensive domain computation from MCP request handling; DuckDB should aggregate these facts rather than re-scan raw streams for hot MCP calls.
- The metric registry already carries units, scope, comparison mode, directionality, requirements, missing reasons, and exposure. Phase 8 should extend it with aggregation mode, denominator, bundle membership, and quantile/distribution behavior.
- The MCP SDK client and `Justfile` latency gate are the right acceptance path for aggregate tool latency.

### Established Patterns

- Product/MCP paths are read-only, Strava-free, sync-free, and admin-free.
- Missing HR/streams/watts/details/facts are represented explicitly through completeness metadata, not zeros or silent fallback formulas.
- Live validation is Docker-first; repo tests use temp or copied databases.
- There are no backward-compatibility obligations for old internal schemas or old CLI JSON shapes, but the Strava mirror data itself must be preserved.

### Integration Points

- Add a DuckDB adapter boundary rather than keeping new work under `adapters/sqlite/` names long-term.
- Refit settings, deploy preflight, Docker env, CLI/admin commands, refresh runtime, and MCP services to point at DuckDB primary.
- Add `get_training_aggregates` to the MCP allowlist and tests, while preserving forbidden admin/sync/raw/sql/recompute boundaries.
- Rebuild `compare_periods` as a formatter over the aggregate query layer.
- Extend migration/parity checks to cover source tables, stream point coverage, channel metadata, kudos, refresh state, read-model facts, metric versions, and MCP output parity.

</code_context>

<specifics>
## Specific Ideas

- `get_training_aggregates` should feel like a training-metrics tool, not like SQL. The name is intentionally product-facing.
- Useful agent scenarios are morning brief, weekly/monthly digest, period comparison, sport-specific efficiency trends, and historical factual exploration.
- The aggregate layer should return rows like `metric_id`, `bucket_start`, `bucket_end`, `scope`, `sport_type`, `value`, `distribution_buckets`, `sample_size`, `active_days`, `missing_reasons`, `completeness_status`, and `metric_version_status`.
- The planner should benchmark logical views/query builders against the live Docker DB before proposing physical aggregate tables.
- Existing `rolling_period_facts` may be migrated as part of parity; planner may decide whether it remains a fact source or becomes redundant after the aggregate layer covers rolling windows.

</specifics>

<deferred>
## Deferred Ideas

- Gear/equipment aggregation and filtering are explicitly out of Phase 8.
- Physical period aggregate tables are deferred until benchmark evidence shows DuckDB views/query builders miss the latency target.
- Permanent raw payload archive, Parquet/lakehouse layering, CDC, bidirectional sync, and multi-user/SaaS storage concerns remain out of scope.
- Training-model redesign and coaching interpretation remain outside the service.

</deferred>

---

*Phase: 08-DuckDB Primary Storage & Aggregate Analytics Surface*
*Context gathered: 2026-05-25*
