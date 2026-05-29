# Phase 12: Decouple db.py into focused modules - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-30
**Phase:** 12-decouple-db-py-into-focused-modules
**Mode:** discuss-phase `--analyze`; architecture decisions delegated to an expert panel at the owner's request.
**Areas discussed:** Connection helpers, Repository factories, Auth/config, clock/sleeper home, HTTP access, get_zones layer, Migration order

---

## Meta-decisions (owner)

| Decision | Description | Selected |
|----------|-------------|----------|
| Who answers architecture Qs | Owner self-assesses as non-specialist; routed layering/placement questions to an expert panel rather than direct AskUserQuestion | ✓ |
| No legacy/compat | No backward-compat obligations; still in development → hard-cut, delete db.py, eliminate `_CompatTokenProvider` | ✓ |
| Lock the panel output | "Lock, but keep db.py logic split finer" — planner may split facade/service across more plans | ✓ |
| Clean vs fast | When clean conflicts with quick-but-dirty (Kaizen/minimalist shortcut), **choose clean** | ✓ |

---

## HTTP access (panel conflict)

| Option | Description | Selected |
|--------|-------------|----------|
| StravaClient facade | New `adapters/strava/client.py` owns construction + `(data, rate_headers)` contract + error mapping | ✓ |
| Direct StravaTransport | Callers construct `StravaTransport` themselves | |

**Resolution:** Facade — 3 consumers + centralized `StravaUnavailable`→error/sentinel mapping; aligns with clean-over-fast (GP-01).

## clock/sleeper home (panel conflict)

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated module (`adapters/strava/clock.py`) | `SystemClock`/`SystemSleeper` get a clean single-responsibility home | ✓ |
| Tucked into transport.py | Minimal-effort placement | |
| Shared `mcp_strava/clock.py` | Promote later if a 2nd consumer appears | (future) |

**Resolution:** Dedicated module now (clean over the YAGNI shortcut, GP-01); promote to shared only when justified.

## get_zones layer

| Option | Description | Selected |
|--------|-------------|----------|
| Application service | `application/athlete_zones.py` depends on repo + StravaClient | ✓ |
| Leave in an adapter | Would make one adapter depend on another | |

**Resolution:** Application service — orchestrates two adapters; dependency rule. No panel conflict.

## Connection helpers / Repo factories / Auth-config / Migration

See CONTEXT.md D-01..D-10. Summary: connection helpers → `adapters/duckdb/connection.py` (rename `DbConn`→`MirrorConn`); repo factories deleted (callers use `DuckDBRepository.from_*`); `_CompatTokenProvider`/`.env`-parsing deleted, config to `settings.py`; hard-cut migration (application → refresh/sync → cli → tests → delete db.py) with `just test` as the regression net.

## Claude's Discretion

- Exact new module/file names; whether to split facade/service across multiple plans (permitted by GP-03).

## Deferred Ideas

None — discussion stayed within phase scope.
