---
phase: 1
cycle: 1
reviewers: [claude, opencode]
reviewed_at: 2026-05-20T19:45:32+05:00
plans_reviewed:
  - .planning/phases/01-package-foundation-settings/01-01-PLAN.md
  - .planning/phases/01-package-foundation-settings/01-02-PLAN.md
  - .planning/phases/01-package-foundation-settings/01-03-PLAN.md
---

# Cross-AI Plan Review - Phase 1

## Cycle Summary

CYCLE_SUMMARY: current_high=1

## Current HIGH Concerns

- Non-pytest verification commands in Plan 01-01 require the package to be importable, but the plan does not specify an editable install or `PYTHONPATH=src`; `python3 -c "from mcp_strava..."` and `python3 -m mcp_strava` are likely to fail as written.

## Consensus Summary

Both reviewers agree that Phase 1 is well-scoped and coherent: package layout first, typed settings second, pytest workflow third. Both reviews found the data-safety boundary intact: no sync/backfill/API/migration work is planned, and `data/strava.db`, `.env`, and `.planning/config.json` stay outside the modified-file and commit scope.

### Agreed Strengths

- The wave order is correct: package move before settings wiring, settings before pytest migration.
- The plans avoid premature repository, adapter, MCP, Docker, or training-model redesign.
- The acceptance criteria repeatedly check that `data/strava.db` still exists and that ignored local config/secrets are not committed.
- The move from custom smoke runner to pytest is aligned with the Phase 1 requirements.

### Agreed Concerns

- `db.py` path resolution and settings caching need sharper execution instructions so tests do not accidentally bind to stale paths or the wrong root.
- The package importability story should be explicit for commands run outside pytest.
- `.env` compatibility parsing and precedence should be specified clearly enough to avoid accidental token/config behavior changes.
- The cleanup contract for old `scripts/` paths should be unambiguous and verified.

### Divergent Views

- Claude treats the missing editable-install or `PYTHONPATH=src` step for non-pytest verification commands as a HIGH execution blocker. OpenCode does not raise a HIGH and considers the phase approved with recommendations. For convergence counting, this cycle keeps Claude's HIGH as unresolved because no plan change or verification has closed it.
- OpenCode emphasizes `.env` parser edge cases more strongly than Claude; Claude mentions parser compatibility but rates it LOW.

---

## Claude Review

# Cross-AI Plan Review: Phase 1 — Package Foundation & Settings

## Summary

The three plans form a coherent, conservative Phase 1: mechanical package move (01-01), TDD settings boundary (01-02), and pytest migration (01-03). Scope is correctly held at packaging/settings — no sync, OAuth, migration, or MCP work bleeds in. The dependency chain (Wave 1 → 2 → 3) is sound and matches the research. However, there is one **HIGH-severity blocker** affecting acceptance-criteria execution (no editable install step is provided, so `python -m mcp_strava` and direct `python -c "from mcp_strava..."` verifies will fail), plus several MEDIUM issues around `db.py` global-path refactor, `get_settings()` caching in tests, and pytest fixture usage. With those fixed, the plans should deliver FOUND-01/02/03.

---

## Plan 01-01: Package Manifest & Source Layout

### Strengths
- Mechanical move strategy honors D-01/D-02 — no premature core/repo/adapter decomposition.
- Explicitly forbids `[project.scripts]` per D-07, with a checkable acceptance criterion.
- `pythonpath = ["src"]` in pytest config is a nice touch — lets `pytest` work without install.
- Threat model correctly isolates `data/strava.db`, `.env`, `.planning/config.json` as untouchable.

