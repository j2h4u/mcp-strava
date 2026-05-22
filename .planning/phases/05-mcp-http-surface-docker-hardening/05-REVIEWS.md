---
phase: 5
reviewers: [claude, opencode]
reviewed_at: 2026-05-22T13:55:26+05:00
plans_reviewed:
  - 05-01-PLAN.md
  - 05-02-PLAN.md
  - 05-03-PLAN.md
  - 05-04-PLAN.md
  - 05-05-PLAN.md
  - 05-06-PLAN.md
---

# Cross-AI Plan Review — Phase 5

## Review Invocation Notes

- Requested reviewers preserved exactly: Claude and OpenCode.
- Claude and OpenCode were invoked in parallel for the initial review run.
- Claude completed successfully on the initial run.
- OpenCode's initial parallel run returned empty review content after auto-rejected attempts to read `/opt/docker/mcp-gateway/*`. OpenCode was rerun with prompt-only instructions and completed successfully; no reviewer substitution was used.

## Claude Review

# Cross-AI Plan Review — Phase 5: MCP HTTP Surface & Docker Hardening

## 1. Summary

The six-plan sequence is well-structured and decision-traceable: it builds a metric registry contract first, layers metric services on it, exposes them through an MCP HTTP server, then hardens the container and integrates with the live gateway. The phase boundary holds the line clearly on no-coaching, no-sync, no-admin, read-only MCP, and the data-preservation constraint is honored with backup/rollback patterns. The main risks cluster at the seams: registry growth coupling, MCP SDK version/feature assumptions, an unresolved dev↔deploy DB ownership question, and the live-gateway mutation step touching shared infrastructure that already serves four other services.

## 2. Strengths

- **Registry-first sequencing.** 05-01 forces the synthetic-metric inventory to exist before any tool wiring, with `EXCLUDED_INTERPRETATIONS` as the explicit boundary between facts and coaching. This directly mitigates D-08/D-11 metric-loss risk.
- **No-coaching contract is testable.** Negative assertions on `recommendation`, `action`, `intensity`, `on_track`, `should`, `ready`, `best_scenario`, `heart_improved`, `vessels_improved` give the contract real teeth.
- **Allowlist + AST import guards.** Combining a five-tool allowlist test, a forbidden-name test, and AST-based import guards on `metric_services.py` and `mcp_http.py` gives layered defense against sync/admin/SQL leakage (D-06, MCP-02).
- **Fail-closed Docker preflight.** `validate_runtime_db` opening via `mode=rw` without file creation, and a HEALTHCHECK using the same preflight, cleanly extends Phase 2's fail-closed rule into runtime.
- **Live gateway changes are gated.** 05-06's backup → atomic write → smoke → rollback flow is the right shape for editing `/opt/docker/mcp-gateway/*` while four other tenants share the gateway.
- **`sport_scope` metadata in the registry** is a smart design choice: per-sport vs global comparison behavior is encoded once, not re-decided per tool.

## 3. Concerns

### HIGH

- **Dev DB vs deploy DB ownership is unresolved.** 05-05 copies `data/strava.db` to `/opt/docker/mcp-strava/data/strava.db`. After deployment, the refresh runtime (Phase 3) and CLI admin still write to the dev path, while the MCP container reads the deploy path. These will diverge unless one of the following is decided: (a) deploy DB is a periodic one-shot snapshot, (b) dev tooling repoints to the deploy path, or (c) refresh moves into the container. None of the six plans addresses this, and it materially affects the value of MCP responses (freshness will drift). *(Phase boundary / operational design.)*
- **05-06 mutates shared infrastructure used by four other tenants.** A bug in `register_strava_gateway` or in the gateway restart sequence can interrupt `dotmd`, `ozon`, `telegram`, and `beads`. The plan does not explicitly state when/how `docker compose up -d --force-recreate mcp-gateway` runs, in what order relative to file edits and smoke, or what happens if the helper crashes mid-write *between* catalog and compose files. Cross-file atomicity needs a clearer contract (e.g., backup both → write both → restart → smoke → rollback both if any step fails). *(Operational blast radius.)*
- **MCP SDK assumptions are not pinned.** 05-04 uses `mcp>=1.21,<2` and "FastMCP Streamable HTTP at `/mcp`" without verifying that the official SDK's `FastMCP` exposes (a) a Streamable HTTP app that serves at a configurable path, (b) Origin/host middleware, and (c) `ToolAnnotations` through a stable public API. The plan acknowledges the Origin gap ("otherwise keep the bind guard and document the SDK limitation"), but MCP spec security guidance explicitly requires Origin validation. Soft-acknowledging the gap rather than closing it is a real risk for MCP-04. *(Dependency / spec compliance.)*
- **`MCP_STRAVA_ALLOW_CONTAINER_BIND` is introduced without wiring into `settings.py`.** 05-04 and 05-05 reference this env var, but `settings.py:_KEYS` does not include it and `Settings` has no field for it. Tests will pass if checked via `os.environ` directly inside `validate_http_settings`, but it bypasses the typed settings layer (FOUND-02) and the env-file lookup. *(Cross-plan consistency.)*

