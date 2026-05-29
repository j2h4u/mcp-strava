---
phase: 12
reviewers: [codex, opencode]
reviewed_at: 2026-05-30T04:10:00+06:00
plans_reviewed: [12-01-PLAN.md, 12-02-PLAN.md, 12-03-PLAN.md, 12-04-PLAN.md, 12-05-PLAN.md]
---

# Cross-AI Plan Review — Phase 12

## Codex Review

**Summary**
The plan set is directionally solid and matches the phase goal: add focused homes, migrate callers, delete `db.py`, and verify with the real suite plus Docker smoke. I would not approve it as-is yet. The main weakness is blast-radius accuracy: the current checkout has several test and import couplings not covered by the plans, and Plan 12-03 can break `cli.py` before Plan 12-04 gets a chance to migrate it.

**Strengths**
- Clean wave structure: additive homes first, caller migration second, deletion last.
- Correctly identifies the highest-risk behavior: `ReadConn` thread-local reuse and reset semantics.
- Good hard-cut stance: no permanent `db.py` re-export shim.
- Verification is appropriately strong at the phase gate: pytest, ruff, pyright, Docker build, MCP smoke.
- Good security intent around secret non-disclosure and preserving read-path network-import guards.

**Concerns**
- **[HIGH] Plan 12-03 has an ordering break.** It deletes/replaces `refresh.bootstrap.RealClock` / `RealSleeper`, but `cli.py` (L19-21) still imports those names until 12-04. If 12-03 runs its full suite, importing CLI should fail.
- **[HIGH] Test blast radius is incomplete.** Current references include `tests/test_refresh_runtime.py`, `tests/test_application_services.py`, and `tests/test_cli_surface.py`, not just the files listed in 12-04. Examples: `test_refresh_runtime.py:581` monkeypatches `worker.DbConn` and `worker.repository_from_connection`; `test_application_services.py:203` monkeypatches `freshness.repository_from_connection`; `test_cli_surface.py:182/185` still guards `cli.api_request` / `cli.DbConn`.
- **[MEDIUM] Settings fail-fast is ambiguous.** The plan says credentials should be "required-when-used", but task wording could be implemented as `load_settings()` raising when Strava client creds are missing. That would break read-only product paths that only need the local mirror.
- **[MEDIUM] `StravaClient.api_request(path, token=None)` needs a precise token-override decision.** Existing `db.api_request(..., token=...)` can use an explicit access token before falling back to file-backed refresh. The plan names the parameter but does not specify how the new facade preserves it.
- **[MEDIUM] Security guards need semantic retargeting, not only string replacement.** Some guards still reason about `mcp_strava.db`, `DbConn`, and network functions in several sections of `test_security_guards.py`. After the rename, product-handler guards should probably forbid `MirrorConn` where they previously forbade `DbConn`, and network-import guards should target the actual `StravaClient` lookup path.
- **[LOW] The AST import check in 12-04 is brittle.** It appears to miss plain `import mcp_strava.db` and has precedence issues. Use the existing `rg "from mcp_strava\.db import|import mcp_strava\.db|mcp_strava\.db\." src tests` gate instead.
- **[LOW] Deleting `get_zones()` leaves at least one stale source comment.** `src/mcp_strava/strava_api_reference.py` still references `get_zones()`. Small, but this repo's stated preference is not to keep stale legacy references.

**Suggestions**
- Move the `cli.py` clock rename into 12-03, or keep temporary `RealClock = SystemClock` / `RealSleeper = SystemSleeper` aliases only until 12-04 and remove them in 12-04 or 12-05.
- Expand the migration tasks to include all current grep hits: `tests/test_refresh_runtime.py`, `tests/test_application_services.py`, `tests/test_cli_surface.py`, and all relevant sections of `tests/test_security_guards.py`.
- Make Strava auth settings explicit, for example `settings.strava_auth.require_client_credentials()`, and call it only from `StravaClient` / refresh collaborator construction.
- Factor transport construction into one helper used by both `StravaClient` and `build_refresh_collaborators`, to avoid a third parallel wiring path.
- Add one focused facade test for `StravaClient`: normal `(data, rate_headers)`, rate-limited sentinel, non-rate `RuntimeError`, refresh-token error mapping, and no secret leakage.
- Retarget the old `init_db` DDL guard to live runtime/bootstrap/sync modules if the invariant still matters; otherwise delete it intentionally and document why.

