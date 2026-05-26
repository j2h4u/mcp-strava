---
analysis_date: 2026-05-26
last_mapped_commit: ab203ab
scope:
  - README.md
  - mcp-content
  - tests
---
# Technology Stack

**Analysis Date:** 2026-05-26

## Languages

**Primary:**
- Python 3.14+ - Runtime package under `src/mcp_strava`, package metadata in `pyproject.toml`, and test coverage in `tests/*.py`. The Python version contract is declared in `pyproject.toml` and asserted by `tests/test_docker_runtime.py`.

**Secondary:**
- Markdown - Operator documentation in `README.md` and MCP prompt content in `mcp-content/prompts/strava_daily_training_brief.md`, `mcp-content/prompts/strava_weekly_training_digest.md`, and `mcp-content/prompts/strava_shoe_mileage_watchdog.md`.
- TOML - Project metadata and pytest configuration in `pyproject.toml`; dependency lock data in `uv.lock`.
- Justfile task syntax - Local command surface in `Justfile`.
- Docker Compose / Dockerfile syntax - Container runtime contract is tested by `tests/test_docker_runtime.py` against `deploy/docker-compose.yml` and `deploy/Dockerfile`.

## Runtime

**Environment:**
- CPython 3.14 - `pyproject.toml` declares `requires-python = ">=3.14"`; `tests/test_docker_runtime.py` asserts `sys.version_info[:2] == (3, 14)` and a `python:3.14-slim` container base.
- Docker container runtime - `README.md` and `Justfile` run the product MCP server in Docker Compose, with the HTTP MCP endpoint checked at `http://127.0.0.1:8080/mcp`.
- Local source runtime - `tests/test_phase01_validation.py` verifies `PYTHONPATH=src python -m mcp_strava` usage.

**Package Manager:**
- `uv` - Required by `README.md`; `uv.lock` pins the resolved dependency graph.
- `setuptools` - Build backend in `pyproject.toml`.
- Lockfile: present at `uv.lock`.

## Frameworks

**Core:**
- `mcp` 1.27.1 - Provides FastMCP, streamable HTTP transport, tool annotations, and transport security. SDK feature contracts are asserted in `tests/test_mcp_sdk_contract.py`; product surface behavior is asserted in `tests/test_mcp_surface.py`.

**Testing:**
- `pytest` 9.0.3 - Declared as the `test` extra in `pyproject.toml`, pinned in `uv.lock`, configured with `testpaths = ["tests"]` and `pythonpath = ["src"]`.

**Build/Dev:**
- `just` - Developer command runner in `Justfile`.
- Docker Compose - Container build/start/smoke workflow in `Justfile`, with source contracts asserted by `tests/test_docker_runtime.py`.
- `compileall` - `Justfile` `build` target compiles `src`, `deploy`, and `tests`.

## Key Dependencies

**Critical:**
- `duckdb` 1.5.3 - Primary runtime storage/read-model engine. `pyproject.toml` requires `duckdb>=1.5.3,<1.6`, `uv.lock` pins 1.5.3, and `tests/test_duckdb_repository.py` covers repository behavior.
- `mcp` 1.27.1 - MCP HTTP server and client tooling. `tests/test_mcp_surface.py` verifies exposed tools, prompts, read-only annotations, structured output, and short-lived response caching.
- `PyYAML` 6.0.3 - Declared runtime dependency in `pyproject.toml` and pinned in `uv.lock` for YAML-backed deployment/configuration support.

**Infrastructure:**
- `sqlite3` (stdlib) - SQLite mirror, migrations, compatibility input, and fixtures. README documents `data/strava.db`; tests cover SQLite repositories and migration behavior in `tests/test_full_fidelity_mirror.py`, `tests/test_repository_boundary.py`, and `tests/test_sqlite_safety.py`.
- `urllib.request` / `urllib.error` (stdlib) - Strava HTTP and OAuth transport boundary, isolated by `tests/test_strava_adapter.py` and guarded by `tests/test_security_guards.py`.
- `json` (stdlib) - CLI/MCP payloads, fake MCP server messages, Strava fixtures, and read-model test payloads across `tests/test_mcp_test_client.py`, `tests/fixtures/fake_mcp_server.py`, and `tests/test_refresh_runtime.py`.
- `tomllib` (stdlib) - Metadata validation in `tests/test_phase01_validation.py` and `tests/test_docker_runtime.py`.

## Configuration

**Environment:**
- Runtime settings are environment driven through `mcp_strava.settings`, with defaults and validation asserted in `tests/test_settings.py`.
- Primary runtime setting: `MCP_STRAVA_DB_PATH`. Local defaults resolve to `data/strava.duckdb`; Docker profile defaults resolve to `/runtime/data/strava.duckdb`.
- Token file setting: `MCP_STRAVA_TOKEN_PATH`, defaulting to `.env` locally and `/runtime/.env` in Docker.
- HTTP settings: `MCP_STRAVA_RUNTIME_PROFILE`, `MCP_STRAVA_HTTP_HOST`, `MCP_STRAVA_HTTP_PORT`, `MCP_STRAVA_ALLOW_CONTAINER_BIND`, `MCP_STRAVA_ALLOWED_HOSTS`, and `MCP_STRAVA_ALLOWED_ORIGINS`.
- Freshness and refresh settings: `MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS`, `MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS`, `MCP_STRAVA_REFRESH_INTERVAL_SECONDS`, `MCP_STRAVA_STREAM_BACKFILL_BATCH_SIZE`, and `MCP_STRAVA_READ_MODEL_BATCH_SIZE`.
- Service/runtime settings seen in tests: `MCP_STRAVA_PROJECT_ROOT`, `MCP_STRAVA_REFRESH_WORKER_ENABLED`, and `MCP_STRAVA_SUPERVISOR_STATE_PATH`.
- Strava credentials are file-backed in `.env` or `/opt/docker/mcp-strava/.env`: `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_ACCESS_TOKEN`, `STRAVA_REFRESH_TOKEN`, and `STRAVA_EXPIRES_AT`.
- `.env` file present - contains local environment configuration and secret material; contents are not read.

**Build:**
- `pyproject.toml` defines project metadata, build backend, dependencies, `src` package root, and pytest configuration.
- `uv.lock` pins dependency versions.
- `Justfile` defines Docker build/start/smoke tasks.
- `tests/test_docker_runtime.py` asserts `deploy/Dockerfile`, `deploy/docker-compose.yml`, and `deploy/.dockerignore` runtime contracts.

## Platform Requirements

**Development:**
- Python 3.14+.
- `uv`.
- Docker with Compose.
- `just`.
- Local `.env` containing Strava OAuth credentials.
- Network access to `https://www.strava.com` for OAuth/token refresh and Strava API reads.
- Writable local storage under `data/` for DuckDB/SQLite mirror files and test fixtures.

**Production:**
- Docker Compose service named `mcp-strava` on the local MCP network.
- Runtime state under `/opt/docker/mcp-strava`, mounted into the container as `/runtime`.
- Streamable HTTP MCP endpoint exposed on container port `8080`; `Justfile` smoke tasks access `http://127.0.0.1:8080/mcp`.
- Local/container-network-safe HTTP settings with allowed hosts and origins enforced by the MCP transport security tests in `tests/test_mcp_surface.py`.

---

*Stack analysis: 2026-05-26*
