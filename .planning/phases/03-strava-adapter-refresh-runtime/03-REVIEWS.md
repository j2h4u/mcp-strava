---
phase: 3
reviewers: [opencode]
reviewed_at: 2026-05-21
plans_reviewed:
  - 03-01-PLAN.md
  - 03-02-PLAN.md
  - 03-03-PLAN.md
  - 03-04-PLAN.md
opencode_model: deepseek-v4-pro
---

# Cross-AI Plan Review — Phase 3

## OpenCode Review

# Cross-AI Plan Review: Phase 3 — Strava Adapter & Refresh Runtime

## 1. Summary

Phase 3's four-plan decomposition is architecturally sound and deeply grounded in the existing codebase. The TDD approach across all plans, the boundary enforcement via AST guards, and the hermetic test discipline are all strong. The primary structural risk is that **03-02 (refresh runtime) is under-specified regarding how existing sync logic maps into the new checkpoint stages**, and **03-04 (integration) glosses over the semantic mismatch between `run_once()` (daily idempotent refresh) and `sync_activities(quick=True)` (ad-hoc quick sync)**. If the implementer resolves these in Plan 03-02's execution, the phase should succeed.

---

## 2. Strengths

- **Architecture follows locked decisions precisely**: D-01 through D-14 are each traceable to specific modules and test assertions. The read-runtime/refresh-runtime split is enforced at the AST level, not just convention.
- **TDD-first with hermetic fakes is excellent**: `FakeStravaTransport`, `FakeClock`, `FakeSleeper`, and module-level `urlopen` monkeypatches ensure zero live network access in tests. The "never log tokens" assertions are particularly well-specified.
- **Token provider design is robust**: `fcntl.flock(LOCK_EX)` + tempfile + `os.fsync` + `os.replace` + `chmod 0o600` covers the race, crash, and permission concerns. The re-read-after-lock pattern handles cooperative single-writer refresh correctly.
- **Dual-window rate-limit policy is correct**: Tracking all four Strava limit windows (overall_short, overall_long, read_short, read_long) and enforcing `min(remaining)` is the right abstraction. The graceful fallback for missing headers (returning `None`) matches Strava's actual behavior well.
- **Checkpoint state machine maps directly to existing sync phases**: The five stages (summaries -> streams -> details -> schema_validate -> kudos -> complete) mirror the current `sync.py` structure exactly, minimizing the refactor surface.
- **Migration v2 fits the Phase 2 gate cleanly**: Preflight -> backup -> migrate -> post-check -> parity is preserved. The `REQUIRED_TABLES` extension is idiomatic with the existing schema inventory pattern.
- **AST boundary guards are concrete and enforceable**: The `_strava_adapter_import_violations()` and `test_urllib_lives_only_in_strava_adapter` patterns make boundary violations fail CI deterministically.
- **Lease via atomic UPDATE WHERE is the right complexity level**: Single-row SQLite lease avoids introducing Redis/etcd for a single-user local tool.

---

## 3. Concerns

### HIGH Severity

- **03-02 / 03-04: `run_once()` vs `sync_activities(quick=True)` semantic gap.** `run_once()` is designed as an idempotent daily refresh — it short-circuits if `last_success_at` is today. But `sync_activities(quick=True)` is called ad-hoc from the CLI to do an incremental sync regardless of whether today's refresh already ran. Plan 03-04 Task 1 says `sync_activities` becomes a thin wrapper around `run_once()`, which would break the ad-hoc sync use case (operator wants to pull new activities mid-day after a run). The plans need either a `force` parameter on `run_once()` or a separate `sync_now()` entrypoint that bypasses the daily-idempotency check while still using the checkpoint/lease machinery.

- **03-04: `backfill_activities()` refactor is under-specified.** Backfill only syncs GAP streams and details — it doesn't run summaries, schema_validate, or kudos stages. The plan says "expose a sibling runtime entrypoint (planner discretion: either parameterize `run_once` with a `mode='backfill'` flag or add `refresh.runtime.run_backfill`)." This is a critical design decision left to the implementer. If done wrong, backfill could trigger full re-sync and burn quota. The plan should lock this decision.

