---
phase: 5
reviewers: [claude, opencode]
reviewed_at: 2026-05-22T14:20:09+05:00
plans_reviewed:
  - 05-01-PLAN.md
  - 05-02-PLAN.md
  - 05-03-PLAN.md
  - 05-04-PLAN.md
  - 05-05-PLAN.md
  - 05-06-PLAN.md
reviewed_after_commit: d44176e929e9f55d06525e682e7fd99372c198b8
current_high: 2
---

# Cross-AI Plan Review — Phase 5

## Review Invocation Notes

- Requested reviewers preserved exactly: Claude and OpenCode.
- Claude and OpenCode were invoked in parallel for the re-review cycle after commit `d44176e`.
- Claude completed successfully on the initial parallel run.
- OpenCode completed successfully on the initial parallel run using `/home/j2h4u/.opencode/bin/opencode`, because `opencode` is not in the default PATH for this shell.
- No reviewer substitution was used and no sequential fallback was needed.

## Cycle Summary

CYCLE_SUMMARY: current_high=2

## Current HIGH Concerns

- Live gateway mutation still runs as an autonomous Phase 5 execution task; reviewer recommends an explicit operator-confirm boundary and a documented contingency for rollback restart failure.
- `get_fitness_state` may leak nested recommendation/weekly-plan/prose fields if implemented by serializing `DailyReport` and filtering keys; reviewer recommends explicit metric-registry projection and stricter no-coaching tests.

## Claude Review

# Phase 5 Plan Review — After Replan (post-d44176e)

## 1. Summary

The replan substantially addresses the seven prior HIGH concerns: MCP SDK is now version-pinned with a feature-probe test, container-bind allowance flows through typed `Settings.http`, gateway integration is atomic across catalog+compose with YAML parsing and rollback restart, the smoke client uses the official SDK transport, and `prepare_runtime` plus `live.env` resolve dev/deploy DB ownership. The remaining risks are mostly operational (live gateway mutation as an autonomous task) and a few semantic gaps in period comparison and recommendation-stripping that could cause test/contract drift during implementation.

## 2. Strengths

- **Registry-first sequencing.** 05-01 forces the full synthetic-metric inventory before any tool wiring, with a coverage test that lists each id by name. Loss of metrics during MCP wiring is materially harder now.
- **Closed-set warning contract.** `SAFETY_WARNING_CODES` in 05-02 converts natural-language Russian warnings into structured codes with `metric_ids`/`values`/`thresholds`. Good D-14 compliance.
- **SDK contract test.** 05-04 Task 1 probes `FastMCP.streamable_http_path`, `TransportSecuritySettings.allowed_hosts/origins`, and `mcp.client.streamable_http` before the server is written. This is the right shape for the previous "verify before code" HIGH.
- **Cross-file gateway atomicity.** 05-06 spells out the order: prevalidate → backup both → write both atomically → validate → restart → smoke → rollback both + restart old config. Explicit rollback restart command closes the previous "restart-after-rollback" gap.
- **Boundary preservation.** AST import guards extend cleanly from prior phases to `metric_services.py` and `interfaces/mcp_http.py`. Forbidden-name lists in 05-04 include the actual product service names (`daily_report`, `weekly_summary`, …) — that's a real check, not theatre.
- **Live `live.env` decision.** 05-05 makes `/opt/docker/mcp-strava` canonical and documents that host CLI/refresh must point there post-cutover. Resolves the dev/deploy split that the prior cycle left implicit.

## 3. Concerns

- **HIGH — Live gateway mutation runs autonomously inside 05-06 Task 3.** The task description says "during execution of this plan, after tests pass and Docker backend is up, run the live prepare/build/up/register flow against `/opt/docker/mcp-gateway`." This rewrites the shared `mcp-gateway` configuration and restarts the container used by `ozon`, `telegram`, `beads`, and `dotmd`. Even with rollback, brief downtime and the risk of a rollback-restart that itself fails (no contingency stated) make this an operator-confirm boundary, not an autonomous one. Recommend an explicit gate: tests + build are autonomous, but the live `gateway_register.py` run requires human go-ahead, and the plan should say what happens if rollback restart also fails (manual recovery doc reference + exit code distinction).

