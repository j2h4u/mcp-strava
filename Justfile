set shell := ["bash", "-uc"]

compose := "docker compose -f deploy/docker-compose.yml"
mcp_url := "http://127.0.0.1:8080/mcp"
smoke_basic := "python -m mcp_strava.devtools.mcp_client.cli smoke-basic --compact --url " + mcp_url

# Show available repo commands.
default:
    @just --list

# Compile Python sources for syntax errors.
compile:
    uv run python -m compileall -q src deploy tests

# Lint with ruff across the whole repo.
lint:
    uv run ruff check .

# Check formatting without writing.
fmt-check:
    uv run ruff format --check .

# Check import-layer architecture contracts.
import-contracts:
    uv run lint-imports

# Run the canonical static type checker.
typecheck:
    uv run basedpyright src

# Scan for dead code with vulture.
dead-code:
    uv run vulture src tests --min-confidence 80

# Auto-fix ruff findings and formatting.
fix:
    uv run ruff check --fix .
    uv run ruff format .

# Static quality gate: format, lint, types, imports, compile, dead code.
check: fmt-check lint typecheck import-contracts compile dead-code

# Unit tests only.
unit:
    uv run pytest -q -n auto

# Build the Docker image.
docker-build:
    {{compose}} build

# Recreate and wait for the local Docker service.
docker-up:
    {{compose}} up -d --force-recreate --remove-orphans --wait --wait-timeout 90

# Basic MCP smoke against a running Docker service.
mcp-smoke-basic:
    {{compose}} exec -T mcp-strava {{smoke_basic}}

# Full MCP smoke against a running Docker service.
mcp-smoke-full timeout="5":
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli smoke-live --timeout {{timeout}} --compact --url {{mcp_url}}

# Read-model perf gate against a running Docker service.
mcp-read-model-perf samples="20" warmup="2" p95_ms="100":
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli perf-read-model --samples {{samples}} --warmup {{warmup}} --p95-ms {{p95_ms}} --compact --url {{mcp_url}}

# Docker runtime gate: unit tests, Docker build/recreate, basic MCP smoke.
runtime-verify: unit docker-build docker-up mcp-smoke-basic

# Full local gate for agents before claiming completion.
verify: check runtime-verify

# Surface smoke with targeted MCP tests plus live full MCP smoke.
mcp-surface-smoke timeout="5": docker-build docker-up
    uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli smoke-live --timeout {{timeout}} --compact --url {{mcp_url}}

# List MCP tools on a running Docker service.
mcp-list-tools:
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli list-tools --url {{mcp_url}}

# Call one MCP tool on a running Docker service.
mcp-call tool arguments="{}":
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli call-tool --name {{tool}} --arguments '{{arguments}}' --url {{mcp_url}}

# Run an admin CLI command in a one-shot container.
admin *args:
    #!/usr/bin/env bash
    set -euo pipefail
    trap '{{compose}} start mcp-strava >/dev/null' EXIT
    {{compose}} stop mcp-strava
    {{compose}} run --rm --no-deps -T --entrypoint python mcp-strava -m mcp_strava admin {{args}}