**Risk Assessment**
**MEDIUM-HIGH** as written. The architecture direction is right, but the current plans are likely to fail mid-wave because 12-03 breaks CLI imports and the test blast radius is undercounted. Once those ordering and test-retargeting issues are fixed, the residual risk drops to **MEDIUM**: mostly behavior parity around auth construction, token override semantics, and thread-local connection reuse.

---

## OpenCode Review

### 1. Summary

The five plans form a well-researched, methodical decomposition of the db.py dissolution into the D-10 hard-cut migration order. Each wave is additive-first (new homes land before callers cut over), with per-task `pytest` gates and per-wave full-suite verification. The RESEARCH.md blast-radius table is exhaustive; PATTERNS.md provides concrete code excerpts for every new/modified file. The plans correctly handle the thread-local pool integrity critical path, dead-code deletions (`get_zones`/`init_db`), and security-guard literal retargeting. The phase goal — dissolve `db.py`, behavior unchanged, suite green — is achievable with this plan set.

### 2. Strengths

- **Exhaustive blast-radius mapping** in RESEARCH.md covering all import sites + monkeypatch-by-path couplings + security-guard string literals.
- **Thread-local pool integrity (Pitfall 1)** is handled correctly: `_thread_state` + `ReadConn` + `reset_thread_connections` move as a single verbatim unit into `connection.py` so the conftest reset hook and read path share one `threading.local()` instance.
- **Additive-first migration order** (D-10) is enforced: 12-01/12-02 add new homes without touching `db.py`; 12-03/12-04 migrate callers; 12-05 deletes `db.py` last.
- **Dead-code discipline** is explicit: `get_zones()` and `init_db` are deleted rather than relocated; no `application/athlete_zones.py` is created.
- **Security-guard updates** are planned in the same wave as the facade migration (12-04 Task 3), preventing the "vacuously-passing guard" trap (Pitfall 2).

### 3. Concerns

- **[HIGH] Missing explicit monkeypatch retargets for `sync.DbConn` in `test_security_guards.py`.** `test_sync_activities_quick_...` (L637) and `test_backfill_activities_...` (L700) both do `monkeypatch.setattr(sync, "DbConn", FakeDbConn)`. After 12-03, `sync.py` imports `MirrorConn` (not `DbConn`), so `setattr(sync, "DbConn", ...)` would silently create a dead attribute — the real `MirrorConn` bypasses the mock, breaking both tests. Plan 12-04 Task 2 mentions repointing monkeypatches but doesn't enumerate these two specific sites. The test mock name must change to `monkeypatch.setattr(sync, "MirrorConn", FakeDbConn)`.
- **[MEDIUM] `StravaClient.api_request(token=None)` parameter has zero live callers but is specified in the contract.** `FileTokenProvider` has no `token` arg. If the facade preserves the parameter but can't implement it, the signature is misleading. Per GP-02 (no compat), the plan should either drop the parameter or document that it is not supported.
- **[MEDIUM] `_env_path()` / `_build_transport` / `_build_token_provider` internals are not explicitly accounted for in the deletion plan.** They go away with `db.py`, so this is self-correcting, but the plan should confirm no external caller reaches them (grep confirms zero).
- **[LOW] `settings.py` key naming inconsistency.** Adding bare `STRAVA_CLIENT_ID`/`STRAVA_CLIENT_SECRET` to `_KEYS` breaks the `MCP_STRAVA_*` prefix convention of the other keys. No behavior problem, but a maintenance smell.
- **[LOW] `repository_from_path(expected_mirror=...)` flag semantics.** The executor must verify that `DuckDBRepository.from_path` without `expected_mirror` uses `duckdb.connect` directly, matching the `False` path that `cli.py` relies on.

### 4. Suggestions

- Add explicit monkeypatch-site enumeration for `sync.DbConn` → `sync.MirrorConn` in `test_security_guards.py` to plan 12-04 Task 3 (L637, L700). `get_settings` patches are imported from `settings`, not `db`, so are unaffected.
- Drop or document the `token=None` parameter on `StravaClient.api_request` (recommend dropping per GP-02).
- Consider a `just test` gate after 12-04 (before deleting `db.py` in 12-05) rather than only at the phase gate.
- Add a note in 12-05 Task 1 to also verify no `mcp_strava.db` reference exists in `Justfile`, `Dockerfile`, or compose configs — not just `src/` and `tests/`.
- In 12-03 Task 2, specify the exact code for sourcing creds from settings in `bootstrap.py`, with the same fail-fast semantics as the current `_required_strava_client`.

