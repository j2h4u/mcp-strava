---
phase: 9
reviewers: [claude, opencode]
reviewed_at: 2026-05-26T11:57:22.351Z
plans_reviewed: [09-01-PLAN.md, 09-02-PLAN.md, 09-03-PLAN.md, 09-04-PLAN.md]
---

# Phase 9 Review Convergence

Phase: 09 — Product factual bundles and CLI read-model consolidation
Cycle: 1
Reviewers: claude, opencode
Generated: 2026-05-26

CYCLE_SUMMARY: current_high=3

## Current HIGH Concerns

1. Claude H-1: `historical_facts` maps `activity_streak_days`, `rest_streak_days`, and `last_hike_days_ago` to columns/computations that do not exist, while 09-01 does not scope materializer changes or explicit windowed view derivation.
2. Claude H-2: D-09 status facts such as consecutive high-load hikes and running-volume-jump require windowed cross-activity computation and a threshold/evidence data shape that 09-01 does not scope.
3. OpenCode H-1: 09-02 lacks an explicit bundle completeness contract for skipped, dropped, or scope-incompatible metrics, so product bundles can be partial without caller-visible reason codes.

## Claude Review

I have what I need — the registry confirms the central risk. Here's my review.

# Cross-AI Plan Review — Phase 9: Product Factual Bundles & CLI Read-Model Consolidation

## 1. Summary

This is a well-sequenced, boundary-disciplined four-plan set that correctly keeps the MCP surface frozen at six tools, routes all new "bundle" behavior through the existing `get_training_aggregates`, and preserves `compare_periods` on the aggregate layer per D-14. The TDD structure, AST import guards, and threat models are unusually thorough, and the registry-as-source-of-truth discipline is respected. However, the plan set has one structural blind spot that threads through 09-01 and 09-02: several named deliverables (historical streak/last-hike facts, and the "consecutive high-load hikes"/"running volume jump" status facts) **reference read-model columns that do not exist and are not materialized**, yet 09-01's file list excludes the materializer and `types.py`. The `historical_facts` bundle is, by inspection of the current code, already query-broken. Secondary gaps: the legacy `report.py`/`analytics.py`/`reports.py`/`workouts.py` paths are never decisively retired (risking the exact duplicate-path situation D-15 forbids), and the MCP-vs-CLI daily-brief output asymmetry is never reconciled.

## 2. Strengths

- **MCP boundary is airtight.** All four plans hold the six-tool allowlist (D-03), route bundles through `get_training_aggregates`, and add AST/import guards (`test_security_guards.py`) proving no sync/admin/raw/SQL/token leakage. 09-04 explicitly re-asserts the exact allowlist. This is the highest-risk constraint and it is handled correctly.
- **No legacy recompute revival in the read path.** `compare_periods` stays on the aggregate service (D-14); guards forbid `daily_report`/`weekly_digest`/`enrich_activity`/raw-stream queries in `metric_services.py`. CLI product handlers are AST-checked against `DbConn`/`api_request`/embedded SQL.
- **Registry remains the contract.** Bundle membership, aggregate metadata, and the materialized fact-column registry are all drift-tested; 09-01/09-04 reinforce this rather than bypassing it.
- **Gear/kudos discipline matches decisions.** `kudos_names` stays detail-only, `kudos_count` is a `kudos_count`-mode aggregate, and `AggregateRequest` (frozen dataclass) already rejects gear filters by raising `TypeError` (D-20/D-22).
- **Clean wave dependencies.** 09-01 → 09-02 → 09-03, with 09-04 fanning in from 09-02+09-03. No circular or out-of-order dependencies.

## 3. Concerns

**HIGH — `historical_facts` bundle maps to non-existent columns; 09-01 cannot make it factual with its declared file set.**
`AGGREGATE_METRIC_BUNDLES["historical_facts"]` includes `activity_streak_days`, `rest_streak_days`, `last_hike_days_ago`. Their aggregate metadata (`metric_registry.py:724-750`) maps them to source `historical_fact` → view `v_training_model_state_facts` with `value_column` equal to those ids. That view (`schema.py:388-412`) and the underlying `training_model_daily` table contain **no such columns**, and the read-model materializer never computes them. A `get_training_aggregates(bundle_id="historical_facts")` call will emit `SELECT activity_streak_days ... FROM v_training_model_state_facts` and fail at execution — this is the "current bundle failure point" the CONTEXT itself names. 09-01 proposes to fix this via "DuckDB view projections … without new physical period tables," but streak and last-hike facts are window/scan computations (consecutive-day runs; days-since-last-`Hike`), not column renames. Producing them correctly requires either non-trivial windowed view SQL (unacknowledged in the plan) or materializer changes — and `read_model_materializer.py` is **not** in 09-01's `files_modified`. The plan must explicitly choose: (a) materialize these (expand the file set + migration/parity), (b) derive via documented window-function views, or (c) delete them from the bundle under D-15. As written, the most likely outcome is tests that pass only by returning `completeness: unavailable`, i.e. a hollow deliverable for a named D-07 capability.

