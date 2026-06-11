# Phase 3: Strava Adapter & Refresh Runtime - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-21
**Phase:** 3-Strava Adapter & Refresh Runtime
**Areas discussed:** Freshness and request-triggered refresh policy, Mirror completeness semantics, Token persistence and failure behavior

---

## Freshness and Request-Triggered Refresh Policy

| Option | Description | Selected |
|--------|-------------|----------|
| Return stale local data with metadata | Fastest and DB-only, but first daily use may answer from old mirror. | |
| Wait for refresh when feasible | Favors freshness for small updates, but risks coupling requests to sync work. | |
| Retry-later instead of stale analytics | Honest for stale data, but too disruptive for history reads. | |
| MCP/read-runtime writes idempotent SQLite refresh request | Keeps MCP off Strava while letting first-use-of-day signal refresh-runtime. | ✓ |

**User's choice:** MCP/read-runtime may write only an idempotent refresh request into SQLite; refresh-runtime owns the API, token, lease, backoff, checkpoints, and mirror writes.
**Notes:** User rejected exposing sync/logs through MCP and also rejected repeated request-time Strava probing because multiple MCP requests within 15 minutes must not spend API quota. Expert panel resolved the conflict by separating the read data path from a local SQLite refresh signal.

---

## Mirror Completeness Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Complete-or-explicit | Refresh success requires fetched data or explicit `partial`/`unknown`/`unavailable` state. | ✓ |
| Summary-first | Activity summaries refresh first; details/streams/kudos catch up in background. | |
| Best-effort as currently implemented | Keep whatever was fetched and infer less from missing metadata. | |

**User's choice:** Complete-or-explicit.
**Notes:** Missing HR, streams, details, or kudos must not be silently interpreted as rest or complete data. This carries forward Phase 2 missing-data semantics.

---

## Token Persistence and Failure Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Fail closed for freshness, keep old mirror readable | Old data remains readable, but failed/stale freshness blocks or degrades high-confidence advice. | ✓ |
| Fail open | Continue using old mirror almost normally with warnings. | |
| Hard unavailable | Analytics unavailable whenever refresh is broken. | |

**User's choice:** Fail closed for freshness, keep old mirror readable.
**Notes:** Historical reads remain available. Readiness and recommendation outputs must not pretend to be fresh when refresh failed due to token, rate-limit, network, or partial-fetch problems.

---

## the agent's Discretion

- Exact table and enum names can be chosen during planning.
- Exact wait/debounce/backoff values can be chosen during planning, as long as Strava quota protection and read-runtime isolation are testable.

## Deferred Ideas

- Exact MCP HTTP tool contracts are deferred to Phase 5.
- CLI refit and operator-facing command mapping are deferred to Phase 4.
- Docker service supervision and local gateway integration are deferred to Phase 5.
