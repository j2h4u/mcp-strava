# Phase 12: Decouple db.py into focused modules - Research

**Researched:** 2026-05-30
**Domain:** Python intra-architecture refactor (ports-and-adapters, DuckDB + Strava HTTP)
**Confidence:** HIGH (whole-codebase grep verification; no external dependencies)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Move `DbConn`, `ReadConn`, `_thread_state`/`_thread_read_connections`, `reset_thread_connections`, `init_db`, `_db_path()`, `_open_storage_connection()` into `src/mcp_strava/adapters/duckdb/connection.py`.
- **D-02:** Relocate the thread-local read-connection pool (`ReadConn` + `_thread_state` + `reset_thread_connections`) **verbatim** — preserve evict-on-error semantics and the reset hook exactly. Highest-risk move.
- **D-03:** Rename `DbConn` → `MirrorConn`. Keep `ReadConn`. No compat constraint on renaming (GP-02).
- **D-04:** **Delete** `repository_from_connection` and `repository_from_path`. Callers call `DuckDBRepository.from_connection(conn)` / `DuckDBRepository.from_path(...)` directly.
- **D-05:** **Delete** `_CompatTokenProvider` and `_read_token_values` (.env parsing). Compat bridge gone (GP-02).
- **D-06:** `settings.py` owns Strava auth config — expose `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` alongside the existing `token_path`. Adapters consume settings. (See RI-04 findings.)
- **D-07:** `SystemClock` / `SystemSleeper` (real clock/sleeper port impls, formerly `_RealClock`/`_RealSleeper`) live in their own dedicated module. Default placement: `src/mcp_strava/adapters/strava/clock.py`. Planner picks the exact module name.
- **D-08:** Introduce a `StravaClient` facade in `src/mcp_strava/adapters/strava/client.py`. Owns transport construction (token provider + `RateLimitPolicy` + clock/sleeper, built from settings), the `(data, rate_headers)` return contract, `StravaUnavailable → RuntimeError` / rate-limited-sentinel mapping, and `refresh_token()`.
- **D-09:** `get_zones()` becomes an application service depending on the repository port and `StravaClient`. **Confirm callers before moving (RI-02)** — see CRITICAL finding below.
- **D-10:** Hard-cut migration order, running `just test` between steps: (1) land new homes additively; (2) `application/*` → (3) `refresh/*` + `sync.py` → (4) `cli.py` → (5) tests + conftest; (6) delete `db.py` last.

### Claude's Discretion
- Exact new module/file names (`clock.py`, `client.py`, `athlete_zones.py`), and whether to split the facade/service across multiple plans (GP-03 permits finer splits).
- Internal organization within `connection.py` after the helpers land.

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within `db.py` decoupling scope.

### Governing Principles (owner-locked)
- **GP-01 Clean over fast** · **GP-02 No backward-compat / no shims** · **GP-03 Fine-grained over catch-all** · **GP-04 Ports-and-adapters + behavior parity** (single-writer DuckDB, per-thread readers, SQL unchanged).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| Core/domain separation — residual `db.py` coupling | Dissolve `db.py`, migrate callers, delete it; behavior unchanged | The blast-radius map (below) enumerates all 18 import sites + 3 monkeypatch-by-path test couplings; the 323-test suite is runnable locally via `uv run pytest -q`, giving a per-task regression net. |
</phase_requirements>

## Summary

`db.py` (235 lines) is pure glue — every concern it owns is a thin wrapper over an adapter that already exists. Research confirms the decomposition is mechanical, **with two scope corrections** that the planner must apply:

1. **`get_zones()` and `init_db()` are DEAD CODE.** Whole-codebase grep finds **zero live callers** of either. `get_zones` is referenced only in a comment in `strava_api_reference.py`; `init_db` is referenced only by `test_security_guards.py` (an AST guard asserting it contains no DDL, plus a guard that `sync` never calls it). Per GP-02 + RI-03, **genuinely-dead symbols are deleted, not relocated.** This means **D-09's athlete-zones application service should NOT be built** — there is no live orchestration to home. The planner should delete `get_zones`, and either delete `init_db` outright or note that its security-guard tests must be removed/retargeted (see Test Coupling below).

