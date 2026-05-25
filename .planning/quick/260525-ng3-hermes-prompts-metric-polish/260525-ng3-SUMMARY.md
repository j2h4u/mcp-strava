---
quick_id: 260525-ng3
slug: hermes-prompts-metric-polish
status: complete
completed_at: "2026-05-25T17:01:06+05:00"
---

# Summary

Implemented the approved MCP/metric polish as a GSD quick task.

## Completed

- Added markdown-backed MCP prompts for daily training brief, weekly digest, and shoe-mileage watchdog scenarios.
- Kept MCP tool allowlist unchanged and added factual narrative guardrails to MCP instructions.
- Rounded floats at the MCP payload boundary while preserving raw service serialization by default.
- Restored freshness gating for per-sport cardiac-cost progressive trends.
- Exposed Strava kudos as `kudos_count` in workout list/detail and `kudos_names` in workout detail.
- Added kudos metrics and interpretation caveats to the metric registry documentation.

## Verification

- `uv run pytest -q tests/test_smoke.py tests/test_metric_registry.py tests/test_metric_services.py tests/test_mcp_surface.py tests/test_docker_runtime.py tests/test_repository_boundary.py tests/test_read_model_queries.py` -> 80 passed, 1 skipped.
- `uv run pytest -q` -> 274 passed, 1 skipped.
- `just test` -> Docker build, healthy container, MCP smoke passed.
- Docker prompt check -> three MCP prompts available and content loaded from `/app/mcp-content`.
