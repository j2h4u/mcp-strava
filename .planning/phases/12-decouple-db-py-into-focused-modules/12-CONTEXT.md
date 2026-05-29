# Phase 12: Decouple db.py into focused modules - Context

**Gathered:** 2026-05-30
**Status:** Ready for planning
**Source:** discuss-phase `--analyze` + expert panel (owner delegated architecture decisions to the panel)

<domain>
## Phase Boundary

Dissolve the legacy glue module `src/mcp_strava/db.py` (235 lines, 5 mixed concerns) into focused homes — most of which already exist under `adapters/strava/` and `adapters/duckdb/` — then migrate all callers and **delete `db.py` entirely**. No behavior change; the full `just test` suite (~323 tests) must stay green throughout.

This is intra-architecture cleanup (the last meaningful coupling hotspot after Phase 10). It delivers no new product capability — every decision here is layering/placement.

</domain>

<governing_principles>
## Governing Principles (owner-locked — override panel tiebreakers)

- **GP-01 — Clean over fast.** When a clean decomposition conflicts with a quick-but-dirty shortcut, choose clean. The minimalist/Kaizen "do it dirty but fast" tendency is explicitly overruled for this phase. The owner wants the resulting code clean, even at more effort.
- **GP-02 — No backward compatibility, no legacy/compat shims.** The project has no compat obligations and is still in development. `db.py` is deleted outright; `_CompatTokenProvider` is eliminated; no transitional re-export layer. Hard-cut migration is acceptable — intermediate operability is NOT required.
- **GP-03 — Fine-grained over catch-all.** Prefer splitting into small, single-responsibility modules. The planner MAY split the StravaClient facade and the athlete-zones service across more plans/modules if they grow large; do not collapse concerns into one god-module to save effort.
- **GP-04 — Ports-and-adapters + behavior parity.** Respect the dependency rule (application depends on adapters/ports, not vice versa). DuckDB stays single-writer-owner + per-thread readers. SQL/behavior unchanged.
</governing_principles>

<decisions>
## Implementation Decisions

Decisions below were produced by an expert panel (hexagonal architect, Python legacy-refactoring specialist, pragmatic minimalist, testing/runtime-safety reviewer) and confirmed by the owner. Each maps a `db.py` concern-cluster to a home.

### Connection helpers (cluster A)
- **D-01:** Move `DbConn`, `ReadConn`, `_thread_state`/`_thread_read_connections`, `reset_thread_connections`, `init_db`, `_db_path()`, `_open_storage_connection()` into `src/mcp_strava/adapters/duckdb/connection.py` (the existing home alongside `open_expected_mirror_db`/`open_fixture_db`). DuckDB connection-lifetime logic belongs in the DuckDB adapter.
- **D-02:** Relocate the thread-local read-connection pool (`ReadConn` + `_thread_state` + `reset_thread_connections`) **verbatim** — preserve evict-on-error semantics and the reset hook exactly. This is the highest-risk move (see R-01).
- **D-03:** Rename `DbConn` → `MirrorConn` (DuckDB mirror semantics; drops the generic legacy "Db"/SQLite-era name). Keep `ReadConn` (already specific). Per GP-02 there is no compat constraint on renaming.

### Repository factories (cluster B)
- **D-04:** **Delete** `repository_from_connection` and `repository_from_path`. Callers call `DuckDBRepository.from_connection(conn)` / `DuckDBRepository.from_path(...)` directly (8 call sites). Pure indirection with no value (clean removal, GP-01).

### Auth + config (cluster C)
- **D-05:** **Delete** `_CompatTokenProvider` and `_read_token_values` (.env parsing). Per GP-02 the compat bridge is gone.
- **D-06:** `settings.py` owns Strava auth config — expose `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` alongside the existing `token_path`. Config resolution is the settings layer's job; adapters consume settings. (Confirm during research how settings currently resolves these — see R-03.)
- **D-07:** `SystemClock` / `SystemSleeper` (real implementations of the injected clock/sleeper ports, formerly `_RealClock`/`_RealSleeper`) live in their **own dedicated module**, not tucked into `transport.py`. Clean home wins over the YAGNI shortcut (GP-01). Default placement: `src/mcp_strava/adapters/strava/clock.py` (sole consumer today); promote to a shared `mcp_strava/clock.py` only if a second consumer appears. Planner picks the exact module name.

### HTTP access (cluster D)
- **D-08:** Introduce a `StravaClient` facade in `src/mcp_strava/adapters/strava/client.py`. It owns: transport construction (token provider + `RateLimitPolicy` + clock/sleeper, built from settings), the `(data, rate_headers)` return contract, the `StravaUnavailable → RuntimeError` / rate-limited-sentinel mapping, and `refresh_token()`. Replaces `_build_transport`/`api_request`/`refresh_token` glue. Facade chosen over direct `StravaTransport` use (3 consumers + centralized error mapping; GP-01/GP-03).