### MEDIUM

- **`get_fitness_state_service` performance.** 05-02 bundles `daily_report_from_connection` (enriches up to 14 days × multiple stream-derived metrics) with `weekly_digest` (rolling 7/28/90-day windows + per-sport efficiency). For an active mirror this can be hundreds of stream queries per call. Agents may poll this tool frequently. No caching, no row-budget, no per-call timing constraint mentioned. *(Performance.)*
- **Safety-warning text → structured codes mapping is undefined.** 05-02 says "convert old `safety_warnings` text into structured `warnings` with codes plus numeric fields where available." The current strings are Russian, templated, and inline-formatted in `report.py`. The mapping needs an explicit code table (e.g., `z5_excessive`, `consecutive_hike_load_high`, `running_volume_jump`, `cardiac_drift_severe`) and corresponding numeric payloads. Plan leaves this to discretion. *(Contract under-specification.)*
- **`list_workouts_service` filters require new repository surface.** 05-02 introduces `start_date`, `end_date`, and `sport` parameters. The current `SQLiteRepository.recent_activities(limit)` does not support range or sport filters. Either new repo methods land in 05-02 (scope creep into the repository layer untracked in `files_modified`) or the parameters are effectively dead. *(Scope drift.)*
- **`compare_periods_service` data plumbing is large but unbroken-out.** 05-03 Task 2 implements global + per-sport + both for 8 comparison modes across ~15 metrics in a single task. This is the largest task in the phase and the plan does not name the underlying aggregation helpers it expects. Risk of one bloated commit with weak tests for individual modes. *(Task granularity.)*
- **`maintain` and `custom` projection scenarios are loosely defined.** 05-03: `maintain` = "recent observed average daily TRIMP with rest days preserved as zero where possible" ("where possible" is ambiguous), and `custom` accepts caller-provided rows without an explicit schema (date format, missing-day handling, max horizon, non-negative TRIMP validation). Agents calling this will hit undefined behavior. *(Contract clarity.)*
- **Registry coverage tests hardcode ~70 metric IDs.** 05-01 makes every renamed or removed metric a two-file change (test + registry). That is intentional but creates churn during execution. If a metric is split (e.g., `hr_recovery_*` becomes a nested dict), tests + docs + registry all move together. Consider whether at least some assertions should be derived from a single source list. *(Maintainability.)*
- **Dev `.env` → deploy `.env` copy via `prepare_runtime --copy-env`.** Dev `.env` is a mutable token store that the refresh runtime rewrites in place. Copying it to deploy creates a second mutable token store that immediately diverges on the next refresh. If refresh keeps running against dev DB while the container reads deploy DB, deploy's tokens will silently rot too. Same root cause as the dev/deploy DB ownership concern. *(Secret lifecycle.)*

### LOW

