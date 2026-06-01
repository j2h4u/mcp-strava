---
analysis_date: 2026-06-01
last_mapped_commit: d16b5fd
scope: full-repo
---
# Technology Stack

**Analysis Date:** 2026-06-01

## Languages

**Primary:**
- Python 3.14 - All application code in `src/mcp_strava/`

**Secondary:**
- Bash - `deploy/Dockerfile`, `Justfile` shell recipes (via `set shell := ["bash", "-uc"]`)
- YAML - `deploy/docker-compose.yml`, `deploy/gateway_register.py` catalog manipulation
- Markdown - `mcp-content/prompts/*.md` (MCP prompt templates served at runtime)

## Runtime

**Environment:**
- CPython 3.14 (minimum: `requires-python = ">=3.14"`)
- Uses Python 3.14 idioms via ruff's `UP` ruleset (enforced)

**Package Manager:**
- `uv` for development (all Justfile recipes use `uv run`)
- `pip install /app` for container image builds (no uv in container)
- Lockfile: not present in repo (pip install from `pyproject.toml` constraints only)

## Frameworks

**Core:**
- `mcp>=1.27.1,<1.28` - MCP SDK; `FastMCP` used for HTTP server, tool registration, transport security
  - Transport: `streamable-http` at `/mcp` path (`src/mcp_strava/interfaces/mcp_http.py`)
  - Security: `TransportSecuritySettings` with DNS rebinding protection, host/origin allowlists

**Testing:**
- `pytest>=9` - test runner; config in `pyproject.toml` (`testpaths = ["tests"]`, `pythonpath = ["src"]`)

**Build/Dev:**
- `ruff>=0.15` - linter + formatter (`line-length = 120`, selects `E4/E7/E9,F,I,B,UP`)
- `pyright>=1.1.390` - static type checker (`typeCheckingMode = "standard"`, `pythonVersion = "3.14"`)
- `just` (Justfile) - task runner for lint, test, smoke, deploy recipes
- `setuptools>=69` - build backend (`package-dir = {"" = "src"}`)

## Key Dependencies

**Critical:**
- `duckdb>=1.5.3,<1.6` - embedded analytical database used as the local Strava mirror (`src/mcp_strava/adapters/duckdb/`)
- `mcp>=1.27.1,<1.28` - Model Context Protocol SDK; pins minor to avoid breaking changes
- `PyYAML>=6.0.2,<7` - used in `deploy/gateway_register.py` for MCP gateway catalog manipulation

**Standard library only for HTTP:**
- Strava API calls use `urllib.request` + `urllib.error` exclusively — no requests/httpx dependency
  (see `src/mcp_strava/adapters/strava/transport.py`, `src/mcp_strava/adapters/strava/token_refresh.py`)

## Configuration

**Environment:**
- Settings loaded via `src/mcp_strava/settings.py` — reads from env vars (priority) then a `.env` file
- Token file (`MCP_STRAVA_TOKEN_PATH`, default `<project-root>/.env`; compose sets `/runtime/.env`) holds OAuth tokens and Strava client credentials separately from runtime settings
- `MCP_STRAVA_*` namespace for all operational settings; `STRAVA_*` namespace for OAuth credentials (never mixed)
- Key required configs:
  - `MCP_STRAVA_DB_PATH` - path to DuckDB file
  - `MCP_STRAVA_TOKEN_PATH` - path to token/credential file
  - `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_ACCESS_TOKEN`, `STRAVA_REFRESH_TOKEN`, `STRAVA_EXPIRES_AT` (in token file)
  - `MCP_STRAVA_HR_REST` - operator's resting heart rate (optional but required for some computations)
- `MCP_STRAVA_RUNTIME_PROFILE`: `local` | `container` / `docker` / `live`

**Build:**
- `pyproject.toml` - single source of truth for package metadata, dependencies, ruff, pyright, pytest config
- `deploy/Dockerfile` - `python:3.14-slim` base, installs package via `pip install /app`, runs as uid 1000:1000
- `deploy/docker-compose.yml` - single-service compose, external `mcp-backends` network, volume mount at `/runtime`

## Platform Requirements

**Development:**
- Python 3.14+
- `uv` for running lint/test/typecheck (`just check`, `just test`)
- Docker + `docker compose` for integration smoke tests (`just test` builds and runs the container)

**Production:**
- Docker container on `mcp-backends` external network
- Volume mount: `/opt/docker/mcp-strava` → `/runtime` (holds DuckDB file and token env file)
- Exposed port: 8080 (internal only — no host port published by default)
- Healthcheck: `python -m mcp_strava.deploy.healthcheck` every 30s

---

*Stack analysis: 2026-06-01*