### Concerns
- **HIGH — Verifies require package to be importable but no install step exists.** Task 2 verify (`python3 -c "from mcp_strava.training import ewma..."`) and Task 3 verify (`python3 -m mcp_strava`) need either `pip install -e .` or `PYTHONPATH=src` to succeed. `pythonpath = ["src"]` in `pyproject.toml` only applies under pytest. As written, both tasks will fail acceptance. Add an explicit `pip install -e .` step (or equivalent venv setup) before the verify commands, or prefix verifies with `PYTHONPATH=src`.
- **MEDIUM — `pyproject.toml` shape underspecified.** The plan mentions both `package-dir = {"" = "src"}` and `where = ["src"]`. With setuptools you typically pick one (`[tool.setuptools.packages.find] where = ["src"]` + `[tool.setuptools] package-dir = {"" = "src"}`). The acceptance criteria only check string presence; an inconsistent config could still pass while not actually discovering the package. Specify the exact section layout.
- **MEDIUM — `scripts/strava_lib/constants.py` has an internal `from strava_lib.sports import …` (line 113).** The post-move `rg "strava_lib" src/mcp_strava` check catches this, but the task description should call it out explicitly so the executor doesn't miss it.
- **LOW — `src/mcp_strava/__init__.py` listed in `files_modified` but no task explicitly creates it.** It's implicit in "move modules", but worth a one-line task instruction so it isn't accidentally omitted.
- **LOW — Task 3 verify uses `test "$?" -eq 1; rg …` chain.** If the first command exits 0 (unexpectedly), the second still runs and may give a misleading PASS. Use `&&` or check exit code via Python.
- **LOW — `scripts/cli.py` removal language is soft** ("Remove … as a primary executable after the package entrypoint works"). Files_modified lists `scripts/cli.py` and `scripts/strava_lib/`. Clarify whether they are deleted outright (per D-01) or kept as a shim.

### Suggestions
- Add Task 0 (or inline in Task 1): `pip install -e .` after `pyproject.toml` is created, so subsequent verifies work.
- Pin the exact `pyproject.toml` template (build-system, project metadata, `[tool.setuptools.packages.find]`, `[tool.pytest.ini_options]`).
- Add an acceptance check that `python3 -c "import mcp_strava; print(mcp_strava.__file__)"` resolves to the `src/` tree, not a stale install.

---

## Plan 01-02: Typed Settings Boundary

### Strengths
- True RED → GREEN → REFACTOR ordering with explicit acceptance gates.
- Validation, env-file compat, and explicit-env override precedence are all named in behavior.
- Refactor task includes a guard against reading `.planning/config.json` and against printing tokens in tests — good belt-and-suspenders.
- `tests/test_settings.py` is isolated from the smoke suite, so failures localize cleanly.

### Concerns
- **MEDIUM — `db.py` refactor scope is underspecified.** The original `db.py` has module-level `BASE_DIR`, `DB_PATH`, `ENV_PATH` constants used directly by `DbConn.__enter__`, `load_env`, `save_env`, `refresh_token`. The plan says "DB_PATH and ENV_PATH are resolved from `get_settings()`" but doesn't say whether they remain module-level (resolved at import) or become lazy (resolved per call). Module-level resolution makes test isolation hard (the cache is locked at import time); lazy resolution is cleaner but requires touching every reference site. Pick one and state it.
- **MEDIUM — `get_settings()` caching collides with tests.** If `get_settings()` is `@functools.cache`-style, tests that change `MCP_STRAVA_DB_PATH` after first call won't see the override. Either:
  - Tests should always call `load_settings(...)` (non-cached) directly, OR
  - The cache must expose a `clear()` hook and the `db.py` refactor must not depend on cache contents.
  Make this explicit.
- **MEDIUM — Default project root inference is brittle.** Inferring repo root from `__file__` of the package works in `src/mcp_strava/...` but breaks once `mcp-strava` is installed into a site-packages venv (the package will be far from the data directory). For Phase 1 this is OK, but worth documenting that the default is `src`-layout-aware and that future Docker work (Phase 5) will need an explicit `MCP_STRAVA_DB_PATH`.
- **MEDIUM — Default freshness values (12h warn / 24h max) aren't traceable to context.** Neither `CONTEXT.md` nor `RESEARCH.md` specify defaults. They're reasonable, but the planner is making a policy choice. Either cite the source or flag as "Phase 4 may revise."
- **LOW — `.env` parsing assumptions.** The existing `load_env` does naive `split('=', 1)`. The new parser should match that behavior (no quote stripping, no escape handling) to avoid silently changing how `STRAVA_*` tokens are read. Add an acceptance criterion: `load_settings` env-file parsing must be byte-equivalent to existing `load_env` for the keys it doesn't own.
- **LOW — Test names don't cover `.env` precedence vs `environ`.** Add `test_explicit_environ_wins_over_env_file` to lock the precedence rule named in the feature behavior.

