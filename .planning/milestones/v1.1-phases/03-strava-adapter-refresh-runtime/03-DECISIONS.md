---
phase: 03-strava-adapter-refresh-runtime
addendum_for:
  - 03-01-PLAN.md
  - 03-02-PLAN.md
  - 03-03-PLAN.md
  - 03-04-PLAN.md
origin: 03-REVIEWS.md cycle 1 (opencode/deepseek-v4-pro, 2026-05-21)
status: locked
---

# Phase 3 Locked Decisions Addendum

This file locks the four design gates raised by the cycle-1 cross-AI review
(`03-REVIEWS.md`) as well as the SQL syntax for the dedupe constraint. Every
PLAN.md in this phase MUST honour these decisions; conflicting wording in a
specific plan is superseded by this addendum.

The five decisions below correspond to the five HIGH-severity concerns in
`03-REVIEWS.md`. Each decision specifies (a) the choice, (b) the rationale,
(c) the concrete contract the executor must implement, and (d) which plan
owns the implementation.

---

## D-15 — `run_once(force=False)` plus thin `sync_now` wrapper (resolves HIGH-1)

**Choice.** Add a `force: bool = False` parameter to
`refresh.runtime.run_once(...)`. When `force=False` (default), the daily
idempotency check applies (a second invocation on the same local calendar day
after `checkpoint_stage='complete'` short-circuits with
`RefreshSkipped('already_complete')`). When `force=True`, the daily
idempotency check is skipped but the lease, checkpoint resume, freshness
state machine, and product-safe error codes all still apply.

`refresh.runtime.run_once` is the single entrypoint; there is **no** separate
`sync_now()` function. `sync_activities(quick=True)` becomes a thin wrapper
that calls `run_once(..., force=True, mode='quick')`. `sync_activities()`
(no `quick`) calls `run_once(..., force=False, mode='quick')` — same daily
idempotency as the scheduled refresh.

The `mode='quick' | 'daily'` parameter is informational metadata for
checkpoint/audit only; it does NOT change the stage sequence or persisted
schema in Phase 3. Phase 4 may use it to differentiate sync_log rows.

**Rationale.** One code path keeps lease/checkpoint discipline uniform. The
`force` flag is the minimum surface area to unblock the operator's ad-hoc
"pull new activities mid-day after a run" use case. A separate `sync_now`
would duplicate orchestration logic and risk drift.

**Contract (executor MUST implement):**

- `run_once(repo, transport, policy, clock, sleeper, *, owner='refresh-runtime', force: bool = False, mode: str = 'daily')`.
- When `force=True`, skip the `last_success_at is today AND checkpoint_stage == complete` short-circuit; otherwise honour it.
- `force=True` does **not** bypass `refresh_in_progress` lease checks, backoff windows, or any STRIDE mitigations.
- CLI `db-refresh` accepts `--force` and maps it to `run_once(force=True)`.
- `RefreshSkipped` reasons remain in the existing set; `force=True` cannot return `already_complete`.

**Owner plans.** 03-02 (runtime signature, lease/idempotency tests), 03-04
(sync wrapper wiring, CLI `--force` flag, end-to-end smoke).

---

## D-16 — Separate `run_backfill` entrypoint (resolves HIGH-2)

**Choice.** Add a sibling entrypoint
`refresh.runtime.run_backfill(repo, transport, policy, clock, sleeper, *, since: str | None = None, owner='refresh-backfill')`
in `src/mcp_strava/refresh/runtime.py`. **Do not** parameterize `run_once`
with `mode='backfill'`.

Backfill executes a restricted stage subset — `streams` and `details` only —
over activities whose `streams` rows or `details` payload are missing
(GAP-only). It does NOT run `summaries`, `schema_validate`, or `kudos`.
It still acquires the lease, persists checkpoint progress, persists
product-safe error codes on failure, and respects `backoff_until`.

`backfill_activities()` in `sync.py` becomes a thin wrapper that builds
production collaborators and calls `run_backfill(...)`.

**Rationale.** Backfill has a different stage profile from daily refresh:
the summaries page walk would burn quota fetching activity lists the mirror
already has, and the kudos stage is irrelevant for historical gap-fill.
Treating backfill as a parameter of `run_once` would either (a) require
branching inside every stage helper or (b) silently re-run the full
sequence and burn quota. A dedicated function is clearer and audit-friendly.

**Contract (executor MUST implement):**

