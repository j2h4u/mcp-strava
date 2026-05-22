---
phase: 5
reviewers: [claude, opencode]
reviewed_at: 2026-05-22T14:37:06+05:00
plans_reviewed:
  - 05-01-PLAN.md
  - 05-02-PLAN.md
  - 05-03-PLAN.md
  - 05-04-PLAN.md
  - 05-05-PLAN.md
  - 05-06-PLAN.md
reviewed_after_commit: f5ca0f45ad49821eed7f7c8a0e747c087e04afa1
current_high: 0
---

# Cross-AI Plan Review — Phase 5

## Review Invocation Notes

- Requested reviewers preserved exactly: Claude and OpenCode.
- Claude and OpenCode were invoked in parallel for the final re-review cycle after commit `f5ca0f4`.
- Claude completed successfully on the initial parallel run.
- OpenCode completed successfully on the initial parallel run using `/home/j2h4u/.opencode/bin/opencode`.
- No reviewer substitution was used and no sequential fallback was needed.

## Cycle Summary

CYCLE_SUMMARY: current_high=0

## Current HIGH Concerns

None.

## Consensus Summary

Both reviewers agreed that the two previous HIGH blockers are resolved:

- Live gateway mutation now has a non-autonomous/operator-confirmed boundary, dry-run default behavior, `--apply --confirm-live-gateway` gating, rollback restart handling, and manual recovery instructions.
- `get_fitness_state_service` now requires explicit metric-registry projection and tests/source guards against `DailyReport` serialize-then-filter leakage, nested coaching/prose fields, and Cyrillic natural-language content in service data.

No remaining HIGH blockers were reported. Residual notes are MEDIUM/LOW implementation details and should not block Phase 5 execution.

## Claude Review

# 1. Summary

Reviewed the six Phase 5 plans at commit f5ca0f4 plus their referenced code (`types.py`, `metrics.py`, `training.py`, `analytics.py`, `report.py`, application services, security guards, SQLite safety) and the live gateway files at `/opt/docker/mcp-gateway/{catalog,compose}.yaml`.

Both previously raised HIGH concerns are now addressed with enforceable contracts (frontmatter truths, tasks, tests, and acceptance criteria). I see **no remaining HIGH blockers** for Phase 5 to start execution.

# 2. Remaining HIGH Concerns

None.

# 3. Previous HIGH Recheck

**(A) Live gateway mutation: operator-confirm boundary + rollback restart failure contingency — RESOLVED**

Evidence in `05-06-PLAN.md`:
- Frontmatter `autonomous: false` and `operator_confirm_required: true` make this plan distinct from the autonomous waves.
- Truth: "live `/opt/docker/mcp-gateway/*` mutation is never unprompted; autonomous execution may prepare, test, build, and dry-run only, while actual live writes require explicit operator confirmation."
- Task 1 mandates CLI guard tests asserting default invocation is dry-run, and any attempt to mutate the live files requires both `--apply` *and* `--confirm-live-gateway`; without both flags the command exits before writing.
- Task 1 includes a dedicated **rollback-restart-failure test** asserting a distinct failure code, no further mutation attempts, and only redacted recovery info.
- Task 2 implementation contract: "If rollback restart fails, return a distinct exit code, report only redacted backup paths and recovery commands, and do not attempt additional writes."
- Task 3 runbook codifies: "Before any command that writes `/opt/docker/mcp-gateway/catalog.yaml`, writes `/opt/docker/mcp-gateway/compose.yaml`, or restarts `mcp-gateway`, stop and ask the operator for explicit approval" and adds an explicit rollback-restart-failure contingency (stop automation, verify backups, `docker compose ... config` + `... logs --tail=200`, restore older backup or escalate).
- STRIDE T-05-19 / T-05-20a / T-05-20b are tied to these mitigations.

This is sufficient for both the consent boundary and the failure-mode-of-the-rollback path.

**(B) `get_fitness_state` explicit metric-registry projection (no DailyReport leakage) — RESOLVED**

