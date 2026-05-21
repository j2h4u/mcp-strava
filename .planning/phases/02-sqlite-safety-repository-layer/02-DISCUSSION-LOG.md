# Phase 2: SQLite Safety & Repository Layer - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-21
**Phase:** 2-SQLite Safety & Repository Layer
**Areas discussed:** migration safety, repository boundary, missing data semantics, verification strategy, report parity

---

## Migration Safety

| Option | Description | Selected |
|--------|-------------|----------|
| Keep inline `init_db()` plus backup command | Smallest change, but keeps non-replayable runtime schema mutation and weak fail-closed behavior. | |
| Custom in-repo migration gate | Explicit preflight, backup, migration, post-check, and parity without adding a large framework. | ✓ |
| Alembic/SQLAlchemy | Mature migration ecosystem, but too large a tooling jump for this phase. | |
| Shadow-copy migrate and atomic swap | Strongest rollback posture, but too complex for the current Phase 2 need. | |

**User's choice:** Technical decision delegated to expert panel; panel converged on custom in-repo migration gate.
**Notes:** Gate must fail closed, protect existing mirror data, and avoid implicit DDL during normal runtime.

---

## Repository Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| One giant SQLite repository facade | Fast to wire, but likely to become a god object. | |
| Focused repositories plus unit of work | Clear ownership for activities, streams/load data, zones/kudos, and sync metadata. | ✓ |
| Read/write split/CQRS | Clear but too much abstraction for a local single-user service at Phase 2. | |
| Thin `DbConn` shim only | Fastest short-term safety layer, but risks becoming permanent scattered SQL. | |

**User's choice:** Technical decision delegated to expert panel; panel recommended focused repositories plus a shared SQLite unit-of-work boundary.
**Notes:** Direct `sqlite3` should be banned outside adapter/migration tooling and narrowly allowed tests.

---

## Missing Data Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Daily load record with explicit statuses | Separates `REST`, `UNKNOWN`, `PARTIAL`, and `OBSERVED` while preserving existing numeric model input. | ✓ |
| Activity-level flags only | Useful provenance but too easy for each consumer to re-aggregate differently. | |
| Dual numeric series without statuses | Minimal plumbing, but hides why the numbers are incomplete. | |

**User's choice:** Technical decision delegated to expert panel; panel recommended explicit daily load status at repository boundary.
**Notes:** Missing HR/streams must not be treated as rest days.

---

## Verification Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Synthetic tiny fixture DBs | Fast and deterministic; good default test base. | ✓ |
| Snapshot/copy of local DB | High fidelity; should be guarded or operator-driven so the real DB is not mutated. | ✓ |
| Committed golden DB fixture | Stable but needs curation and may drift from real data. | |
| Operator-only manual preflight | Needed for the real mirror, but not enough as the only verification. | ✓ |

**User's choice:** Technical decision delegated to expert panel; panel recommended hybrid automated hermetic tests plus operator preflight for the real DB.
**Notes:** `just test` must not mutate `data/strava.db` or hit live Strava.

---

## Report Parity

| Option | Description | Selected |
|--------|-------------|----------|
| Lower-level parity gate | Protect row counts and numeric/load invariants; do not exact-match full user-facing report output. | ✓ |
| Full report exact-match | Strictest, but can reject useful missing/partial-data improvements. | |
| Hybrid | Exact numeric parity plus selected user-facing fields. | |

**User's choice:** Lower-level parity gate.
**Notes:** The user asked what “blocking useful changes” meant. Clarification: fixing missing-HR semantics may legitimately change confidence/warnings/text while preserving data and observed numeric signals.

---

## Agent Discretion

- Planner may choose exact module/file names and schema-version mechanics.
- Planner may choose exact fixture-building approach as long as default tests stay fast, deterministic, and real-DB safe.

## Deferred Ideas

- Strava adapter, refresh runtime, application services, CLI refit, MCP HTTP, and Docker runtime remain later phases.