- **HIGH — `get_fitness_state` payload may leak `Recommendation`/`WeeklyPlan` via `daily_report_from_connection`.** The current `DailyReport` carries `recommendation`, `weekly_plan`, and Russian-language `safety_warnings` strings. 05-02 Task 2 leans on `daily_report_from_connection()` for compute, then "normalizes payload keys" and "strips" interpretation fields. The risk is that the implementation serializes `DailyReport` via `dc_to_dict()` and merely deletes top-level keys, leaving nested fields (`weekly_plan.plan_days[i].activity`, `progressive_signal.reasons` in Russian, `safety_warnings` strings) in place. The negative-assertion tests will catch top-level keys but may not catch nested Russian text or `progressive_signal.reasons`. Plan should require the service to construct a new dict explicitly from registry ids, not to filter `dc_to_dict(DailyReport)`. The test for D-14 should also reject any string value containing Cyrillic in service `data`.

- **MEDIUM — Banister metrics in `compare_periods` have no aggregation semantics.** Registry has `fitness`, `fatigue`, `form`, `acwr`, `atl`, `ctl` as `comparison_mode in {"last","avg","median",...}` but these are EWMA series, not sums per window. "Sum" or "avg of period TRIMP" makes sense; "form at period end" makes sense; the plan doesn't pin which. 05-03 Task 2 implementation note lists comparison modes but doesn't say which mode each Banister metric uses. Recommend per-metric `comparison_mode` decisions encoded directly in the registry entries created by 05-01, so 05-03's executor has no choice to make.

- **MEDIUM — `comparison_mode="trend"` between two periods is undefined.** A "trend" is computed from a series; comparing two pre-computed trends (period A trend vs period B trend) doesn't have an obvious shape. The plan should either drop `"trend"` from the closed set in `compare_periods` (period comparison aggregates raw values into A/B scalars and computes its own delta direction) or define it explicitly (e.g., trend slope within A vs trend slope within B).

- **MEDIUM — `--forbid-tool sync` in live gateway smoke can false-positive across other servers.** The Docker MCP gateway aggregates tools from `ozon`, `telegram`, `beads`, `dotmd`, and `strava`. If any other server now or in the future exposes a tool literally named `sync`, the Strava deploy smoke will fail and trigger a rollback. The forbid-list should scope by server prefix (e.g., the gateway tool registry typically namespaces tools as `strava/<tool>`) or the smoke should only assert presence of the five Strava tool names and absence of forbidden names *under the Strava prefix*. Recommend Task 2 verify the actual gateway tool-naming convention before locking `--forbid-tool` semantics.

- **MEDIUM — `prepare_runtime` is described as "one-shot bootstrap" but DB drift after day 2 is unaddressed.** If the canonical DB lives at `/opt/docker/mcp-strava/data/strava.db` and host CLI uses `live.env`, that's fine. But the plan still allows `prepare_runtime --source-db data/strava.db --target-root /opt/docker/mcp-strava` to overwrite the live DB at any time (with backup). That's a footgun: if someone runs it after the container has been writing for a week, the dev snapshot replaces the live state. Recommend `prepare_runtime` require `--replace-db` flag (analogous to `--replace-env`), refuse silently to overwrite a target DB whose `synced_at`/refresh state is newer than source, or emit a strongly worded warning.

- **MEDIUM — `--quiet` flag on healthcheck not in `preflight.main` interface.** Dockerfile HEALTHCHECK calls `python -m mcp_strava.deploy.preflight --db /data/strava.db --quick --quiet` (05-05 Task 3) but Task 2's `main(argv)` description only mentions `--quick`. Trivial fix — list the flag in Task 2 — but otherwise tests for Task 2 won't enforce it and the healthcheck will print to container logs on every probe.

- **MEDIUM — MCP SDK pin `mcp>=1.27.1,<1.28` is tight.** A patch release within the same minor would be excluded. The prior HIGH was about under-pinning, but the swing to a single-minor pin will create patch-version friction. Recommend `>=1.27.1,<1.28` only if there is a known break in 1.28; otherwise `>=1.27.1,<2` with the SDK contract test (which is the actual safety net) is more pragmatic.