- **`comparable_metrics(scope, sport_scope)` parameter semantics.** 05-01 lists `scope` and `sport_scope` as separate registry fields but never defines what `scope` means as distinct from `sport_scope` (window? per-activity vs aggregate?). Plan should name the allowed `scope` values up front.
- **HEALTHCHECK interval not set.** 05-05 Dockerfile adds HEALTHCHECK but does not specify `--interval` / `--timeout`. Default 30s may be fine but should be intentional.
- **Smoke runbook references `/opt/docker/mcp-strava/docker-compose.yml`** in 05-06 but 05-05 puts the compose file at `deploy/docker-compose.yml` in the repo. Either the runbook copies/symlinks compose into `/opt/docker/mcp-strava/` or it should reference the repo path. Minor but will trip live execution.
- **`docker compose -f /opt/docker/mcp-gateway/compose.yaml config` validation** requires the gateway's `${MCP_GATEWAY_EXTERNAL_URL}` etc. to resolve. If the agent runs config validation without those env vars sourced, it may report spurious failures and trigger an unnecessary rollback.
- **Post-weekend Monday form** in projection is only meaningful when target lands on a weekend. Plan says "when target date/weekend context is applicable" — output schema should make this an optional field with a documented absence condition rather than "applicable" semantics.

## 4. Suggestions

- **Add a 0-th plan task or an explicit decision in 05-05/05-06**: choose between (a) dev DB stays canonical and deploy DB is a periodic snapshot, (b) deploy DB takes over and refresh runtime moves into the container, or (c) dev tooling repoints to `/opt/docker/mcp-strava/data/strava.db` via settings. Document the chosen path in `docs/deployment.md` and adjust `prepare_runtime` accordingly.
- **Tighten 05-06's atomicity**: backup both files → write both → restart gateway → smoke → if any step fails, restore both and restart again. Add a test where `register_strava_gateway` is killed between catalog write and compose write (e.g., monkeypatch to raise on the second write) and asserts both files are restored.
- **Pin the MCP SDK feature surface**. Before writing 05-04, the planner should add a research note (or a `read_first` step in Task 2) verifying: which class provides Streamable HTTP, whether `/mcp` is the SDK default, whether `ToolAnnotations` is exported, and whether Origin allowlisting is configurable. If Origin enforcement is not available in the SDK, add a minimal ASGI middleware in `mcp_http.py` rather than documenting the gap.
- **Wire `MCP_STRAVA_ALLOW_CONTAINER_BIND` into `settings.py`** (`_KEYS`, `Settings`, `load_settings`) so the bind guard reads a typed field, not raw `os.environ`. This keeps FOUND-02 intact.
- **Split 05-03 Task 2** into (a) build period-aggregation helpers per comparison mode against the repository, (b) wire registry → aggregator dispatch and per-sport routing. The current single-task scope is too large for one TDD cycle.
- **Define a `safety_warning_codes.md` or registry entry table** in 05-02, listing the closed set of warning codes (`z5_excessive`, `hike_load_consecutive_high`, `running_volume_jump_high`, `cardiac_drift_severe_yesterday`, `hr_anomaly_burst`, etc.) plus the numeric fields each carries. Test the code list, not the message strings.
- **Document `custom` scenario schema** in 05-03: required `date` ISO format, non-negative TRIMP, monotonic dates, max horizon (e.g., 90 days), and the behavior for gaps (filled as zero? rejected?).
- **In 05-05, explicitly note that `prepare_runtime --copy-env` is a one-shot bootstrap** and that subsequent token rotations belong in the container's `/opt/docker/mcp-strava/.env`, not the dev `.env`. Or block `--copy-env` once `target_root/.env` exists.
- **Add a guard test in 05-06** that `register_strava_gateway` refuses to write if `docker compose -f /opt/docker/mcp-gateway/compose.yaml config` (validation step) fails *before* mutation, not just after.

## 5. Risk Assessment

**Overall risk: MEDIUM-HIGH.**

The contract-design portions (05-01, 05-02, 05-03) are LOW–MEDIUM risk: well-scoped, TDD-first, and reversible. The MCP wire-up (05-04) is MEDIUM risk, gated on SDK feature assumptions and the bind-guard wiring detail. The Docker step (05-05) is MEDIUM risk, mostly because of the unresolved dev/deploy DB and secret ownership question. The live gateway integration (05-06) is the HIGH-risk step: it mutates shared infrastructure that already serves four production tenants, and the cross-file atomicity, restart order, and rollback verification details need to be tightened before it runs. The phase goals are achievable, but the live-rollout step should not execute until the data-ownership question is settled and the gateway helper's atomicity contract is explicit and tested.

