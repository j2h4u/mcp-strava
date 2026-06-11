# Phase 6: Full-Fidelity Strava Mirror - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-22
**Phase:** 06-Full-Fidelity Strava Mirror
**Areas discussed:** Raw payload retention, Stream storage model, GPS canonical format, Legacy `latlng` handling, Historical backfill, Operator surface, Storage engine

---

## Raw Payload Retention

| Option | Description | Selected |
|--------|-------------|----------|
| Lossless normalized mirror | Raw payload is not the goal; preserve all information in structured normalized storage | ✓ |
| Permanent raw payload archive | Store original Strava stream payloads as source-of-truth audit/replay layer | |
| Optional/transient raw capture | Keep raw only as debug/transient implementation detail | |

**User's choice:** Lossless normalized mirror.
**Notes:** User questioned what problem permanent raw payload storage solves and stated normalized information is acceptable. Decision: raw payload storage is not a product goal; the goal is not losing information during normalization.

---

## Stream Storage Model

| Option | Description | Selected |
|--------|-------------|----------|
| Wide + extra JSON | Keep hot scalar columns for metrics and store other channel values in structured JSON | ✓ |
| Long/EAV table | One row per activity/time/channel/value | |
| Fixed columns only | Add known Strava keys as columns | |

**User's choice:** Wide + extra JSON.
**Notes:** This preserves current analytics performance while avoiding loss of unknown/future channels.

---

## GPS Canonical Format

| Option | Description | Selected |
|--------|-------------|----------|
| `lat` + `lng` columns | Canonical GPS as two REAL columns, better for SQL and future map/export work | ✓ |
| `latlng` JSON | Store GPS as Strava `[lat, lng]` JSON | |
| Keep both permanently | Store both representations forever | |

**User's choice:** `lat` + `lng` columns.
**Notes:** Canonical GPS should be queryable and consistent.

---

## Legacy `latlng` Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Keep temporarily | Fill `lat`/`lng`, stop using `latlng`, remove later | |
| Delete immediately | Fill `lat`/`lng`, verify parity, then remove `latlng` in Phase 6 | ✓ |
| Keep forever | Maintain both formats permanently | |

**User's choice:** Delete immediately.
**Notes:** No backward-compatibility obligation. Planner must use backup/preflight/post-check/parity because this is a higher-risk SQLite migration.

---

## Historical Backfill

| Option | Description | Selected |
|--------|-------------|----------|
| Backfill missing channels only | Re-fetch streams only to add missing channels/metadata without deleting rows | ✓ |
| Future-only | Apply new schema only to future refreshes | |
| Full stream rebuild | Rebuild streams for every activity from Strava | |

**User's choice:** Backfill missing channels only.
**Notes:** The backfill must be rate-limit-aware, resumable, and must not perform full resync or delete existing normalized stream rows.

---

## Operator Surface

| Option | Description | Selected |
|--------|-------------|----------|
| CLI admin commands | Add local admin commands for coverage and backfill; MCP remains unaware | ✓ |
| Docker one-shot only | Run only through `docker exec ... python -m ...` style commands | |
| Internal runtime only | No explicit operator command | |

**User's choice:** CLI admin commands.
**Notes:** This matches the established product/admin split. Live validation should still be Docker-first because runtime data lives under `/opt/docker/mcp-strava`.

---

## Storage Engine

| Option | Description | Selected |
|--------|-------------|----------|
| SQLite primary | Keep SQLite as source of truth; defer DuckDB | ✓ |
| Hybrid now | Keep SQLite primary and add DuckDB read model in Phase 6 | |
| DuckDB primary | Migrate operational mirror from SQLite to DuckDB | |

**User's choice:** SQLite primary.
**Notes:** DuckDB is relevant as a possible future analytics/read-model layer, but Phase 6 should not become a storage-engine migration. SQLite remains aligned with existing live mirror, WAL, migrations, repository, Docker runtime, and MCP/read plus refresh/write process model.

---

## the agent's Discretion

- Exact table names, command names, migration version numbers, DTO/dataclass names, checkpoint shape, and coverage output schema are left to planning.
- Optional temporary/debug raw stream capture is allowed if it is cheap and does not become the source-of-truth contract.

## Deferred Ideas

- Permanent raw Strava stream payload archive.
- MCP raw mirror payload tools.
- Full Strava account archival outside activity/stream mirror scope.
- DuckDB-derived analytics/read model for heavy scans or exports if SQLite becomes a bottleneck.