**HIGH — D-09 status facts ("high-load hikes", "running volume jump", and the threshold/evidence shape) are under-scoped.** 09-01 Task 1 Test 3 asserts that *all* of stale-mirror, stale-read-model, missing-HR, missing-streams, excessive-high-zone, HR-anomaly-burst, cardiac-drift-significance/quality, **consecutive high-load hikes**, and **running-volume-jump** facts carry registered `code`/`threshold`/`window`/`evidence`/`completeness`/`metric_id`. Two problems: (1) The `MetricDefinition` dataclass has no `code`/`threshold`/`window`/`evidence` fields, and `types.py` is **not** in 09-01's file list — a new dataclass or a separate status-fact structure is needed and unscoped. (2) "Consecutive high-load hikes" and "running volume jump" are windowed cross-activity signals not present as materialized columns; like the streaks, they can be *registered* but not *valued* without computation the plan doesn't fund. Decide which status facts are recoverable from existing columns (Z5 seconds, `anomaly_count`, `high_zone_seconds`, `cardiac_drift_significant`, freshness state) versus which require new materialization or deletion.

**MEDIUM — Legacy daily/weekly compute paths are never decisively retired.** CONTEXT flags `application/reports.py`, `application/workouts.py`, `report.py`, and `analytics.py` as paths "that should be consolidated," and D-15 says recovered facts move to the read model *or are deleted*. 09-02 builds a *parallel* `product_facts.py`; 09-03 rewires the CLI onto it and removes dead CLI *handlers* — but no plan deletes `reports.py`/`workouts.py` or retires the `daily_report`/`weekly_digest` compute functions, and 09-03 says it will "include" (not replace) product-fact services in `registry.py`. The realistic end state is two daily/weekly implementations coexisting — the duplicate situation the phase is meant to eliminate. The plan should state explicitly which legacy services/modules are deleted and assert their absence (an AST/import guard), or justify retaining them.

**MEDIUM — MCP vs CLI daily-brief asymmetry is unreconciled against D-05.** 09-02's `get_daily_brief_facts_service` composes multiple services (recent workouts, fitness state, status facts, aggregates) for the CLI. But 09-04 exposes bundles to MCP *only* through `get_training_aggregates`, whose service returns aggregate rows + bundle sections — it does not call `product_facts`, so it cannot include the "recent workouts" list or per-activity facts D-05 enumerates. So D-05's full daily brief is a CLI-only guarantee; the MCP agent must compose `list_workouts` + `get_training_aggregates` itself. This may be an acceptable boundary, but the phase goal says "MCP **and** CLI product reads expose … daily … facts," and no plan states the agent-composition expectation or which D-05 elements are intentionally absent from the MCP bundle. Make this explicit so executors don't try to cram workout objects into the aggregate tool (scope creep).

**MEDIUM — Gear/shoe-mileage data availability is assumed, not verified (D-21).** The shoe-mileage MCP prompt exists, but shoe mileage historically came from the live `/athlete` gear endpoint (old `cmd_gear`), not from the mirror's read-model. No aggregate view or fact column exposes gear. The plans correctly gate gear facts to "when mirrored activity JSON contains supported gear fields," but never confirm that gear mileage is reconstructable from mirrored data (per-activity `gear_id` + distance summation) without a sync/admin path. If it isn't, the shoe-mileage prompt stays non-factual and D-21 is unmet. 09-01/09-02 should include a discovery check on what gear data the mirror actually holds before committing to the field.