### Suggestions
- Explicitly state lazy vs. eager path resolution in `db.py`.
- Add a `get_settings.cache_clear()` or `_reset_settings_for_tests()` helper and use it in test setup.
- Add the explicit precedence test.

---

## Plan 01-03: Pytest Smoke Workflow

### Strengths
- Preserves the existing smoke surface (imports, daily report, pure helpers, sports registry) — minimal regression risk.
- Removes `scripts/run_tests.py` cleanly without leaving a dead shim.
- Acceptance checks include both positive (`just test` exits 0) and negative (`rg "strava_lib|scripts/run_tests.py"` finds no primary references).

### Concerns
- **MEDIUM — `tmp_path` fixture incompatibility.** The existing `test_smoke.py` is plain functions called by name (no fixtures). Task 1 says to add an assertion that uses `tmp_path`. To use the fixture, the test function must take `tmp_path` as a parameter — pytest will inject it, but the surrounding module style is non-fixture. This works fine under pytest discovery, just call out that the new assertion lives in a new test function (e.g. `test_settings_loads_under_pytest(tmp_path)`).
- **MEDIUM — `test_daily_report` depends on a populated `data/strava.db`.** It will pass on the developer's machine but fail in any clean checkout. Phase 1 isn't the time to fix this, but the plan should acknowledge it (existing baseline behavior) and not let pytest fail the workflow on a missing DB. Consider an `pytest.importorskip`/`skipif` guard, OR explicitly note this is pre-existing and won't be hardened until Phase 2 (SAFE-04).
- **MEDIUM — `just test` install dependency.** `just test` → `python3 -m pytest`. Pytest will pick up `pythonpath = ["src"]`, so this works without `pip install -e .`. Good. But the plan should state this explicitly so the executor doesn't run `pip install` as a side step and contaminate the local environment.
- **LOW — `alias tests := test` / `alias smoke := test` line ordering.** The current `Justfile` defines aliases after the recipe; the plan acceptance only checks presence, not position. Fine as-is, but worth a one-liner that the recipe form matches the existing style.
- **LOW — Test for `mcp_strava.types` shadow.** The risk table in research flags the `types.py` shadowing problem. Add an explicit smoke assertion: `import mcp_strava.types; assert mcp_strava.types.__file__.endswith("src/mcp_strava/types.py")`. Cheap insurance.

### Suggestions
- Either skip or fixture-mock the daily-report smoke when `data/strava.db` is absent, or document the dependency.
- Add the `mcp_strava.types` non-shadow assertion.
- State that `just test` works without prior `pip install -e .` thanks to `pythonpath`.

---

## Data Safety Audit

All three plans correctly leave `data/strava.db`, `.env`, and `.planning/config.json` outside `files_modified`. Acceptance criteria include `test -f data/strava.db` checks in 01-01 Task 3, 01-02 Task 2, and 01-03 Task 3 — good redundancy. No plan invokes sync, backfill, OAuth refresh, or schema migration. **No data-safety blockers found.**

One latent concern: if `db.py` `DB_PATH` resolution moves to a lazy `get_settings()` call and a test invokes `DbConn()` with an unset `MCP_STRAVA_DB_PATH`, the default project_root inference could point to a temp directory (in fixtures) and `DbConn.__enter__` would create an empty `data/strava.db` there via `os.makedirs`. That's not corruption of the real mirror, but it's a Phase 2 SAFE-04 precursor — worth flagging so it doesn't get baked into Phase 1.

---

## Cross-Plan Consistency

| Check | Status |
|-------|--------|
| Wave ordering (01-01 → 01-02 → 01-03) | ✅ Correct |
| Requirements coverage (FOUND-01/02/03) | ✅ Mapped |
| D-01 through D-09 reflected | ✅ All present |
| `scripts/` removed without compat obligation (per spec) | ✅ Consistent with CONTEXT.md |
| pytest as primary runner | ✅ Consistent |
| Module entrypoint only (no console script) | ✅ Consistent |
| Install/PYTHONPATH story | ⚠️ **Inconsistent — `pytest` uses `pythonpath`, but `python -c`/`python -m` verifies don't** |

---

## Risk Assessment: **MEDIUM**

