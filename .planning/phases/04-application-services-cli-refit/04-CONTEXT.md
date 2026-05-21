# Phase 4: Application Services & CLI Refit - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 creates the product-facing application service layer for local-mirror training analytics and refits the CLI to call those services. The services cover daily report, weekly summary, recent workouts, per-workout analytics, and freshness status from SQLite mirror data. They do not call Strava directly, do not run sync as a user-facing action, and do not add new coach-style analytics beyond preserving the useful metrics the existing product already exposes.

</domain>

<decisions>
## Implementation Decisions

### Application Service Contract

- **D-01:** Application services are the only product read/use-case layer for Phase 4. Expected service capabilities are daily report, weekly summary, recent workouts, per-workout analytics, and freshness status.
- **D-02:** Product read services compute from the local SQLite mirror. They must not call Strava APIs, refresh OAuth tokens, run sync/backfill, inspect sync logs, or expose operational controls.
- **D-03:** Services may perform only local freshness inspection and controlled local refresh signaling through the existing refresh-state/request mechanism. Any Strava work remains inside refresh runtime infrastructure.

### Refresh Policy

- **D-04:** Replace the older "at least once daily by timer/background service" product requirement with lazy first-use refresh per local day. If no user-facing/MCP request arrives, the service should not spend Strava API quota just because a day passed.
- **D-05:** On first user-facing request for a local day, application/core logic checks `refresh_state`. If that day has not had a successful refresh, it may enqueue or request refresh through the internal mechanism, respecting lease, dedupe, and backoff. MCP still does not know this happened.
- **D-06:** Repeated product requests in a short interval are served from SQLite state and must not create repeated Strava work. Existing lease/dedupe/backoff semantics should remain the guardrail.

### Freshness And Completeness Metadata

- **D-07:** Do not encode a multi-step stale-data coaching ladder in application services. Services return analytics/recommendations from the local mirror and expose factual freshness/completeness facts. Intelligent consumers decide how much to trust or reinterpret the answer.
- **D-08:** Freshness metadata must distinguish `last_successful_refresh_at` from `last_activity_at`. A recent refresh plus an old last activity means "probably no recent Strava activities"; an old refresh means "mirror may be stale."
- **D-09:** Product responses should expose factual fields such as `freshness_state`, `last_successful_refresh_at`, refresh age, `last_activity_at`, last-activity age, completeness status, missing reasons, and metric availability.
- **D-10:** Warnings are factual only. Examples: mirror last refreshed N hours/days ago, last activity was M hours/days ago, HR stream missing, streams/details missing, metric unavailable or partial. Warnings should not say "therefore train lighter" or otherwise interpret stale data as coaching policy.
- **D-11:** If inputs for a metric are missing, the metric is `null`/`unavailable`/`partial` with a missing-data reason. Do not invent zeros or silently treat missing HR/streams as rest or complete load.

### Response Envelope

- **D-12:** Product service responses should share one metadata envelope:
  - `data`: typed service-specific payload.
  - `freshness`: local mirror freshness facts and local refresh signal status.
  - `completeness`: complete/partial/insufficient/unavailable plus missing reasons and coverage where meaningful.
  - `warnings`: factual warnings only.
  - `rationale`: short explanation of computed analytics or recommendation from available mirror data, not refresh-runtime debug output.
- **D-13:** Standardize metadata, not every `data` shape. Daily report, weekly summary, workouts, and workout analytics may keep typed payloads appropriate to their domain.

### CLI Surface

- **D-14:** Use a Product/Admin split. Product commands expose report, weekly summary, recent workouts, per-workout analytics, and freshness. Admin commands expose refresh/backfill/sql/raw/log/debug workflows separately.
- **D-15:** The future MCP surface must consume only the product service registry. It must not discover, wrap, or reuse admin/debug CLI commands.
- **D-16:** No legacy compatibility aliases are required. Document replacement mapping for retained capabilities, but old command names may fail clearly.
- **D-17:** Product CLI commands should support both modes: a human-readable default for manual use, and `--json` returning the full service envelope for tests, automation, and future MCP contract alignment. Admin/debug commands may keep whichever text or JSON output is most useful for local operator workflows.

### Per-Workout Analytics

- **D-18:** Phase 4 should preserve existing useful analytics parity instead of inventing a new coaching layer.
- **D-19:** Existing per-activity metrics come from `EnrichedActivity` and `DailyReport.activities_14d`: id/date/name/sport, distance, moving/elapsed time, elevation, TRIMP, average/max HR, HR recovery, vertical speed, cardiac cost, cardiac drift, HRR percentage, and start time.
- **D-20:** Recent workouts may stay compact, but workout detail/analytics should expose the existing computed fields plus factual metric availability/completeness metadata.