---

## OpenCode Review

# Phase 5 Plan Review — MCP HTTP Surface & Docker Hardening

## 05-01: Metric Registry & Synthetic Metric Inventory

### Summary
A thorough, well-scoped foundation that inventories every computed metric into a typed registry with comparison metadata and explicit interpretation exclusions. This is the right first plan because all downstream MCP tool wiring depends on knowing what metrics exist and how they should be compared.

### Strengths
- Complete inventory coverage: names ~70+ specific metric IDs, leaving no room for silent loss.
- `EXCLUDED_INTERPRETATIONS` preserves numeric/model inputs for recommendation/weekly-plan fields while preventing coaching labels from surfacing as metrics.
- `sport_scope` (global/per_sport/both) is a clean mechanism for automatic comparison behavior that prevents incorrectly averaging cardiac metrics across different sports.
- `docs/metrics.md` synchronization tests prevent contract drift between code and documentation.
- Waves 2–6 all depend on this plan, making the dependency ordering correct.

### Concerns
- **MEDIUM**: The test file asserts ~70+ specific metric ID strings. If a legitimate metric rename or split occurs during implementation, the test breaks. The intent (no silent loss) is correct, but the test could also accept a superset check (all expected IDs present) rather than exact string matches, allowing room for additions.
- **LOW**: The registry has no explicit "agent-discoverable" path defined. The SPEC.md mentions agents should know units, missing-data conditions, and comparison semantics, but this plan only produces `docs/metrics.md` (human-readable) and `Registry` (code-level). An MCP resource endpoint for the registry is not scoped here. If downstream agents need structured metric definition data at query time, that's a gap.
- **LOW**: `ExcludedInterpretation` fields reference `preserved_metric_ids` but the mapping between an excluded interpretation and *which* tool(s) should expose its preserved metrics is not explicitly tracked.

### Suggestions
- Make the registry test a superset assertion: "every metric in `EXPECTED_METRIC_IDS` is in `METRIC_REGISTRY`" rather than exact equality. This allows legitimate additions without breaking.
- Add a `registry_accessible_via` field or a note that a future plan (or MCP resource) will make the registry discoverable to agents.

### Risk Assessment: **LOW** — This is a data-definition plan. The scope is well-bounded, the test coverage is aggressive but correct, and there are no runtime or integration concerns.

---

## 05-02: Fitness & Workout Metric Services

### Summary
Translates the existing daily report, workout analytics, and digest logic into three metric-oriented service functions whose response payloads use registry IDs and carry freshness/completeness envelopes. The no-coaching and no-admin contracts are enforced via tests and AST import guards.

### Strengths
- Reuses existing computation (daily report, weekly digest, enrich_activity) without reimplementing formulas — good YAGNI.
- AST guard tests reject `mcp_strava.adapters.strava`, `mcp_strava.sync`, etc. from metric service modules. This prevents accidental coupling to operational code.
- Safety warnings are converted from free-text to structured codes with numeric fields — this preserves facts without coaching.
- Each workout row in `list_workouts_service` carries per-row `completeness`, not just an aggregate status, which gives agents fine-grained data quality awareness.

### Concerns
- **MEDIUM**: `get_fitness_state_service` calls through `daily_report_from_connection()`, which computes more than fitness state (it also computes recommendations, weekly plans, projections). The plan says to strip recommendation/weekly-plan interpretation fields, but if `daily_report_from_connection()` is expensive, the service does unnecessary work that gets discarded. This is acceptable at current scale (SQLite, one user) but could be tightened.
- **MEDIUM**: The specific structure of "structured warnings with codes" is not specified in the plan’s task action. The acceptance criteria mention it conceptually, but without example codes, the implementation could diverge from what agents expect.
- **LOW**: `list_workouts_service` accepts `start_date/end_date/sport` filters but the plan doesn't specify whether date ordering defaults to descending (most recent first), which is the expected agent behavior.