### 5. Risk Assessment: **MEDIUM**

The plans are thorough and well-researched. The HIGH concern (sync monkeypatch retargets) is a concrete, fixable gap. The MEDIUM concerns are edge-case omissions that won't break the suite but could leave misleading API surfaces. With the `sync.DbConn` → `MirrorConn` monkeypatch updates added to 12-04, the risk drops to LOW.

---

## Consensus Summary

Both reviewers agree the architecture direction, wave structure, and hard-cut discipline are correct, and that the phase goal is achievable. Both also independently flagged the **same dominant HIGH risk: the test blast radius is undercounted** — plan 12-04 lists only 5 test files in `files_modified`, but the working tree has `db.py`-coupled monkeypatches in `tests/test_refresh_runtime.py`, `tests/test_application_services.py`, `tests/test_cli_surface.py`, plus two un-enumerated `sync.DbConn` patches in `tests/test_security_guards.py`. After 12-03 renames `DbConn`→`MirrorConn` and removes `repository_from_connection`, these stale `monkeypatch.setattr(..., "DbConn"/"repository_from_connection", ...)` sites will either silently no-op (the `raising=False` cases bypass the mock and hit real code) or fail outright. **All of these claims were verified directly against the checkout during this review** (cli.py L15-21, test_refresh_runtime.py L581/621/723/785/838/866, test_application_services.py L203, test_cli_surface.py L182/185/445, test_security_guards.py L637/700).

### Agreed Strengths
- Additive-first → migrate → delete-last wave ordering (D-10) with per-wave suite gates.
- Thread-local read pool (`_thread_state`+`ReadConn`+`reset_thread_connections`) moved as one verbatim unit, preserving the conftest reset-hook object identity.
- Hard-cut, no-shim deletion discipline; dead `get_zones`/`init_db` deleted rather than relocated.
- Strong phase gate: pytest + ruff + pyright + Docker build + MCP smoke.

### Agreed Concerns
- **[HIGH] Incomplete test blast radius.** Three test files (`test_refresh_runtime.py`, `test_application_services.py`, `test_cli_surface.py`) and two specific `sync.DbConn` patch sites in `test_security_guards.py` are not in 12-04's scope; their monkeypatch targets must be retargeted to `MirrorConn` / `DuckDBRepository.from_connection` or they will silently bypass or break. This is the single concern that must be resolved before execution.
- **[MEDIUM] `StravaClient.api_request(token=None)` token-override semantics unspecified.** Both reviewers note the parameter is carried into the new facade with no defined behavior; `FileTokenProvider` has no `token` arg. Decide: drop it (GP-02) or define the override path.
- **[MEDIUM] Settings fail-fast scope (Codex) / `MCP_STRAVA_*` key-prefix inconsistency (OpenCode).** Credential resolution must not make `load_settings()` raise on the read-only mirror path that needs no Strava creds; keep the fail-fast at `StravaClient`/refresh-construction time.
- **[MEDIUM] Security-guard semantic retargeting (Codex).** Guards must forbid `MirrorConn`/the real `StravaClient` lookup path, not just swap string literals, or they pass vacuously.

### Divergent Views
- **12-03 → cli.py clock-import ordering (Codex HIGH; OpenCode silent).** Codex reads 12-03's removal of `RealClock`/`RealSleeper` as breaking `cli.py`'s import before 12-04 migrates it. Verification: `cli.py` imports `RealClock`/`RealSleeper` from `sync` (re-exports), and 12-03 Task 2 explicitly repoints sync's re-exports — so the break is avoided *only if* 12-03 preserves the `RealClock`/`RealSleeper` names (or aliases) on `sync` through wave 3. The plan's wording ("repoint those names to SystemClock/SystemSleeper (or re-export the new names)") is ambiguous on this point. Lower-confidence than the test-blast HIGH, but worth a one-line clarification: keep `RealClock`/`RealSleeper` as `sync` aliases until cli.py migrates in 12-04.
- **Overall risk rating.** Codex: MEDIUM-HIGH as written (CLI ordering + undercounted tests). OpenCode: MEDIUM (single fixable HIGH). Both converge to LOW–MEDIUM once the test blast radius is corrected.
