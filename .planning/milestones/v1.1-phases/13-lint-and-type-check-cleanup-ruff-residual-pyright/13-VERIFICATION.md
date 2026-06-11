---
phase: 13-lint-and-type-check-cleanup-ruff-residual-pyright
verified: 2026-05-30T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 13: Lint and Type-Check Cleanup Verification Report

**Phase Goal:** Drive pyright to 0 errors on `src/` and clean up residual ruff/lint debt introduced in Phase 11 side-work, with the 0-error state pinned reproducibly.
**Verified:** 2026-05-30
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `uv run pyright src` reports 0 errors, 0 warnings, 0 informations | VERIFIED | Ran live: `0 errors, 0 warnings, 0 informations` |
| 2 | `uv run ruff check src tests` reports "All checks passed!" | VERIFIED | Ran live: `All checks passed!` |
| 3 | `uv run ruff format --check src tests` reports no reformatting needed | VERIFIED | Ran live: `98 files already formatted` |
| 4 | pyproject.toml `[tool.pyright]` contains `typeCheckingMode = "standard"` (D-05 pin) | VERIFIED | Line 48: `typeCheckingMode = "standard"` — scope unchanged (`include = ["src"]`, `pythonVersion = "3.14"`) |
| 5 | Full test suite exits 0 (328 tests, no failures) | VERIFIED | Ran live: `328 passed in 209.44s` |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mcp_strava/adapters/duckdb/repository.py` | `Row = dict[str, Any]` alias; `_fetchone` → `Row | None`; `_fetchall` → `list[Row]`; `_scalar` → `Any | None` | VERIFIED | Line 25: `Row = dict[str, Any]`; line 248: `-> Row | None`; line 261: `-> list[Row]`; line 272: `-> Any | None` |
| `src/mcp_strava/types.py` | `dc_to_dict` returns `-> Any` | VERIFIED | Line 818: `def dc_to_dict(obj: Any, *, round_floats: bool = False) -> Any:` |
| `pyproject.toml` | `typeCheckingMode = "standard"` in `[tool.pyright]` | VERIFIED | Line 48 confirmed; `include = ["src"]` unchanged |
| `src/mcp_strava/refresh/worker.py` | No `noqa: BLE001` comments | VERIFIED | `grep -n "noqa: BLE001"` returns no matches |
| `src/mcp_strava/refresh/health.py` | No `noqa: BLE001` comments | VERIFIED | Same grep: no matches |
| `src/mcp_strava/interfaces/mcp_http.py` | Public import `from mcp.server.transport_security import TransportSecuritySettings` | VERIFIED | Line 12 confirmed; private `fastmcp.server` path absent |
| `src/mcp_strava/devtools/mcp_client/client.py` | None-filtered set comprehension in `verify_tool_surface` | VERIFIED | Line 253: walrus `(name := tool.get("name")) is not None` pattern present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `repository.py _fetchone/_fetchall/_scalar` | All consumer call sites | `Row = dict[str, Any]` propagates `Any` automatically | VERIFIED | pyright 0 errors confirms propagation resolved all downstream type errors |
| `types.py dc_to_dict` | `aggregate_services.py`, `product_facts.py`, `cli.py` | `-> Any` annotation collapses `reportReturnType` cluster | VERIFIED | pyright 0 errors confirms |
| `mcp_http.py` | `mcp.server.transport_security.TransportSecuritySettings` | Public module path | VERIFIED | Import confirmed at line 12 |
| `[tool.pyright]` | `uv run pyright src` | `typeCheckingMode = "standard"` pin | VERIFIED | Config line 48 + live pyright run confirms |
| Live `noqa` suppressions | `mcp_http.py:26 F401`, `constants.py:118 E402/F401/I001` | Retained, not removed | VERIFIED | Both lines confirmed present and untouched |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| pyright 0 errors | `uv run pyright src` | `0 errors, 0 warnings, 0 informations` | PASS |
| ruff lint clean | `uv run ruff check src tests` | `All checks passed!` | PASS |
| ruff format clean | `uv run ruff format --check src tests` | `98 files already formatted` | PASS |
| 328 tests pass | `uv run pytest tests/ -q` | `328 passed in 209.44s` | PASS |
| typeCheckingMode pinned | `grep typeCheckingMode pyproject.toml` | Line 48: `typeCheckingMode = "standard"` | PASS |
| No BLE001 noqa | `rg 'noqa: BLE001' src/` | No matches | PASS |
| Public mcp import | `grep 'mcp.server.transport_security' mcp_http.py` | Line 12 confirmed | PASS |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/mcp_strava/application/metric_services.py` | 668, 673, 674 | `# type: ignore[arg-type]` | INFO | Narrowly scoped to `_distribution_delta` where runtime `_is_number()` guard narrows type but pyright cannot track through the helper's untyped signature. This is a well-known pyright limitation, not a blanket escape. 3 suppressions total in all of `src/`. No debt markers (TBD/FIXME/XXX) found anywhere in `src/`. |

**Debt marker scan:** 0 TBD/FIXME/XXX markers in `src/`. Clean.

### Commit Verification

All 5 commits documented in SUMMARYs confirmed present in git history:

| Commit | Plan | Description |
|--------|------|-------------|
| `10546e3` | 13-01 T1 | Widen DuckDB fetch boundary to `Row = dict[str, Any]` (D-01) |
| `b13c439` | 13-01 T2 | Annotate `dc_to_dict` return type `-> Any` (D-03) |
| `c5fde89` | 13-02 | Sweep pyright residual to 0 errors (D-02/D-04 + dict[str,Any] widening) |
| `c837a0f` | 13-03 T1 | Pin `typeCheckingMode = standard` in `[tool.pyright]` (D-05) |
| `51a58d0` | 13-03 T2 | Remove vestigial `noqa: BLE001` comments (D-07) |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| Code quality / tooling hygiene | ruff + pyright introduced in Phase 11 side-work; clear all errors, pin reproducible state | SATISFIED | pyright: 0 errors; ruff: clean; typeCheckingMode pinned; 328 tests green |

### Human Verification Required

None. All phase deliverables are machine-verifiable and were verified live.

### Notes on Scope Deviation (Plan 02)

Plan 02 listed 4 `files_modified` in frontmatter; the actual sweep touched 16 files. This deviation is within the plan's explicit authorized scope: the plan itself states "extending the file set at execution time is parallel-safe" and authorizes D-04.4 fixes across any files showing residual errors. The expanded scope (widening `dict[str, object]` → `dict[str, Any]` throughout the application layer) is consistent with the D-01 boundary decision and does not introduce new runtime behavior — it is annotation-only. No behavioral risk.

The 3 `type: ignore[arg-type]` suppressions in `metric_services.py` were introduced in Plan 02's sweep. These are narrowly targeted (`[arg-type]` only), located inside a `_is_number()`-guarded conditional, and represent a genuine pyright limitation (helper function narrowing is not tracked). They do not hide logic errors and are the minimum suppression needed after explicit `dict[str, Any]` annotation was already applied to the surrounding variables.

---

_Verified: 2026-05-30_
_Verifier: Claude (gsd-verifier)_
