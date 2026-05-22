# Phase 05 Research: MCP HTTP Surface & Docker Hardening

**Date:** 2026-05-22
**Phase:** 05 - MCP HTTP Surface & Docker Hardening
**Status:** Research complete

## Research Questions

1. How should the MCP surface expose training metrics without inheriting CLI names or coaching behavior?
2. Which existing synthetic metrics must be inventoried before tool implementation?
3. What MCP SDK and HTTP transport details affect the plan?
4. What Docker/gateway constraints are already present on this host?

## Findings

### MCP Protocol And SDK

- Official MCP SDK docs list the Python SDK as Tier 1 and support local and remote transports.
- The current MCP specification defines Streamable HTTP as a standard transport with one MCP endpoint path supporting POST and GET.
- Streamable HTTP security guidance requires Origin validation, localhost binding for local servers, and authentication for exposed connections.
- The Python SDK FastMCP server supports structured tool outputs from typed return values and direct `CallToolResult.structuredContent`.
- Tool definitions can carry `outputSchema` and `annotations`; `ToolAnnotations` includes `readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint`.

Primary sources:
- https://modelcontextprotocol.io/docs/sdk
- https://modelcontextprotocol.io/specification/2025-03-26/basic/transports
- https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- https://modelcontextprotocol.io/specification/2025-06-18/schema
- https://py.sdk.modelcontextprotocol.io/server/

### Existing Application Surface

- Phase 4 created `ServiceEnvelope` with `data`, `freshness`, `completeness`, `warnings`, and `rationale`.
- Current product registry names (`daily_report`, `weekly_summary`, `recent_workouts`, `workout_analytics`, `freshness`) are not the final MCP naming surface.
- MCP should expose five new agent-facing tools:
  - `get_fitness_state`
  - `list_workouts`
  - `get_workout_detail`
  - `compare_periods`
  - `project_fitness_state`
- There should be no standalone `get_data_status` tool. Freshness and completeness must be embedded in every tool response.
- MCP must not expose `sync`, `backfill`, raw Strava API, arbitrary SQL, token/admin operations, sync logs, or debug surfaces.

### Synthetic Metric Inventory

Current code computes metrics across several layers:

- Activity identity and volume: id, date, sport, name, distance, moving/elapsed time, elevation, start time.
- Activity intensity/load: TRIMP, average/max HR, HR zone minutes, Z5 seconds.
- Stream-derived workout metrics: HR recovery, vertical speed/VMH, cardiac cost `cc`, adjusted cardiac cost `cc_adj`, cardiac drift, HRR percentage, HR anomaly count, elevation per km.
- Model metrics: Banister fitness, fatigue, form, form zone, Banister history.
- Load metrics: weekly TRIMP, 14-day TRIMP, 7/28/90-day load, active/rest days, ACWR, ATL, CTL, ACWR zone/history.
- Period metrics: per-sport rolling efficiency, per-sport volume, load trends, 28/90-day cardiac cost trends, streaks, last hike recency.
- Projection metrics: forward simulated daily TRIMP, projected fitness/fatigue/form, target-date form, post-weekend simulations, activity template TRIMP values.
- Existing interpretation fields: `Recommendation.action`, `Recommendation.intensity`, `WeeklyPlan.on_track`, natural-language weekly plan activity labels, and some safety-warning text. These should not be exposed as recommendations; their numeric inputs and model facts must be preserved.

The implementation needs a metric registry before MCP tool wiring so every current synthetic metric is either exposed, mapped to a stable metric id, or explicitly marked `excluded_interpretation` with numeric inputs preserved.

### Period Comparison

`compare_periods` must not be limited to volume. It should compare all registry metrics where comparison is valid:

- global metrics: TRIMP, fitness, fatigue, form, ACWR/ATL/CTL, active/rest days.
- per-sport metrics: cardiac cost, adjusted cardiac cost, HR recovery, cardiac drift, HRR percentage, vertical speed, elevation density.
- both where valid: distance, duration, elevation, load, zones.

Each metric comparison needs period A/B values, delta, delta percent where valid, sample size, coverage, and missing reasons. The service returns facts only; it does not claim that the heart, vessels, or training state improved.

### Fitness Projection

The useful old weekly planning logic should be refit as `project_fitness_state`, a model simulator. It should support:

- `rest`: zero daily TRIMP until target date.
- `easy`: low/easy template load.
- `maintain`: recent average load pattern.
- `custom`: caller-provided daily TRIMP values.

Output is projected fitness, fatigue, form, daily TRIMP, target-date form, model assumptions, freshness, and completeness. The service must not choose the best scenario or say what the athlete should do.

### Docker And Gateway Reality

Live gateway files exist:

- `/opt/docker/mcp-gateway/catalog.yaml`
- `/opt/docker/mcp-gateway/compose.yaml`

The gateway currently uses catalog entries for `dotmd`, `ozon`, `telegram`, and `beads`, with `--servers=ozon,telegram,beads,dotmd`. Backend services are reachable on Docker networks such as `mcp-backends`; external access is mediated by `mcp-auth-proxy`.

Phase 5 should:

- build and run `mcp-strava` as a backend container on shared MCP networks.
- keep Strava backend ports unpublished by default.
- mount `/opt/docker/mcp-strava/data/strava.db`.
- load live secrets from `/opt/docker/mcp-strava/.env`.
- fail startup when the expected mirror DB is absent, unreadable, corrupt, or structurally invalid.
- update the live gateway with backup, atomic edit, smoke, and rollback.

## Validation Architecture

Use the existing pytest infrastructure and add focused tests before implementation.

- Quick command: `python3 -m pytest tests/test_metric_registry.py tests/test_mcp_surface.py tests/test_docker_runtime.py -q`
- Full command: `just test`
- Live smoke command after Docker artifacts exist: `python3 -m mcp_strava.deploy.smoke --url http://127.0.0.1:${MCP_STRAVA_HTTP_PORT:-8000}/mcp --expect-tool get_fitness_state` for direct backend smoke, then an internal gateway URL from the backend container for live registry smoke.
- Default tests must use fixture/copy databases and must not mutate `data/strava.db`.

Required validation coverage:

1. Metric registry covers every intentional synthetic metric and marks excluded interpretation fields explicitly.
2. MCP allowlist contains exactly `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, and `project_fitness_state`.
3. Forbidden sync/admin/debug/raw names are absent from MCP tools and cannot be discovered through product registries.
4. Every MCP tool response includes freshness and completeness metadata.
5. HTTP startup rejects unsafe local bind/origin combinations unless container/gateway mode explicitly allows them.
6. Docker runtime is non-root, uses explicit persistent data mount, has no public host port by default, and preflights the DB before serving.
7. Live gateway integration script creates backups, applies atomic changes, smokes, and rolls back on failure.

## Planning Implications

- Build the metric registry first; it is the source of truth for service and MCP exposure.
- Add metric-oriented application services separate from old CLI/product service names.
- Keep MCP implementation thin: it maps tools to services and returns structured output.
- Docker hardening should come after the backend server exists.
- Live gateway integration should be last and must be rollback-capable.

## RESEARCH COMPLETE

Research is sufficient to plan Phase 5.
