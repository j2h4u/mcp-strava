---
phase: 12
reviewers: [codex, opencode]
reviewed_at: 2026-05-30T05:05:00+06:00
plans_reviewed: [12-01-PLAN.md, 12-02-PLAN.md, 12-03-PLAN.md, 12-04-PLAN.md, 12-05-PLAN.md]
cycle: convergence-2
---

# Cross-AI Plan Review — Phase 12 (Convergence Re-Review, cycle 2)

> Prior cycle (cycle 1) raised a HIGH consensus concern (incomplete test blast
> radius) plus several MEDIUM/LOW items. The plans were revised; this cycle
> re-reviews the revised set. Both reviewers agree the cycle-1 HIGH is resolved.
> Codex surfaces a NEW HIGH about wave placement of the (now-complete) test
> retargets; OpenCode does not flag it.

## Codex Review

**Summary**

The revised plans are substantially better than the prior cycle: they enumerate the real blast radius, address the `token=` decision, preserve read-only settings loading, and add a final Docker smoke gate. However, as written they still have a HIGH convergence issue: several test retargets are scheduled in 12-04 even though the corresponding production code is migrated in 12-03 and 12-03 explicitly runs those tests. That makes the intermediate wave unlikely to stay green.

**Strengths**

- Clear hard-cut strategy: no compatibility shim, `db.py` deleted last.
- Good wave dependency shape overall: additive homes first, caller migration next, deletion last.
- Prior missing test files are now explicitly listed.
- `StravaClient.api_request(path)` drops the dead `token=` parameter and verifies the signature.
- Settings fail-fast scope is corrected: `load_settings()` remains safe for read-only mirror paths.
- Final gate includes `just test`, which matches this repo's need for Docker/MCP runtime validation.

**Concerns**

- **[HIGH] Test retargeting is complete but in the wrong wave.** 12-03 migrates `metric_services`, `worker`, `sync`, and `freshness`, then runs tests that still patch old `mcp_strava.db` or `*.DbConn` symbols. Examples: `test_metric_services.py` still patches `mcp_strava.db._db_path/open_expected_mirror_db`, `test_refresh_runtime.py` still patches `worker.DbConn/repository_from_connection`, and `test_security_guards.py` still patches `sync.DbConn`. `conftest.py` also still resets the old read pool while 12-03 starts using the new pool. These are deterministic intermediate failures or vacuous guards.

- **[MEDIUM] `StravaClient` construction/test seam is underspecified.** The plan says focused tests should use fakes/monkeypatches, but if `StravaClient()` eagerly builds the real transport and credentials are required at construction, tests and CLI guards may need brittle private monkeypatching. Specify an explicit optional transport/settings/clock injection seam.

- **[MEDIUM] Some verification commands are not fail-closed.** 12-04 uses patterns like `rg ... && echo FAIL || echo ok`; that prints failure text but exits successfully. Use `! rg -q ...` or an explicit `if rg ...; then exit 1; fi`.

- **[LOW] The shared transport helper is private but planned as cross-module API.** If `bootstrap.py` is meant to import `_build_strava_transport`, either make it public (`build_strava_transport`) or explicitly document it as an intentional private shared helper.

- **[LOW] Repository-boundary retargeting is vague.** Retargeting `legacy_db.api_request/refresh_token` to "where migrated code looks them up" is unclear for tests whose invariant is "repository must never touch Strava." Prefer an AST import guard against `mcp_strava.adapters.strava` in repository modules or patch `StravaClient.__init__` fail-closed.

**Suggestions**

- Move test retargets that correspond to application/refresh/sync migration into 12-03: `conftest.py`, `test_metric_services.py`, `test_refresh_runtime.py`, `test_application_services.py`, and the `sync.MirrorConn` parts of `test_security_guards.py`.
- Leave CLI-specific retargeting for 12-04: `test_cli_surface.py`, CLI product guards, and remaining `DbConn -> MirrorConn` imports in smoke/phase tests.
- Add explicit tests for missing `STRAVA_CLIENT_ID/SECRET`: `load_settings()` succeeds with an empty temp token file, while `Settings.strava_client_credentials()` or `StravaClient()` fails with the expected path/key message.
- Replace 12-04/12-05 grep checks with fail-closed shell snippets and avoid missing-path `rg` false failures for optional `Dockerfile`/compose paths.

