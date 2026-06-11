# Phase 1: Package Foundation & Settings - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 1-Package Foundation & Settings
**Areas discussed:** Code move strategy, Settings boundary, Package entrypoint, Test workflow

---

## Code Move Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal package skeleton | Create `src/mcp_strava` with shims around the existing `scripts/` layout | |
| Immediate package move | Move existing runtime modules into package layout immediately, even if old script execution breaks temporarily | ✓ |

**User's choice:** Immediately move code into the package layout.
**Notes:** User said intermediate product operability during refactor is not important; development efficiency is the priority.

---

## Settings Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Typed `.env` compatibility | Add typed settings while keeping current `.env` shape as the main boundary | |
| Separate settings paths | Introduce separate DB path, token path, runtime profile, HTTP bind, and freshness settings | ✓ |

**User's choice:** Separate settings paths.
**Notes:** This aligns with the project goal of a future Docker/local MCP runtime where DB and token paths must be explicit.

---

## Package Entrypoint

| Option | Description | Selected |
|--------|-------------|----------|
| Module entrypoint | Provide `python -m mcp_strava` in Phase 1 | ✓ |
| Console executable | Add a dedicated `mcp-strava` executable immediately | |

**User's choice:** Module entrypoint is enough.
**Notes:** Dedicated CLI executable can wait until later CLI surface decisions are clearer.

---

## Test Workflow

| Option | Description | Selected |
|--------|-------------|----------|
| Preserve custom runner | Keep `scripts/run_tests.py` as primary runner behind `just test` | |
| Switch to pytest | Move directly to pytest and pyproject-based test discovery | ✓ |

**User's choice:** Immediately switch to pytest.
**Notes:** `just test` should continue as the developer command, but it can call pytest instead of the custom runner.

---

## Agent Discretion

- Planner may choose exact packaging/tooling details consistent with Python 3.13 and local-first simplicity.
- Planner may choose whether temporary shims are useful, but old script compatibility is not required.

## Deferred Ideas

None.