### Suggestions
- Consider a lighter `fitness_state_from_connection()` function that computes only Banister/ACWR/load facts without the full report machinery, or document the decision to reuse `daily_report_from_connection()`.
- Add a small known set of warning codes (e.g., `low_hr_data`, `insufficient_history`, `inconsistent_hr`) as a constant list referenced in the plan.

### Risk Assessment: **LOW** — Services are thin wrappers over proven core logic. The import guards and payload contract tests are well-designed.

---

## 05-03: Period Comparison & Fitness Projection Services

### Summary
Extends the metric service layer with registry-driven period comparison (aggregating metrics per sport_scope) and a projection simulator that supports rest/easy/maintain/custom scenarios without making recommendations.

### Strengths
- `compare_periods_service` is driven by `METRIC_REGISTRY` metadata rather than hardcoded metric lists. This means newly registered comparable metrics automatically appear in comparisons without service code changes.
- `sport_scope` correctly prevents cardiac drift or vertical speed from being averaged across running and cycling — this is a nuanced design that matters for training analytics.
- Projection scenarios are parallel facts, not ranked recommendations. The acceptance criteria explicitly check for absence of `best_scenario`, `recommended_scenario`, and `on_track`.
- `delta_pct` is only computed when both values are numeric and period B is non-zero, avoiding division-by-zero noise.

### Concerns
- **MEDIUM**: The "easy" scenario template load is said to be "derived from existing `Config.Plan`/weekly-plan template values." If `Config.Plan` was part of the old coaching/recommendation layer and has been refactored, the template values may not be stable or may have been classified as interpretation. The plan should confirm `Config.Plan` template TRIMP values exist and are numeric facts, not coaching constructs.
- **MEDIUM**: `post_weekend_monday_form` requires identifying weekends relative to target_date. The plan doesn't specify how weekend boundaries interact with custom date ranges or non-standard training schedules.
- **LOW**: Period comparison for `distribution` mode (e.g., zone distributions) is listed but the plan doesn't specify what comparison output looks like for distributions — e.g., Jensen-Shannon distance, bucket-wise deltas, etc.
- **LOW**: `compare_periods_service` with `sport=None` returns both global and per-sport sections, but with `sport="running"`, does it return global metrics filtered to that sport or global metrics unchanged? This edge case isn't clarified.

### Suggestions
- Verify `Config.Plan` template values are stable numeric data before implementing `easy` scenario.
- Document how `distribution` comparison output is structured (bucket deltas, overlap metrics, or simply two distributions side-by-side).
- Specify sport-filtered period comparison behavior: when `sport` is provided, do global body/load metrics get pulled from only that sport's activities or remain full-body?

### Risk Assessment: **MEDIUM** — The registry-driven comparison design is excellent, but the "easy" scenario dependency on old template config and the under-defined distribution comparison edge cases introduce some execution risk.

---

## 05-04: MCP HTTP Server & Tool Allowlist

### Summary
Exposes the five metric services through an HTTP MCP server using FastMCP SDK, enforces the tool allowlist with forbidden-name tests, and guards against unsafe bind configurations.

### Strengths
- Exact allowlist enforcement with both positive (exactly these five) and negative (not these names) assertions, including old CLI/product names like `daily_report` and `weekly_summary`.
- Bind guard `validate_http_settings` distinguishes local vs. container runtime profiles, with explicit `MCP_STRAVA_ALLOW_CONTAINER_BIND=1` gate for container `0.0.0.0`.
- Tool annotations (`readOnlyHint=True`, `destructiveHint=False`) correctly signal to MCP clients that these are safe read-only operations.
- Structured content through `dc_to_dict()` prevents raw JSON string duplication in text content.
- Missing workout returns `completeness.status == "unavailable"` rather than an error, keeping the "missing data is factual metadata" contract.