- `run_backfill(repo, transport, policy, clock, sleeper, *, since=None, owner='refresh-backfill') -> RefreshResult`.
- Stage subset: `streams_backfill -> details_backfill -> complete_backfill`. These names share infrastructure with the `Stage` enum but live as backfill-specific values (e.g. `Stage.streams_backfill`, `Stage.details_backfill`, `Stage.complete_backfill`) so checkpoint resume cannot confuse a daily refresh with a backfill mid-flight.
- Activity selection: `repo.activities_missing_streams(since)` and `repo.activities_missing_details(since)` (these helpers exist or are added in 03-03 if missing — see 03-03 task notes below).
- Lease owner string differs from daily (`refresh-backfill`) so dashboards can distinguish.
- On `StravaUnavailable`, persists the same product-safe codes through `record_refresh_failure`.

**Owner plans.** 03-02 (`run_backfill` implementation + tests), 03-03
(repository helpers if not already present), 03-04 (backfill wrapper wiring
in `sync.py`).

---

## D-17 — Sync helpers move to `refresh/_sync_ops.py` (resolves HIGH-3)

**Choice.** Move the following helpers out of `sync.py` and into a new
private module `src/mcp_strava/refresh/_sync_ops.py`:

- `_sync_kudos`
- `_insert_streams`
- `_replace_streams`
- `_stream_payload`
- `STREAM_KEYS`
- `_is_iso_day`
- `_safe_quick_sync_start_day`

The new module is private (`_sync_ops`) to make it clear that callers
outside the refresh package must not import it directly.

**Dependency direction (one-way, enforced by AST guard in 03-04):**

```
sync.py  --(imports)-->  refresh/__init__.py
                          |
                          v
                         refresh/runtime.py
                          |
                          v
                         refresh/_sync_ops.py
```

`refresh/*` never imports from `sync.py`. `sync.py` may import from
`refresh/` only via its public API (`refresh.runtime.run_once`,
`refresh.runtime.run_backfill`, `refresh.RefreshPolicy`, `refresh.RefreshResult`,
`refresh.RefreshSkipped`). The private `refresh._sync_ops` module is not
re-exported from `refresh/__init__.py`.

**Rationale.** Co-locating Strava-shaped helpers (streams payload, kudos
sync) with the runtime that owns refresh orchestration eliminates the
circular-import risk and keeps `sync.py` a pure entrypoint shim. The
one-way dependency rule is testable via AST walk.

**Contract (executor MUST implement):**

- Create `src/mcp_strava/refresh/_sync_ops.py` with the seven names listed.
- Delete the matching definitions from `sync.py` (do not leave duplicates).
- `refresh/runtime.py` imports `_sync_ops` directly; never goes through `sync.py`.
- 03-04 boundary test `test_refresh_does_not_import_sync` walks `src/mcp_strava/refresh/**.py` and asserts no `from mcp_strava.sync` / `import mcp_strava.sync` line exists.
- `refresh/__init__.py` does NOT re-export `_sync_ops` symbols.

**Owner plans.** 03-02 (move helpers, import them in `runtime.py`), 03-04
(delete from `sync.py`, add AST boundary test).

---

## D-18 — `TokenRefreshTransport` owns OAuth retry budget (resolves HIGH-4)

**Choice.** Introduce a dedicated `TokenRefreshTransport` inside
`src/mcp_strava/adapters/strava/token_refresh.py` that owns the OAuth POST
to `https://www.strava.com/oauth/token` with its own retry policy. The
`FileTokenProvider` takes a `TokenRefreshTransport` instance (not a raw
`Callable`) in its constructor. The data-fetch `StravaTransport` retry
budget is **completely separate** from the OAuth retry budget.

**Retry policies (locked):**

- **Data-fetch transport (`StravaTransport.fetch`):** up to 3 attempts on
  429/`URLError`/`OSError`/`socket.timeout`; backoff `[1, 5, 30]` seconds.
  Exhaustion raises `StravaUnavailable('rate_limited' | 'network_unstable')`.
- **Token-refresh transport (`TokenRefreshTransport.refresh_tokens`):** up to 3
  attempts on `URLError`/`OSError`/`socket.timeout`; backoff `[2, 8, 30]`
  seconds. Exhaustion raises `StravaUnavailable('token_unavailable')`. Does
  NOT retry on HTTP 4xx (those indicate a permanent refresh-token problem
  the operator must address).
