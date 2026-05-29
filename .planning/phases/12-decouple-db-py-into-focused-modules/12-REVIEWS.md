---
phase: 12
reviewers: [codex, opencode]
reviewed_at: 2026-05-30T05:25:00+06:00
plans_reviewed: [12-01-PLAN.md, 12-02-PLAN.md, 12-03-PLAN.md, 12-04-PLAN.md, 12-05-PLAN.md]
cycle: convergence-3
---

# Cross-AI Plan Review — Phase 12 (Convergence Re-Review, cycle 3)

> Prior cycle (cycle 2) raised one divergent HIGH (Codex: wave placement of the
> application/refresh/sync test retargets — 12-03 migrated production code whose
> monkeypatch retargets were deferred to 12-04, so 12-03's own full-suite gate
> would fail mid-migration). The plans were replanned (commit 2e6a5d6) to add a
> dedicated 12-03 Task 3 that retargets those test sites in the same wave, and to
> scope 12-04 to CLI-only retargets. This cycle re-reviews the revised set.
>
> **Both reviewers agree the cycle-2 HIGH is RESOLVED.** Codex surfaces a NEW HIGH:
> 12-04 Task 1's `RealClock|RealSleeper` grep is overbroad and matches the
> still-present `_RealClock`/`_RealSleeper` in `db.py`, so the gate fails
> deterministically before 12-05 deletes db.py. **This claim was verified against
> the repo and is well-founded (see Orchestrator Verification below).** OpenCode
> quotes the same grep approvingly and rates risk LOW — it did not cross-check the
> grep against db.py's contents.

## Codex Review

## Summary

The cycle-2 HIGH issue is resolved: application/refresh/sync test retargets now land in 12-03 with the production moves they exercise. The overall decomposition is sound and aligned with the phase goal. However, there is a new blocking verification issue: 12-04's `RealClock|RealSleeper` grep scans all `src/mcp_strava`, while `db.py` is intentionally still present until 12-05 and still contains `_RealClock`/`_RealSleeper`. As written, 12-04 cannot pass.

## Strengths

- Clean hard-cut sequencing: additive homes, caller migration, CLI migration, then `db.py` deletion.
- Prior HIGH wave-placement concern is fixed by moving `conftest.py`, metric, refresh, application, and sync test retargets into 12-03.
- `test_repository_boundary.py` retarget is now concrete: `StravaClient.api_request` and `.refresh_token`.
- `StravaClient` has an explicit fake-transport injection seam.
- Final `just test` Docker/MCP smoke is appropriate for this repo.

## Concerns

- **HIGH**: 12-04 Task 1 verification will fail. `! rg -q "RealClock|RealSleeper" src/mcp_strava` matches `_RealClock`/`_RealSleeper` in `src/mcp_strava/db.py`, which is not deleted until 12-05. Scope the grep to `cli.py`, `refresh/bootstrap.py`, and `sync.py`, or exclude `db.py`.

- **MEDIUM**: credential accessor behavior is under-tested. 12-02 specifies important behavior, but verification does not directly test missing token file, missing individual keys, comment/whitespace parsing, or secret-safe errors.

- **MEDIUM**: monkeypatching `DuckDBRepository.from_connection` should specify descriptor-safe replacement. Since it is a `@classmethod`, a plain lambda on the class can get an unexpected `cls`; prescribe `staticmethod(lambda conn: FakeRepo())` or `classmethod(lambda cls, conn: FakeRepo())`.

- **LOW**: 12-03 Task 3 still uses `rg ... && exit 1 || echo`, which can mask `rg` errors. Use `! rg -q ...`.

- **LOW**: 12-05 action says `ruff format --check`, but verify omits it. Align the gate with the stated action.

## Suggestions

- Change 12-04 Task 1 grep to:
  `! rg -q "RealClock|RealSleeper" src/mcp_strava/cli.py src/mcp_strava/refresh/bootstrap.py src/mcp_strava/sync.py`

- Add settings tests for `strava_client_credentials()` or equivalent: `load_settings()` succeeds without creds, accessor fails with missing keys + token path, valid token file parses, no secret leaks.

- Strengthen repository boundary with an AST/import guard that `adapters/duckdb/repository.py` does not import `mcp_strava.adapters.strava`, in addition to patching `StravaClient` methods.

