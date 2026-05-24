---
analysis_date: 2026-05-22
last_mapped_commit: b207e64f8293ddb0b3432562705b96a0a0264082
---
# Technology Stack

**Analysis Date:** 2026-05-22

## Languages

**Primary:**
- Python 3.14+ - Runtime code in `src/mcp_strava/*.py`, deployment helpers in `deploy/*.py`, and package metadata in `pyproject.toml`.

**Secondary:**
- YAML - Docker Compose and gateway catalog mutation in `deploy/docker-compose.yml` and `deploy/gateway_register.py`.
- Dockerfile syntax - Container image build in `deploy/Dockerfile`.

## Runtime

**Environment:**
- CPython 3.14 - The project declares `requires-python = ">=3.14"` in `pyproject.toml`, and the container image uses `python:3.14-slim` in `deploy/Dockerfile`.
- Local package install - The container build installs the project from `/app` with `pip install --no-cache-dir /app`.

**Package Manager:**
- `uv` lockfile is present - `uv.lock` pins the resolved dependency graph.
- `pip` is used during image build - `deploy/Dockerfile` installs the project directly from the source tree.

## Frameworks

**Core:**
- `mcp` 1.27.1 - Provides `FastMCP`, the `streamable-http` transport, MCP client smoke tooling, and transport security in `src/mcp_strava/interfaces/mcp_http.py` and `src/mcp_strava/deploy/smoke.py`.

**Testing:**
- `pytest` - Declared as the `test` extra in `pyproject.toml`; not the primary runtime entrypoint.

**Build/Dev:**
- `setuptools` - Build backend declared in `pyproject.toml`.
- `docker` / `docker compose` - Container build and service wiring in `deploy/Dockerfile` and `deploy/docker-compose.yml`.

## Key Dependencies

**Critical:**
- `mcp` 1.27.1 - MCP server surface and SDK client support; the lockfile shows `anyio`, `httpx`, `jsonschema`, `pydantic`, `pydantic-settings`, `starlette`, `uvicorn`, and related transitive packages.
- `PyYAML` 6.0.3 - YAML parsing/serialization for gateway registration in `deploy/gateway_register.py`.

**Infrastructure:**
- `sqlite3` (stdlib) - Local mirror storage, preflight checks, backups, and migrations in `src/mcp_strava/adapters/sqlite/*`.
- `urllib.request` / `urllib.error` / `urllib.parse` (stdlib) - Strava OAuth and API requests in `src/mcp_strava/adapters/strava/token_refresh.py` and `src/mcp_strava/adapters/strava/transport.py`.
- `json` (stdlib) - Serialization of Strava payloads, MCP envelopes, and CLI output across `src/mcp_strava/*.py`.

## Configuration

**Environment:**
- `src/mcp_strava/settings.py` loads `MCP_STRAVA_DB_PATH`, `MCP_STRAVA_TOKEN_PATH`, `MCP_STRAVA_RUNTIME_PROFILE`, `MCP_STRAVA_HTTP_HOST`, `MCP_STRAVA_HTTP_PORT`, `MCP_STRAVA_ALLOW_CONTAINER_BIND`, `MCP_STRAVA_ALLOWED_HOSTS`, `MCP_STRAVA_ALLOWED_ORIGINS`, `MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS`, `MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS`, and `MCP_STRAVA_PROJECT_ROOT`.
- Strava auth values are file-backed in the token file: `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`, `STRAVA_ACCESS_TOKEN`, and `STRAVA_EXPIRES_AT` in `src/mcp_strava/adapters/strava/token_provider.py` and `src/mcp_strava/db.py`.
- `deploy/Dockerfile` and `deploy/docker-compose.yml` hard-set container-safe defaults for `MCP_STRAVA_RUNTIME_PROFILE`, `MCP_STRAVA_HTTP_HOST`, `MCP_STRAVA_HTTP_PORT`, `MCP_STRAVA_ALLOW_CONTAINER_BIND`, and `MCP_STRAVA_DB_PATH`.

**Build:**
- `pyproject.toml` defines the build backend, package metadata, and the `src` package root.
- `uv.lock` pins the full resolved dependency set.
- `deploy/Dockerfile` and `deploy/docker-compose.yml` define the container runtime contract.

## Platform Requirements

**Development:**
- Python 3.14+ with write access to the repo checkout, local `.env`, and `data/`.
- Network access to `https://www.strava.com` for token refresh and API fetches.
- Local SQLite mirror state under `data/strava.db` or the path selected by `MCP_STRAVA_DB_PATH`.

**Production:**
- Docker container runtime on the local MCP network.
- Local-only or container-network-safe HTTP binding enforced by `src/mcp_strava/interfaces/mcp_http.py` and `deploy/Dockerfile`.

---

*Stack analysis: 2026-05-22*
