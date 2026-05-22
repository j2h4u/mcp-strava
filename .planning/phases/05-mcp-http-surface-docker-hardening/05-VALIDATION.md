---
phase: 05
slug: mcp-http-surface-docker-hardening
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-22
---

# Phase 05 - Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pyproject.toml` |
| Quick run command | `python3 -m pytest tests/test_metric_registry.py tests/test_metric_services.py tests/test_mcp_surface.py tests/test_docker_runtime.py -q` |
| Full suite command | `just test` |
| Estimated runtime | under 30 seconds for unit tests; Docker/live smoke depends on local Docker |

## Sampling Rate

- After every task commit: run the narrow pytest file for the touched surface.
- After every plan wave: run the accumulated Phase 5 pytest set.
- Before phase verification: run `just test` plus Docker/gateway smoke from the final plans.
- Max feedback latency: one task.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | MCP-01, MCP-03 | T-05-01 | Metric inventory cannot silently drop synthetic metrics | unit/source | `python3 -m pytest tests/test_metric_registry.py -q` | W0 | pending |
| 05-01-02 | 01 | 1 | MCP-01, TEST-03 | T-05-02 | Registry marks interpretation exclusions explicitly | unit/source | `python3 -m pytest tests/test_metric_registry.py -q` | W0 | pending |
| 05-02-01 | 02 | 2 | MCP-01, MCP-03 | T-05-03 | Fitness/workout services return facts plus metadata only | unit | `python3 -m pytest tests/test_metric_services.py -q` | W0 | pending |
| 05-03-01 | 03 | 3 | MCP-01, MCP-03 | T-05-04 | Comparison/projection services expose model facts, not advice | unit | `python3 -m pytest tests/test_metric_services.py tests/test_metric_registry.py -q` | W0 | pending |
| 05-04-01 | 04 | 4 | MCP-01, MCP-02, MCP-04, TEST-03 | T-05-05 | MCP tool allowlist is read-only and excludes admin/sync/raw operations | unit/integration | `python3 -m pytest tests/test_mcp_surface.py tests/test_security_guards.py -q` | W0 | pending |
| 05-05-01 | 05 | 5 | DOCKER-01, DOCKER-02, MCP-04 | T-05-06 | Container fails closed on missing DB and has no public port by default | source/smoke | `python3 -m pytest tests/test_docker_runtime.py -q` | W0 | pending |
| 05-06-01 | 06 | 6 | DOCKER-03, MCP-04 | T-05-07 | Gateway edits are backed up and rolled back on failed smoke | source/smoke | `python3 -m pytest tests/test_gateway_integration.py -q` | W0 | pending |

## Wave 0 Requirements

- `tests/test_metric_registry.py` - registry coverage and interpretation exclusion tests.
- `tests/test_metric_services.py` - service envelope and no-coaching tests.
- `tests/test_mcp_surface.py` - MCP tool allowlist, annotations, and structured response tests.
- `tests/test_docker_runtime.py` - Dockerfile/compose/preflight source tests.
- `tests/test_gateway_integration.py` - backup/atomic edit/rollback tests with temp files.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker image build | DOCKER-01, DOCKER-02 | Requires local Docker daemon | `docker compose -f deploy/docker-compose.yml build` |
| Live backend smoke | MCP-01, MCP-04 | Requires container runtime and copied mirror DB | `python3 -m mcp_strava.deploy.smoke --url http://127.0.0.1:${MCP_STRAVA_HTTP_PORT:-8000}/mcp --expect-tool get_fitness_state` when a loopback smoke port is intentionally enabled |
| Live gateway registration | DOCKER-03 | Mutates `/opt/docker/mcp-gateway` and must use backups | Run the planned gateway registration command; confirm smoke passes or rollback restores previous files |

## Validation Sign-Off

- [x] All tasks have automated verification or explicit manual-only justification.
- [x] Sampling continuity: no 3 consecutive tasks without automated verification.
- [x] Wave 0 covers all missing Phase 5 test files.
- [x] No watch-mode flags.
- [x] Feedback latency under one task for unit/source checks.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending execution