**Justification:** Plans are well-scoped, data-safe, and traceable to requirements. The HIGH-severity issue (no editable install for verify commands) is a fixable execution blocker, not a design flaw. Once the install step is added and the three MEDIUM items in 01-02 (`db.py` refactor scope, cache clearing, project-root inference) are clarified, this is a low-risk phase. The biggest residual unknowns are around how cleanly `db.py`'s module-level path globals retrofit to a `get_settings()` boundary without rippling into Phase 2 work.

### Recommended fixes before execution
1. **(HIGH)** Add `pip install -e .` (or equivalent) to 01-01 after `pyproject.toml` is written, OR prefix non-pytest verifies with `PYTHONPATH=src`.
2. **(MEDIUM)** In 01-02, specify lazy vs eager path resolution in `db.py` and add a settings-cache reset hook.
3. **(MEDIUM)** Pin the exact `pyproject.toml` setuptools section layout.
4. **(MEDIUM)** Decide handling of `test_daily_report` when `data/strava.db` is absent (skip vs. document).
5. **(LOW)** Add the `mcp_strava.types` non-shadow assertion and the `environ`-wins-over-`env_file` precedence test.

---

## OpenCode Review

# Cross-AI Plan Review: Phase 1 — Package Foundation & Settings

---

## Overall Assessment

The three plans form a well-sequenced foundation for Phase 1. The mechanical code move (01-01) followed by typed settings (01-02) and test workflow migration (01-03) is a sound dependency chain. Each plan has clear acceptance criteria, threat modeling, and verification gates. The main risks are path-resolution transience between waves, `get_settings()` cache immutability for tests, and the `.env` file parser's edge-case handling.

---

## Plan 01-01: Package Manifest & Source Layout

### Summary

A straightforward mechanical move of the runtime from `scripts/strava_lib/` into `src/mcp_strava/` with `pyproject.toml` creation and `python -m mcp_strava` entrypoint. Risks are low if path-resolution logic in `db.py` survives the directory depth change, but the plan doesn't explicitly verify this.

### Strengths

- Clean, atomic tasks with no scope creep into repository/adapter boundaries
- Good data-safety discipline: `test -f data/strava.db` in verification gates
- Properly defers `[project.scripts]` per decision D-07
- Import search (`rg "strava_lib"`) prevents stale references

### Concerns

- **MEDIUM** — `db.py` path resolution uses `__file__`-relative navigation to reach the repo root. The move from `scripts/strava_lib/` to `src/mcp_strava/` preserves the depth (both are 2 levels from repo root), so it *should* survive, but the plan doesn't verify this. If the code navigates differently (e.g., `../..` vs `../../..`), `data/strava.db` resolution breaks silently in Wave 1. Plan 01-02 will fix this with explicit settings-based paths, but between Wave 1 completion and Wave 2 execution, DB-dependent code could point to a wrong or missing file.
- **MEDIUM** — `constants.py` currently has a post-import round-trip pattern: it imports `sports.py` after defining `Config`, then attaches SQL fragments to `Config.SQL`. The plan makes no mention of verifying this circular-friendly pattern survives the move or whether the module-level SQL attachment timing is affected by the new import hierarchy.
- **LOW** — Task 2 says "Remove `scripts/strava_lib/` only after the package imports are updated" but no explicit verification or task confirms removal actually happens. Plan 01-03 also removes `scripts/run_tests.py` but not `scripts/strava_lib/`. Stale old modules could shadow the new package if `sys.path` isn't clean.
- **LOW** — The verification chain `python3 -c "from mcp_strava.training import ewma; ..."` tests a single module. A broader import check (`from mcp_strava import report, db, sync, metrics`) would catch import-chain breaks (e.g., `training.py` → `db.py` → `constants.py` → `sports.py`).

### Suggestions

- Add a verification step that exercises a multi-module import chain: `from mcp_strava.db import DbConn; from mcp_strava.report import daily_report` to catch transitive import failures.
- Add a note confirming the directory-depth equivalence (`scripts/strava_lib/` → repo root == `src/mcp_strava/` → repo root) or document the `BASE_DIR` resolution logic.
- Specify in Task 2 or 3 whether `scripts/strava_lib/` should be deleted, renamed, or left as non-primary. If left, add a comment marker to prevent accidental re-use.
- Verify `rg "from strava_lib|import strava_lib" src/mcp_strava` returns no matches (the current verification only checks `rg "strava_lib"` which could match comments/docs).

