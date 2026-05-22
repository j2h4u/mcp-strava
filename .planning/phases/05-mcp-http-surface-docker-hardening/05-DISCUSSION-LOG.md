# Phase 5: MCP HTTP Surface & Docker Hardening - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-22
**Phase:** 5-MCP HTTP Surface & Docker Hardening
**Areas discussed:** MCP tool surface, metric registry, projections, Docker gateway integration, deploy data/secrets, live rollback

---

## Expert Panel

The user requested a panel of future intelligent-agent consumers rather than only architecture/QA reviewers. Roles included sports physician, caring endurance coach, training data scientist, MCP/LLM product designer, and athlete/mountain-trip planner.

The panel converged on:

- MCP should provide prepared metrics and model facts, not coaching interpretation;
- rich recent workout tables and period comparisons are essential because they are the current product's main value;
- freshness and completeness metadata should appear in every metric response;
- a dedicated data-status tool is unnecessary unless agents later need it;
- a projection tool is useful if it remains a model simulator, not a plan recommender;
- no sync/admin/log/token/raw SQL operations should be visible in MCP.

---

## Tool Surface

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror current CLI/product service names | Expose `daily_report`, `weekly_summary`, `recent_workouts`, `workout_analytics`, `freshness`. | |
| New agent-facing metric bundles | Design tools from scratch around agent tasks and metrics. | yes |
| Granular one-tool-per-metric surface | Expose many small metric tools. | |

**User's choice:** Design MCP from scratch as a metrics provider.
**Notes:** CLI was created organically and should not define MCP naming.

| Candidate Tool | Decision |
|----------------|----------|
| `get_training_snapshot` | Rejected/renamed; too close to workout listing. |
| `get_training_state` | Renamed to Strava-like terminology. |
| `get_fitness_state` | Selected. |
| `list_workouts` | Selected. |
| `get_workout_detail` | Selected. |
| `compare_periods` | Selected. |
| `get_data_status` | Rejected as a primary tool; metadata belongs in every response. |
| `compare_planned_activity` / route tool | Deferred; agents can compose from generic tools first. |
| `project_fitness_state` | Selected as model projection/simulation. |

---

## Metric Registry

| Option | Description | Selected |
|--------|-------------|----------|
| Hand-pick metrics per tool during MCP implementation | Fast but risks losing intentional synthetic metrics. | |
| Full metric registry with metadata | Registry drives exposure and comparison semantics. | yes |

**User's choice:** Full and detailed metric registry.
**Notes:** Every intentionally computed synthetic metric must be accounted for. Registry should mark units, source, scope, sport sensitivity, comparison mode, directionality, requirements, missing reasons, and exposed tools.

---

## Period Comparison

| Option | Description | Selected |
|--------|-------------|----------|
| Compare only volume/load basics | Distance, time, elevation, TRIMP. | |
| Compare all registry-backed synthetic metrics where meaningful | Includes cardiac/efficiency/recovery proxies and model metrics with coverage. | yes |

**User's choice:** Compare synthetic metric trends too.
**Notes:** Service returns facts and deltas, not claims like "heart improved" or "vessels improved."

---

## Projection Tool

| Option | Description | Selected |
|--------|-------------|----------|
| Agent supplies all scenarios, service only simulates | Clean but less useful. | |
| Small set of standard scenarios plus custom | Pareto option: useful without overengineering. | yes |
| Service finds the optimal training plan | Too close to recommendation engine. | |

**User's choice:** `project_fitness_state` with `rest`, `easy`, `maintain`, and `custom`.
**Notes:** Output is model facts only: projected fitness/fatigue/form, daily TRIMP, target-date form, assumptions.

---

## Live Gateway Integration

| Option | Description | Selected |
|--------|-------------|----------|
| Repo artifacts and docs only | Prepare Docker/catalog snippets but do not touch live gateway. | |
| Live integration into existing Docker MCP gateway | Add Strava to real `/opt/docker/mcp-gateway` with smoke. | yes |
| HTTP server only | No Docker registry artifacts. | |

**User's choice:** Live gateway integration is in scope.
**Notes:** Existing mechanism is Docker MCP gateway with `/opt/docker/mcp-gateway/catalog.yaml`, `/opt/docker/mcp-gateway/compose.yaml`, and `mcp-auth-proxy`.

| Gateway Update Policy | Description | Selected |
|-----------------------|-------------|----------|
| Backup + atomic edit + smoke + rollback | Restore old gateway config if Strava smoke fails. | yes |
| Add and restart directly | Faster, more risk to shared gateway. | |
| Temporary separate gateway first | Safer but more steps. | |

---

## Docker Data And Secrets

| Data Placement | Description | Selected |
|----------------|-------------|----------|
| `/opt/docker/mcp-strava/data/strava.db` | Deploy-owned persistent data path with backup before copy/migration. | yes |
| Mount repo `data/strava.db` | Faster but couples live runtime to dev checkout. | |
| Docker named volume | Docker-clean but less transparent for backup/manual inspection. | |

| Secret Placement | Description | Selected |
|------------------|-------------|----------|
| `/opt/docker/mcp-strava/.env` | Deploy env file outside repo. | yes |
| Docker secrets | Cleaner but heavier than needed. | |
| Repo `.env` | Couples live runtime to dev checkout. | |

---

## Deferred Ideas

- Dedicated route/trip/marathon/event readiness tools.
- Separate `get_data_status` primary MCP tool.
- Server-side coaching text, motivation, or recommendation generation.
- Public multi-user/auth exposure beyond existing gateway/auth-proxy layer.