## Resolution Of Prior Feedback

| Cycle-2 concern | Status | Justification |
|---|---|---|
| HIGH wave placement of test retargets | **RESOLVED** | 12-03 now owns application/refresh/sync retargets before its full-suite gate. |
| MEDIUM `test_repository_boundary.py` target | **RESOLVED** | 12-04 names `mcp_strava.adapters.strava.client.StravaClient.api_request` and `.refresh_token`. |
| MEDIUM StravaClient construction seam | **RESOLVED** | 12-02 specifies `transport=None, *, settings=None, clock=None, sleeper=None`. |
| MEDIUM fail-closed verification | **PARTIALLY RESOLVED** | Most gates improved, but 12-03 still has a non-fail-closed grep pattern and 12-04 has an overbroad grep that fails before deletion. |
| LOW private shared helper | **RESOLVED** | Plans document `_build_strava_transport` as an intentional internal shared helper. |
| LOW connection.py settings edge | **RESOLVED** | 12-01 explicitly acknowledges `get_settings` in the DuckDB connection home. |

## Risk Assessment

**HIGH as written**, because 12-04 has a deterministic verification failure. After narrowing that grep and tightening the small test/descriptor details, risk drops to **LOW/MEDIUM**: the architecture and wave split are otherwise coherent.

---

## OpenCode Review

## 1. Summary

The cycle-3 revision directly addresses both dominant cycle-2 concerns. The **HIGH wave-placement issue** is resolved: 12-03 now carries its own test retargets (conftest, test_metric_services, test_refresh_runtime, test_application_services, sync.DbConn sites) via a dedicated Task 3, and 12-03's own full-suite gate (Task 4) runs after those retargets. 12-04 is consequently scoped to CLI-only retargets. The **MEDIUM repository-boundary retarget** is resolved: 12-04 Task 2 now names the concrete `mcp_strava.adapters.strava.client.StravaClient.api_request` / `.refresh_token` as patch targets. All 6 remaining cycle-2 MEDIUM/LOW items are also resolved. Two minor cycle-3 observations, neither blocking. **Overall risk: LOW.**

## 2. Strengths

- **Wave-placement fix is correct and complete.** 12-03 Task 3 retargets exactly the test sites that exercise production code migrated in 12-03 Tasks 1-2; 12-03 Task 4 runs the full `uv run pytest -q` after those retargets — same wave, same plan. 12-04 `must_haves` / Task 2 explicitly acknowledge those sites were *already* handled in 12-03 and tell the executor not to touch them.
- **Repository-boundary retarget is concrete and fail-safe.** 12-04 Task 2 now specifies `monkeypatch.setattr(mcp_strava.adapters.strava.client.StravaClient, "api_request", _boom)` and `.refresh_token` — the exact network methods on the facade. The invariant "repository must never touch Strava" cannot pass vacuously: if the repository path ever constructs or calls `StravaClient`, the `_boom` fires.
- **StravaClient injection seam is fully specified.** 12-02 Task 3 requires `StravaClient(transport=None, *, settings=None, clock=None, sleeper=None)` with an explicit optional-transport path that bypasses all construction-time cred resolution. The verify block asserts `'transport' in init.parameters`.
- **Fail-closed grep discipline is consistent.** Every verification block across all 5 plans now uses `! rg -q ...` (non-zero exit on match) — no more `&& echo FAIL || echo ok` patterns that mask failures.
- **RealClock/RealSleeper alias lifecycle is explicit:** added on `bootstrap.py` in 12-03 Task 2 (kept through wave 3), deleted from `bootstrap.py` + `sync.py` in 12-04 Task 1 after `cli.py` migrates. The verify checks `! rg -q "RealClock|RealSleeper" src/mcp_strava` after 12-04 proves no leftover.
- **Settings fail-fast scope holds:** `load_settings()` never raises on missing Strava creds; the cred accessor raises only when called. 12-02 Task 1 verify explicitly asserts `load_settings()` succeeds without creds.

## 3. Concerns

