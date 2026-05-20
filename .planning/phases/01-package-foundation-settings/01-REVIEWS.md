---
phase: 1
cycle: 2
reviewers: [claude, opencode]
reviewed_at: 2026-05-20T20:07:56+05:00
plans_reviewed:
  - .planning/phases/01-package-foundation-settings/01-01-PLAN.md
  - .planning/phases/01-package-foundation-settings/01-02-PLAN.md
  - .planning/phases/01-package-foundation-settings/01-03-PLAN.md
reviewer_status:
  claude: failed
  opencode: completed
---

# Cross-AI Plan Review - Phase 1

## Cycle Summary

CYCLE_SUMMARY: current_high=0

## Current HIGH Concerns

None.

## Reviewer Status

- Claude: invoked as requested, but did not produce a review. The normal non-interactive invocation hung with zero stdout/stderr and was terminated; `claude --bare -p` returned `Not logged in`. No Claude findings are counted for this cycle.
- OpenCode: completed successfully through `/home/j2h4u/.opencode/bin/opencode` using the cycle-2 prompt.

## Consensus Summary

Because Claude did not return a substantive review, there is no two-reviewer consensus in this cycle. The successful OpenCode review found that the previous HIGH importability concern is fully resolved by the updated Plan 01-01: non-pytest commands now use `PYTHONPATH=src`, pytest has `pythonpath = ["src"]`, and an editable-install smoke verifies package execution without `PYTHONPATH`.

### Agreed Strengths

- OpenCode found the Phase 1 wave order correct: package layout first, settings second, pytest workflow third.
- OpenCode found the Strava data safety boundary preserved: no sync, backfill, token refresh, migration, or database reset is planned.
- OpenCode found the prior importability HIGH closed in the current plan set.
- Local synthesis confirms the current plans explicitly keep `.planning/config.json`, `.env`, and `data/strava.db` outside the commit and runtime-change scope.

### Agreed Concerns

- No current HIGH concerns remain from the completed review.
- The remaining OpenCode concerns are MEDIUM or LOW and do not block Phase 1 execution: default-root brittleness, `.env` parsing edge cases, `/tmp` editable-install cleanup, minor test-plan precision, and a cosmetic checklist path.

### Divergent Views

- No substantive divergence is available because only OpenCode completed. Claude's cycle-1 HIGH is not carried forward because the updated cycle-2 plans include explicit `PYTHONPATH=src` and editable-install verification.

---

## Claude Review

Claude was selected and invoked for this cycle, preserving the requested reviewer set.

Result: failed to produce review output.

Evidence:

- `cat /tmp/gsd-review-prompt-1.md | claude -p -` hung with zero stdout/stderr and was terminated.
- `timeout 60 claude -p 'Reply with exactly OK.'` also timed out with no stdout/stderr.
- `claude --bare -p 'Reply OK.'` returned `Not logged in`.

No current HIGH concerns are counted from Claude because no cycle-2 review was produced.

---

## OpenCode Review

# Cross-AI Plan Review - Phase 1, Cycle 2

## Summary

Cycle 2 plans are materially stronger than cycle 1. Plan 01-01 now weaves `PYTHONPATH=src` prefixes, `[tool.pytest.ini_options] pythonpath = ["src"]`, and a sandboxed editable-install smoke into every verification and success-criteria checkpoint. The previous cycle's sole HIGH, package importability for non-pytest commands, is fully resolved. Plan 01-02 delivers a clean TDD settings boundary with well-specified precedence, cache isolation, and env-file parsing. Plan 01-03 migrates the smoke suite to pytest and retires the custom runner with sensible skip behavior when the local database is absent. The wave dependency order (01-01 -> 01-02 -> 01-03) is correct, data-safety boundaries hold across all three plans, and no Phase 2+ concerns leak into Phase 1 scope.

## Strengths