Evidence in `05-02-PLAN.md`:
- Truth: "`get_fitness_state_service` builds an explicit metric-registry projection; it must not serialize `DailyReport` and delete/filter fields afterward."
- Task 1 adds three layers of enforcement:
  1. Recursive negative key assertions (`recommendation`, `action`, `intensity`, `on_track`, `should`, `ready`, `best_scenario`, `sync_log`, `sql`, `token`, `raw_strava`).
  2. **Recursive string assertions** that `data` contains no Cyrillic text and no prose fragments from `DailyReport.recommendation`, `DailyReport.weekly_plan`, `DailyReport.safety_warnings`, or `progressive_signal.reasons` — this catches the prose-leak vector at any nesting depth.
  3. Source-level AST/text guard rejecting `dc_to_dict(DailyReport)`, `dataclasses.asdict(DailyReport)`, or any serialize-then-filter construction.
- Task 2 mandates an explicit `_project_fitness_state_metrics(report, digest, registry=METRIC_REGISTRY) -> dict[str, MetricValue]` projection function that assigns each allowed metric id one by one, with safety surfaced only as the closed `SAFETY_WARNING_CODES` set (`z5_excessive`, `hike_load_consecutive_high`, `running_volume_jump_high`, `cardiac_drift_severe_yesterday`, `hr_anomaly_burst`, `low_hr_data`, `insufficient_history`) carrying numeric evidence — never the original Russian `safety_warnings` strings.
- Acceptance criteria explicitly state: "`get_fitness_state_service` constructs `data` through an explicit metric-registry projection function, not by serializing/filtering `DailyReport`" and "no nested natural-language recommendation/prose strings and no Cyrillic strings."

Confirmed against `report.py:140-227` (which builds `Recommendation`, `WeeklyPlan`, Russian `safety_warnings`, `progressive_signal.reasons` in Russian): the contract correctly identifies every prose source that needs filtering and the recursive string test will fail loudly if the implementer tries to copy a sub-tree.

# 4. Risk Assessment

Remaining residual risks are MEDIUM/LOW and shouldn't block execution:

- **MEDIUM (operational, 05-05):** Container UID `10001` writes to `/opt/docker/mcp-strava/data` (first-use refresh signaling writes to `refresh_requests`). The Docker plan doesn't explicitly require `chown -R 10001:10001 /opt/docker/mcp-strava/data` during `prepare_runtime`. If the bootstrap is run as a different host UID, the first MCP write will EBUSY/EACCES at runtime and the failure mode is opaque. Worth a `chown`/`chmod` step in `prepare_runtime` or at least a documented bootstrap check in `docs/deployment.md`. Not HIGH because the fail-closed preflight will surface it before silent corruption.

- **MEDIUM (05-04 SDK pin):** `mcp>=1.27.1,<1.28` is a tight pin. The SDK-contract test (`tests/test_mcp_sdk_contract.py`) does fail-fast probe, so version drift will be caught loudly. Acceptable.

- **LOW (05-06 connectivity):** Live smoke from inside `mcp-strava` to `http://mcp-gateway:8811/mcp` relies on both containers sharing the `mcp-backends` network — `/opt/docker/mcp-gateway/compose.yaml` confirms `mcp-gateway` is attached to `mcp-backends`, so this works as designed. No action needed.

- **LOW (05-05 entrypoint):** `os.execvp(sys.executable, [sys.executable, "-m", "mcp_strava.interfaces.mcp_http"])` requires `mcp_http.py` to expose runnable `__main__` behavior. The plan already requires `main()` in `mcp_http.py`; implementer should add the standard `if __name__ == "__main__": raise SystemExit(main())` block. Implementation detail, not planning gap.

# 5. CYCLE_SUMMARY: current_high=0

---

## OpenCode Review

# Cross-AI Plan Review — Phase 5 (after convergence replan f5ca0f4)

## 1. Summary