### Risk Assessment: LOW

The plan is mechanically safe. The main risk (path resolution) is partially self-correcting (depth equivalence) and fully resolved in Plan 01-02. Transient breakage between waves is tolerable since no DB-mutating commands are exercised.

---

## Plan 01-02: Typed Settings Boundary

### Summary

A TDD plan that introduces a typed `Settings` dataclass with environment variable, `.env` file, and default fallback sources. Route `db.py` path resolution through `get_settings()`. Well-structured RED→GREEN→REFACTOR flow. Main issues are test isolation for the cached settings singleton and edge cases in the `.env` parser.

### Strengths

- Proper TDD sequence with explicit RED and GREEN gates
- Clear `MCP_STRAVA_*` naming convention with all seven keys listed
- Threat model correctly identifies `.planning/config.json` must not be read
- Non-invasive to token persistence behavior (Plan 01-02 defers that)
- Verification includes `test -f data/strava.db` after changes

### Concerns

- **MEDIUM** — `get_settings()` is described as "cached" but the plan provides no cache-reset mechanism. Multiple test functions call `load_settings(environ=...)` independently: if `get_settings()` is a module-level singleton that memoizes on first call, test order and cross-test pollution become unpredictable. The plan must either: (a) make `load_settings()` stateless and have tests use it directly without `get_settings()`, or (b) provide `reset_settings()` / `clear_settings_cache()` for test isolation, or (c) use `monkeypatch` in tests.
- **MEDIUM** — The `.env` file parser spec says "non-comment `KEY=VALUE` lines" but doesn't address: quoted values (`KEY="val"`), values containing `=` (`KEY=val=ue`), trailing whitespace, empty values (`KEY=`), or `export KEY=VALUE` syntax. Real `.env` files frequently contain these patterns. Undefined behavior here could cause silent configuration failures.
- **MEDIUM** — "Default project root as the repo root inferred from the package location" is ambiguous. If inferred from `Path(__file__).parent.parent.parent` in `settings.py`, it works. If inferred from `os.getcwd()` or any runtime-relative path, it breaks when `python -m mcp_strava` is run from a different directory. The plan should specify the inference method.
- **LOW** — The GREEN task says "Export `Settings`, `HttpSettings`, `FreshnessSettings`, `load_settings`, and `get_settings` from `src/mcp_strava/__init__.py` only if doing so does not create import cycles." This conditional export is a design smell. Either the export is safe (hard-code it) or it's not (don't do it). Conditional behavior in a plan task creates ambiguity about what the executor should actually produce.
- **LOW** — `Settings.database_path` and `token_path` default to relative paths (`data/strava.db`, `.env`) resolved against `project_root`. The plan doesn't specify whether these are validated to exist at construction time. A missing `.env` is normal; a missing `data/strava.db` should not fail Phase 1 settings creation (that's a Phase 2 concern per SAFE-04), but the behavior should be explicit.

### Suggestions

- Add a `reset_settings_cache()` function or document that tests should use `load_settings()` directly without the cached `get_settings()` wrapper.
- Specify `.env` parsing rules: split on first `=`, strip quotes, skip lines starting with `#` or `export `, handle empty values, and treat parse failures as `ValueError` or silent skips (choose one and test it).
- Specify the project-root inference algorithm: `Path(__file__).resolve().parent.parent` (from `src/mcp_strava/settings.py`), not `Path.cwd()`.
- Drop the conditional export clause — either hard-export from `__init__.py` or don't export at all. Prefer direct `from mcp_strava.settings import load_settings` in consuming code.
- Document that `database_path` validation (existence checks) is deferred to Phase 2.

### Risk Assessment: MEDIUM

The TDD structure is sound, but the `get_settings()` cache without reset mechanism is a material test pollution risk that could cause non-deterministic test failures. The `.env` parser ambiguity is a correctness concern for real-world usage.

---

## Plan 01-03: Pytest Smoke Workflow

### Summary

Converts smoke tests to pytest discovery with `mcp_strava.*` imports, routes `just test` to `python3 -m pytest`, and retires `scripts/run_tests.py`. Clean, minimal plan with good verification gates. Main concern is a subtle path-dependency on import order in the daily report smoke test.