- **Importability gap fully closed**: Plan 01-01 resolves the previous HIGH through three complementary mechanisms: pytest `pythonpath = ["src"]`, explicit `PYTHONPATH=src` on every raw-Python verification command, and a routed `/tmp` editable-install smoke. Threat T05 and the success criteria both encode the resolution explicitly.
- **Correct wave ordering**: Package layout (01-01) before settings wiring (01-02) before pytest migration (01-03). 01-03 correctly depends on both prior plans.
- **Settings boundary is well-specified**: 01-02 defines exact precedence (explicit environ > env-file > defaults), exact parsing semantics (first-`=` split, skip blank/comment lines), and field-level validation with clear error messages. `reset_settings_cache()` enables isolated testing.
- **Data safety preserved throughout**: All three plans repeat `test -f data/strava.db` checks. No sync, backfill, token refresh, schema migration, or raw Strava calls are touched. 01-03 explicitly skips the report smoke when `data/strava.db` is absent via `pytest.skip` rather than creating a replacement, which defers fail-closed behavior correctly to Phase 2 (SAFE-04).
- **Clean runner migration**: 01-03 retires `scripts/run_tests.py`, routes `just test` through `python3 -m pytest`, and preserves `alias tests := test` / `alias smoke := test`. The `types.py` import-shadow assertion proactively prevents the known stdlib-naming pitfall.
- **Scope discipline**: No `[project.scripts]` console executable (D-07 deferred), no token persistence redesign, no MCP/Docker/Alembic imports. Freshness thresholds are marked as bootstrap defaults only.

## Concerns

- **MEDIUM - `parents[2]` default root is brittle**: Plan 01-02 derives the default project root via `Path(__file__).resolve().parents[2]`, which silently breaks if `settings.py` is later nested deeper, for example `src/mcp_strava/config/settings.py`. The plan acknowledges this is a Phase 1 bootstrap default, but a developer moving the file will get a silently wrong database path rather than a clear misconfiguration error. Consider asserting that `(root / "pyproject.toml").exists()` and raising an actionable error on failure.
- **MEDIUM - `.env` parser edge cases**: The feature behavior specifies first-`=` splitting without quote stripping, escape handling, or trailing-whitespace trimming. A line like `MCP_STRAVA_DB_PATH="/path/with spaces.db"` will include literal quotes in the path. `\r\n` line endings from cross-platform editing may embed `\r` in values. The plan documents this as matching existing `load_env()` behavior, which is fair for Phase 1, but a trailing-whitespace test or `\r\n` test would surface the gap before adapter phases depend on these paths.
- **LOW - 01-01 editable-install venv accumulates**: Task 3 creates `/tmp/mcp-strava-editable-smoke` for verification but never removes it. Harmless but clutters `/tmp` across repeated executions.
- **LOW - 01-03 smoke function names are asserted from plan text only**: Task 1 instructs preserving test function names for "forward simulation, EWMA, form zone, trend, one-day simulation, decoupling, median/pct_change, and sports registry" without seeing the current `tests/test_smoke.py`. The executor will catch mismatches but it is a minor plan-precision gap.
- **LOW - 01-02 verification one-liner uses `/.tmp`**: The checklist example `project_root='/.tmp'` is a non-standard path. If `load_settings` tries to resolve `project_root / "data" / "strava.db"`, this yields `/.tmp/data/strava.db`, which is harmless for the asserted check but not a realistic path test. The test suite covers the same behavior correctly, so this is cosmetic.

## Suggestions

1. Add a `pyproject.toml` existence guard after `parents[2]` in 01-02's GREEN task, so the implementation fails fast with an actionable message instead of silently computing a wrong root.
2. Add a trailing-whitespace and `\r\n` line-ending test to 01-02's RED phase to either prove the parser handles these cases or surface the gap with an `.rstrip()` fix.
3. Note in 01-01 Task 3 that the venv directory is sacrificial and can be removed after verification.
4. Replace `project_root='/.tmp'` in 01-02's verification checklist with a Path that actually exists in the development context.

## Risk Assessment

**Overall: LOW**

The previous cycle's sole HIGH concern is fully resolved. All three plans respect Phase 1 boundaries, preserve data safety, and follow correct wave dependencies. The remaining MEDIUM concerns are about path-resolution fragility and parser edge cases that are explicitly scoped as Phase 1 bootstrap behavior; both can be tightened incrementally without blocking execution. No new HIGH concern is introduced.

## Current HIGH Concerns

None.