- **LOW — `metrics_for_tool("get_data_status")` acceptance criteria is ambiguous.** "is not valid because `get_data_status` is not in `MCP_TOOL_IDS`" — does that mean raise `KeyError`, return `[]`, or return `None`? Pin to one in Task 2.

- **LOW — `streamablehttp_client` vs `streamable_http_client` accepted alternatives.** The SDK contract test in 05-04 accepts either name. If the SDK is pinned, this is a single function — pick one and assert exactly that. Otherwise the test passes today on whichever, and the server code in Task 3 has to choose anyway.

- **LOW — `low_hr_data` and `insufficient_history` are listed under `SAFETY_WARNING_CODES` but read more like completeness metadata than safety.** Doesn't change behavior; could cause future confusion when separating safety warnings from completeness warnings in `_warnings_from_completeness`/`_warnings_for_safety` paths.

- **LOW — 05-01's metric list is large (~70) and entirely hand-written.** Realistic, but registry maintenance burden grows. Consider a `tests/test_metric_registry.py` test that diffs `METRIC_REGISTRY.keys()` against a checked-in `metric_ids.txt` so unintended drops require an explicit change to the manifest, not just a quiet registry edit.

## 4. Suggestions

- Gate the live gateway mutation in 05-06 Task 3 behind an explicit `--apply` flag (default dry-run) and have the plan only run dry-run + diff autonomously; the actual write/restart should be an operator step documented in `docs/deployment.md`.
- Have 05-02 Task 2 explicitly forbid `dc_to_dict(DailyReport)` as the path to the MCP `data` payload and require an explicit projection function (e.g., `_fitness_state_payload(report, digest) -> dict[str, MetricValue]`). Add a "no Cyrillic in service data values" test as the strict version of the no-coaching contract.
- In 05-01, encode `comparison_mode` per registry entry (especially for stateful metrics: `fitness`/`fatigue`/`form` should be `"last"` or `"avg"` per the actual semantic, not "executor's choice"). Drop or define `"trend"` for period comparison.
- In 05-06, replace `--forbid-tool sync` with strava-namespace scoping or with positive-only assertions (`--expect-tool get_fitness_state` etc.); confirm the gateway tool-naming convention as part of Task 1.
- Add a "day-2" section to `docs/deployment.md` clarifying when (and when not to) re-run `prepare_runtime`, and require `--replace-db` to overwrite an existing target DB.
- Loosen the SDK pin to `>=1.27.1,<2` and lean on the contract test for breakage detection; revisit if 1.28 actually breaks.
- Consider splitting 05-03 into 05-03a (period comparison) and 05-03b (projection) — the projection scenario validation and the comparison's distribution/per-sport routing are independently large surfaces.

## 5. Risk Assessment

- **Operational blast radius:** moderate. Live gateway mutation is the largest single risk. Rollback is well-defined for the file edits and the gateway restart, but a failed rollback restart has no documented recovery path and would leave the shared gateway broken.
- **Data loss / mirror corruption:** low. `prepare_runtime` backs up before replacing, container preflight fails closed, no MCP tool writes. Residual risk is human-induced overwrite of live DB by re-running `prepare_runtime`.
- **Contract leakage (coaching/admin into MCP):** moderate. Tests catch top-level forbidden keys and tool-name allowlist. The remaining gap is nested Russian-language strings inside reused DailyReport substructures, which would technically pass the existing key-based negative assertions.
- **Dependency / SDK fragility:** low after pinning + contract test. The tight upper bound will cause low-grade maintenance churn but not phase failure.
- **Test scope:** good for registry, MCP allowlist, and Docker source. Per-period Banister and `trend` comparison-mode behavior are under-specified at the test level.
- **Phase-goal completion:** plans cover all of MCP-01..04, DOCKER-01..03, TEST-03 in code paths and tests. The risk to phase goals is concentrated in the live integration step (05-06 Task 3).

## 6. Prior HIGH Recheck