- **[LOW] 12-03 Task 3 verify uses `||` which catches `rg` errors as false-success.** The check `rg -q 'setattr\(sync,\s*"DbConn"' tests/test_security_guards.py && exit 1 || echo "sync-DbConn-retargeted"` prints the success echo if `rg` exits with code 2 (file-not-found / error), not just code 1 (no-match). In practice the file is guaranteed to exist, but a `! rg -q ...` pattern would be more robust.
- **[LOW] 12-05 `files_modified` omits `strava_api_reference.py`.** Task 1 explicitly says to fix the stale `get_zones()` comment at L54 of that file, but it's not listed in the plan's `files_modified` metadata. The verify grep for zero `get_zones` across `src tests` will catch it regardless.

## 4. Suggestions

- For 12-03 Task 3 verify: replace the `rg ... && exit 1 || echo` pattern with a consistent `! rg -q ...` or `test $(rg -c ...) -eq 0` to avoid masking `rg` file errors.
- Consider adding a 12-01 note about the `_open_storage_connection` collapse: once co-located in `connection.py` with `open_expected_mirror_db`, the one-line `_open_storage_connection` wrapper can be inlined (MirrorConn/ReadConn call `open_expected_mirror_db` directly). Task 1 says "collapse to a direct call" but doesn't say whether to keep the wrapper as a module-level alias — consistent with GP-01 (clean over fast).

## 5. Resolution of Prior Feedback (cycle 2)

| Concern | Severity | Status | Justification |
|---|---|---|---|
| Wave placement of test retargets (12-03 migrates code whose test retargets are in 12-04) | HIGH (Codex) | **RESOLVED** | 12-03 now includes Task 3 (retarget conftest, test_metric_services, test_refresh_runtime, test_application_services, sync.DbConn sites in test_security_guards) before its own Task 4 full-suite gate. 12-04 explicitly scoped to CLI-only retargets. `must_haves` in both plans cross-reference the split. |
| `test_repository_boundary.py` L353-354 retarget destination underspecified | MEDIUM (both) | **RESOLVED** | 12-04 Task 2 names concrete targets: `mcp_strava.adapters.strava.client.StravaClient.api_request` and `.refresh_token` with `_boom`. `must_haves` entry confirms "patches the CONCRETE StravaClient network methods." |
| `StravaClient` construction/test seam underspecified | MEDIUM (Codex) | **RESOLVED** | 12-02 Task 3 specifies `StravaClient(transport=None, *, settings=None, clock=None, sleeper=None)` with optional transport injection; verify checks signature; all 5 focused tests inject fake transport. |
| Verification commands not fail-closed | MEDIUM (Codex) | **RESOLVED** | All 12-04/12-05/12-03 grep checks now use `! rg -q ...` patterns. |
| Shared transport helper private but cross-module | LOW (Codex) | **RESOLVED** | Acknowledged in 12-02/12-03 as intentional private shared helper `_build_strava_transport`; single wiring path documented. |
| `_db_path()` introduces new settings dependency in connection.py | LOW (OpenCode) | **RESOLVED** | 12-01 review-feedback section explicitly calls this out as architecturally valid; Task 1 already adds the import. |

## 6. Risk Assessment

**OVERALL: LOW**

The cycle-2 HIGH (wave placement) is definitively resolved — 12-03 carries its own test retargets in the same wave, and 12-04 is scoped to CLI-only retargets with explicit cross-references confirming the split. The cycle-2 MEDIUM (repository-boundary retarget) is resolved with concrete `StravaClient.api_request`/`.refresh_token` targets. All remaining cycle-2 MEDIUM/LOW items are addressed. Two new cycle-3 observations are LOW (fragile verify shell pattern, minor metadata omission), neither blocking. The additive→migrate→delete wave ordering, fail-closed grep discipline, alias lifecycle, and Docker smoke gate are all sound. The phase goal (dissolve `db.py`, behavior unchanged, full suite green) is achievable against these plans.

---

## Orchestrator Verification (Claude, cycle 3)

I independently verified the single new HIGH against the working tree, because the two
reviewers diverge on it:

```
$ rg -n 'RealClock|RealSleeper' .planning/.../12-04-PLAN.md
77:  <automated>... && ! rg -q "RealClock|RealSleeper" src/mcp_strava</automated>

$ rg -n 'RealClock|RealSleeper' src/mcp_strava/db.py
128:class _RealClock:
133:class _RealSleeper:
189:    clock = _RealClock()
190:    sleeper = _RealSleeper()
195:    clock = _RealClock()
196:    sleeper = _RealSleeper()
```

