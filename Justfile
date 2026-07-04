set shell := ["bash", "-uc"]

compose := "docker compose -f deploy/docker-compose.yml"
compose_ci := "docker compose -p mcp-strava-ci -f deploy/docker-compose.ci.yml"
mcp_url := "http://127.0.0.1:8080/mcp"
smoke_basic := "python -m mcp_strava.devtools.mcp_client.cli smoke-basic --timeout 20 --compact --url " + mcp_url

# Show available repo commands.
default:
    @just --list

# Compile Python sources for syntax errors.
_compile:
    uv run python -m compileall -q src deploy tests

# Lint with ruff across the whole repo.
_lint:
    uv run ruff check .

# Check formatting without writing.
_fmt-check:
    uv run ruff format --check .

# Check import-layer architecture contracts.
_import-contracts:
    uv run lint-imports

# Check GitHub Actions workflow syntax and expressions.
_actionlint:
    uv run actionlint

# Guard supply-chain pins in workflows and Dockerfiles.
_supply-chain-pins:
    uv run python scripts/check_supply_chain_pins.py

# Run the canonical static type checker.
_typecheck:
    uv run basedpyright src

# Scan for dead code with vulture.
_dead-code:
    uv run vulture src tests --min-confidence 80

# Auto-fix ruff findings and formatting.
fix:
    uv run ruff check --fix .
    uv run ruff format .

# Static quality gate: format, lint, types, imports, workflows, compile, dead code, supply-chain pins.
check: _fmt-check _lint _typecheck _import-contracts _actionlint _supply-chain-pins _compile _dead-code

# Opt-in test typecheck debt gate; not part of verify until it is green.
typecheck-tests:
    uv run basedpyright tests --warnings

# Unit tests only.
unit:
    uv run pytest -q -n auto

# Unit tests with coverage enforcement.
coverage:
    uv run pytest -q -n auto --cov=src/mcp_strava --cov-report=term-missing --cov-fail-under=80

# Build the Docker image.
_docker-build:
    {{compose}} build

# Recreate and wait for the local Docker service.
_docker-up:
    {{compose}} up -d --force-recreate --remove-orphans --wait --wait-timeout 90

# Basic MCP smoke against a running Docker service.
_mcp-smoke-basic:
    {{compose}} exec -T mcp-strava {{smoke_basic}}

# Full MCP smoke against a running Docker service.
mcp-smoke-full timeout="5":
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli smoke-live --timeout {{timeout}} --compact --url {{mcp_url}}

# Read-model perf gate against a running Docker service.
mcp-read-model-perf samples="20" warmup="2" p95_ms="100":
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli perf-read-model --samples {{samples}} --warmup {{warmup}} --p95-ms {{p95_ms}} --compact --url {{mcp_url}}

# Docker runtime gate only: build/recreate container and run basic MCP smoke.
runtime: _docker-build _docker-up _mcp-smoke-basic

# CI-safe Docker runtime gate: build the same image and smoke it without host-only mounts or networks.
runtime-ci:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p .tmp
    ci_root="$(mktemp -d "$PWD/.tmp/runtime-ci.XXXXXX")"
    cleanup() {
        status="$1"
        if [ "$status" -ne 0 ]; then
            MCP_STRAVA_CI_RUNTIME_DIR="$ci_root" MCP_STRAVA_CI_DATA_DIR="$ci_root/data" {{compose_ci}} ps || true
            MCP_STRAVA_CI_RUNTIME_DIR="$ci_root" MCP_STRAVA_CI_DATA_DIR="$ci_root/data" {{compose_ci}} logs --no-color --timestamps --tail=200 || true
        fi
        MCP_STRAVA_CI_RUNTIME_DIR="$ci_root" MCP_STRAVA_CI_DATA_DIR="$ci_root/data" {{compose_ci}} down -v --remove-orphans || true
        rm -rf "$ci_root"
    }
    trap 'cleanup "$?"' EXIT
    uv run python -c 'from pathlib import Path; import sys; from tests._fixtures_duckdb import create_fixture_db; root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True); create_fixture_db(root / "data" / "strava.duckdb")' "$ci_root"
    chmod -R a+rwX "$ci_root"
    MCP_STRAVA_CI_RUNTIME_DIR="$ci_root" MCP_STRAVA_CI_DATA_DIR="$ci_root/data" {{compose_ci}} build
    MCP_STRAVA_CI_RUNTIME_DIR="$ci_root" MCP_STRAVA_CI_DATA_DIR="$ci_root/data" {{compose_ci}} up -d --force-recreate --remove-orphans --wait --wait-timeout 90
    MCP_STRAVA_CI_RUNTIME_DIR="$ci_root" MCP_STRAVA_CI_DATA_DIR="$ci_root/data" {{compose_ci}} exec -T mcp-strava {{smoke_basic}}

# Full local gate for agents before claiming completion.
verify: check unit runtime

# Surface smoke with targeted MCP tests plus live full MCP smoke.
mcp-surface-smoke timeout="5": _docker-build _docker-up
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