1. **Dev/deploy DB ownership — Resolved.** 05-05 adds `prepare_runtime`, writes `live.env`, and 05-06's runbook makes `/opt/docker/mcp-strava` canonical with host CLI/refresh required to point there. Residual day-2 footgun is filed under MEDIUM above, not unresolved.
2. **MCP SDK dependency / feature assumptions — Resolved.** 05-04 Task 1 pins `mcp>=1.27.1,<1.28` and adds `tests/test_mcp_sdk_contract.py` probing FastMCP, Streamable HTTP, ToolAnnotations, TransportSecuritySettings, and the SDK client. The tightness of the pin is a separate MEDIUM, not a recurrence.
3. **`MCP_STRAVA_ALLOW_CONTAINER_BIND` wiring — Resolved.** 05-04 Task 1 adds `allow_container_bind: bool` (plus `allowed_hosts`, `allowed_origins`) to `HttpSettings`, parses the env keys in `_KEYS`, and extends `tests/test_settings.py`. The server reads from typed settings, not raw `os.environ`.
4. **Live gateway cross-file atomicity, restart, smoke, rollback — Resolved.** 05-06 Task 1/2 spell out: prevalidate compose → backup both → atomic write both → validate compose → restart → smoke → rollback both + restart old config on any failure. Three failure-point rollback tests are required. The only residual concern is the rollback-restart-fails edge case (MEDIUM above).
5. **Docker preflight/entrypoint semantics — Resolved.** 05-05 Task 2 defines `validate_runtime_db(path, quick=False)` (opens with URI `mode=rw`, no file creation) and `entrypoint.main` runs full preflight then `os.execvp` so the MCP server becomes PID 1. Healthcheck flag mismatch (`--quiet`) is a MEDIUM clarity item, not unresolved.
6. **Gateway smoke uses MCP protocol correctly — Resolved.** 05-06 Task 2 mandates `mcp.client.streamable_http` + `mcp.ClientSession`, and Task 1 tests explicitly assert no hand-rolled JSON-RPC. Forbid-tool scoping across multi-server gateway is a separate MEDIUM.
7. **Gateway compose `--servers=` mutation fragility — Resolved.** 05-06 uses `yaml.safe_load`/`yaml.safe_dump`, requires `PyYAML>=6.0.2,<7`, and handles both list-form and string-form compose `command:` with tests for each. Existing servers are preserved by test assertion.

---

## OpenCode Review

Now let me read a few key source files that are referenced in the plans to verify assumptions.
Now I have sufficient context. Here is my review:

---

# Cross-AI Plan Review — Phase 5: MCP HTTP Surface & Docker Hardening (Replan)

## 1. Summary

All seven prior HIGH concerns from the previous review cycle are now addressed in the updated plans. The six-plan sequence is well-sequenced (Registry → Services → Comparison/Projection → MCP Server → Docker → Gateway), and the traces of each plan back to requirements (MCP-01 through MCP-04, DOCKER-01 through DOCKER-03, TEST-03) are explicit. The MCP boundary (no sync/admin/raw SQL/token) is enforced at three layers: tool allowlist, forbidden-name tests, and AST import guards. The phase goals are achievable with the current plans.

## 2. Strengths

- **Registry-first design (05-01) is the correct foundation.** Encoding `sport_scope` (global/per_sport/both) and `comparison_mode` once prevents per-tool re-decisions and protects against cross-sport metric contamination (e.g., averaging cardiac drift across running and cycling).
- **Triple-layered MCP boundary enforcement.** The combination of (a) exact five-tool allowlist test, (b) forbidden-name assertion list including old CLI/product names, and (c) AST import guards rejecting `mcp_strava.adapters.strava`/`sync`/`refresh.runtime` from service and MCP modules gives robust defense against accidental admin/sync leakage.
- **No-coaching contract is testable.** Negative assertions on `recommendation`, `action`, `intensity`, `on_track`, `should`, `ready`, `best_scenario`, `heart_improved`, `vessels_improved` across 05-02, 05-03, and 05-04 make this mechanically verifiable.
- **Live gateway mutation is properly gated (05-06).** Backup → in-memory YAML mutation → atomic write → compose config validation → restart → smoke → rollback on failure, with explicit mid-write crash recovery tests. This is the right shape for a shared gateway serving four other tenants.
- **Fail-closed Docker preflight extends Phase 2 patterns into runtime.** `mode=rw` (not `mode=rwc`) prevents accidental DB creation, `os.execvp` cleanly hands off PID 1 after preflight, and HEALTHCHECK uses lightweight `SELECT COUNT(*)` to avoid restart storms from transient WAL locks.
- **All prior HIGH concerns from the previous review cycle are addressed** (see Section 6).

