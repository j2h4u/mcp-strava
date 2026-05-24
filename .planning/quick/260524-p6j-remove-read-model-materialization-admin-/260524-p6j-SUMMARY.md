---
quick_id: 260524-p6j
status: complete
completed: 2026-05-24
---

# Quick Task 260524-p6j Summary

Removed the manual read-model materialization admin command and redundant MCP forbidden-name list.

## Changed

- Removed `admin read-model-materialize` from the CLI surface.
- Kept materialization as automatic runtime behavior under refresh/backfill paths.
- Removed `FORBIDDEN_TOOL_NAMES` and made the reusable MCP client verify the exact expected product tool set.
- Updated deployment smoke options and docs to rely on exact tool-surface verification.
- Removed tests that encoded the deleted manual admin command and redundant forbidden-name guard.

## Verified

- `uv run pytest -q tests/test_cli_surface.py tests/test_mcp_surface.py tests/test_gateway_integration.py tests/test_smoke.py tests/test_refresh_runtime.py tests/test_docker_runtime.py`
- `uv run pytest -q`
- `just test`
