set shell := ["bash", "-uc"]

compose := "docker compose -f deploy/docker-compose.yml"
smoke := "python -m mcp_strava.devtools.mcp_client.cli smoke-basic --compact --url http://127.0.0.1:8080/mcp"

default:
    @just --list

test:
    {{compose}} build
    {{compose}} up -d --force-recreate --remove-orphans --wait --wait-timeout 90
    {{compose}} exec -T mcp-strava {{smoke}}

mcp-smoke-full timeout="5":
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli smoke-live --timeout {{timeout}} --compact --url http://127.0.0.1:8080/mcp

mcp-read-model-perf samples="20" warmup="2" p95_ms="100":
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli perf-read-model --samples {{samples}} --warmup {{warmup}} --p95-ms {{p95_ms}} --compact --url http://127.0.0.1:8080/mcp

mcp-list-tools:
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli list-tools --url http://127.0.0.1:8080/mcp

mcp-call tool arguments="{}":
    {{compose}} exec -T mcp-strava python -m mcp_strava.devtools.mcp_client.cli call-tool --name {{tool}} --arguments '{{arguments}}' --url http://127.0.0.1:8080/mcp

alias tests := test
alias smoke := test