2. **Auth/transport wiring already has a canonical home in `refresh/bootstrap.py`.** `bootstrap.py` defines `RealClock`/`RealSleeper` (already public, no underscore), its own `_read_token_values` + `_required_strava_client`, and `build_refresh_collaborators()` which constructs exactly the `FileTokenProvider → TokenRefreshTransport → StravaTransport` chain that `db.py`'s `_CompatTokenProvider`/`_build_transport` duplicate. The `StravaClient` facade (D-08) and `SystemClock`/`SystemSleeper` (D-07) should **converge with** this existing wiring, not create a third parallel copy. `RealClock`/`RealSleeper` are already re-exported through `sync.py` and consumed by `cli.py` — D-07's rename to `SystemClock`/`SystemSleeper` ripples into those re-exports.

**Primary recommendation:** Land new homes additively (connection helpers in `adapters/duckdb/connection.py`; `SystemClock`/`SystemSleeper` in `adapters/strava/clock.py`; `StravaClient` in `adapters/strava/client.py` reading creds from settings). Delete dead `get_zones`/`init_db` rather than relocating. Migrate callers in the D-10 order. Retarget the three by-path test monkeypatches and the security-guard string literals to the new homes. Delete `db.py` last. Run `uv run pytest -q` after each step; `just test` (Docker smoke) at the phase gate.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| DuckDB connection lifetime (`MirrorConn`/`ReadConn`/thread pool) | Database / Storage adapter | — | DuckDB-specific; belongs beside `open_expected_mirror_db` (D-01) |
| Repository construction | Database / Storage adapter | — | `DuckDBRepository.from_*` already owns this; factory indirection deleted (D-04) |
| Strava auth config (`STRAVA_CLIENT_ID/SECRET`) | Settings layer | — | Config resolution is settings' job; adapters consume it (D-06) |
| Real clock/sleeper impls | Strava adapter | (promote to shared if 2nd consumer) | Sole consumer is the Strava transport timing path (D-07) |
| Strava HTTP access + error mapping | Strava adapter (facade) | — | `StravaClient` composes existing transport; centralizes `StravaUnavailable → RuntimeError` (D-08) |
| ~~Athlete-zones cache+fetch orchestration~~ | ~~Application~~ | — | **Dead code — delete, do not build (RI-02/RI-03)** |

## Standard Stack

No new packages. This phase only moves code between existing modules.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| duckdb | 1.5.3 (verified in venv) | Storage engine | Already the project's primary store (Phase 08) |
| pytest | >=9 | Test runner | Existing 323-test suite |
| ruff | >=0.15 | Lint + format | Project linter (line-length 120, select E4/E7/E9,F,I,B,UP) |
| pyright | >=1.1.390 | Type checking | `just typecheck` → `uv run pyright src` |

**Installation:** None. `pip index versions` / package legitimacy gate **not applicable** — no installs in this phase.

## Architecture Patterns

### Recommended Module Layout (after phase)
```
src/mcp_strava/
├── adapters/
│   ├── duckdb/
│   │   └── connection.py   # + MirrorConn, ReadConn, thread pool, reset_thread_connections (D-01..D-03)
│   └── strava/
│       ├── clock.py        # NEW: SystemClock, SystemSleeper (D-07, formerly _RealClock/_RealSleeper)
│       └── client.py       # NEW: StravaClient facade (D-08)
├── settings.py             # + STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET resolution (D-06)
└── db.py                   # DELETED at end of phase
```

### Pattern 1: Verbatim relocation of stateful module-level singletons (D-02)
**What:** `_thread_state = threading.local()` plus `ReadConn` + `reset_thread_connections` form one unit of mutable module-global state.
**When to use:** Moving thread-local pools — the `threading.local()` instance and all functions that read/mutate it must move together to the **same** module so they share one object identity.
**Landmine:** If `_thread_state` is split from `ReadConn`/`reset_thread_connections`, two distinct thread-locals exist and the conftest reset hook silently stops clearing the pool the read path uses → leaked connections + cross-test contamination. Move all three into `connection.py` in a single edit.