**Resolution Of Prior Feedback**

| Prior concern | Status | Justification |
|---|---|---|
| HIGH test blast radius | **PARTIALLY RESOLVED** | All important files/sites are now enumerated, but too many are retargeted in 12-04 after 12-03 already migrates and tests them. |
| MEDIUM `token=` parameter | **RESOLVED** | `StravaClient.api_request(path)` explicitly drops `token`, with signature verification. |
| MEDIUM settings fail-fast scope | **RESOLVED** | Plans clearly keep `load_settings()` non-throwing and make Strava creds required-when-used. Add stronger tests, but the design is correct. |
| MEDIUM security-guard semantic retarget | **PARTIALLY RESOLVED** | The plan names semantic retargeting, but some guards are still moved too late and one repository-boundary retarget is ambiguous. |
| LOW key-prefix inconsistency | **RESOLVED** | `STRAVA_CLIENT_*` are explicitly not added to `_KEYS`. |
| LOW AST import gate brittleness | **RESOLVED** | Replaced with an `rg` gate, though it should also fail closed. |
| LOW stale `get_zones` comment | **RESOLVED** | 12-05 explicitly fixes `strava_api_reference.py` and greps for remaining `get_zones`. |

**Risk Assessment**

**HIGH as written**, because 12-03's own verification is likely to fail after production migration but before test retargeting. Once those test retargets move into the same wave as the code they exercise, the plan drops to MEDIUM/LOW: the decomposition is otherwise coherent and the final runtime smoke gate is appropriate.

---

## OpenCode Review

### 1. Summary

The revised plan set is a substantial improvement over the prior cycle. The HIGH-concern incomplete test blast radius has been comprehensively addressed — all 8 test files are now in scope for 12-04, every monkeypatch-by-path site is enumerated with explicit retarget instructions, and dead-attribute / vacuous-no-op traps are identified and mitigated. The additive-then-migrate wave ordering (01→02→03→04→05) is correct, dependencies are properly declared, and the hard-cut deletion (12-05) is gated by a zero-reference grep across src, tests, and ops config plus a Docker smoke test. All 5 prior MEDIUM/HIGH concerns are RESOLVED, and the 6 LOW/suggestion items are also addressed. Two minor new concerns noted below, neither blocking.

### 2. Strengths

- **Complete monkeypatch blast radius**: 12-04 `files_modified` now covers all 8 test files with coupling; Task 2 enumerates every site (`worker.DbConn` x6, `freshness.repository_from_connection`, `metric_services.repository_from_connection`, `cli.api_request`/`cli.DbConn`, `legacy_db.api_request`/`refresh_token`, `DbConn→MirrorConn` in smoke/phase01 tests) and prescribes the correct retarget for each.
- **Dead-attribute and vacuous-no-op traps explicitly mitigated**: `worker.DbConn` (plain `setattr`, would error), `cli.api_request`/`cli.DbConn` (`raising=False`, would silently no-op), and `sync.DbConn` (would create dead attribute) are all called out with the required fix — `raising=False` dropped where attributes should exist so misses fail loudly.
- **Security guard retargeting is semantic, not string-swap**: 12-04 Task 3 explicitly says guards must forbid the actual `StravaClient` network path and `MirrorConn` in read/product modules, not merely swap the literal and pass vacuously.
- **Wave ordering preserves importability mid-migration**: RealClock/RealSleeper aliases are kept on bootstrap through wave 3 so `cli.py` (which still imports them from `refresh.bootstrap`) doesn't break between 12-03 and 12-04.
- **Hard-cut gate is rigorous**: 12-05 Task 1 gates deletion on a zero-reference grep covering `src`, `tests`, AND ops config (`Justfile`, `Dockerfile`, `compose.yaml`), plus `just test` Docker smoke — catches runtime-only breakage that static analysis misses.
- **Governing principles consistently honored**: GP-02 (no shims, hard cut), GP-01 (clean over fast — dedicated `clock.py`, shared `_build_strava_transport`), GP-04 (dependency rule — application depends on adapters, not vice versa).

