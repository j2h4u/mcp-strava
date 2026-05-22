---
phase: 05-mcp-http-surface-docker-hardening
plan: 05-06
subsystem: deploy
tags: [gateway, docker, rollback, smoke, docs, operator-confirm]
requires:
  - phase: 05-04
    provides: read-only MCP HTTP surface and tool contracts
  - phase: 05-05
    provides: docker runtime/preflight and canonical live runtime paths
provides:
  - safe gateway registration helper with backup/atomic rollback flow
  - SDK-backed MCP smoke client via streamable HTTP client/session
  - deployment runbook with dry-run default and operator-approved live apply boundary
affects: [gateway-integration, deploy-tooling, docs, tests]
tech-stack:
  added: [PyYAML>=6.0.2,<7]
  patterns: [dry-run-by-default, dual-file-atomic-mutation, rollback-restart, operator-confirm-gate]
key-files:
  created:
    - deploy/gateway_register.py
    - src/mcp_strava/deploy/smoke.py
    - docs/deployment.md
    - tests/test_gateway_integration.py
  modified:
    - pyproject.toml
    - tests/test_smoke.py
decisions:
  - "Live gateway paths can be dry-run checked, but mutation requires both --apply and --confirm-live-gateway."
  - "Gateway registration mutates catalog and compose as one operation with backup, post-write validation, restart, smoke, and rollback restart."
  - "Plan closes at operator-confirm boundary without mutating /opt/docker/mcp-gateway/*."
metrics:
  duration: "completed in-session"
  completed: 2026-05-22
requirements-completed: [MCP-01, MCP-02, MCP-03, MCP-04, DOCKER-01, DOCKER-02, DOCKER-03, TEST-03]
---

# Phase 05 Plan 06: Gateway Integration Safety and Operator Boundary Summary

Safe MCP gateway integration tooling, SDK smoke client, and deployment runbook were implemented and verified in dry-run mode; live `/opt/docker/mcp-gateway/*` mutation is intentionally pending explicit operator approval.

## Task Commits

1. `cffe056` — `test(05-06): add failing gateway integration and smoke tests`
2. `6f54e2f` — `feat(05-06): add safe gateway registration helper and sdk smoke client`
3. `776f9aa` — `fix(05-06): allow live-path dry-run while gating apply by confirm flag`
4. `cb29e82` — `docs(05-06): add deployment and gateway integration runbook`

## Verification

- `python3 -m pytest tests/test_gateway_integration.py tests/test_smoke.py -q` ✅ fails in RED before implementation (`ImportError` for missing `deploy.gateway_register`)
- `uv run python -m pytest tests/test_gateway_integration.py tests/test_mcp_surface.py -q` ✅ (15 passed)
- `uv run python -m pytest tests/test_gateway_integration.py tests/test_docker_runtime.py tests/test_mcp_surface.py -q` ✅ (28 passed)
- `docker compose -f deploy/docker-compose.yml config` ⚠️ fails in this repo-only environment because `/opt/docker/mcp-strava/.env` is not present yet
- `docker compose -f deploy/docker-compose.yml build` ✅
- `python3 deploy/gateway_register.py --catalog /opt/docker/mcp-gateway/catalog.yaml --compose /opt/docker/mcp-gateway/compose.yaml --service strava --url http://mcp-strava:8080/mcp --smoke-cmd "docker compose -f deploy/docker-compose.yml exec -T mcp-strava python -m mcp_strava.deploy.smoke --url http://mcp-gateway:8811/mcp --expect-tool get_fitness_state --forbid-tool sync --forbid-tool sql"` ✅ dry-run only (`dry-run: planned catalog/compose mutation prepared`)
- `just test` ✅ (180 passed)

## Operator-Confirm Boundary

No live gateway files were mutated:

- `/opt/docker/mcp-gateway/catalog.yaml` untouched
- `/opt/docker/mcp-gateway/compose.yaml` untouched
- `mcp-gateway` was not restarted by this plan execution

Pending operator-approved command:

```bash
python3 deploy/gateway_register.py --apply --confirm-live-gateway --catalog /opt/docker/mcp-gateway/catalog.yaml --compose /opt/docker/mcp-gateway/compose.yaml --service strava --url http://mcp-strava:8080/mcp --smoke-cmd "docker compose -f deploy/docker-compose.yml exec -T mcp-strava python -m mcp_strava.deploy.smoke --url http://mcp-gateway:8811/mcp --expect-tool get_fitness_state --forbid-tool sync --forbid-tool sql"
```

## Deviations from Plan

### Auto-fixed Issues

1. **[Rule 1 - Bug] Idempotent path rewrote unchanged YAML**
- **Found during:** Task 2 verification
- **Issue:** applying when `strava` already existed rewrote YAML formatting.
- **Fix:** added semantic no-op fast path to return success without writing when parsed catalog+compose are unchanged.
- **Files modified:** `deploy/gateway_register.py`
- **Commit:** `6f54e2f`

2. **[Rule 2 - Missing Critical Functionality] Dry-run should be allowed for live path planning**
- **Found during:** Task 3 verification alignment
- **Issue:** guard rejected live-path dry-run even without mutation.
- **Fix:** require `--confirm-live-gateway` only when `--apply` is requested; keep live writes blocked without both flags.
- **Files modified:** `deploy/gateway_register.py`, `tests/test_gateway_integration.py`
- **Commit:** `776f9aa`

## Authentication Gates

None.

## Known Stubs

None.

## Self-Check: PASSED