### Pattern 2: Converge auth wiring instead of duplicating (D-07/D-08)
**What:** `refresh/bootstrap.py::build_refresh_collaborators` is the reference construction of the `FileTokenProvider → TokenRefreshTransport → StravaTransport` chain.
**When to use:** Building the `StravaClient` facade — compose the same chain, sourcing `client_id`/`client_secret` from settings (D-06) rather than re-parsing `.env`. `SystemClock`/`SystemSleeper` replace `RealClock`/`RealSleeper`; update `bootstrap.py`, `sync.py` re-exports, and `cli.py` consumers in the same migration step.

### Anti-Patterns to Avoid
- **Relocating dead code:** Do not move `get_zones`/`init_db` to new homes "for completeness." They have no live callers — relocating them re-anchors dead code in a clean module (violates GP-01/GP-02). Delete them.
- **Third copy of auth wiring:** Do not write a fresh token-provider chain in `client.py` divorced from `bootstrap.py`. Converge or share.
- **Bare `grep -c` gates on the security-guard tests:** those tests AST-parse import strings; see Test Coupling for the exact literals to update.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Strava cred resolution | New `.env` parser in `client.py` | `settings.py` resolution (D-06) | Settings already parses env+file with caching; a 3rd parser (db.py + bootstrap.py already have 2) is the exact duplication this phase removes |
| Connection lifetime | New context managers | Move existing `MirrorConn`/`ReadConn` verbatim (D-02) | Evict-on-error + reuse semantics are subtle and test-locked |

**Key insight:** Every "build" in this phase is actually a "move" or a "delete." The only genuinely-new code is the `StravaClient` facade surface and the `SystemClock`/`SystemSleeper` rename — both thin.

## Runtime State Inventory

> Refactor phase — all five categories answered explicitly.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None.** No DB keys/collection names embed `db`/`DbConn`/`get_zones`/`init_db`. DuckDB table names (`athlete_zones` etc.) are unchanged — only Python call sites move. | Code edit only |
| Live service config | **None.** No external service (Docker, MCP registration) references these Python symbols by name; the container entrypoint imports modules, not these functions. | None |
| OS-registered state | **None.** No systemd unit / cron / scheduler embeds `db.py` symbol names. | None |
| Secrets / env vars | `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` env var **names are unchanged** — only the code that reads them moves (db.py + bootstrap.py → settings.py per D-06). `MCP_STRAVA_*` keys unchanged. | Code edit only (no secret rotation) |
| Build artifacts | **None.** No compiled artifact carries `db.py`; `uv run python -m compileall` (`just build`) regenerates `.pyc` from source. Stale `__pycache__/db.cpython-*.pyc` will be orphaned after deletion — harmless, cleared on next compile. | None (optional: `find -name '__pycache__' -prune` cleanup) |

**Canonical question — after every file is updated, what still references `db.py`?** Nothing at runtime: imports are static (verified by grep), there is no dynamic `importlib`/`getattr` dispatch on the `db` module. The only non-import couplings are **three test monkeypatch-by-path sites** and **security-guard string literals** (see Test Coupling) — these are source edits, not runtime state.

## Blast Radius — Every Live Coupling to `db.py`

> Verified via `rg "from mcp_strava.db import|import mcp_strava.db"` across `src/` and `tests/`.

### Production callers (src/) — migrate in D-10 order
| File | Imports today | Migrate to |
|------|---------------|------------|
| `application/aggregate_services.py` | `ReadConn, repository_from_connection` | `ReadConn` from `adapters/duckdb/connection`; `DuckDBRepository.from_connection` direct (D-04) |
| `application/metric_services.py` | `ReadConn, repository_from_connection` | same |
| `application/product_facts.py` | `ReadConn` | `adapters/duckdb/connection` |
| `application/freshness.py` | `DbConn, repository_from_connection` | `MirrorConn` + direct factory |
| `application/mirror_coverage.py` | `DbConn, repository_from_connection` | `MirrorConn` + direct factory |
| `cli.py` | `DbConn, refresh_token, repository_from_connection, repository_from_path` + `api_request` (local import L122) | `MirrorConn`, `StravaClient` (refresh_token + api_request), direct factories |
| `sync.py` | `DbConn` | `MirrorConn` from `adapters/duckdb/connection` |
| `refresh/bootstrap.py` | `DbConn, repository_from_connection` | `MirrorConn` + direct factory; also drop its duplicate `_read_token_values`/`_required_strava_client` if D-06 centralizes creds |
| `refresh/worker.py` | `DbConn, repository_from_connection` | `MirrorConn` + direct factory |