### Concerns
- **HIGH**: Adding `mcp>=1.21,<2` is the project's first external runtime dependency. The project is currently stdlib-only. This is architecturally significant. The plan should confirm that the MCP SDK is available in the target Python environment (Docker, local dev). The dependency should also be reflected in lockfile management if the project adopts one.
- **MEDIUM**: The plan says "If SDK exposes Origin middleware/settings, configure allowed origins" — this is conditional and makes origin validation dependent on SDK capabilities. If the SDK lacks origin controls, the gap should be documented as a known limitation, not silently accepted.
- **MEDIUM**: The plan references both "the official MCP Python SDK FastMCP server" and "Streamable HTTP" transport. If the project adopts the newer 2025 spec transport, the `mcp` package version pinning must align with the transport features available.
- **LOW**: The `main()` entry point parses `argv`. How does this integrate with `python -m mcp_strava.interfaces.mcp_http`? The plan doesn't specify whether `main()` reads settings from env vars or CLI args, or both.

### Suggestions
- Verify `mcp>=1.21` availability in the Docker Python 3.13-slim image (may need system deps for the SDK).
- If the SDK doesn't support Origin headers natively, add a documentation note and consider a lightweight WSGI/ASGI middleware layer as a follow-up.
- Specify the entry point interaction: `main()` should read `MCP_STRAVA_HTTP_HOST`, `MCP_STRAVA_HTTP_PORT`, `MCP_STRAVA_RUNTIME_PROFILE` from settings/env, not require CLI args for these.

### Risk Assessment: **MEDIUM** — The design is solid but the external SDK dependency, uncertain origin validation, and potential SDK version/transport misalignment create meaningful execution risk.

---

## 05-05: Container Runtime & Data Hardening

### Summary
Creates Docker artifacts (Dockerfile, compose, preflight, runtime preparation) that package the MCP backend as a non-root container with persistent storage, fail-closed DB startup, and no public host port exposure.

### Strengths
- `validate_runtime_db` opens with `mode=rw` (not `mode=rwc`) — this correctly prevents SQLite from creating an empty replacement DB, fulfilling D-27.
- `prepare_runtime` creates a timestamped backup before replacing the target DB, then validates both source and target — this is the same discipline used in Phase 2 migrations.
- Dockerfile runs as non-root (uid 10001), sets `PYTHONUNBUFFERED=1`, and runs preflight before the server.
- Compose has `expose` but no `ports:` by default — correct for internal Docker network access only.
- `.dockerignore` excludes `.env`, `data/*.db*`, and `.planning/config.json`.

### Concerns
- **HIGH**: The Dockerfile command runs preflight AND the MCP server. The plan shows `python -m mcp_strava.deploy.preflight --db /data/strava.db` before `python -m mcp_strava.interfaces.mcp_http`. If preflight passes and then the MCP server crashes or hangs, the container stays "up" with a PID 1 that is the MCP server (not the preflight). This is correct if preflight is a pre-start script — but the plan should specify whether preflight is a separate ENTRYPOINT script or inline in CMD. If preflight fails, the container should exit before the server starts.
- **MEDIUM**: The healthcheck runs `preflight.py --quiet` every interval. If the DB is on a persistent volume and another process (sync, migration) temporarily locks it, a healthcheck failure could trigger unnecessary container restarts. Consider whether the healthcheck should only verify DB file existence and readability, not full integrity, or should use a timeout/short busy timeout.
- **MEDIUM**: `prepare_runtime` copies the source DB and optionally copies `.env`. Copying secrets requires careful permissions — the plan says "restrictive local permissions" but this is OS-dependent and may not work consistently across deployment environments.
- **LOW**: The `deploy/.dockerignore` excludes `data/*.db*` but the build copies `src/` — is the deployed DB really coming from a volume mount (`/data`), not from a baked-in empty DB? The plan correctly uses a volume mount, but verifying no DB gets baked into the image is worth an additional test.

### Suggestions
- Use a wrapper script (e.g., `deploy/entrypoint.sh`) that runs preflight then execs the server, ensuring clean signal handling and proper failure propagation.
- Make the healthcheck a lightweight DB readability check (SELECT COUNT(*) FROM activities) rather than full preflight, or add a busy timeout.
- Add a test that the built Docker image does not contain any `.db` or `.env` files (can be done in `tests/test_docker_runtime.py` with a source assertion on `.dockerignore` coverage).

### Risk Assessment: **MEDIUM** — The data safety patterns (backup, validation, fail-closed) are excellent, but the entrypoint/healthcheck interaction and secret-file permission handling need more precision.

