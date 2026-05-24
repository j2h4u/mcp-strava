---
quick_id: 260524-kiy
status: complete
completed: 2026-05-24
---

# Quick Task 260524-kiy Summary

Added persistent MCP testing and observability support while deferring performance fixes to Phase 7.

## Changed

- Added a reusable MCP SDK client under `mcp_strava.devtools.mcp_client`.
- Added fast `smoke-basic`, explicit full `smoke-live`, `list-tools`, `call-tool`, and script client commands.
- Added structured MCP tool-call logs with duration, warning count, and response data shape.
- Changed the Docker runtime user from the previous hard-coded `10001:10001` to the local host-user `1000:1000`.
- Added Phase 7 planning for a materialized metrics read model instead of committing request-time Python optimization.

## Verified

- `uv run pytest -q`
- `just test`