**MEDIUM — Status facts risk hollow delivery via "unavailable."** Tied to the two HIGH items: because several status/historical facts can be *registered* without being *materialized*, the tests can pass while the runtime returns `completeness: unavailable` for most of them. That is technically "factual" (absence is a fact) but does not "restore product value," which is the stated phase intent. Recommend the plans add at least one assertion per recovered status fact that a populated fixture yields a non-`unavailable`, threshold-evaluated value — otherwise "recovered" is unfalsifiable.

**LOW — D-12 dead-column removal vs live DuckDB drift.** D-12 wants unused materialized columns removed. Editing `schema.py` `CREATE TABLE` only affects fresh DBs; the live Phase-8 DuckDB already has the current columns, and `test_materialized_fact_column_registry_matches_duckdb_schema` builds a fresh in-memory DB so it would not catch drift. If any column removal is actually attempted, it needs a migration path and parity check (none of the four plans own the migrator). Safer to interpret D-12 as "do not add unregistered columns" and explicitly defer physical removal.

**LOW — docs/cli.md replacement-mapping test couples to removed commands.** `test_cli_docs_replacement_mapping_accounts_for_old_commands` requires rows for `backtest`, `trend`, `kudos`, `gear`, `stats`, etc. 09-03 removes those handlers and rewrites `docs/cli.md` "without promising old command names." The executor must keep the mapping table rows (status: removed/deferred/folded) while deleting the handlers — a small but easy-to-miss constraint worth calling out in 09-03.

**LOW — bundle fan-out performance is only half-gated.** A `daily_brief` call expands to ~15 metrics, several scope-split into two queries; `compare_periods` already proves ~60 sub-queries stay <500ms warm with the response cache, and `get_training_aggregates` is cacheable. But the *CLI* `product_facts` composition (which fans out across aggregates + list + fitness + detail) is not covered by PERF-01 (MCP-only). Not a release blocker, but 09-02/09-03 should note the composed-bundle query count so it doesn't regress unnoticed.

## 4. Suggestions