- **03-02: Existing sync helpers (`_sync_kudos`, `_insert_streams`, `_replace_streams`, `_stream_payload`, `STREAM_KEYS`) have no specified migration path.** Plan 03-04 says they "may remain in `sync.py` and be imported by `refresh/runtime.py`, or move into the runtime — keep them in one place only." This ambiguity means the implementer could accidentally create a circular import (`refresh/runtime.py` importing from `sync.py` which imports from `refresh/`). The plans should decide: move them to `refresh/` or keep them in `sync.py` and have `runtime.py` import from there (one-way dependency).

- **03-01: Token refresh during transport retry has ambiguous error handling.** The transport's `fetch()` handles 401 by calling `token_provider.refresh()` and retrying once. But `TokenProvider.refresh()` itself makes an HTTP call — what if THAT call fails with a network error? The plans say the token provider takes an injected `http: Callable`, but don't specify who retries the token refresh call. The transport's retry budget should not be exhausted by token refresh attempts — they're a different failure domain.

- **03-03: The dedupe constraint syntax needs exact SQLite DDL.** The plan references `UNIQUE(reason, requested_for_day, consumed_at_is_null)` but SQLite doesn't allow functions in UNIQUE constraints. The PATTERNS.md correctly specifies a partial unique index: `CREATE UNIQUE INDEX ... ON refresh_requests(reason, requested_for_day) WHERE consumed_at IS NULL`. The plan text should be corrected to avoid implementer confusion.

### MEDIUM Severity

- **03-01: Thread-based concurrency test may be flaky.** The test for `TokenProvider` uses `threading.Thread` with real `fcntl.flock`. On Linux, `flock` semantics across threads of the same process can differ from cross-process behavior. A `subprocess`-based test would be more realistic for the actual threat model (concurrent CLI invocations). The plans mention `subprocess.Popen` as an alternative — this should be the preferred approach.

- **03-04: `get_zones()` leaves a direct Strava call + direct SQLite write in `db.py`.** The plan says this is "acceptable" for Phase 3 if Phase 4 owns the zone service. But `get_zones()` writes directly to `athlete_zones` via `conn.execute("INSERT INTO athlete_zones...")` — bypassing the repository. This is inconsistent with the architecture's "all persistence through repository" principle from Phase 2.

- **03-02: Freshness state machine precedence needs explicit specification.** The plan says precedence is `refresh_in_progress` > `refresh_delayed` > `refresh_failed` > age-based. But what about `refresh_in_progress` AND `backoff_until > now()`? Can both be true? The state machine should document the exact `if/elif` chain with full condition coverage so implementers don't guess.

- **03-02: `checkpoint_cursor` for summaries stage.** The research doc says cursor for summaries is "last page completed" — but the current code uses `after=<timestamp>` based on latest activity date, not page numbers. Strava's activity list is ordered by `start_date` descending, and the `after` parameter is more robust than page cursors (activities can shift between pages). The checkpoint should store the timestamp of the last-seen activity start_date, not a page number.

- **03-03: `mark_refresh_requests_consumed(ids, consumed_at)` needs dynamic SQL.** SQLite's Python driver doesn't support `WHERE id IN (?)` with a list — you need `WHERE id IN (?, ?, ...)` with one placeholder per item. The plan should acknowledge this requires dynamic placeholder generation, which is slightly error-prone. Consider an alternative: `UPDATE refresh_requests SET consumed_at = ? WHERE consumed_at IS NULL` (mark-all-pending-at-once) since the refresh-runtime consumes all pending requests in one pass anyway.

- **03-04: `load_env()` callers are not enumerated.** The plan says to delete `load_env` from `db.py` and provide a thin shim. But `load_env` is called from `sync.py` (line 13, 177, 295), `db.py::api_request` (line 123), `db.py::get_zones` (line 156), and `db.py::refresh_token` (line 65). After the refactor, `sync.py` calls `FileTokenProvider` directly, so the shim may be unused. But if any CLI command or test imports `load_env` directly, they'll break. The plan needs a call-site audit.