### Test couplings (tests/) — retarget, do not leave dangling
| File | Coupling | Action |
|------|----------|--------|
| `conftest.py` (L58-62) | imports + calls `reset_thread_connections` in isolation fixture | repoint import to `adapters/duckdb/connection`; **RI-01 confirmed: fixture must keep calling it** |
| `test_metric_services.py` (L368-409) | `import mcp_strava.db as db`; monkeypatches `db._db_path`, `db.open_expected_mirror_db`, calls `db.reset_thread_connections` | repoint module + all three monkeypatch targets to `adapters/duckdb/connection` |
| `test_repository_boundary.py` (L348, L369) | `import mcp_strava.db as legacy_db`; monkeypatches `legacy_db.api_request`/`refresh_token`; imports `DbConn, repository_from_connection` | repoint to `StravaClient` method targets + `MirrorConn`/direct factory |
| `test_smoke.py` (L21), `test_phase01_validation.py` (L9) | `from mcp_strava.db import DbConn` | `MirrorConn` from `adapters/duckdb/connection` |
| `test_security_guards.py` (L200-205) | AST guard `init_db` has no DDL + `sync` never calls `init_db` | **`init_db` is being deleted** — remove or rewrite these guards (the "no DDL in init_db" invariant becomes vacuous once the symbol is gone) |
| `test_security_guards.py` (L468-485) | negative-import guards on literal strings `mcp_strava.db.api_request` / `mcp_strava.db.refresh_token` | update literals to the new home (`mcp_strava.adapters.strava.client.*` or whatever the facade method path is) so the guard still protects metric/read modules from pulling network code |

## Common Pitfalls

