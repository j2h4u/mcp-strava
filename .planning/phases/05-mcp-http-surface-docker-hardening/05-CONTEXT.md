# Phase 5: MCP HTTP Surface & Docker Hardening - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 5 exposes a read-only HTTP MCP server for local Strava mirror metrics and hardens the Docker/runtime path for the existing local MCP gateway. The MCP surface is an agent-facing metrics provider, not a CLI clone, not a Strava API wrapper, and not a coaching engine. This phase also performs live integration into the existing Docker MCP registry with backup, smoke, and rollback.

</domain>

<decisions>
## Implementation Decisions

### MCP Tool Surface

- **D-01:** MCP tool names must be designed from scratch for intelligent-agent use, not inherited from the accidental CLI surface.
- **D-02:** MCP exposes prepared metrics and model facts only. It must not formulate coaching recommendations, readiness judgments, motivation, or human advice.
- **D-03:** Primary MCP tools for Phase 5 are:
  - `get_fitness_state`
  - `list_workouts`
  - `get_workout_detail`
  - `compare_periods`
  - `project_fitness_state`
- **D-04:** Do not expose a separate `get_data_status` primary tool. Freshness, completeness, warnings, and missing-data coverage are metadata included in every tool response.
- **D-05:** Do not add a planned-activity or route-readiness tool in Phase 5. Agents can compose that reasoning from fitness state, workout history, period comparisons, workout details, and projections.
- **D-06:** Tool registry must exclude sync, backfill, token refresh, raw Strava API, arbitrary SQL, sync logs, admin/debug operations, and any direct operational control.

### Metric Registry

- **D-07:** Phase 5 must create a complete metric registry as a contract between core/application services and MCP. MCP tools must not manually cherry-pick metrics from code.
- **D-08:** Every current synthetic metric must be either:
  - registered and exposed through one or more MCP tools;
  - registered with a stable rename/mapping from old code names to MCP metric IDs; or
  - explicitly marked `excluded_interpretation`, with its numeric/model inputs preserved elsewhere.
- **D-09:** Metric registry entries should include at least: `metric_id`, `unit`, `source`, `scope`, `sport_scope`, `comparison_mode`, `directionality`, `requirements`, `missing_reasons`, and `exposed_in`.
- **D-10:** `sport_scope` should allow automatic comparison behavior: `global`, `per_sport`, or `both`. Body/load metrics such as TRIMP, fitness, fatigue, form, ACWR, ATL/CTL can compare globally; sport-sensitive metrics such as cardiac cost, pace/HR drift, vertical speed, and elevation density should compare per sport unless explicitly marked otherwise.
- **D-11:** Tests must prove that intended synthetic metrics are not lost when exposed through MCP.

### Period Comparison

- **D-12:** `compare_periods` must compare synthetic metrics, not just volume/load basics. It should support trends over cardiac/efficiency proxies such as cardiac cost, adjusted cardiac cost, HR recovery, cardiac drift, HRR percentage, zone distribution, vertical speed, and related quality signals when the metric registry says comparison is valid.
- **D-13:** Period comparison output must include values for both periods plus `delta`, `delta_pct`, trend direction where meaningful, sample size, coverage/confidence, and missing reasons.
- **D-14:** The service must not translate metric trends into medical/coaching claims such as "heart improved" or "vessels improved." It returns facts like median cardiac drift decreased or median HR recovery rate changed; the intelligent agent explains meaning to the athlete.

### Fitness Projection

- **D-15:** `project_fitness_state` preserves the useful old planning logic as model simulation, not as a recommendation engine.
- **D-16:** The tool should support a small Pareto set of standard scenarios plus custom input: `rest`, `easy`, `maintain`, and `custom`.
- **D-17:** Output is projected fitness, fatigue, form, daily TRIMP, target-date form, model assumptions, freshness, and completeness. It must not choose a best scenario or say when to run/walk/rest.
- **D-18:** Existing `recommendation` and `weekly_plan` fields should not be exposed as coaching fields. Preserve their numeric/model facts where useful: load bonus, projected form, post-weekend simulations, trend inputs, and safety metric flags.

### HTTP MCP Runtime

- **D-19:** Phase 5 integrates with the existing Docker MCP gateway mechanism, not a standalone public HTTP deployment.
- **D-20:** The known live gateway files are `/opt/docker/mcp-gateway/catalog.yaml` and `/opt/docker/mcp-gateway/compose.yaml`. Current gateway uses catalog entries such as `dotmd`, `ozon`, `telegram`, and `beads`.
- **D-21:** `mcp-strava` should run as a backend container on the shared MCP Docker networks. It should expose `/mcp` to the gateway by container name, for example `http://mcp-strava:<port>/mcp`.
- **D-22:** Do not publish the Strava MCP backend port to the public host by default. External access/auth remains the job of the existing `mcp-auth-proxy` and gateway layer.
- **D-23:** Live integration is in scope for Phase 5: add `strava` to the live gateway catalog and `--servers` list, then smoke through the real gateway.
- **D-24:** Live gateway edits must use backup + atomic edit + smoke + rollback. If Strava MCP smoke fails, restore backed-up gateway files and restart the old gateway configuration.

### Docker Data And Secrets

- **D-25:** Live runtime data lives under `/opt/docker/mcp-strava/data/strava.db`, not directly in the development checkout.
- **D-26:** Before copying or migrating the existing mirror DB into deploy state, create a backup. Preserve the existing Strava mirror because full resync is expensive and rate-limited.
- **D-27:** Container startup must fail closed if the expected mirror DB is absent, unreadable, or invalid.
- **D-28:** Live Strava secrets live in `/opt/docker/mcp-strava/.env`, not in the repository. They are for runtime internals only and must never be surfaced through MCP.
- **D-29:** Docker runtime should run non-root by default, mount persistent data explicitly, and avoid public host-port exposure unless intentionally configured outside the default path.