**Codex is correct.** 12-04 Task 1's verify uses `! rg -q "RealClock|RealSleeper" src/mcp_strava`.
`rg` matches substrings by default (no word boundary), so the pattern matches `_RealClock`
and `_RealSleeper` inside `db.py`. Because `db.py` is intentionally not deleted until 12-05,
the `! rg -q` gate exits non-zero and **12-04 Task 1 fails deterministically**, regardless of
whether cli.py/bootstrap.py/sync.py were correctly migrated. OpenCode quoted the same grep as
a strength without cross-checking db.py and therefore missed it.

**Recommended fix (Codex):** scope the grep to the files actually being cleaned in this wave:
`! rg -q "RealClock|RealSleeper" src/mcp_strava/cli.py src/mcp_strava/refresh/bootstrap.py src/mcp_strava/sync.py`.
(Equivalently, add `--glob '!db.py'`, but the explicit-files form is clearer.) Once narrowed,
this HIGH drops away and the residual items are MEDIUM/LOW.

---

## Consensus Summary

Both reviewers agree the **cycle-2 HIGH (wave placement of test retargets) is RESOLVED** — 12-03
now carries its own application/refresh/sync test retargets (new Task 3) in the same wave as the
production migration, and its full-suite gate (Task 4) runs after those retargets; 12-04 is scoped
to CLI-only retargets, with `must_haves` in both plans cross-referencing the split. Both also agree
the **cycle-2 MEDIUM (`test_repository_boundary.py` retarget destination)** is RESOLVED — 12-04 Task 2
now names the concrete `StravaClient.api_request`/`.refresh_token` methods. All remaining cycle-2
MEDIUM/LOW items are resolved by both.

### Agreed Strengths
- Cycle-2 HIGH wave-placement fix is correct and complete (test retargets co-located with the code they exercise; full-suite gate runs after).
- Repository-boundary retarget is now concrete and cannot pass vacuously.
- StravaClient transport/settings/clock/sleeper injection seam fully specified.
- Hard-cut sequencing (additive homes → caller migration → CLI migration → db.py deletion) with explicit RealClock/RealSleeper alias lifecycle.
- Final `just test` Docker/MCP smoke gate.

### Agreed Concerns
- None at HIGH consensus. The two LOW items OpenCode raises (12-03 Task 3 non-fail-closed `rg ... && exit 1 || echo` pattern; 12-05 `files_modified` omits `strava_api_reference.py`) overlap with Codex's own LOW about the same 12-03 grep pattern.

### Divergent Views — the dominant open question this cycle
- **[HIGH per Codex / not flagged by OpenCode — VERIFIED VALID by orchestrator] 12-04 Task 1 grep is overbroad.**
  `! rg -q "RealClock|RealSleeper" src/mcp_strava` matches `_RealClock`/`_RealSleeper` still
  present in `db.py` (db.py deleted only in 12-05), so 12-04 Task 1's gate fails deterministically.
  Confirmed against the working tree (db.py L128/133/189-196). OpenCode rated risk LOW and quoted
  this grep as a strength without checking db.py, so it missed the issue.
  - **Recommended fix:** narrow the grep to `src/mcp_strava/cli.py src/mcp_strava/refresh/bootstrap.py src/mcp_strava/sync.py` (the files this wave cleans), or exclude `db.py`.
- **Overall risk rating.** Codex: HIGH as written (deterministic 12-04 gate failure). OpenCode: LOW.
  Both converge to LOW/MEDIUM once the 12-04 grep is scoped.

### Open MEDIUMs (fold into a final replan along with the HIGH grep fix)
- Credential-accessor behavior under-tested (Codex): add explicit tests for missing token file, missing individual keys, comment/whitespace parsing, secret-safe error messages.
- `DuckDBRepository.from_connection` monkeypatch is a `@classmethod` (Codex): prescribe a descriptor-safe replacement (`staticmethod(lambda conn: FakeRepo())` or `classmethod(lambda cls, conn: FakeRepo())`) so the fake doesn't receive an unexpected `cls`.
