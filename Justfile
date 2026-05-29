set shell := ["bash", "-uc"]

compose := "docker compose -f deploy/docker-compose.yml"
smoke := "python -m mcp_strava.devtools.mcp_client.cli smoke-basic --compact --url http://127.0.0.1:8080/mcp"

default:
    @just --list

build:
    uv run python -m compileall -q src deploy tests

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