1. **Resolve the materialization fork in 09-01 before execution.** For `historical_facts` streaks/last-hike and the windowed status facts, pick one path per fact and write it into the plan: materialize (add `read_model_materializer.py` + a DuckDB migration + parity to the file set), derive-via-view (add the explicit window SQL to `schema.py` and a query test on populated data), or delete (remove from `AGGREGATE_METRIC_BUNDLES` and update drift tests). Add `types.py` to 09-01 if a status-fact dataclass is introduced.
2. **Add a deletion/absence guard in 09-03** asserting that retired legacy modules/functions (`application/reports.py`, `application/workouts.py`, or `report.daily_report`/`analytics.weekly_digest` as product paths) are no longer importable from product code — making D-15 consolidation verifiable rather than aspirational.
3. **State the MCP daily-brief contract explicitly in 09-04**: enumerate which D-05/D-06 elements the `get_training_aggregates` bundle returns vs which the agent composes from `list_workouts`/`get_workout_detail`. Add a smoke assertion for the exact bundle-section keys.
4. **Insert a gear-data discovery step** (09-01 or 09-02 Task 1) that confirms what gear fields the mirror actually stores, and make the shoe-mileage deliverable conditional on that evidence (consistent with D-22's "unless planning proves it is required").
5. **Require non-`unavailable` fixtures** for at least the recoverable status facts so the tests prove value recovery, not just metadata registration.

## 5. Risk Assessment

**Overall risk: MEDIUM.** The constraint that matters most to this project — the product-only MCP boundary with no sync/admin/raw/recompute leakage — is handled rigorously across all four plans, and data-preservation/rate-limit constraints are respected (the work is read-model-only, no Strava calls, no full resync). The risk is concentrated in *deliverability of named facts*, not in safety or boundary violations: two HIGH concerns reflect that historical/status facts are registered against columns and computations that don't exist and aren't scoped to be built, which will surface during 09-01 execution either as failing queries or as silently-empty bundles. These are correctable at the planning stage (decide materialize vs derive vs delete; add the missing files), and none threaten the mirror or the MCP contract. Resolve the two HIGH items and the plan set is sound.

## Current HIGH Concerns

- **09-01: `historical_facts` bundle (`activity_streak_days`, `rest_streak_days`, `last_hike_days_ago`) maps to columns that do not exist in `v_training_model_state_facts`/`training_model_daily` and are not materialized; the plan proposes view projections but the facts require window/scan computation, and the materializer is not in 09-01's file set — the bundle is currently query-broken and the fix is under-scoped.**
- **09-01: D-09 status facts ("consecutive high-load hikes", "running volume jump") require windowed cross-activity computation not present as materialized columns, and the `code`/`threshold`/`window`/`evidence` status-fact structure needs a data shape with `types.py` absent from the file set — risk of registering metadata that can only ever return `completeness: unavailable`.**

---

## OpenCode Review

# Phase 9 Plan Review: Product Factual Bundles and CLI Read-Model Consolidation

---

## 09-01-PLAN.md — Registry-Backed Bundle-Safe Aggregate Facts and Status/Gear Contracts

**Summary:** Plan 09-01 establishes the registry and DuckDB aggregate layer foundation needed for Phase 9 product bundles. It adds metric definitions, aggregate metadata, DuckDB views, and query support for `daily_brief`, `weekly_digest`, `historical_facts`, status facts, kudos, and gear context — all within the existing registry-backed architecture. The TDD approach with failing tests first is sound.

**Strengths:**
- Strong TDD structure: RED tests define exact bundle contract expectations before implementation.
- Registry-is-the-source-of-truth discipline (D-11/D-12) is enforced at the aggregate query level, preventing unregistered column leakage.
- Mixed-scope bundle handling (global vs per-sport metrics) is addressed as a first-class concern per D-04, avoiding the current `ValueError` failures.
- Status facts are explicitly required to be machine-readable with `code`, `threshold`, `window`, `evidence`, `completeness` fields — no coaching language.
- STRIDE threat model covers injection (T-09-01-T: parameterized inputs, no caller-supplied SQL), information disclosure (T-09-01-I: kudos names detail-only), and elevation of privilege (T-09-01-E: no admin parameters).

**Concerns:**
- **MEDIUM:** Task 1's RED tests assert `metrics_for_aggregate_bundle("daily_brief")` etc. return known metrics, but the plan does not explicitly address what happens when a bundle includes a metric whose aggregate mode (`SUM`/`AVG`/`MAX`) is incompatible with the requested time window or grouping dimensions. The split-internally approach mentioned in Task 2 is vague — the plan should clarify whether the query builder emits warnings, skips silently, or raises structured errors.
- **MEDIUM:** Status facts for `excessive high-zone exposure`, `HR anomaly bursts`, `cardiac drift significance/quality`, and `running volume jump` require threshold definitions. The plan says these must be registered with `code`, `threshold`, `window`, `evidence`, `completeness`, but does not specify where these threshold values originate. If they come from `Config`/`settings`, that's fine; if they're hardcoded in the query builder, that breaks D-11 (registry as source of truth).
- **LOW:** The `historical_facts` bundle mentions `activity streak`, `rest streak`, `last hike age`, and `season/current-week context`. Some of these (streak calculations) may require windowed queries that are expensive on the full mirror without appropriate indexing. The plan does not address whether the DuckDB views will need `activity_date` indexes.
- **LOW:** Task 3 (docs update) is listed as auto but has no TDD gate — the doc drift test presumably already exists from prior phases, but it's worth noting that doc-only tasks can become stale if the implementation deviates.

**Suggestions:**
- In Task 2, specify the bundle splitting behavior explicitly: when a metric's aggregate mode is incompatible with the bundle's window, the query builder should return that metric with `None` values and a `"scope_incompatible": true` completeness flag, not silently drop it.
- Require that every status fact threshold references a registered `Config` or `settings` value, not a hardcoded literal in the aggregate query module.
- Consider adding a note in the PLAN about DuckDB index requirements for streak/duration calculations against the full activity history.

**Risk Assessment:** **LOW** — This is foundational registry/infrastructure work with well-understood existing patterns. The main risks are around bundle semantics clarity, which the TDD approach should surface early.

---

## 09-02-PLAN.md — Shared Product Factual Bundle Services and Aggregate Response Shaping

**Summary:** Plan 09-02 creates the application-layer product fact services (`product_facts.py`) that shape daily brief, weekly digest, and historical fact bundles from existing aggregate and metric service calls. It wires these into `get_training_aggregates_service` so existing MCP tools can serve bundle-shaped responses without new MCP tools. The plan properly avoids coaching language, sync calls, raw SQL, and old report recompute paths.

**Strengths:**
- Clear separation: `product_facts.py` becomes the shared contract between CLI and MCP aggregate calls, with explicit service functions per bundle.
- Bundle shaping is added to `aggregate_services.py` via `bundle_id` without modifying the existing `rows` contract — backward compatibility preserved.
- D-03 (no new MCP tools) is enforced: bundles are served through existing `get_training_aggregates`, not new tool registrations.
- Status facts must be threshold-backed with no advice verbs — tests explicitly search for forbidden words (`rest`, `train`, `worry`, `hydrate`, etc.).
- STRIDE covers bundle ID validation (T-09-02-S: accept only registered bundle IDs), preventing unbounded expansion.

**Concerns:**
- **HIGH:** The plan depends on 09-01's bundle query support being fully working. If `daily_brief` needs metrics that span multiple incompatible aggregate scopes, and 09-01's split-internally mechanism isn't robust, 09-02's service layer will produce incorrect or incomplete bundles without the caller knowing which metrics were dropped. The plan needs an explicit completeness contract: each bundle section should report which metrics contributed and which were unavailable with reason codes.
- **MEDIUM:** `get_daily_brief_facts_service` is specified to include `current_state`, `recent_workouts`, `daily_load_14d`, `by_sport`, `model_context`, `status_facts`, `freshness`, and `read_model` sections. Building `current_state` from `get_fitness_state_service` + `model_context` from aggregate queries may be redundant — fitness state is a projection of the same model data. The plan should clarify whether these sections share underlying queries or duplicate work.
- **MEDIUM:** `get_historical_facts_service` includes `season/current-week context`. "Season" is a vague concept not defined in the registry, CONTEXT.md, or prior phases. The plan should either define what "season" means concretely (month? quarter? meteorological season? training block?) or defer it per D-07's "when registry-backed and materialized" caveat.
- **LOW:** The plan says services are built from `get_training_aggregates_service`, `list_workouts_service`, `get_workout_detail_service`, and `get_fitness_state_service`. If a single bundle calls 3-4 internal services sequentially, the p95 latency could approach or exceed 500 ms on warm cache. The plan doesn't mention performance targets for bundle assembly.
- **LOW:** `historical_facts` mentions `coverage metadata` — this should not expose stream channel gap details that are admin territory per D-19. The plan should clarify coverage metadata is at the "activity has HR / no HR" level, not per-channel gap reporting.

**Suggestions:**
- Add a `bundle_completeness` field to each bundle section reporting which metrics were available, which were skipped due to scope incompatibility, and which are missing from the read model entirely.
- Define "season" explicitly or drop it from the initial historical facts bundle — D-07 says "when those facts are registry-backed and materialized," and "season" is not currently a registered dimension.
- Consider a lightweight integration test that measures bundle assembly wall-clock time to catch performance regressions early.
- Clarify in the plan that coverage metadata in product bundles stays at the "HR present/missing" level, not per-channel audit detail.

**Risk Assessment:** **MEDIUM** — The bundle service shaping is well-specified, but the dependency on 09-01's mixed-scope query robustness and the undefined "season" concept introduce uncertainty. The HIGH concern about completeness transparency is addressable with a clear contract addition.

---

## 09-03-PLAN.md — CLI Read-Model Consolidation and Dead Legacy Handler Cleanup

**Summary:** Plan 09-03 rewires CLI product commands to call Phase 9 product fact services and metric services, removes dead legacy handlers (`cmd_activities`, `cmd_gear`, `cmd_stats`, `cmd_backtest`, `cmd_trend`, `cmd_kudos`, etc.), and preserves admin commands under the `admin` namespace. This directly implements D-16 through D-22.

**Strengths:**
- Concrete dead-handler list: names every legacy handler to remove, making verification unambiguous.
- AST/source guards in `test_security_guards.py` prevent removed handlers from silently returning — this is a strong defensive pattern.
- Admin/product boundary is explicitly enforced: root CLI registry has only product + `admin` namespace; admin commands remain local-only per D-19.
- Monkeypatch spy tests ensure CLI commands actually delegate to the correct application services, not just that they don't crash.
- CLI docs update is included, maintaining the replacement mapping contract from CLI-03.

**Concerns:**
- **MEDIUM:** Removing `cmd_kudos` and `cmd_gear` handlers means the only path to kudos/gear facts is through product bundles or workout detail. The plan says CLI JSON output "includes kudos and supported gear facts from product services where present," but if a user previously ran a standalone `kudos` command and that handler is gone, the replacement path (`workout detail <id>` or `report daily`) must be clearly documented. Plan 09-04's deployment docs should cover this migration path, but 09-03 itself should verify that the replacement path actually produces equivalent kudos data.
- **MEDIUM:** Removing `cmd_trend` handler removes trend views that Phase 4's analytics previously exposed. D-06 mentions "period trend facts" in the weekly digest, but if trend was a standalone command for exploring form/fitness/fatigue curves, its removal without a documented replacement could be a regression. The plan should confirm whether `weekly --json` or a `compare_periods` CLI wrapper covers the trend use case.
- **LOW:** The plan removes `cmd_activities` but retains `workouts recent`. If the old `activities` command had filtering capabilities (by date range, sport type) that `workouts recent` doesn't replicate, operators lose query flexibility. The plan should confirm `workouts recent` supports equivalent filters or document the gap.
- **LOW:** AST guard tests in `test_security_guards.py` checking for removed import names could produce false positives if those names appear in docstrings, comments, or type annotations for preserved code. The plan should specify that guards search AST `Import`/`ImportFrom` nodes only, not arbitrary string matches.
- **LOW:** The plan doesn't explicitly address whether `cmd_sync` and `cmd_backfill` handlers remain in the `admin` namespace after the cleanup — the dead-handler list doesn't include them, but the plan should confirm they are intentionally preserved under `admin`.

**Suggestions:**
- Add a test that calls `workout detail <id>` and asserts kudos/gear sections match what the old `cmd_kudos`/`cmd_gear` handlers would have produced for the same activity ID.
- Confirm whether `compare_periods` CLI command existed before and, if not, whether `weekly` + `report daily` together cover the trend use case that `cmd_trend` removal creates.
- Verify that `workouts recent` can accept date range and sport filters to cover the old `cmd_activities` use case.
- In security guard AST tests, restrict import checks to `ast.Import`/`ast.ImportFrom` nodes to avoid false positives from docstrings or comments.
- Add `cmd_sync`, `cmd_backfill`, `cmd_backfill_streams` to the explicitly-preserved admin handler list in the plan text.

**Risk Assessment:** **MEDIUM** — The dead-handler removal is surgical and well-tested, but the gap between removed standalone commands (`kudos`, `trend`, `activities`, `gear`, `stats`) and their replacement paths in the bundle-centric product surface needs explicit verification to avoid capability regression.

---

## 09-04-PLAN.md — MCP Bundle Smoke, Boundary Guards, and Verification Docs

**Summary:** Plan 09-04 is the final verification gate. It adds MCP smoke tests for bundle calls through the existing six-tool surface, extends security guards to prove no admin/raw/recompute leakage from the new product services, and updates deployment docs with the Phase 9 verification sequence.

**Strengths:**
- MCP allowlist test is exact: asserts `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, `project_fitness_state`, `get_training_aggregates` — no additions, no renames.
- Smoke tests exercise `daily_brief`, `weekly_digest`, `historical_facts` through `get_training_aggregates` with existing cache behavior, validating the D-03 constraint end-to-end.
- Security guards check that `product_facts.py`, `aggregate_services.py`, and `cli.py` do not import Strava adapters, sync runtime, token refresh, old report recompute, or dead CLI handlers — closing the loop on D-11 through D-16 and D-18/D-19.
- Deployment docs are practical: they list exact test commands (`uv run pytest -q tests/test_mcp_surface.py ...`) rather than vague verification steps.
- STRIDE covers all six categories with specific mitigations.

**Concerns:**
- **LOW:** The plan says "Add a `Justfile` recipe only if the existing smoke/perf recipes cannot express the Phase 9 bundle smoke." This conditional approach could lead to the recipe not being added and executors not knowing the right commands. The plan should commit to either adding the recipe or documenting the exact `just` invocation that covers it.
- **LOW:** The `p95 gate when Docker is available` mentioned in Task 2 is vague. If Docker is not available, does the verification skip performance entirely? The plan should define a fallback: run the aggregate service benchmarks directly against a DuckDB fixture (which doesn't require Docker) with a documented p95 target.
- **LOW:** Task 1 mentions "keep the existing response cache behavior for expensive aggregate calls" but doesn't verify that the cache doesn't accidentally cache bundle-specific sections alongside the raw rows, which could cause stale bundle output if the underlying data changes. The plan should add a cache-invalidation or cache-key test.
- **LOW:** The plan's dependency is on both 09-02 and 09-03, but the bundle smoke tests primarily exercise 09-02's service layer. The CLI consolidation from 09-03 is only tangentially tested through security guards. Consider making the dependency more precise: 09-04 depends on 09-02 for MCP smoke and 09-03 for CLI boundary guards, but the MCP smoke could theoretically run before 09-03 is complete.

**Suggestions:**
- Commit to either adding a `just smoke-phase9` recipe or documenting that `just test-mcp && just test` covers it.
- Define a non-Docker performance fallback: run `get_training_aggregates` with bundle requests against a test fixture and assert p95 < 500 ms.
- Add a test that verifies aggregate response caching does not persist stale bundle sections across data changes.
- Split the dependency: 09-04's MCP smoke task depends on 09-02, while the CLI guard task depends on 09-03. This allows partial parallel verification.

**Risk Assessment:** **LOW** — This is primarily test and documentation work. The main risk is that the smoke coverage might miss edge cases that only manifest with live data on Docker, which the plan partially addresses by recommending Docker smoke but doesn't fully close with a local fallback.

---

## Cross-Plan Concerns

### Dependency Ordering
The wave structure (09-01 → 09-02 → 09-03 → 09-04) is logically correct. 09-01 builds the registry/query foundation, 09-02 builds services on top, 09-03 rewires CLI to those services, and 09-04 verifies the whole stack. The only concern is that 09-03 has no direct dependency on 09-01 (only on 09-02), which means 09-03 implicitly trusts that 09-02 correctly wraps 09-01's query layer — this is fine given the wave structure.

### MCP Boundary
All four plans respect the MCP boundary: no new tools are added (D-03), admin/sync/raw/debug controls remain below the MCP surface (D-19), and product reads are registry-backed and read-model-sourced (D-11/D-12). The STRIDE models consistently call out elevation-of-privilege threats.

### Legacy CLI Revival
The dead-handler removal in 09-03 is comprehensive and guarded by AST tests in 09-04. The main risk is capability regression for standalone commands that don't have a 1:1 replacement in the bundle-centric surface.

### Data Preservation / Rate Limits
No plan introduces new Strava API calls, resync, or schema migration. All reads are against the existing DuckDB read model. Data preservation and rate-limit constraints are fully respected.

### Scope Creep
The plans stay within Phase 9's scope. "Season" in historical facts is the only undefined concept that could expand scope; it should be concretely defined or deferred.

---

## Current HIGH Concerns

- **09-02 bundle completeness transparency:** No explicit contract for reporting which metrics were skipped/dropped when bundle queries encounter scope-incompatible metrics. The split-internally mechanism from 09-01 needs a completeness-reporting companion in 09-02 so callers know when bundles are partial.

Overall, Phase 9 plans are well-structured, faithful to the CONTEXT.md decisions, and maintain the hard-won MCP/admin boundary and read-model architecture. The concerns above are addressable with minor plan clarifications.

---

## Consensus Summary

Both reviewers agree that Phase 9 preserves the hard product boundary: no new MCP tools, no sync/admin/debug exposure, no Strava calls, and no revival of raw SQL or legacy recompute paths. The plan ordering is coherent: 09-01 builds registry/query foundations, 09-02 shapes product bundles, 09-03 rewires CLI reads, and 09-04 verifies MCP/CLI boundaries.

### Agreed Strengths

- MCP stays on the existing six-tool product surface, with bundles served through `get_training_aggregates`.
- CLI cleanup is guarded by AST/source tests so removed legacy handlers do not drift back in.
- Registry-backed metric and aggregate metadata remain the source of truth for product facts.
- Data preservation and Strava rate-limit constraints are respected; the plans do not require live API sync or full resync.

### Agreed Concerns

- Several named historical/status deliverables depend on facts that may not exist as current DuckDB/read-model columns and need explicit materialization, explicit windowed view derivation, or removal from the bundle contract.
- Bundle completeness must be caller-visible. Product sections should report unavailable/skipped/scope-incompatible metrics with reason codes rather than silently dropping or returning hollow sections.
- Legacy command/module retirement needs replacement-path verification so removing `kudos`, `gear`, `trend`, `activities`, and related handlers does not create untracked capability regressions.

### Divergent Views

- Claude treats missing historical/status computations as two current HIGH blockers because the plan can produce query-broken or hollow factual bundles.
- OpenCode treats 09-01 mostly as low risk, but raises a HIGH on 09-02 because downstream bundle services need an explicit partial-completeness contract.
