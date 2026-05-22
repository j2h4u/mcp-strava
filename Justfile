set shell := ["bash", "-uc"]

compose := "docker compose -f deploy/docker-compose.yml"
smoke := "python -m mcp_strava.deploy.smoke --expect-tool get_fitness_state --expect-tool list_workouts --expect-tool get_workout_detail --expect-tool compare_periods --expect-tool project_fitness_state --forbid-tool sync --forbid-tool backfill --forbid-tool sql --forbid-tool get_data_status --call get_fitness_state"

default:
    @just --list

test:
    {{compose}} build
    {{compose}} up -d --force-recreate --wait --wait-timeout 90
    {{compose}} exec -T mcp-strava {{smoke}} --url http://127.0.0.1:8080/mcp

gateway-smoke:
    {{compose}} exec -T mcp-strava {{smoke}} --url http://mcp-gateway:8811/mcp

alias tests := test
alias smoke := test
