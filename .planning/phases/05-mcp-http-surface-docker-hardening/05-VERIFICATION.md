---
phase: 05-mcp-http-surface-docker-hardening
verified: 2026-05-22T12:08:23Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
---

# Phase 05: MCP HTTP Surface & Docker Hardening Verification Report

**Phase Goal:** MCP users can access read-only intent-level training tools over a local-safe HTTP server, with container/runtime boundaries ready for local gateway integration.
**Verified:** 2026-05-22T12:08:23Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | MCP HTTP server exposes only read-only training tools for workouts/reports/load/readiness/recommendations intent. | ✓ VERIFIED | `MCP_TOOL_NAMES` is exactly five tools and all tool annotations are read-only in `mcp_http.py`; forbidden names are explicitly excluded and tested. |
| 2 | MCP surface excludes sync/backfill/raw/sql/token/admin/sync-log operations and tests prove absence. | ✓ VERIFIED | Forbidden names are defined in `FORBIDDEN_TOOL_NAMES` and tested as disjoint in MCP surface tests; gateway smoke also supports forbid checks. |
| 3 | MCP responses include freshness and completeness metadata when data is stale/partial. | ✓ VERIFIED | Every tool returns `_envelope_payload` with `freshness`/`completeness`; metric service envelopes include partial/unavailable completeness and warning metadata. |
| 4 | Container runtime uses persistent `data/`, fails closed on missing/unreadable DB, runs non-root, and keeps local-safe bind defaults. | ✓ VERIFIED | Docker compose mounts `/opt/docker/mcp-strava/data:/data` and exposes only internal port; Dockerfile switches to non-root UID/GID; preflight validates expected DB/integrity/tables and exits non-zero on failure. |
| 5 | Metric contract is registry-driven and not a CLI-name clone. | ✓ VERIFIED | `METRIC_REGISTRY` + `MCP_TOOL_IDS` define tool exposure, with comprehensive registry tests and docs-sync guard. |
| 6 | Comparison/projection services provide factual metrics/model outputs without coaching/advice fields. | ✓ VERIFIED | `compare_periods_service` and `project_fitness_state_service` output facts; tests assert forbidden recommendation/ready/should fields are absent. |
| 7 | Gateway integration tooling is dry-run by default and live mutation is gated by explicit operator confirmation. | ✓ VERIFIED | `register_strava_gateway(... apply=False)` is no-write dry-run; live path apply requires `--apply --confirm-live-gateway`; tested in gateway integration tests. |
| 8 | Gateway mutation workflow supports prevalidate, backup both files, atomic write, restart, smoke, and rollback (including rollback-restart failure code). | ✓ VERIFIED | `gateway_register.py` enforces operation order and rollback; tests cover prevalidation failure, mid-write crash rollback, smoke failure rollback, and distinct rollback restart failure code `42`. |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/mcp_strava/interfaces/mcp_http.py` | MCP HTTP read-only server and allowlist | ✓ VERIFIED | Exists, substantive, wired via tests and module entrypoint. |
| `src/mcp_strava/application/metric_registry.py` | Metric contract and exclusions | ✓ VERIFIED | Exists, substantive registry + helpers + exclusion map. |
| `src/mcp_strava/application/metric_services.py` | Five metric service backends | ✓ VERIFIED | Exists, substantive service logic for fitness/workouts/compare/project. |
| `deploy/Dockerfile` | Non-root runtime with preflight entrypoint | ✓ VERIFIED | Exists, non-root UID/GID, preflight healthcheck, entrypoint. |
| `deploy/docker-compose.yml` | Persistent data volume, local-safe network exposure | ✓ VERIFIED | Exists, `expose` only, external `mcp-backends`, no host `ports`. |
| `deploy/gateway_register.py` | Safe gateway registration with rollback | ✓ VERIFIED | Exists, YAML mutation, backup, rollback, operator-confirm gate. |
| `src/mcp_strava/deploy/preflight.py` | Fail-closed runtime DB checks | ✓ VERIFIED | Exists, expected DB open + integrity/table checks. |
| `src/mcp_strava/deploy/prepare_runtime.py` | Backup/copy runtime prep + live env marker | ✓ VERIFIED | Exists, backup-before-replace and canonical live env output. |
| `src/mcp_strava/deploy/smoke.py` | SDK-based MCP smoke client | ✓ VERIFIED | Exists, uses `mcp.client.streamable_http` + `ClientSession`. |
| `docs/deployment.md` | Operator runbook with dry-run/apply/rollback semantics | ✓ VERIFIED | Exists, canonical paths + explicit operator approval boundary documented. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `mcp_http.py` | `metric_services.py` | direct imports + tool handlers | WIRED | Each of 5 MCP tools calls the matching service function. |
| `metric_services.py` | `metric_registry.py` | `METRIC_REGISTRY` usage + metric projection | WIRED | Service payloads and comparison routing are registry-driven. |
| `metric_services.py` | local data sources | `SQLiteRepository` + `daily_report_from_connection` + `weekly_digest` | WIRED | Runtime data is sourced from repo/report/analytics paths, not static stubs. |
| `entrypoint.py` | `preflight.py` + MCP server | preflight then `os.execvp` server handoff | WIRED | Startup path fails closed before serving. |
| `gateway_register.py` | gateway files + restart/smoke/rollback | YAML parse/mutate + backup + command execution | WIRED | Full apply and rollback flow implemented and tested. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `metric_services.py` (`get_fitness_state_service`) | `data` payload | `daily_report_from_connection` + `weekly_digest` + repository checks | Yes | ✓ FLOWING |
| `metric_services.py` (`list_workouts_service`) | workout rows list | `repo.list_activities(...)` + parsed summary JSON | Yes | ✓ FLOWING |
| `metric_services.py` (`get_workout_detail_service`) | detailed metric dict | `repo.activity_by_id` + `enrich_activity` + stream checks | Yes | ✓ FLOWING |
| `metric_services.py` (`compare_periods_service`) | `global/per_sport metrics` | period rows + metric aggregations + report snapshots | Yes | ✓ FLOWING |
| `metric_services.py` (`project_fitness_state_service`) | scenario projections | historical TRIMP + `calc_banister` + `forward_simulate` | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| MCP allowlist, forbidden tools, metadata envelope, and read-only behavior are enforced | `uv run python -m pytest tests/test_mcp_surface.py tests/test_metric_services.py tests/test_metric_registry.py -q` | Passed | ✓ PASS |
| Docker runtime hardening and fail-closed preflight behavior | `uv run python -m pytest tests/test_docker_runtime.py tests/test_security_guards.py -q` | Passed | ✓ PASS |
| Gateway registration safety (dry-run, apply gate, backup, rollback) | `uv run python -m pytest tests/test_gateway_integration.py -q` | Passed | ✓ PASS |
| Smoke CLI entrypoint is available in managed runtime | `uv run python -m mcp_strava.deploy.smoke --help` | Exit 0 | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED (no `scripts/*/tests/probe-*.sh` declared or present for this phase).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| MCP-01 | 05-01/02/03/04/06 | Read-only intent-level MCP tools | ✓ SATISFIED | Five-tool MCP allowlist and read-only annotations in server + tests. |
| MCP-02 | 05-04/06 | Exclude sync/backfill/raw/sql/token/admin/sync-log from MCP | ✓ SATISFIED | Forbidden tool list in server and explicit disjoint assertions in tests. |
| MCP-03 | 05-01/02/03/04/06 | Include freshness/completeness metadata in MCP responses | ✓ SATISFIED | Envelope serialization includes `freshness` + `completeness`; service tests validate partial/unavailable cases. |
| MCP-04 | 05-04/05/06 | Local/container-safe bind/origin defaults and unsafe rejection | ✓ SATISFIED | HTTP settings validation rejects unsafe local bind/wildcards; transport allowlists enforced and tested. |
| DOCKER-01 | 05-05/06 | Persistent data volume and fail startup on missing/unreadable DB | ✓ SATISFIED | Compose mounts `/opt/docker/mcp-strava/data`; preflight checks existence/readability/integrity/tables. |
| DOCKER-02 | 05-05/06 | Non-root runtime and no public port by default | ✓ SATISFIED | Dockerfile uses non-root user; compose uses `expose` without host `ports`. |
| DOCKER-03 | 05-06 | Gateway integration path documented without requiring unprompted rollout | ✓ SATISFIED | Runbook documents dry-run/apply boundary and operator-confirm requirement; gateway helper enforces it. |
| TEST-03 | 05-01/02/03/04/05/06 | Tests prove allowlist and forbidden tools absent | ✓ SATISFIED | MCP surface + security + gateway smoke contract tests cover allowlist and forbidden operations. |

Orphaned requirements for Phase 5: none found.

### Anti-Patterns Found

No blocker or warning anti-patterns found in phase-modified files (`TBD/FIXME/XXX` absent; no placeholder stubs detected in runtime paths).

### Human Verification Required

None.  
Operator-approved live `/opt/docker/mcp-gateway/*` mutation was intentionally deferred and is explicitly represented as a protected apply boundary, which matches phase contract and tests.

---

_Verified: 2026-05-22T12:08:23Z_  
_Verifier: the agent (gsd-verifier)_
