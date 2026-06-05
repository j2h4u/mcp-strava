set shell := ["bash", "-uc"]

compose := "docker compose -f deploy/docker-compose.yml"
smoke := "python -m mcp_strava.devtools.mcp_client.cli smoke-basic --compact --url http://127.0.0.1:8080/mcp"

default:
    @just --list

# Build syntax check — compile all sources (matches CI)
build:
    uv run python -m compileall -q src deploy tests

# Lint with ruff — whole repo, matching CI's `ruff check .` (NOT just src/tests:
# deploy/ and root scripts are linted too, or stale findings there slip past).
lint:
    uv run ruff check .

# Check formatting without writing — whole repo, matching CI
fmt-check:
    uv run ruff format --check .

# Import-layer contracts (import-linter; matches CI's `lint-imports`)
import-contracts:
    uv run lint-imports

# Static type checking — basedpyright is the canonical checker (matches CI:
# `uv run basedpyright src`). It reads the [tool.pyright] table in pyproject.
typecheck:
    uv run basedpyright src

# Dead-code scan (also wired into `check`). At --min-confidence 80 this is
# currently false-positive-free; if a real false positive ever appears (vulture
# can't see decorator/dynamic use), add a vulture whitelist rather than dropping
# it from the gate — dead code removal is a core value of this codebase.
dead-code:
    uv run vulture src tests --min-confidence 80

# Auto-fix lint findings + formatting (whole repo, matching CI scope)
fix:
    uv run ruff check --fix .
    uv run ruff format .

# Full static gate — mirrors CI's `quality` job exactly: whole-repo lint +
# format, types, import contracts, build syntax check, dead-code scan.
check: fmt-check lint typecheck import-contracts build dead-code

# Pre-push preflight: the full CI static gate plus unit tests, locally.
# (Docker build + MCP smoke is `just test`.)
preflight: check
    uv run pytest -q

test:
    uv run pytest -q
    {{compose}} build
    {{compose}} up -d --force-recreate --remove-orphans --wait --wait-timeout 90
    {{compose}} exec -T mcp-strava {{smoke}}

mcp-smoke-full timeout="5":
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli smoke-live --timeout {{timeout}} --compact --url http://127.0.0.1:8080/mcp

mcp-read-model-perf samples="20" warmup="2" p95_ms="100":
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli perf-read-model --samples {{samples}} --warmup {{warmup}} --p95-ms {{p95_ms}} --compact --url http://127.0.0.1:8080/mcp

phase9-bundle-smoke timeout="5":
    uv run pytest -q tests/test_mcp_surface.py tests/test_mcp_test_client.py
    {{compose}} build
    {{compose}} up -d --force-recreate --remove-orphans --wait --wait-timeout 90
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli smoke-live --timeout {{timeout}} --compact --url http://127.0.0.1:8080/mcp

mcp-list-tools:
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli list-tools --url http://127.0.0.1:8080/mcp

mcp-call tool arguments="{}":
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli call-tool --name {{tool}} --arguments '{{arguments}}' --url http://127.0.0.1:8080/mcp

# Run an admin CLI command against the live mirror.
# DuckDB takes an exclusive file lock on the writer side, so admin commands
# cannot run while the owner container is up. This recipe stops the owner,
# runs the admin command in a one-shot container against the same volume,
# and restarts the owner unconditionally (trap on EXIT covers Ctrl-C and
# admin failures).
admin *args:
    #!/usr/bin/env bash
    set -euo pipefail
    trap '{{compose}} start mcp-strava >/dev/null' EXIT
    {{compose}} stop mcp-strava
    {{compose}} run --rm --no-deps -T --entrypoint python mcp-strava -m mcp_strava admin {{args}}

alias tests := test
alias smoke := test
