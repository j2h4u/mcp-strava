---
phase: 04-application-services-cli-refit
review_cycle: 1
reviewers:
  - claude
  - opencode
plans_reviewed:
  - 04-01-PLAN.md
  - 04-02-PLAN.md
  - 04-03-PLAN.md
  - 04-04-PLAN.md
status: revisions_applied_pending_rereview
---

# Phase 4 Plan Review Convergence

## Cycle 1

### Reviewer: Claude

**HIGH**

- H1: First-use refresh semantics risked using the existing age-based `aging`/`stale` helper instead of the approved local-day predicate. A refresh late yesterday followed by a request just after midnight could remain "fresh" by age and fail to signal first-use refresh for the new day.

**MEDIUM**

- M1: The plan did not state clearly whether Phase 4 only enqueues a local `refresh_requests` signal or also consumes it.
- M2: Service tests did not specify how fixture DBs are injected.
- M3: Report completeness risked inventing a second definition instead of using repository load status.
- M4: Product registry should end as a callable allowlist for Phase 5 MCP, not just names.
- M5: `freshness` CLI lacked a planned `get_freshness_service` envelope entrypoint.
- M6: Live-DB CLI smoke was listed as acceptance instead of an automated fixture-backed check.

### Reviewer: OpenCode

**HIGH**

- H1: Admin `refresh` naming was ambiguous because current CLI has OAuth token refresh and mirror refresh; replacement mapping did not account for every existing command.
- H2: Human-readable CLI output was underspecified and could regress from the current report/weekly/activity formatting.
- H3: Plans lacked an automated end-to-end test for CLI -> application service -> freshness envelope -> repository -> SQLite.

**MEDIUM**

- M1: Product-only AST guards needed scope clarity so admin handlers do not create false positives.
- M2: Weekly service may double-instantiate repository unless refactored or documented.
- M3: Weekly completeness must inspect `WeeklyDigest.this_week` dict entries, not `EnrichedActivity` attributes.
- M4: Doc content tests should validate table structure rather than brittle prose.
- M5: Workout completeness should primarily use `EnrichedActivity` output instead of redundant stream-row queries.

## Revisions Applied

- 04-01 now requires explicit local-day first-use signaling, including a cross-midnight regression test, and forbids using `enqueue_refresh_request_if_stale()` for the lazy first-use predicate.
- 04-01 now adds `get_freshness_service` and clarifies that `PRODUCT_SERVICES` must end as a callable product-service allowlist.
- 04-02 now requires fixture DB injection, authoritative daily load status for completeness, and dict-key handling for weekly `this_week`.
- 04-03 now includes `zone_minutes`, fixture injection, and completeness based primarily on `EnrichedActivity`.
- 04-04 now separates `admin mirror-refresh` from `admin token-refresh`, requires replacement mapping for all 18 current CLI command keys, specifies preservation of current human-readable CLI style, and adds a fixture-backed Phase 4 E2E test.

CYCLE_SUMMARY: current_high=4 status=revisions_applied_pending_rereview