### Strengths

- Simple three-task sequence with clear success criteria
- Explicit acceptance criteria that existing 11 test functions survive the migration
- Preserves `alias tests` and `alias smoke` Justfile targets
- Adds a lightweight settings integration smoke check without over-testing
- Verification checks for stale references to old runner path

### Concerns

- **LOW** — The daily report smoke test in `test_smoke.py` currently reads `data/strava.db`. After Plan 01-02 wires settings, this depends on `get_settings()` correctly resolving the database path. If the cached-settings concern from Plan 01-02 isn't addressed, the smoke test will see whatever the first caller's path was. This is fine in practice (tests run from repo root with standard layout) but should be explicit.
- **LOW** — The plan adds a settings assertion to `test_smoke.py` ("one lightweight assertion that `load_settings(environ={}, project_root=tmp_path)` returns a settings object..."). This uses `tmp_path` (a pytest fixture) but `test_smoke.py` currently uses no fixtures. The plan should note that the test signature must change to `def test_...(tmp_path)` or use `tempfile.mkdtemp()`.
- **LOW** — Task 3 says "Delete `scripts/run_tests.py` if no remaining primary workflow references it." But what about the `scripts/` directory itself? If only `run_tests.py` remains after Plan 01's cleanup, deleting it leaves an empty `scripts/` directory. The plan should either remove it or add a `.gitkeep`/note.
- **LOW** — Verification says `rg "scripts/run_tests.py" ...` should return no matches "except historical text in planning artifacts." The `rg` command can't distinguish planning artifacts from source. Use `rg --glob='!**/.planning/**'` or accept that planning references are harmless.

### Suggestions

- Note that `tmp_path` requires pytest fixture support — either convert the test to use it or use `tempfile.TemporaryDirectory` for consistency with the existing no-fixture style.
- After deleting `scripts/run_tests.py`, remove the `scripts/` directory if empty, or add a comment explaining why it remains.
- Use `rg --glob='!.planning/**'` for the stale-reference check to avoid false matches in planning docs.

### Risk Assessment: LOW

The plan is well-contained. The only execution risk is the `tmp_path` fixture assumption and stale empty directory, both trivial to resolve during execution.

---

## Cross-Plan Concerns

| # | Concern | Severity | Affected Plans | Mitigation |
|---|---------|----------|----------------|------------|
| 1 | `get_settings()` cache not resettable for tests | MEDIUM | 01-02, 01-03 | Add `reset_settings_cache()` or test `load_settings()` directly |
| 2 | Path resolution after module move unverified | LOW | 01-01, 01-02 | Plan 01-02 explicitly wires settings; transient gap between waves is harmless |
| 3 | Old `scripts/strava_lib/` cleanup responsibility split | LOW | 01-01, 01-03 | 01-01 says remove it; 01-03 removes `run_tests.py`; neither verifies `scripts/` is clean |
| 4 | `constants.py` post-import SQL fragment attachment | LOW | 01-01 | Add an import check that exercises `Config.SQL` after package move |
| 5 | `.gitignore` update for `src/mcp_strava/` `.pyc`/`__pycache__` | LOW | 01-01 | Verify existing patterns cover `src/` or add them |

---

## Data Safety Audit

| Asset | Plan 01-01 | Plan 01-02 | Plan 01-03 | Status |
|-------|-----------|-----------|-----------|--------|
| `data/strava.db` | Not modified, verified in each task | Not modified, verified | Not modified, verified | PROTECTED |
| `.env` | Not modified or committed | Read for path values only | Not read in test migration | PROTECTED |
| `.planning/config.json` | Not referenced | REFACTOR task explicitly verifies exclusion | Not referenced | PROTECTED |
| Secret values in test output | N/A | REFACTOR task verifies no token keys in tests | Not referenced | PROTECTED |

All plans respect the data preservation constraint.

---

## Verdict

**Plans are APPROVED with recommendations.** The sequence is coherent, the scope boundaries are well-enforced, and data safety is maintained throughout. The two MEDIUM concerns (settings cache test isolation and `.env` parser edge cases) should be addressed in Plan 01-02 before or during execution, but neither is blocking. The LOW concerns can be handled inline by the executor.

