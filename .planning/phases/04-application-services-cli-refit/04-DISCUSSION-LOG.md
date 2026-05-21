# Phase 4: Application Services & CLI Refit - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-21
**Phase:** 4-Application Services & CLI Refit
**Areas discussed:** Freshness contract, Response envelope, CLI surface, Per-workout analytics scope

---

## Expert Panel

The user requested an expert panel with a Product Manager, athlete-user representative, sports physician, coach, architect, and QA. The panel converged on:

- product read services should serve local-mirror analytics with explicit trust metadata;
- historical facts should remain available even when freshness/completeness is weak;
- application services must not turn freshness into hidden sync or MCP-visible operations;
- response metadata must preserve freshness/completeness/warnings/rationale;
- CLI must keep product workflows separate from admin/debug workflows.

The user rejected enterprise-style blocking and multi-step stale-data coaching ladders as over-engineering for this local helper.

---

## Freshness Contract

| Option | Description | Selected |
|--------|-------------|----------|
| Keep at-least-daily timer refresh | Refresh once per day even when nobody asks for data. | |
| Switch to first-use refresh per local day | Avoid Strava API calls unless a user-facing request arrives; use local refresh state and internal refresh requests. | yes |

**User's choice:** Switch to lazy first-use refresh per local day.
**Notes:** MCP still does not know about sync. If there are no MCP/user-facing requests, the service should not call Strava just because a day passed.

| Option | Description | Selected |
|--------|-------------|----------|
| Hard-block stale recommendations | Enterprise/safety style: no recommendation when stale/incomplete. | |
| Degraded recommendation ladder | Encode multiple age thresholds and recommendation behavior in services. | |
| Factual freshness metadata only | Return local analytics plus facts; consumers decide how much to trust them. | yes |

**User's choice:** Factual freshness metadata only.
**Notes:** The user explicitly rejected a five-step stale-data ladder as over-engineering. Services should not encode trainer-like policy based on data age.

---

## Response Envelope

| Option | Description | Selected |
|--------|-------------|----------|
| Factual warnings only | Warn about refresh age, last activity age, missing HR/streams/details, and unavailable metrics. | yes |
| Warnings with recommendation guidance | Add interpretation such as "therefore train lighter" when data is stale. | |

**User's choice:** Factual warnings only.
**Notes:** MCP-facing/product responses provide prepared metrics, not coaching interpretation based on freshness.

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal freshness state | Only return `fresh/aging/stale/...`. | |
| Explicit refresh and last-activity timestamps | Include last refresh, refresh age, last activity, last-activity age, state, completeness, missing reasons. | yes |

**User's choice:** Explicit refresh and last-activity timestamps.
**Notes:** Distinguish old data because the mirror has not refreshed from old last activity because there may have been no recent Strava activity.

---

## CLI Surface

| Option | Description | Selected |
|--------|-------------|----------|
| Product/Admin split | Product analytics commands separate from admin/debug commands. | yes |
| Flat CLI | All commands stay top-level. | |
| Product-only CLI | Remove or defer admin/debug commands. | |

**User's choice:** Product/Admin split.
**Notes:** Future MCP must consume only the product service registry and must not discover admin/debug commands.

| Option | Description | Selected |
|--------|-------------|----------|
| JSON envelope by default | Every command prints the full envelope by default. | |
| Human-readable by default with optional `--json` | Better manual CLI but still supports automation. | |
| Both modes required | Product commands support human-readable default and full `--json`; admin/debug output can stay pragmatic. | yes |

**User's choice:** Both modes required.
**Notes:** Product commands should be convenient by hand while keeping the full envelope available for tests and future MCP alignment.

---

## Per-Workout Analytics Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Training summary | Basic load and HR/pace summary only. | |
| Coach-style analysis | Add richer interpretive coaching output. | |
| Full comparison | Compare to similar workouts/history. | |
| Preserve existing analytics parity | Move current useful metrics into services without inventing new analytics. | yes |

**User's choice:** Preserve existing analytics parity.
**Notes:** The old product already worked well enough for the agent to make useful recommendations. Phase 4 should preserve the existing `EnrichedActivity` metrics surface from `report.activities_14d`: distance/time/elevation, TRIMP, HR, HR recovery, vertical speed, cardiac cost, cardiac drift, HRR percentage, and start time.

---

## the agent's Discretion

- Exact module/class names, command spelling, DTO/dataclass names, and human-readable formatting.
- Exact internal service composition, as long as services are product read/use-case boundaries and CLI remains thin.

## Deferred Ideas

- Full similar-workout comparison, unless already present in current outputs.
- Detached timer/background refresh, unless a future local deployment needs it.
- Coach-style interpretation of stale/incomplete data inside the MCP/product service surface.