### 3. Concerns

- **MEDIUM — test_repository_boundary.py L353–354 retarget destination is underspecified**. The plan says "retarget L353-354 `legacy_db.api_request`/`refresh_token` to the `StravaClient` home (patch where the migrated code looks them up)." The code under test in `test_repository_boundary.py` exercises the DuckDB repository, not the StravaClient facade. After migration, the repository's `api_request`/`refresh_token` calls route through `StravaClient` (for sync/refresh paths) or may not involve them at all for pure-repository tests. The plan correctly identifies the site but leaves the exact patch target (e.g., `repository_boundary_module.StravaClient.api_request` vs. patching the transport layer) to the executor. A wrong choice could leave the test either broken or vacuously passing. Recommend explicitly naming the target module+attribute in the action block.

- **LOW — `_db_path()` in `connection.py` introduces a new settings dependency**. Plan 12-01 defines `_db_path()` as `str(get_settings().database_path)`. This creates an import of `get_settings` in `adapters/duckdb/connection.py` where it may not have existed before (the existing `open_expected_mirror_db` currently takes a path parameter). This is architecturally fine — the DuckDB adapter can depend on settings — but the plan doesn't acknowledge the new import edge.

### 4. Suggestions

- For the test_repository_boundary.py retarget (12-04 Task 2), add a one-liner specifying the concrete module to patch (e.g., "patch `StravaClient.api_request` on the module object where the repository boundary code resolves it — likely `mcp_strava.adapters.strava.client.StravaClient.api_request` or the transport it wraps").
- In 12-01 Task 1, explicitly note that adding `from mcp_strava.settings import get_settings` to `connection.py` is intentional and architecturally valid (DuckDB adapter depending on settings for the data path).

### 5. Resolution of Prior Cycle's Feedback

| Prior Concern | Severity | Status | Justification |
|---|---|---|---|
| Incomplete test blast radius | HIGH (consensus) | **RESOLVED** | 12-04 `files_modified` expanded to all 8 test files; Task 2 enumerates every monkeypatch site with explicit retarget; Task 3 covers `sync.DbConn` L637/L700 → `sync.MirrorConn` |
| StravaClient.api_request(token=None) override unspecified | MEDIUM (consensus) | **RESOLVED** | 12-02 drops the `token` param (verified zero live callers); verify asserts `token` not in signature |
| Settings fail-fast scope / read-only mirror path | MEDIUM (consensus) | **RESOLVED** | 12-02 Task 1: creds resolve from token file, `load_settings()` never raises, fail-fast only at StravaClient/refresh construction |
| Security guards need semantic retargeting | MEDIUM (Codex) | **RESOLVED** | 12-04 Task 3: guards forbid `MirrorConn` + real `StravaClient` network path; `sync.DbConn` → `sync.MirrorConn`; `init_db` guards removed |
| MCP_STRAVA_* key-prefix inconsistency | LOW (OpenCode) | **RESOLVED** | `STRAVA_CLIENT_*` explicitly NOT added to `_KEYS` env set |
| Brittle AST import check | LOW (Codex) | **RESOLVED** | Replaced with `rg` gate |
| Stale get_zones() comment | LOW (Codex) | **RESOLVED** | 12-05 Task 1 fixes L54 comment; greps for zero `get_zones` |
| No focused StravaClient facade test | suggestion (Codex) | **RESOLVED** | 12-02 Task 3 adds `tests/test_strava_client.py` (5 cases) |
| Third parallel transport wiring path | suggestion (Codex) | **RESOLVED** | 12-02 adds shared `_build_strava_transport`; 12-03 bootstrap calls it |
| db.py refs may linger in ops config | suggestion (OpenCode) | **RESOLVED** | 12-05 Task 1 greps ops config, not just src/tests |
| init_db DDL guards reference soon-deleted symbol | (Codex/OpenCode) | **RESOLVED** | 12-04 Task 3: guard + test removed |

