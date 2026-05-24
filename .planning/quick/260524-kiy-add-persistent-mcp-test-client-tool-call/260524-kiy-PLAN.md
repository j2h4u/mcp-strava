---
quick_id: 260524-kiy
status: planned
---

# Add persistent MCP test client, tool-call logging, and host UID/GID Docker runtime defaults

## Scope

- Add a reusable MCP client inside the installed package so Docker-based smoke tests and manual MCP checks use the same code.
- Add structured logs around MCP tool calls so runtime diagnosis uses container logs instead of external guessing.
- Replace hard-coded container UID/GID `10001:10001` with host-user defaults configurable through compose environment.

## Verification

- Unit tests for the reusable MCP client against a fake MCP server.
- Full pytest suite.
- Docker `just test` live MCP smoke.