---

## 05-06: Live Gateway Integration & Rollback Smoke

### Summary
Provides the tooling to safely add `strava` to the existing Docker MCP gateway with backup, atomic edit, smoke, and rollback. Also documents the live deployment runbook.

### Strengths
- Temp-file tests prove backup creation, exact preservation of existing gateway servers (`ozon`, `telegram`, `beads`, `dotmd`), and byte-for-byte rollback on smoke failure.
- `atomic_write_text` prevents partial writes from corrupting live gateway files.
- Smoke client checks both expected tool presence AND forbidden tool absence — this validates the MCP tool surface through the gateway, not just direct backend calls.
- Runbook covers the full flow: prepare runtime DB → build → up → backend smoke → gateway register → gateway smoke.

### Concerns
- **HIGH**: The smoke client in `src/mcp_strava/deploy/smoke.py` needs to speak the MCP protocol (initialize session, list tools, call tools). If implemented with stdlib only (as the project currently is), this requires implementing a minimal JSON-RPC client with session initialization. The plan mentions "stdlib or MCP-SDK client" — the stdlib path is non-trivial and error-prone. The MCP-SDK path adds another usage of the external dependency introduced in 05-04.
- **HIGH**: `register_strava_gateway` must parse the gateway compose file's `--servers=` argument and append `strava`. This is string manipulation on a Docker Compose command field. If the compose format changes (e.g., `command:` becomes a list), the parsing logic breaks. The plan should specify a resilient parsing strategy or note this fragility.
- **MEDIUM**: The live integration task (Task 3) includes "run the live prepare/build/up/register flow against `/opt/docker/mcp-gateway`." This is an online operation that mutates a live system. The plan correctly has backup/rollback, but the task description mixes "document + execute" in one task. If the live execution is separate from the plan implementation, that boundary should be clearer.
- **MEDIUM**: The smoke command in the runbook runs `docker compose exec` inside the gateway compose to call smoke from the backend container. If the gateway network configuration doesn't allow container-to-container HTTP, this smoke will fail even though the backend is healthy.
- **LOW**: The rollback in `register_strava_gateway` restores files but doesn't restart the gateway stack. Restarting the gateway is a separate manual step that should be documented in the rollback procedure.

### Suggestions
- Use the MCP SDK's client capabilities for the smoke client rather than implementing JSON-RPC from scratch — by this wave, the SDK dependency is already established in 05-04.
- Add a test that the compose parser handles both string-format and list-format `command:` entries.
- Split Task 3 into "write runbook" and "execute live integration" as separate sub-tasks or make the live execution an explicit acceptance criteria outside the implementation task.
- Document that after rollback restores files, the operator must `docker compose restart` the gateway stack.

### Risk Assessment: **HIGH** — This plan modifies a live production gateway. The backup/rollback design is correct, but the compose file string parsing fragility and the smoke client implementation complexity (if done without SDK) are significant execution risks. Live integration should not block the plan's "done" state.

---

## Overall Assessment

### Architecture Alignment

The six plans form a coherent wave progression (Registry → Services → Comparison/Projection → MCP Server → Docker → Gateway) that respects all architectural constraints:
- MCP boundary is strictly enforced at every layer (allowlist, forbidden names, AST guards, import guards).
- Coaching/interpretation stays out of the service with explicit exclusion mappings.
- Data preservation (backup, preflight, fail-closed) is applied consistently from Phase 2 patterns through to live gateway deployment.
- Sync/admin/raw/strava surfaces are excluded from MCP tools in all plans.

### Key Risks (consolidated)

| Risk | Severity | Plans Affected | Mitigation |
|------|----------|----------------|------------|
| External `mcp` SDK dependency introduced | **HIGH** | 05-04, 05-06 | Verify availability in target Python image; test early in 05-04 |
| Compose command-line string parsing for registration | **HIGH** | 05-06 | Handle both string and list `command:` formats; test both |
| Live gateway mutation during 05-06 execution | **HIGH** | 05-06 | Separate runbook write from live execution; keep rollback granular |
| `daily_report_from_connection()` computes more than fitness state needs | **MEDIUM** | 05-02 | Acceptable at single-user scale; document trade-off |
| Conditional SDK origin validation | **MEDIUM** | 05-04 | Document gap if SDK doesn't provide it |
| Entrypoint/healthcheck interaction | **MEDIUM** | 05-05 | Use wrapper script for clean failure propagation |
| Metric registry test fragility (70+ exact string IDs) | **LOW** | 05-01 | Switch to superset assertion |