### 6. Risk Assessment

**OVERALL: LOW**

The dominant risk from the prior cycle has been thoroughly addressed. Every known coupling site is enumerated and retargeted. The additive wave ordering with alias preservation eliminates mid-wave import breakage. The hard-cut deletion gate catches stranded imports at both static and runtime levels. The two new concerns are minor and easily addressed during execution. The phase goal is achievable against these plans.

---

## Consensus Summary

Both reviewers agree the **cycle-1 HIGH (incomplete test blast radius) is now resolved** — all 8 coupled test files and every monkeypatch-by-path site are enumerated with explicit, correct retargets, and the dead-attribute / vacuous-no-op traps are called out. Both agree the remaining cycle-1 MEDIUM/LOW items (token= drop, settings fail-fast scope, key-prefix, AST→rg gate, stale get_zones comment, shared transport helper, facade test) are addressed. They diverge on a single new issue around wave placement.

### Agreed Strengths
- Hard-cut, no-shim discipline; `db.py` deleted last (12-05) behind a zero-reference grep over src + tests + ops config plus a `just test` Docker smoke gate.
- Additive-first wave ordering with RealClock/RealSleeper aliases kept on bootstrap through wave 3, so cli.py imports stay resolvable mid-migration.
- Full monkeypatch blast radius enumerated; `token=` dropped with a signature assertion; `load_settings()` kept non-throwing for the read-only mirror path.
- Strong final gate (pytest + ruff + format + pyright + Docker/MCP smoke).

### Agreed Concerns
- **[MEDIUM] `test_repository_boundary.py` L353–354 retarget destination underspecified** (both reviewers, independently). The plan says "patch where the migrated code looks them up" for `legacy_db.api_request`/`refresh_token`, but the repository-boundary test's invariant is "repository must never touch Strava." Name the concrete module+attribute (or convert to an AST import guard against `mcp_strava.adapters.strava`, or a fail-closed `StravaClient.__init__`) so the test cannot pass vacuously.

### Divergent Views — **the dominant open question this cycle**
- **[HIGH per Codex / not flagged by OpenCode] Wave placement of test retargets.** Codex argues 12-03 migrates production code in `metric_services`, `worker`, `sync`, and `freshness`, and 12-03's own verification (Task 2 runs `test_refresh_runtime.py` + `test_security_guards.py`; Task 3 runs the **full** `uv run pytest -q`) executes tests whose monkeypatch retargets are not scheduled until 12-04. After 12-03 renames `DbConn→MirrorConn` / removes `repository_from_connection`, the un-retargeted `monkeypatch.setattr(worker, "DbConn", ...)` (plain setattr) errors and `setattr(sync, "DbConn", ...)` creates a dead attribute — so 12-03 cannot land green as written. `conftest.py` is also only retargeted in 12-04 while 12-03 starts using the relocated read pool. OpenCode reads the 01→05 ordering as correct and rates overall risk LOW, but does not address the intra-12-03 verification scope. **This claim is directly verifiable from the plan text** (12-03 Task 2/3 verify blocks vs. 12-04 Task 2/3 retarget scope) and appears well-founded.
  - **Recommended fix (Codex):** move the application/refresh/sync test retargets (`conftest.py`, `test_metric_services.py`, `test_refresh_runtime.py`, `test_application_services.py`, and the `sync.MirrorConn` part of `test_security_guards.py`) into 12-03 alongside the code they exercise; keep only CLI-specific retargets (`test_cli_surface.py`, CLI guards, `DbConn→MirrorConn` in smoke/phase01) in 12-04. Alternatively, relax 12-03's verification to the narrower targeted subsets that do not depend on the deferred retargets, deferring the full-suite gate to after 12-04.
- **Overall risk rating.** Codex: HIGH as written (wave-placement ordering). OpenCode: LOW. Both converge to LOW/MEDIUM once the 12-03↔12-04 test-retarget split is corrected.