### the agent's Discretion

Planner may choose the exact Python MCP framework, module layout, DTO classes, JSON schema generation approach, local container port, healthcheck command, and smoke-test implementation. These choices must preserve the tool surface, metric registry, no-coaching boundary, no-admin MCP boundary, data preservation, and live gateway rollback policy above.

</decisions>

<specifics>
## Specific Ideas

- Current live gateway process uses Docker MCP gateway with a catalog and `--servers=ozon,telegram,beads,dotmd`. Phase 5 should add `strava` to that same path.
- Existing user value comes from an external intelligent agent that reads metrics and writes morning/weekly coaching-style summaries. MCP should enable that agent, not replace it.
- The old automated script was useful because it exposed rich recent-workout tables, period comparisons, and projections toward weekend freshness. Preserve that usefulness through metrics/projections.
- Metric definitions should be available to agents either in response metadata or a compact registry/resource so agents know units, missing-data conditions, and comparison semantics.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project And Phase Scope

- `.planning/PROJECT.md` - Project goals, constraints, MCP boundary, and data preservation constraint.
- `.planning/REQUIREMENTS.md` - MCP-01..MCP-04, DOCKER-01..DOCKER-03, TEST-03, and out-of-scope admin/sync/raw SQL controls.
- `.planning/ROADMAP.md` - Phase 5 goal and success criteria.
- `.planning/STATE.md` - Current phase routing and completion status.

### Prior Phase Context

- `.planning/phases/04-application-services-cli-refit/04-CONTEXT.md` - Product service envelope, product/admin split, freshness/completeness metadata, and analytics parity.
- `.planning/phases/03-strava-adapter-refresh-runtime/03-CONTEXT.md` - No-sync MCP boundary, refresh states, refresh requests, adapter/runtime split.
- `.planning/phases/02-sqlite-safety-repository-layer/02-CONTEXT.md` - Durable mirror, repository boundary, backup/preflight/parity, and fail-closed DB behavior.

### Current Code

- `src/mcp_strava/application/registry.py` - Current product service allowlist; do not expose it directly as final MCP naming without the Phase 5 tool redesign.
- `src/mcp_strava/application/reports.py` - Daily/weekly service envelope and completeness behavior to adapt into metrics-focused MCP outputs.
- `src/mcp_strava/application/workouts.py` - Recent workout and per-workout analytics service behavior.
- `src/mcp_strava/application/freshness.py` - Freshness metadata and first-use refresh signaling.
- `src/mcp_strava/types.py` - Current dataclasses for enriched activities, model outputs, service envelope, and synthetic metric types.
- `src/mcp_strava/metrics.py` - Per-workout synthetic metrics and missing-data conditions.
- `src/mcp_strava/training.py` - Banister model, projections, progressive signal, and old weekly-plan logic to refit as model facts.
- `src/mcp_strava/analytics.py` - Weekly digest, load, efficiency, volume, and trend calculations.
- `src/mcp_strava/report.py` - Current daily report behavior, recommendation/projection fields, and safety metric inputs.
- `src/mcp_strava/adapters/sqlite/repository.py` - Repository methods for activities, load, refresh state, and persistence boundaries.

### Live Runtime References

- `/opt/docker/mcp-gateway/catalog.yaml` - Existing Docker MCP catalog to back up and update with `strava`.
- `/opt/docker/mcp-gateway/compose.yaml` - Existing gateway/auth-proxy compose stack and `--servers` list to back up and update.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `ServiceEnvelope` already carries `data`, `freshness`, `completeness`, `warnings`, and `rationale`; MCP responses should preserve the trust metadata concept even if tool-specific `data` shapes change.
- `EnrichedActivity` already contains per-workout facts such as TRIMP, HR zones, HR recovery, vertical speed, cardiac cost, cardiac drift, HRR percentage, and start time.
- `DailyReport` already aggregates 14-day load, by-sport breakdown, Banister state/history, ACWR/history, progressive signal, weekly plan, and safety warning inputs.
- `WeeklyDigest` already computes weekly load, efficiency, volume, trends, year-over-year context, and this-week activities.
- Refresh metadata and first-use refresh signaling already exist below the MCP surface; MCP must not expose or manage sync directly.

### Established Patterns

- Product read paths must remain Strava-free and sync-free.
- Missing HR/streams/details must be explicit via nullable metrics and missing reasons.
- CLI/admin commands and MCP tools must stay separated by an explicit allowlist.
- Existing DB safety rules apply to deploy copy/migration work: backup first, fail closed, verify parity where schema/data movement is involved.

### Integration Points

- MCP layer should sit above application/core services and metric registry, not above CLI commands.
- Docker image should mount `/opt/docker/mcp-strava/data` for the mirror DB and consume `/opt/docker/mcp-strava/.env` for runtime secrets.
- Live integration should update the existing Docker MCP gateway after the backend passes local/container smoke.

</code_context>

<deferred>
## Deferred Ideas

- Dedicated planned-activity, trip-readiness, marathon-readiness, or event-advisor tools are deferred. Agents should compose those use cases from the general metric/projection tools first.
- Separate `get_data_status` can be revisited only if real agents need a standalone status query; Phase 5 includes freshness/completeness in every response instead.
- Coaching text, motivation, and human recommendations remain outside the service and belong to the consuming intelligent agent.
- Stronger secret storage than deploy `.env` can be revisited later if the local deployment needs it.
- Public multi-user auth and SaaS-style exposure remain out of scope.

</deferred>

---

*Phase: 05-MCP HTTP Surface & Docker Hardening*
*Context gathered: 2026-05-22*