### the agent's Discretion

Planner may choose exact module/class names, command spelling, DTO/dataclass names, and human-readable CLI formatting as long as the service boundary, product/admin split, factual metadata contract, and analytics parity decisions above hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project And Phase Scope

- `.planning/PROJECT.md` - Project goals, constraints, and MCP boundary. Note that Phase 4 context supersedes older at-least-daily timer wording.
- `.planning/REQUIREMENTS.md` - APP-01..APP-04, CLI-01..CLI-03, TEST-04, and refresh requirements to reconcile with lazy first-use policy.
- `.planning/ROADMAP.md` - Phase 4 goal and success criteria.
- `.planning/STATE.md` - Current phase routing and completion status.

### Prior Phase Context

- `.planning/phases/03-strava-adapter-refresh-runtime/03-CONTEXT.md` - Read-runtime/refresh-runtime split, refresh states, refresh_requests, and MCP no-sync boundary.
- `.planning/phases/02-sqlite-safety-repository-layer/02-CONTEXT.md` - Durable mirror, repository boundary, and missing-data semantics.

### Current Code

- `src/mcp_strava/cli.py` - Current fat CLI and command inventory to refit into product/admin split.
- `src/mcp_strava/report.py` - Current daily report and existing `activities_14d` per-workout analytics source.
- `src/mcp_strava/analytics.py` - Current weekly digest and per-activity efficiency helpers.
- `src/mcp_strava/metrics.py` - Existing `enrich_activity()` and per-workout metric computations.
- `src/mcp_strava/types.py` - Existing dataclasses, including `EnrichedActivity`, `DailyReport`, `WeeklyDigest`, refresh rows, and serialization helper.
- `src/mcp_strava/refresh/freshness.py` - Existing local freshness evaluation and refresh request enqueue helper.
- `src/mcp_strava/refresh/runtime.py` - Refresh runtime, same-day idempotency, leases, failures, and backoff behavior.
- `src/mcp_strava/adapters/sqlite/repository.py` - Repository methods for activities, load, refresh state, and refresh requests.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `DailyReport` and `daily_report()` already provide useful daily report output and embedded `activities_14d` enriched activity metrics.
- `WeeklyDigest` and `weekly_digest()` already provide load, efficiency, volume, trends, and this-week activity summaries.
- `EnrichedActivity` and `enrich_activity()` already compute the per-workout analytics surface Phase 4 should preserve.
- `evaluate_freshness()` and `enqueue_refresh_request_if_stale()` provide the local freshness/read-signal building blocks, but Phase 4 must adapt policy to lazy first-use rather than a hard stale ladder.
- `SQLiteRepository` already exposes activity, load, refresh state, and refresh request methods.

### Established Patterns

- CLI should become a renderer/argument adapter, not a business logic layer.
- Product read paths must remain Strava-free and sync-free.
- Missing HR/streams/details must remain explicit partial/unavailable data, not zeros.
- Dataclasses in `types.py` are the preferred contract style once data crosses module boundaries.

### Integration Points

- New application service modules should sit between CLI/MCP and existing domain/repository code.
- Product service registry should be explicit and separate from admin/debug commands so Phase 5 MCP can only consume safe product services.
- `--json` CLI paths should expose the full service envelope for regression tests and future MCP alignment.

</code_context>

<specifics>
## Specific Ideas

- Product commands can be task-oriented: daily report, weekly summary, recent workouts, per-workout analytics, and freshness.
- Admin commands can group refresh/backfill/sql/raw/log/debug under an admin namespace or equivalent boundary.
- Factual warning examples: `mirror_last_refreshed`, `last_activity_at`, `missing_hr`, `missing_streams`, `missing_details`, `metric_unavailable`.
- Full similar-workout comparison is not part of Phase 4 unless it already exists in current outputs.

</specifics>

<deferred>
## Deferred Ideas

- Full comparison against similar historical workouts is deferred unless already present in current outputs.
- Detached background/timer refresh can be revisited later if local deployment needs it; current product decision is lazy first-use refresh to avoid unused Strava API calls.
- Any coach-style interpretation of stale/incomplete data belongs to downstream intelligent agents or a future product decision, not Phase 4 service metadata.

</deferred>

---

*Phase: 04-Application Services & CLI Refit*
*Context gathered: 2026-05-21*
