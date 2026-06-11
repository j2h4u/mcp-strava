---
phase: 04-application-services-cli-refit
review_cycle: 2
reviewers:
  - claude
  - opencode
plans_reviewed:
  - 04-01-PLAN.md
  - 04-02-PLAN.md
  - 04-03-PLAN.md
  - 04-04-PLAN.md
status: converged_no_high
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

### Cycle 1 Summary

CYCLE_SUMMARY: current_high=4 status=revisions_applied_pending_rereview

## Cycle 2

### Reviewer: Claude

**HIGH:** none

Claude confirmed all four cycle-1 HIGH findings had concrete mitigations in the revised plans:

- explicit local-day predicate and cross-midnight regression test for lazy first-use refresh;
- separate `admin mirror-refresh` and `admin token-refresh` names plus full 18-command replacement mapping;
- specified grouped/table-like human-readable CLI expectations;
- fixture-backed Phase 4 E2E test for CLI -> service -> repository -> SQLite.

Claude noted MEDIUM execution guidance: update pre-existing CLI/security guards after moving commands under `admin`, reset `_hr_max_cache` in fixture tests if needed, parse stored refresh timestamps consistently, prefer one clear weekly repository path, explicitly wire callable `PRODUCT_SERVICES`, and test removed/deferred command behavior.

### Reviewer: OpenCode

**HIGH:** none

OpenCode independently confirmed all cycle-1 HIGH findings were resolved and judged the plans executable. Its MEDIUM notes were implementation-level details: registry key/function-name wiring, `RefreshPolicy` construction, fixture DB injection for subprocess E2E, and product-only AST guard scoping.

## Final Convergence

CYCLE_SUMMARY: current_high=0 status=converged_no_high
