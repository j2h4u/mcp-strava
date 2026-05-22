---
phase: 05-mcp-http-surface-docker-hardening
reviewed: 2026-05-22T11:59:07Z
depth: standard
files_reviewed: 31
files_reviewed_list:
  - Justfile
  - pyproject.toml
  - uv.lock
  - deploy/.dockerignore
  - deploy/Dockerfile
  - deploy/docker-compose.yml
  - deploy/gateway_register.py
  - docs/deployment.md
  - docs/metrics.md
  - src/mcp_strava/adapters/sqlite/repository.py
  - src/mcp_strava/application/__init__.py
  - src/mcp_strava/application/metric_registry.py
  - src/mcp_strava/application/metric_services.py
  - src/mcp_strava/deploy/__init__.py
  - src/mcp_strava/deploy/entrypoint.py
  - src/mcp_strava/deploy/preflight.py
  - src/mcp_strava/deploy/prepare_runtime.py
  - src/mcp_strava/deploy/smoke.py
  - src/mcp_strava/interfaces/__init__.py
  - src/mcp_strava/interfaces/mcp_http.py
  - src/mcp_strava/settings.py
  - src/mcp_strava/types.py
  - tests/test_docker_runtime.py
  - tests/test_gateway_integration.py
  - tests/test_mcp_sdk_contract.py
  - tests/test_mcp_surface.py
  - tests/test_metric_registry.py
  - tests/test_metric_services.py
  - tests/test_security_guards.py
  - tests/test_settings.py
  - tests/test_smoke.py
findings:
  critical: 2
  warning: 3
  info: 0
  total: 5
status: issues_found
---
# Phase 05: Code Review Report

**Reviewed:** 2026-05-22T11:59:07Z  
**Depth:** standard  
**Files Reviewed:** 31  
**Status:** issues_found

## Summary

Reviewed MCP HTTP boundary, metric services, Docker runtime/preflight, and gateway registration flow with corresponding tests. The implementation has security and correctness defects that can break boundary guarantees or fail at runtime for valid-but-imperfect inputs.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: [BLOCKER] Transport security accepts wildcard hosts/origins

**File:** `src/mcp_strava/interfaces/mcp_http.py:86`  
**Issue:** `build_transport_security()` only checks non-empty lists and accepts values like `*` for `allowed_hosts`/`allowed_origins`. That weakens rebinding/origin protections and violates local-first fail-closed intent.  
**Fix:**
```python
def _reject_wildcards(values: tuple[str, ...], field: str) -> None:
    if any(v.strip() in {"*", "0.0.0.0", "::"} for v in values):
        raise ValueError(f"{field} contains unsafe wildcard entries")

def build_transport_security(settings: Settings) -> TransportSecuritySettings:
    if not settings.http.allowed_hosts:
        raise ValueError("allowed_hosts must not be empty")
    if not settings.http.allowed_origins:
        raise ValueError("allowed_origins must not be empty")
    _reject_wildcards(settings.http.allowed_hosts, "allowed_hosts")
    _reject_wildcards(settings.http.allowed_origins, "allowed_origins")
    ...
```

### CR-02: [BLOCKER] `project_fitness_state` crashes with malformed row shape

**File:** `src/mcp_strava/application/metric_services.py:557`  
**Issue:** `_validated_custom_series()` sorts with `key=lambda item: item["date"]`. If any row is not a dict or misses `date`, a `KeyError`/`TypeError` escapes and returns an internal error instead of a controlled validation error. This is untrusted MCP input and should be fail-closed with explicit `ValueError`.  
**Fix:**
```python
for row in custom_daily_trimp:
    if not isinstance(row, dict) or "date" not in row:
        raise ValueError("custom_daily_trimp rows must include date and trimp")

for row in sorted(custom_daily_trimp, key=lambda item: item["date"]):
    ...
```

## Warnings

### WR-01: [WARNING] Unbounded/invalid `limit` accepted by MCP list endpoint

**File:** `src/mcp_strava/application/metric_services.py:716`  
**Issue:** `list_workouts_service(limit=...)` forwards limit directly to SQL without bounds checks. Negative values in SQLite can disable limiting semantics, allowing unexpectedly large reads and unstable behavior.  
**Fix:** Validate and clamp (`1 <= limit <= max_limit`, e.g. 200) before repository call.

### WR-02: [WARNING] Gateway register is not self-healing for stale existing catalog entries

**File:** `deploy/gateway_register.py:121`  
**Issue:** `_build_mutations()` only inserts `registry[service_name]` when missing; it never updates URL/transport when entry exists but is wrong. Registration can report success while leaving gateway pointed to stale backend.  
**Fix:** Always reconcile target entry:
```python
registry[service_name] = {
    "remote": {"url": service_url, "transport_type": "http"}
}
```

### WR-03: [WARNING] String command rewrite can corrupt quoting/arguments

**File:** `deploy/gateway_register.py:71`  
**Issue:** For string compose commands, `shlex.split()` then `" ".join(tokens)` drops original quoting. Commands containing spaced/quoted arguments can be rewritten into different semantics.  
**Fix:** Preserve list form in YAML (preferred) or re-quote with `shlex.join(tokens)` instead of plain join.

---

_Reviewed: 2026-05-22T11:59:07Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: standard_
