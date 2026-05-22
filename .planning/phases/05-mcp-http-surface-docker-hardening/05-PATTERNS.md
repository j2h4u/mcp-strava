# Phase 05 Pattern Map

**Phase:** 05 - MCP HTTP Surface & Docker Hardening
**Status:** Ready for planner use

## Existing Patterns To Reuse

| Role | Existing Pattern | Files | Phase 5 Use |
|------|------------------|-------|-------------|
| Shared response envelope | Dataclasses plus `dc_to_dict()` | `src/mcp_strava/types.py` | Preserve `data`, `freshness`, `completeness`, `warnings`, `rationale` in MCP structured content. |
| Product freshness metadata | Build metadata from repository and refresh policy | `src/mcp_strava/application/freshness.py` | Reuse for every metric tool; do not expose a separate data-status tool. |
| Local DB access | Repository over injected connection | `src/mcp_strava/adapters/sqlite/repository.py` | All metric services should read through repository or existing domain functions. |
| Workout enrichment | Existing synthetic metric calculation | `src/mcp_strava/metrics.py` | `get_workout_detail` and registry coverage source. |
| Daily model state | Existing report calculation | `src/mcp_strava/report.py` | `get_fitness_state` source for Banister, ACWR, 14-day load, safety inputs. |
| Weekly load/efficiency | Existing weekly digest | `src/mcp_strava/analytics.py` | `get_fitness_state` and `compare_periods` source for rolling load/efficiency trends. |
| Forward simulation | Pure Banister simulation helpers | `src/mcp_strava/training.py` | `project_fitness_state` model projections. |
| Import guards | AST boundary checks | `tests/test_security_guards.py` | Add MCP allowlist/import guards and Docker/source guards. |
| Fixture SQLite tests | Temp DB plus `run_migrations()` | `tests/test_application_reports.py`, `tests/test_application_workouts.py` | Use for metric registry/services/MCP tests without touching live DB. |

## Files Likely Created

- `src/mcp_strava/application/metric_registry.py`
- `src/mcp_strava/application/metric_services.py`
- `src/mcp_strava/interfaces/mcp_http.py`
- `src/mcp_strava/deploy/preflight.py`
- `src/mcp_strava/deploy/smoke.py`
- `deploy/Dockerfile`
- `deploy/docker-compose.yml`
- `deploy/gateway_register.py`
- `docs/metrics.md`
- `docs/deployment.md`
- `tests/test_metric_registry.py`
- `tests/test_metric_services.py`
- `tests/test_mcp_surface.py`
- `tests/test_docker_runtime.py`
- `tests/test_gateway_integration.py`

## Data Flow

```text
MCP tool -> metric service -> repository/domain analytics -> ServiceEnvelope -> structuredContent
```

The MCP layer should not call CLI handlers, sync runtime, Strava adapter, raw SQL, token refresh, or sync logs.

## Risk Patterns

- Same-wave file conflicts are likely if registry, service registry, and MCP tool map are edited in parallel. Keep the phase mostly serialized.
- Metric loss is the main product risk. Make registry coverage tests fail before MCP implementation.
- Coaching leakage is the main contract risk. Tests should reject `recommendation`, `action`, `intensity`, `on_track`, `should`, and `ready` in MCP data shapes where they imply advice.
- Live gateway rollout is an operational risk. Keep it last, with backups and rollback.