### Overall Risk: **MEDIUM**

The plans are comprehensive, well-sequenced, and adhere to all Phase 5 constraints. The primary risks are concentrated in wave 5 (Docker entrypoint/healthcheck) and wave 6 (live gateway mutation). Plans 05-01 through 05-04 are low-risk and well-specified. The external SDK dependency is the only architectural departure from the current stdlib-only project and should be validated early.

### Will These Plans Achieve Phase 5 Goals?

**Yes**, with the caveat that 05-06's live integration should be scoped as "tooling + documented runbook" in the plan's core implementation, with live execution as a separate operational step that may or may not succeed on first attempt. The rollback design makes it safe to retry. All MCP-01 through MCP-04, DOCKER-01 through DOCKER-03, and TEST-03 requirements are traced to specific plans with test coverage.

---

## Consensus Summary

### Agreed Strengths

- The six-wave order is coherent: metric registry, metric services, comparison/projection services, MCP HTTP surface, Docker hardening, then live gateway integration.
- The MCP boundary is correctly read-only and excludes sync/admin/raw SQL/token/log surfaces.
- The registry-first approach is the right mechanism to avoid losing intentional synthetic metrics.
- Freshness/completeness metadata and per-metric missing reasons are central enough in the plan to be testable.
- Docker and gateway plans use the right safety shape: fail-closed DB preflight, backup before mutation, smoke checks, and rollback.

### Current HIGH Concerns

- Dev/deploy data ownership is unresolved: copying `data/strava.db` to `/opt/docker/mcp-strava/data/strava.db` can create divergent mirrors unless the canonical DB/refresh path is explicitly decided.
- MCP SDK dependency and feature assumptions are not pinned tightly enough: the first external runtime dependency needs early verification for Python 3.13/Docker, Streamable HTTP, tool annotations, and Origin enforcement.
- `MCP_STRAVA_ALLOW_CONTAINER_BIND` is referenced by plans but not clearly wired into the typed settings layer.
- Live gateway mutation still needs a stronger cross-file atomicity/restart/rollback contract because `/opt/docker/mcp-gateway` serves other MCP tenants.
- Docker preflight/server startup semantics need to be explicit, preferably via an entrypoint that runs preflight then `exec`s the MCP server.
- Gateway smoke client scope is under-specified: it must use the MCP protocol correctly rather than hand-rolling fragile JSON-RPC unless the SDK client path is chosen.
- Gateway compose mutation is fragile if it only string-parses `--servers=`; it needs tested handling for string and list `command:` formats or an explicitly constrained format.

### Agreed Concerns

- `compare_periods` and projection behavior needs tighter contracts for distribution metrics, sport filtering semantics, custom scenario validation, and template TRIMP assumptions.
- Warning codes should be a closed structured contract rather than ad-hoc mappings from existing warning text.
- `list_workouts` filtering implies repository support that should be explicit in the plan.
- Healthcheck design should avoid turning transient SQLite locks into unnecessary container restarts.
- The live execution boundary in 05-06 should distinguish implementation of tooling/runbook from actually mutating the live gateway.

### Divergent Views

- Claude rates the overall risk as MEDIUM-HIGH, while OpenCode rates it as MEDIUM. Both place the highest risk in Docker/gateway rollout rather than metric-service design.
- Claude treats dev/deploy DB ownership as the most material blocker; OpenCode focuses more on SDK dependency and gateway/smoke implementation complexity.
- OpenCode is more accepting of the expensive reuse of existing daily report logic at one-user scale; Claude calls out performance more strongly.

### Convergence Input

The next planning revision should address the seven Current HIGH concerns before execution. Most fixes are plan clarifications or small task additions, not design reversals.

CYCLE_SUMMARY: current_high=7