## 3. Concerns

### MEDIUM

- **`prepare_runtime` DB copy lacks safe-copy guarantee (05-05).** The plan says "copy the source DB only after validating source" but does not specify the copy mechanism. A plain `shutil.copy2` of an in-use WAL-mode SQLite database (the source could be the host CLI's active `data/strava.db`) can produce a snapshot with incomplete WAL replay. The plan should use SQLite's backup API or `VACUUM INTO` for the live copy, or explicitly document that the source DB must not be in use during prepare. The risk is a silently corrupt deploy DB that only manifests later.
- **No MCP resource endpoint for the metric registry (05-01).** The CONTEXT.md says "Metric definitions should be available to agents either in response metadata or a compact registry/resource." The plan produces `docs/metrics.md` (human) and `METRIC_REGISTRY` (code), but no MCP resource or tool exposes the structured metric catalog to agents at query time. Agents that want to understand units, missing-data conditions, or comparison semantics must have that knowledge out-of-band. This is a gap against the stated intent, though MCP-01 does not strictly require it.
- **`get_fitness_state_service` computes more than fitness state (05-02).** It calls through `daily_report_from_connection()` which builds a full daily report including projections, weekly plans, and recommendations that get stripped. At single-user SQLite scale this is fine, but the discarded computation is an execution cost the plan acknowledges only implicitly by reusing the helper rather than extracting a narrower fitness query. The acceptance criteria are met, but a future maintainer might be confused about what "fitness state" computes.

### LOW

- **05-03 Task 1 test assertion uses "or equivalent" language** (`assert data["metrics"] or equivalent contains comparison records...`). This gives the executor too much discretion over the output shape and weakens the structural contract that 05-03 Task 2 implements. The expected output key should be pinned.
- **05-05 `expose` vs `EXPOSE` confusion.** The plan says `expose: ["8080"]` in docker-compose, which is a documentation-only directive. The Dockerfile's `EXPOSE` directive carries the actual port metadata. The intent (internal-only access, no `ports:`) is correct, but mentioning both and conflating them is minor.
- **Smoke runbook in 05-06 references backend smoke URL `http://127.0.0.1:${MCP_STRAVA_HTTP_PORT:-8000}/mcp`.** This implies a loopback port exists, which contradicts the default "no published port" compose design. The runbook should clarify that direct backend smoke is optional/conditional and that primary verification is through the gateway URL.
- **`custom_daily_trimp` validation (05-03) requires dates "within today..target_date inclusive"** but doesn't handle timezone-aware dates. The rest of the codebase uses naive `datetime` and `YYYY-MM-DD` strings, so this is consistent, but agents calling this from different timezone contexts might get off-by-one boundary behavior.

## 4. Suggestions

- **05-05: Use SQLite backup API for `prepare_runtime` DB copy.** Replace plain file copy with `source_conn.backup(target_conn)` (sqlite3 backup API) to guarantee a consistent snapshot regardless of concurrent WAL activity, or document that `prepare_runtime` requires the source DB to not be in use.
- **05-01: Consider an MCP resource for the metric catalog** (e.g., a `mcp:metrics` URI returning `metric_catalog_payload()`). This could be a deferred follow-up, but the registry infrastructure already exists; exposing it as a resource is a small addition that closes the agent-discoverability gap.
- **05-03 Task 1: Pin the output key** to `data["metrics"]` rather than `data["metrics"] or equivalent`, so the structural contract is unambiguous.
- **05-06: Clarify backend smoke preconditions** in the runbook. State explicitly that direct backend smoke via `127.0.0.1` requires an intentional published port (not default), and that the primary smoke path is through the gateway URL.

## 5. Risk Assessment

**Overall risk: LOW–MEDIUM.**

- Plans 05-01 through 05-03 (metric registry, services) are **LOW risk**: well-scoped, TDD-first, reversible, and built on existing proven computation.
- Plan 05-04 (MCP HTTP server) is **LOW risk** now: SDK pinned to a verified minor version, contract tests before implementation, and typed settings for bind/security guards.
- Plan 05-05 (Docker runtime) is **MEDIUM risk**: the `prepare_runtime` DB copy safety gap is the primary concern; the rest is solid.
- Plan 05-06 (live gateway integration) is **MEDIUM risk**: the YAML-based mutation and atomic rollback design is correct and tested; the risk is execution-time (the actual live gateway is shared infrastructure), not design-time.

The phase goals will be met. No blocking HIGH concerns remain.

## 6. Prior HIGH Recheck

| # | Prior HIGH Concern | Status |
|---|-------------------|--------|
| 1 | Dev/deploy DB ownership unresolved | **Resolved.** 05-05 adds `live.env` with canonical `/opt/docker/mcp-strava` paths, docs require host CLI/refresh to repoint there after cutover, and `prepare_runtime` refuses to overwrite existing `.env` without an explicit flag. The design contract is clear: after live cutover, the deploy path is canonical. |
| 2 | MCP SDK dependency and feature assumptions need early pinning/verification | **Resolved.** 05-04 pins `mcp>=1.27.1,<1.28` and adds `tests/test_mcp_sdk_contract.py` that verifies FastMCP Streamable HTTP, `ToolAnnotations`, `TransportSecuritySettings`, and SDK client APIs before server code is written. |
| 3 | `MCP_STRAVA_ALLOW_CONTAINER_BIND` referenced but not clearly wired into typed settings | **Resolved.** 05-04 Task 1 extends `HttpSettings` with `allow_container_bind`, `allowed_hosts`, `allowed_origins`; adds `_KEYS` entries; and parses boolean and comma-separated values formally. |
| 4 | Live gateway mutation needs stronger cross-file atomicity, restart, smoke, and rollback contract | **Resolved.** 05-06 specifies exact operation order: prevalidate → backup both → prepare both in memory → atomic-write both → validate → restart gateway → smoke → restore both + restart old config on any failure. Tests cover mid-write crash recovery and smoke-failure rollback. |
| 5 | Docker preflight/server startup semantics need explicit entrypoint behavior | **Resolved.** 05-05 uses `os.execvp` so PID 1 is the MCP server after preflight passes, with signal-safe handoff. HEALTHCHECK uses `--quick --quiet` with explicit `--interval=30s --timeout=5s --start-period=10s --retries=3`. |
| 6 | Gateway smoke client must use MCP protocol correctly; stdlib JSON-RPC path under-specified | **Resolved.** 05-06 requires official MCP SDK client (`mcp.client.streamable_http` + `mcp.ClientSession`); tests assert no hand-rolled JSON-RPC in the smoke module. |
| 7 | Gateway compose mutation fragile if it only string-parses `--servers=` | **Resolved.** 05-06 uses `yaml.safe_load`/`yaml.safe_dump` for catalog and compose, supports both string-form and list-form `command:` entries, and tests exercise both formats. |

---

## Consensus Summary

### Agreed Strengths

- Both reviewers consider the registry-first plan sequence sound and aligned with the goal of preserving synthetic metrics.
- Both reviewers consider the read-only MCP boundary materially improved through allowlist tests, forbidden-name checks, and AST import guards.
- Both reviewers consider the prior seven HIGH concerns substantially addressed by the replan: SDK verification, typed bind settings, Docker entrypoint semantics, MCP smoke protocol, and YAML-based gateway mutation are now planned explicitly.

### Agreed Concerns

- Runtime DB handling still deserves extra care. OpenCode flags safe SQLite snapshot creation during `prepare_runtime`; Claude flags day-2 overwrite risk after cutover.
- Live gateway integration remains the highest operational-risk area because it touches shared gateway infrastructure, even though the backup/rollback design is much stronger after the replan.
- Several output contracts should be pinned more tightly before execution: explicit metric projection for `get_fitness_state`, comparison semantics for stateful/trend metrics, and backend/gateway smoke assumptions.

### Divergent Views

- Claude still rates two issues as HIGH: autonomous live gateway mutation and possible nested recommendation leakage from `DailyReport` reuse.
- OpenCode rates the current plan LOW-MEDIUM overall and reports no blocking HIGH concerns, but still raises medium concerns around safe DB copying and metric registry discoverability.
