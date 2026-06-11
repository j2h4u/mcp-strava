# Phase 09: Product factual bundles and CLI read-model consolidation - Context

**Gathered:** 2026-05-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 9 restores the useful product facts that existed in the old CLI/reporting flow and consolidates MCP plus CLI product reads onto the DuckDB/read-model application layer.

This phase is not a training-model redesign, not a coaching/recommendation phase, not a new MCP admin surface, and not a backward-compatibility exercise for old CLI command names or JSON shapes. The target is one factual core/read-model contract consumed by thin MCP and CLI surfaces.

</domain>

<decisions>
## Implementation Decisions

### Product Factual Bundles

- **D-01:** No additional product discovery is required before planning. The prior audit and expert panel are sufficient; downstream agents should treat this context as the locked synthesis.
- **D-02:** Restore product-shaped factual bundles for daily brief, weekly digest, historical/context facts, and period comparison support. These bundles must expose metrics, windows, sample counts, coverage, freshness, and calculation metadata, not coaching advice.
- **D-03:** Keep the current MCP product surface shape: `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, `project_fitness_state`, and `get_training_aggregates`. Improve existing tools and bundles before adding any new MCP tool.
- **D-04:** `daily_brief`, `weekly_digest`, and `historical_facts` must not fail because a mixed bundle contains metrics with incompatible scopes. The planner should normalize bundle semantics, split mixed-scope output internally, or otherwise make scenario bundles safe for agents to call.
- **D-05:** Daily brief facts should recover at least current fitness/load state, recent workouts, 14-day daily TRIMP/load context, by-sport breakdown, ACWR/Banister context, freshness/read-model metadata, and factual status flags.
- **D-06:** Weekly digest facts should recover load, volume, efficiency, by-sport summaries, current week activity facts, and period trend facts that agents previously used for narrative summaries.
- **D-07:** Historical/context facts should recover useful non-interpretive context such as activity streak, rest streak, last hike age, season/current-week context, and related coverage metadata when those facts are registry-backed and materialized.

### Safety And Status Facts

- **D-08:** Old safety warnings may be preserved only as factual threshold/status facts with machine-readable code, threshold, window, evidence, and completeness. The server must not tell the athlete to rest, train, worry, hydrate, or change behavior.
- **D-09:** Candidate safety/status facts to recover include excessive Z5 exposure, HR anomaly bursts, significant cardiac drift with quality, consecutive high-load hikes, running volume jump, missing HR, missing streams, stale mirror data, and stale read-model facts.
- **D-10:** Threshold labels such as `form_zone`, `acwr_zone`, or warning/status codes are valid derived facts when their formula and thresholds are registered. They are not considered duplicate metrics merely because an agent could theoretically reapply thresholds.

### Metric Registry And Read Model

- **D-11:** The metric registry remains the source of truth for every Strava-sourced metric, calculated metric, derived category, aggregate bundle member, and materialized analytic fact column.
- **D-12:** Materialized fact columns should exist only when the registry maps them as a metric, dependency, dimension, or provenance column. Unused columns and dead calculations should be removed rather than retained for possible future use.
- **D-13:** Synthetic metrics must not be lost. Period comparison and aggregate bundles should include trends for synthetic metrics where meaningful, including cardiac cost, adjusted cardiac cost, cardiac drift, HR recovery, load, fitness/fatigue/form, ACWR, TRIMP, and by-sport efficiency facts.
- **D-14:** `compare_periods` should continue to use the aggregate layer. Do not reintroduce separate Python row-scanning or duplicate per-metric comparison logic.
- **D-15:** Facts that are currently computed in old report/analytics modules but not exposed through registry-backed read-model paths should either be moved into the registry/read model or deliberately deleted if they no longer serve a product use case.

### CLI Read-Model Consolidation

- **D-16:** CLI remains a product surface for users who do not want MCP, but it must be thin in the same way as MCP. Product CLI commands should call the same application/read-model services as MCP.
- **D-17:** Retain product CLI capability for daily report, weekly summary, recent workouts, workout detail/analysis, and freshness/status. Exact old command names and JSON shapes are not compatibility constraints.
- **D-18:** Remove dead/unregistered CLI handlers after useful facts are recovered into product services. Known candidates include legacy activity, gear, stats, sync, backtest, trend, and kudos handlers if they are not registered current product/admin paths.
- **D-19:** Local admin commands remain local admin commands. `sync`, `backfill`, `raw`, `sql`, token, migration, mirror coverage, logs, and DB maintenance must not cross into MCP or product factual bundles.

### Gear And Kudos

- **D-20:** Kudos are product facts. Preserve `kudos_count` in list/detail/aggregate contexts where useful, and preserve `kudos_names` only at per-workout detail level, not in aggregate bucket payloads.
- **D-21:** Gear/shoe mileage is factual product context because the MCP prompt surface includes a shoe-mileage scenario. Expose gear facts through existing product bundles or workout detail where supported by mirrored Strava data.
- **D-22:** Do not add gear/equipment filtering or grouping to aggregate queries in this phase unless planning proves it is required to make existing shoe-mileage prompts factual. Phase 8 explicitly excluded gear filters from aggregate queries.

### The Agent's Discretion

The planner may choose exact JSON field names, bundle sub-section names, query method names, test fixture shapes, and whether gear facts fit best inside `get_training_aggregates`, `get_workout_detail`, or a CLI-only product command. These choices must preserve the locked constraints above: factual-only MCP, registry-backed metrics, thin CLI, DuckDB/read-model primary reads, and no admin/sync/raw exposure.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project And Phase Context

- `.planning/PROJECT.md` - Core value, MCP boundary, durable mirror constraint, current DuckDB/read-model direction, and key project decisions.
- `.planning/REQUIREMENTS.md` - Validated v1/v1.1 requirements, MCP exclusions, read-model requirements, and performance expectations.
- `.planning/ROADMAP.md` - Phase sequencing and the Phase 9 entry.
- `.planning/STATE.md` - Accumulated decisions from Phases 1-8, including DuckDB primary storage and aggregate semantics.
- `.planning/phases/08-duckdb-primary-storage-aggregate-analytics-surface/08-CONTEXT.md` - DuckDB primary storage, aggregate bundles, scope semantics, no raw SQL/admin MCP, and `get_training_aggregates`.
- `.planning/phases/07-materialized-metrics-read-model/07-CONTEXT.md` - Read-model fact contract, no request-time recompute, read-model metadata, and MCP latency boundary.
- `.planning/phases/06-full-fidelity-strava-mirror/06-CONTEXT.md` - Lossless normalized mirror, channel/GPS preservation, kudos/coverage context, and no-MCP-admin boundary.

### Application And Interface Code

- `src/mcp_strava/interfaces/mcp_http.py` - Current six-tool MCP surface, prompt registration, tool logging, and cache behavior.
- `src/mcp_strava/application/metric_registry.py` - Metric registry, bundle definitions, aggregate metadata, and materialized fact column registry.
- `src/mcp_strava/application/aggregate_services.py` - Product aggregate service envelope over DuckDB aggregate queries.
- `src/mcp_strava/adapters/duckdb/aggregate_queries.py` - Registry-whitelisted DuckDB aggregate query builder and current bundle failure point for unsupported scopes/columns.
- `src/mcp_strava/application/metric_services.py` - Current MCP-backed services for fitness state, workouts, period comparison, and projections.
- `src/mcp_strava/cli.py` - Current CLI product/admin split plus dead legacy handlers to consolidate or remove.
- `src/mcp_strava/application/reports.py` - Older report service path that still routes through SQLite/report code and should be consolidated.
- `src/mcp_strava/application/workouts.py` - Older workout service path that still routes through SQLite/enrichment code and should be consolidated.
- `src/mcp_strava/report.py` - Source of legacy daily report facts, safety warnings, recommendation logic, and weekly plan logic to salvage only as factual metrics where appropriate.
- `src/mcp_strava/analytics.py` - Source of legacy weekly digest facts such as load, efficiency, trends, streaks, last hike, and this-week context.

### Tests And Verification

- `tests/test_metric_registry.py` - Registry coverage, bundle expectations, aggregate exposure, and no gear filter assertions.
- `tests/test_mcp_surface.py` - MCP tool allowlist and forbidden surface expectations.
- `tests/test_mcp_test_client.py` - Persistent MCP test client and aggregate smoke script coverage.
- `tests/test_cli_surface.py` - CLI surface/product-admin split expectations.
- `tests/test_security_guards.py` - Boundary guards that must continue to block admin/raw/recompute leakage.
- `Justfile` - Docker-first smoke, MCP call, and performance gate commands.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `ServiceEnvelope`, `FreshnessMetadata`, `CompletenessMetadata`, `ServiceWarning`, and `ServiceRationale` already provide the right response envelope for both MCP and CLI product surfaces.
- `METRIC_REGISTRY`, `AGGREGATE_METRIC_BUNDLES`, and `MATERIALIZED_FACT_COLUMN_REGISTRY` are the right central contract for metrics, bundle membership, aggregation, and fact-column audits.
- `get_training_aggregates_service()` and `query_training_aggregates()` are the right base for daily/weekly/historical factual bundles once bundle scope/column issues are fixed.
- `compare_periods_service()` already formats two aggregate requests and should remain the comparison path.
- Old `report.py` and `analytics.py` still contain useful product facts to recover, but not as hot request-time computation paths.

### Established Patterns

- Edge handlers stay thin. MCP and CLI should call application services rather than reimplementing analytics.
- Product read paths are Strava-free, sync-free, admin-free, raw-SQL-free, and should read prepared facts.
- Missing or stale facts are represented as completeness/freshness metadata, not hidden by request-time recomputation.
- No backward compatibility is required for old CLI JSON or old internal schemas.

### Integration Points

- Fix or extend aggregate registry metadata so scenario bundles call cleanly with mixed global/per-sport metrics.
- Move old daily/weekly product facts into read-model-backed application services and route CLI product commands to those services.
- Delete dead CLI handlers and duplicate Python calculations after their useful product facts are either recovered or deliberately rejected.
- Add focused tests for live product bundle calls, CLI-to-service parity at capability level, dead-handler removal, and registry/fact-column drift.

</code_context>

<specifics>
## Specific Ideas

- The expert-panel synthesis is the product source for this phase: restore factual product value, not server-side coaching.
- Useful old daily report facts include recent activities, daily TRIMP/load, by-sport summary, Banister/ACWR context, progressive inputs, safety/status facts, and freshness/completeness metadata.
- Useful old weekly facts include load windows, efficiency by sport, volume by sport, trends, current week activities, activity/rest streaks, and last hike context.
- Recommendation, weekly plan, motivational text, and medical/training advice are not server outputs. If their inputs are useful, expose the inputs as facts.

</specifics>

<deferred>
## Deferred Ideas

- Training model redesign and new coaching interpretation remain out of scope.
- Medical diagnosis or prescriptive training advice remains out of scope for the MCP server and service core.
- Gear/equipment filtering/grouping in aggregate queries remains out of scope unless a later phase makes it a first-class product need.
- Raw SQL, raw Strava payload, sync/backfill controls, token state, and logs remain admin/debug concerns outside MCP.

</deferred>

---

*Phase: 09-Product factual bundles and CLI read-model consolidation*
*Context gathered: 2026-05-26*