### Application logic (cluster E)
- **D-09:** `get_zones()` becomes an **application service** (e.g., `src/mcp_strava/application/athlete_zones.py`) depending on the repository port and the `StravaClient`. It orchestrates two adapters (DB cache + Strava HTTP) with a caching policy — textbook application-layer responsibility, not an adapter concern (dependency rule). Confirm callers before moving (R-02).

### Migration (Q7)
- **D-10:** Hard-cut migration order, running `just test` between each step: (1) land new homes additively; (2) migrate `application/*` (5 files) → (3) `refresh/*` + `sync.py` → (4) `cli.py` → (5) tests (6 files + conftest); (6) delete `db.py` last. The 323-test suite is the regression net; no new characterization tests required (no behavior change).

### Claude's Discretion
- Exact new module/file names (`clock.py`, `client.py`, `athlete_zones.py`), and whether to split the facade/service across multiple plans (GP-03 permits finer splits).
- Internal organization within `connection.py` after the helpers land.
</decisions>

<research_items>
## Research Items (for the planner / researcher — NOT user decisions)

- **RI-01:** Confirm `conftest.py`'s test-isolation fixture still invokes `reset_thread_connections` after relocation; verify no test imports the thread-local internals by path.
- **RI-02:** Locate all callers of `get_zones()` before relocating it (absent from the `from mcp_strava.db import` histogram — likely attribute access via `cli`/`hr_zones` or test-only). Confirm before moving.
- **RI-03:** `init_db`, `get_zones`, and `reset_thread_connections` did not appear in the static `from db import` import scan — verify real usage (attribute access vs dead code). Any genuinely-dead symbol is deleted, not relocated (GP-02).
- **RI-04:** Confirm how `settings.py` currently surfaces (or should surface) `STRAVA_CLIENT_ID`/`STRAVA_CLIENT_SECRET` vs the token-file parsing being removed (D-06).
</research_items>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The module being dissolved
- `src/mcp_strava/db.py` — the 235-line glue module; source of all 5 concern-clusters.

### Existing target homes (mostly already exist — reuse, don't recreate)
- `src/mcp_strava/adapters/duckdb/connection.py` — `open_expected_mirror_db`/`open_fixture_db`; receives the connection helpers (D-01).
- `src/mcp_strava/adapters/duckdb/repository.py` — `DuckDBRepository.from_connection`/`from_path`; direct target after factory deletion (D-04).
- `src/mcp_strava/adapters/strava/token_provider.py` — `FileTokenProvider`.
- `src/mcp_strava/adapters/strava/token_refresh.py` — `TokenRefreshTransport`.
- `src/mcp_strava/adapters/strava/transport.py` — `StravaTransport`.
- `src/mcp_strava/adapters/strava/rate_limit.py` — `RateLimitPolicy`.
- `src/mcp_strava/adapters/strava/__init__.py` — exports incl. `StravaUnavailable`.
- `src/mcp_strava/settings.py` — config/settings home (D-06).

### Callers to migrate (blast radius)
- `src/mcp_strava/application/{aggregate_services,freshness,metric_services,mirror_coverage,product_facts}.py`
- `src/mcp_strava/{cli.py,sync.py}`, `src/mcp_strava/refresh/{bootstrap,worker}.py`
- `tests/{conftest,test_metric_services,test_phase01_validation,test_repository_boundary,test_security_guards,test_smoke}.py`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `adapters/strava/*` — token provider, refresh transport, transport, rate-limit policy all already exist; `db.py` only wires them. The StravaClient facade composes these, not reimplements them.
- `adapters/duckdb/connection.py` + `DuckDBRepository.from_*` — connection/repo construction already exists; `db.py` factories are thin pass-throughs.

### Established Patterns
- Injected clock/sleeper ports (transport timing testability) — keep the port; relocate the real impls (D-07).
- Single-writer DuckDB owner + per-thread cached readers — the `ReadConn` thread-local pool implements the reader half; its semantics must not change (R-01).

### Integration Points
- `get_zones` is the only cross-adapter orchestration (DB + HTTP) → becomes the application service that depends on both ports (D-09).
</code_context>

<specifics>
## Specific Ideas

- Owner is not an architecture specialist and explicitly delegated layering decisions to the expert panel; the panel output above is the authority, governed by GP-01..GP-04.
- "Clean, even if slower" is the explicit tone for this phase (GP-01).
</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within the phase scope (decoupling `db.py`). No new capabilities surfaced.
</deferred>

---

*Phase: 12-decouple-db-py-into-focused-modules*
*Context gathered: 2026-05-30 via discuss-phase --analyze + expert panel*