Both previous HIGH concerns are **resolved** in the current plans. The live gateway mutation now has an unambiguous operator-confirm boundary (dry-run default, `--confirm-live-gateway` flag, explicit `operator_confirm_required: true` metadata, documented rollback-restart-failure contingency with distinct exit code). The `get_fitness_state` service requires an explicit `_project_fitness_state_metrics()` function that extracts registry ids one-by-one, with source-level guards, recursive key/string rejection, and a documented prohibition on `dc_to_dict(DailyReport)` or serialize-then-filter. No new HIGH concerns were found.

## 2. Remaining HIGH Concerns

None.

## 3. Previous HIGH Recheck

| # | Prior HIGH Concern | Current Status |
|---|-------------------|----------------|
| 1 | Live gateway mutation must have explicit operator-confirm boundary and rollback restart failure contingency | **Resolved.** 05-06 has `autonomous: false`, `operator_confirm_required: true`. Must-have truth states "actual live writes require explicit operator confirmation." Task 1 tests require `--apply --confirm-live-gateway` gate before `/opt/docker/mcp-gateway/*` mutation. Task 2 implements `confirm_live_gateway: bool` parameter with exit-before-write semantics when false. Task 3 documents "Before any command that writes ..., stop and ask the operator for explicit approval." Rollback-restart-failure contingency: distinct exit code (T-05-20b), redacted backup paths in output, documented manual recovery (verify `docker compose config`, check `ps`/`logs`, restore from timestamped backup or escalate). Three failure-point rollback tests (prevalidation, mid-write crash, smoke failure) plus dedicated rollback-restart-failure test in Task 1 acceptance criteria. |
| 2 | `get_fitness_state` must use explicit metric-registry projection and must not leak coaching/recommendation/prose fields from `DailyReport` or nested structures | **Resolved.** 05-02 must-have truth explicitly states "builds an explicit metric-registry projection; it must not serialize `DailyReport` and delete/filter fields afterward." Task 1 source guard rejects `dc_to_dict(DailyReport)`, `dataclasses.asdict(DailyReport)`, or serialize-then-filter patterns. Recursive key rejection covers `recommendation`, `action`, `intensity`, `on_track`, `should`, `ready`, `best_scenario`, `sync_log`, `sql`, `token`, `raw_strava`. Recursive string rejection covers Cyrillic text and `DailyReport.recommendation`, `WeeklyPlan.plan_days[].activity`, `safety_warnings`, and `progressive_signal.reasons` prose fragments. Task 2 mandates `_project_fitness_state_metrics(report, digest, registry=METRIC_REGISTRY) -> dict[str, MetricValue]` assigning each metric id one-by-one from numeric/model facts, with explicit prohibition on serialize-then-filter. `progressive_signal.reasons` (Russian coaching text) explicitly excluded while `progressive_cc_trends` and `progressive_load_bonus` remain as numeric facts. |

## 4. Risk Assessment

**Overall: LOW.** The residual risks are MEDIUM implementation-level details, not plan-level blockers:

- **MEDIUM — 05-02 test assertion list omits `banister_history`.** The registry (05-01) has `banister_history` exposed in `get_fitness_state`. The Task 2 action says "must include current Banister" facts, which covers it. But the Task 1 test enumeration does not explicitly name `banister_history` among the required keys. The cross-check acceptance criterion ("all returned metric ids exist in `METRIC_REGISTRY`") catches missing keys in the wrong direction (ensures nothing exposed is unregistered) but doesn't catch omitted keys. Likely harmless — the executor has implementation intent — but the test list should be complete.
- **MEDIUM — SDK pin `mcp>=1.27.1,<1.28` is tight** (05-04). A patch release in another minor would require a dependency bump. The SDK contract test is the safety net, but the tight pin will cause friction. Mentioned for context but categorically not HIGH — the contract test catches API drift.
- **MEDIUM — MCP resource for metric catalog not planned.** The context doc says "Metric definitions should be available to agents." The registry produces `metric_catalog_payload()` but no MCP resource or tool exposes it. Agents must discover metric semantics out-of-band. Not a HIGH — MCP-01 does not require it, and it can be added later.

## 5. CYCLE_SUMMARY: current_high=0