- The data-fetch transport's retry counter is **not** decremented by token
  refresh attempts. A 401 inside `StravaTransport.fetch` consumes ONE
  data-fetch attempt to refresh tokens (via `token_provider.refresh`), and
  the token refresh itself spends its own (up to 3) attempts internally. If
  the token refresh raises `StravaUnavailable('token_unavailable')`, the
  data-fetch transport surfaces that exception immediately without consuming
  its remaining 429/network retry budget.

**Rationale.** Separating retry budgets prevents a flaky OAuth endpoint from
exhausting the data-fetch attempts (and vice versa). The two failure
domains map to two distinct product-safe reason codes
(`token_unavailable` vs `network_unstable`/`rate_limited`), and the operator
needs to be able to tell them apart in `refresh_state.last_error_code`.

**Contract (executor MUST implement):**

- `src/mcp_strava/adapters/strava/token_refresh.py` defines class `TokenRefreshTransport(http: Callable = urlopen, clock: Clock, sleeper: Sleeper)` with method `refresh_tokens(refresh_token: str) -> RefreshedTokens(access_token, refresh_token, expires_at)`.
- `FileTokenProvider.__init__(path, refresh_transport: TokenRefreshTransport)` — no raw `Callable` constructor parameter remains.
- Tests in `tests/test_strava_adapter.py` cover: (a) data-fetch transport on 401 calls `TokenRefreshTransport.refresh_tokens` exactly once and retries the data call exactly once; (b) when `TokenRefreshTransport.refresh_tokens` raises `StravaUnavailable('token_unavailable')`, the data-fetch transport re-raises immediately without spending its remaining 429/network attempts; (c) network failures inside `refresh_tokens` exhaust its own 3-attempt budget before raising.

**Owner plans.** 03-01 (introduce module, types, tests), 03-04 (CLI/sync
wiring builds both transports).

---

## D-19 — `refresh_requests` dedupe uses partial unique index (resolves HIGH-5)

**Choice.** The dedupe constraint on `refresh_requests` is implemented as a
**partial unique index**, not a SQL `UNIQUE(...)` table constraint with a
synthetic column. SQLite does not allow function expressions in
`CREATE TABLE ... UNIQUE(...)`, so any wording that referenced
`UNIQUE(reason, requested_for_day, consumed_at_is_null)` (in PLAN text or
PATTERNS.md) is superseded by this addendum.

**Locked DDL (verbatim, executor uses exactly this):**

```sql
CREATE TABLE IF NOT EXISTS refresh_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reason TEXT NOT NULL,
    requested_for_day TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    consumed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_refresh_requests_dedupe
    ON refresh_requests(reason, requested_for_day)
    WHERE consumed_at IS NULL;
```

**Rationale.** The partial unique index gives exactly the semantics we want:
at most one pending row per `(reason, requested_for_day)`, while still
allowing historical consumed rows with the same `(reason, requested_for_day)`
to exist. SQLite supports partial indexes since 3.8.0 (2013).

**Consumed_at bulk strategy (per review suggestion 4):**
`mark_refresh_requests_consumed(consumed_at: str)` runs
`UPDATE refresh_requests SET consumed_at = ? WHERE consumed_at IS NULL`
(mark-all-pending). There is no `ids: list[int]` parameter, eliminating the
dynamic-SQL `WHERE id IN (?, ?, ...)` issue. The refresh-runtime always
consumes the full pending set in one pass.

**Contract (executor MUST implement):**

- Migration v2 runs the CREATE TABLE + CREATE UNIQUE INDEX above verbatim.
- `REQUIRED_INDEXES` (new in `schema.py`) contains `idx_refresh_requests_dedupe`.
- `repository.mark_refresh_requests_consumed(consumed_at)` takes a single timestamp argument; no `ids` parameter.
- `tests/test_repository_boundary.py` asserts the index exists via `PRAGMA index_list('refresh_requests')` and that calling `enqueue_refresh_request` for an already-pending `(reason, requested_for_day)` is a no-op.

**Owner plans.** 03-03 (schema, migration, repository method, tests).

---

## Cross-references

- Cycle-1 review source: `03-REVIEWS.md` § 3 "HIGH Severity".
- `PATTERNS.md` line 144 references invalid SQL — superseded by D-19.
- These five decisions extend the D-01..D-14 set established in `03-CONTEXT.md`.
- All five resolutions preserve existing STRIDE mitigations and product-safe reason codes.