- **03-02: `sync_in_progress` reason code is listed but never used.** D-13 includes `sync_in_progress` in the product-safe set, and `ALLOWED_REASON_CODES` includes it. But the runtime's `record_refresh_failure` uses `token_unavailable`, `rate_limited`, `network_unstable`, or `refresh_incomplete`. The `sync_in_progress` code appears to be unused — either it's a future placeholder or it should be removed from the whitelist to avoid confusion.

### LOW Severity

- **03-02: Timezone handling for "same local calendar day".** The `run_once()` daily-idempotency check compares `last_success_at` with `clock.now().date()`. If the clock is UTC but the user is in a different timezone, "today" may not align with the user's expectation. Mitigation: document that the clock should be local-time-aware or use a configurable timezone in Settings.

- **03-01: `StravaTransport` uses `urllib.request.urlopen` directly as default injection.** The plan says `http=urlopen` is the default. But this means the transport module imports `urllib.request` at the top level. The AST guard in 03-04 checks that only `adapters/strava/` imports `urllib` — this is correct and intentional, but it means any test that monkeypatches `urllib.request.urlopen` module-wide will break the transport's default (since the transport already imported the real `urlopen` by the time the monkeypatch runs). The transport should use `import urllib.request; urllib.request.urlopen(...)` inside the method call rather than capturing the function reference at import time, OR tests should inject the fake `http` callable at construction time (which they already do — this is fine).

- **03-03: `REQUIRED_INDEXES` is mentioned but may not exist in `schema.py`.** The existing `schema.py` uses `REQUIRED_TABLES` and `REQUIRED_COLUMNS` — `REQUIRED_INDEXES` would be a new concept. The plan should verify this pattern fits the existing preflight code or adjust accordingly.

- **03-04: `Clock` and `Sleeper` types have no canonical home.** Both the adapter transport and refresh runtime inject these collaborators. The plans don't specify whether they live in `adapters/strava/types.py`, `refresh/policy.py`, or a shared location. A concrete `Protocol` or `ABC` for each would prevent duck-typing drift.

---

## 4. Suggestions

1. **Resolve the `run_once()` vs `sync_activities(quick=True)` tension before implementation.** Add a `force: bool = False` parameter to `run_once()` that skips the daily-idempotency check but still uses the lease/checkpoint machinery. `sync_activities(quick=True)` calls `run_once(force=True, mode='quick')`. This keeps one code path while supporting both use cases.

2. **Move all sync helper functions (`_sync_kudos`, `_insert_streams`, `_replace_streams`, `_stream_payload`, `STREAM_KEYS`) into `refresh/runtime.py` or a sibling `refresh/_sync_ops.py`.** This eliminates the ambiguous import direction and keeps the refresh-runtime self-contained. `sync.py` becomes a pure collaborator-builder + delegator.

3. **Add a dedicated `TokenRefreshTransport` inside `adapters/strava/`.** The token provider shouldn't take a raw `Callable` — it should take a small `TokenRefreshTransport` that encapsulates the OAuth POST with its own retry policy. This separates token refresh retries from data-fetch retries and prevents the data transport from wasting its retry budget on token issues.

4. **Change `mark_refresh_requests_consumed` to mark ALL pending at once:** `UPDATE refresh_requests SET consumed_at = ? WHERE consumed_at IS NULL`. The refresh-runtime always consumes all pending requests in one run — there's no use case for partial consumption. This eliminates the dynamic-SQL problem.

5. **Move `get_zones()` into a small `ZonesService` that uses `SQLiteRepository` + `StravaTransport`.** Even if it lives in `db.py` with a compat shim for Phase 3, the implementation should use the repository for persistence (not raw `conn.execute`).

6. **Add an `--force` flag to `db-refresh` CLI command** that maps to `run_once(force=True)`. This gives the operator a way to trigger a mid-day refresh without waiting for the next daily cycle.

