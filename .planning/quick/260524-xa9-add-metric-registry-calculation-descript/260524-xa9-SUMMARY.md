---
quick_id: 260524-xa9
slug: add-metric-registry-calculation-descript
status: complete
completed: 2026-05-25
---

# Quick Task 260524-xa9 - Summary

## Outcome

Added calculation descriptions to the metric registry contract so agents can understand how each metric is produced without reading implementation code.

## Changes

- Added required `MetricDefinition.calculation` metadata.
- Populated calculation descriptions for all 74 current registry metrics.
- Exposed calculation metadata through `metric_catalog_payload()`.
- Regenerated `docs/metrics.md` with a calculation column.
- Added tests that reject missing or placeholder calculation descriptions and verify docs/catalog sync.

## Verification

| Command | Result |
|---------|--------|
| `uv run pytest -q tests/test_metric_registry.py` | `9 passed` |
| `uv run pytest -q tests/test_metric_registry.py tests/test_security_guards.py` | `32 passed` |
| `uv run pytest -q` | `264 passed, 1 skipped` |
| `just test` | Docker image rebuilt, container healthy, MCP smoke returned the five product tools and called `list_workouts`. |
| `docker compose -f deploy/docker-compose.yml exec -T mcp-strava python - <<'PY' ...` | Runtime registry has 74 metrics and all 74 expose non-empty `calculation`. |

## Notes

The descriptions intentionally document current implementation gaps where they exist, for example `cardiac_cost_adjusted` currently materializes to the same value as `cardiac_cost` in the v5 read model.