### Pitfall 1: Splitting the thread-local pool from its reset hook
**What goes wrong:** `_thread_state` and `reset_thread_connections` land in different modules → conftest resets a different thread-local than the read path uses.
**Why it happens:** Treating each function as independently movable.
**How to avoid:** Move `_thread_state` + `ReadConn` + `_thread_read_connections` + `reset_thread_connections` together, in one edit, to `connection.py`. (D-02 "verbatim.")
**Warning signs:** `test_read_path_reuses_connection_and_checks_schema_once` asserting `open_calls["n"] == 1` starts failing (a second open means the pool isn't shared).

### Pitfall 2: Leaving security-guard literals pointing at the deleted module
**What goes wrong:** After `db.py` deletion, `mcp_strava.db.api_request` string in `test_security_guards.py` matches nothing → the guard passes vacuously, silently dropping the "metric services must not import network code" protection.
**Why it happens:** String-literal guards don't error when their target disappears.
**How to avoid:** Repoint the literals to the StravaClient facade path **in the same step** that creates the facade.
**Warning signs:** Guard test green but a metric module imports `StravaClient` unnoticed.

### Pitfall 3: `just test` (Docker) vs `uv run pytest` (local) divergence
**What goes wrong:** Phase 11 SUMMARY notes `uv run pytest` historically needed duckdb in-env. Verified now: duckdb 1.5.3 IS in the venv and all 323 tests collect/run locally.
**How to avoid:** Use `uv run pytest -q` (fast, ~1s collection) for per-task gates; reserve full `just test` (Docker build + container smoke) for the phase gate. Both must be green before delete-`db.py`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | test/lint runner | ✓ | (project standard) | — |
| pytest | unit suite | ✓ | >=9 | — |
| duckdb | storage + tests | ✓ | 1.5.3 (in venv) | — |
| docker compose | `just test` smoke gate | ✓ (server has Docker) | — | `uv run pytest -q` covers unit regressions; smoke is phase-gate only |
| just | command surface | ✓ | /usr/bin/just | run recipes manually |

**Missing dependencies with no fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`) |
| Quick run command | `uv run pytest -q -x` (targeted: `uv run pytest -q tests/test_metric_services.py -x`) |
| Full suite command | `uv run pytest -q` (323 tests, ~runs locally) then `just test` (adds Docker build + container smoke) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| Core/domain separation | Connection helpers behave identically after move | unit | `uv run pytest -q tests/test_repository_boundary.py tests/test_metric_services.py -x` | ✅ |
| Core/domain separation | Thread-local read pool reuse + reset preserved | unit | `uv run pytest -q tests/test_metric_services.py::test_read_path_reuses_connection_and_checks_schema_once -x` | ✅ |
| Core/domain separation | Security guards (no network import in read paths) still enforce against new home | unit | `uv run pytest -q tests/test_security_guards.py -x` | ✅ (literals must be updated) |
| Core/domain separation | Smoke + phase01 validation use new connection home | unit | `uv run pytest -q tests/test_smoke.py tests/test_phase01_validation.py -x` | ✅ |
| Core/domain separation | Full behavior parity incl. MCP surface | smoke | `just test` | ✅ |

### Sampling Rate
- **Per task commit:** targeted `uv run pytest -q tests/<touched>.py -x`
- **Per wave merge:** `uv run pytest -q` (full local suite, 323 tests)
- **Phase gate:** `uv run pytest -q` green AND `just test` (Docker smoke) green before `db.py` deletion and before `/gsd-verify-work`

### Wave 0 Gaps
- None — existing 323-test suite is the regression net. CONTEXT.md D-10 explicitly states no new characterization tests are required (no behavior change). The only test edits are **retargeting** existing tests to new import paths, not adding coverage.

## Security Domain

> `security_enforcement` enabled. Stack: internal Python refactor; no new attack surface, no new inputs, no new network paths.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (no change) | Strava OAuth token flow unchanged — only relocated |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | no (no new inputs) | settings already validates env values |
| V6 Cryptography | no | no crypto touched |
| V14 Config | yes (minor) | `STRAVA_CLIENT_ID/SECRET` resolution moves into settings (D-06) — keep secrets out of logs/exceptions |

### Known Threat Patterns for this refactor
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Behavior drift during relocation breaks an existing security guard | Tampering | Keep `test_security_guards.py` green; update guard literals to the new home so read-path-network-isolation stays enforced |
| Secret leakage via new code path (client.py / settings) | Information Disclosure | Reuse settings' existing resolution; never echo `client_secret` in `StravaClient` error messages (preserve current `StravaUnavailable → RuntimeError` reason-only mapping) |
| Supply chain | Tampering | N/A — no package installs this phase (`T-12-SC` accept: no installs) |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `get_zones`/`init_db` are dead and safe to delete | Summary | LOW — grep covered src+tests incl. dynamic `getattr`/`importlib` scan (none found); the only references are a comment and AST-guard tests. If a runtime caller exists via reflection it would surface immediately in `just test` smoke. |

**All other claims verified by grep against the working tree.**

## Open Questions (RESOLVED)

1. **Should `init_db` be deleted or kept as a no-op?**
   - What we know: It is dead (no live caller); `test_security_guards.py` asserts it has no DDL and that `sync` doesn't call it.
   - What's unclear: Whether the security guard's *intent* ("the runtime must never run schema DDL") should be preserved against a different anchor after `init_db` is gone.
   - **RESOLVED:** Delete `init_db` with `db.py` (GP-02 default — dead code is removed, not kept as a no-op). The now-vacuous `init_db` DDL guards in `test_security_guards.py` are removed or retargeted to `sync.py`/runtime modules — handled in Plan 12-04 Task 3, where the executor may optionally preserve the "no runtime DDL" invariant against a live anchor if the operator values it. No checkpoint needed; the GP-02 default applies.

## Sources

### Primary (HIGH confidence)
- Working tree grep (`rg`) across `src/` and `tests/` — all import sites, monkeypatch targets, dead-code confirmation
- `src/mcp_strava/db.py`, `adapters/duckdb/connection.py`, `settings.py`, `refresh/bootstrap.py`, `adapters/strava/{__init__,types,token_provider,token_refresh,transport}.py` — read directly
- `Justfile`, `pyproject.toml` — test/lint/typecheck commands verified
- `uv run pytest -q --co` — 323 tests collected; `import duckdb` → 1.5.3 confirmed in venv

## Metadata

**Confidence breakdown:**
- Blast radius: HIGH — exhaustive grep, every site enumerated
- Dead-code calls (get_zones/init_db): HIGH — zero live callers found across src+tests
- Validation strategy: HIGH — full suite runs locally, commands verified

**Research date:** 2026-05-30
**Valid until:** 2026-06-29 (stable internal refactor; valid until source changes)