7. **Document the `Clock` and `Sleeper` protocols in `adapters/strava/types.py`** since they're shared between the adapter and refresh packages. A `typing.Protocol` is ideal for duck-type verification without runtime overhead.

8. **Add a `state_machine_precedence_table` test** that parametrizes all overlapping state conditions (e.g., `backoff_until > now AND lease_expires_at > now`) and asserts deterministic output. Six combos are easy to miss in manual implementation.

9. **Audit all `load_env()` call sites** before deleting from `db.py`. A quick `grep -r "load_env" src/ tests/` should surface every reference. Map each to its replacement (TokenProvider for new code, shim for legacy).

---

## 5. Risk Assessment

**Overall risk: MEDIUM**

The phase has strong architectural foundations, thorough research, and well-specified test coverage. The risks are concentrated in the integration boundary (Plan 03-04) where legacy CLI/sync paths meet the new runtime, and in the under-specification of how existing 386-line `sync.py` logic maps into the checkpoint stages of `refresh/runtime.py`.

The three HIGH-severity concerns (sync semantics mismatch, backfill refactor ambiguity, helper migration path) are all resolvable with clearer specification before execution begins. None requires rethinking the architecture. The MEDIUM concerns are implementation details that a careful implementer would catch, but specifying them upfront reduces rework.

Recommended gate before execution: lock the decisions on:
1. `run_once(force=)` vs separate `sync_now()`
2. `backfill_activities()` -> `run_backfill()` vs parameterized `run_once(mode='backfill')`
3. Helper function home: `refresh/` or `sync.py`
4. `get_zones()` migration strategy (repo-backed now vs Phase 4)

With those four decisions made, the implementation risk drops to LOW.

---

## Consensus Summary

Only one reviewer (OpenCode / deepseek-v4-pro) was invoked for this cycle, so this section reproduces its key findings rather than synthesizing across reviewers.

### Agreed Strengths

- TDD-first design with hermetic fakes (`FakeStravaTransport`, `FakeClock`, `FakeSleeper`)
- Robust token provider locking (`fcntl.flock` + tempfile + `os.fsync` + `os.replace` + `chmod 0o600`)
- Dual-window rate-limit policy tracking all four Strava limit windows correctly
- Checkpoint state machine mirroring existing `sync.py` phases, minimizing refactor surface
- AST boundary guards making layering violations fail deterministically in CI
- Single-row SQLite lease — right complexity level for a single-user local tool

### Agreed Concerns (HIGH)

1. **`run_once()` vs `sync_activities(quick=True)` semantic gap** — daily-idempotency check would break ad-hoc quick sync. Needs `force` flag or separate entrypoint.
2. **`backfill_activities()` refactor under-specified** — implementer choice between `mode='backfill'` flag and `run_backfill()` is left unresolved; wrong choice could burn quota.
3. **Sync helper migration path is ambiguous** — risk of circular imports between `sync.py` and `refresh/runtime.py`.
4. **Token-refresh-during-fetch error handling unclear** — who retries the OAuth POST if it fails with a network error? Transport retry budget should not be consumed by token-refresh failures.
5. **Dedupe constraint syntax is invalid SQL** — `UNIQUE(reason, requested_for_day, consumed_at_is_null)` not legal; PATTERNS.md correctly uses a partial unique index, but PLAN text must be aligned.

### Divergent Views

N/A — single reviewer in this cycle. Cross-reviewer divergence will appear once additional reviewers (Gemini, Codex, etc.) are added.

### Recommended Next Step

Lock the four gate decisions in `03-04-PLAN.md` (or a new `03-DECISIONS.md` addendum) before execution:
1. `run_once(force=)` parameter vs separate `sync_now()`
2. Backfill entrypoint shape
3. Helper function home (one-way dependency direction)
4. `get_zones()` migration strategy

Then re-run `/gsd-plan-phase 3 --reviews` to fold the addendum into the plans.
