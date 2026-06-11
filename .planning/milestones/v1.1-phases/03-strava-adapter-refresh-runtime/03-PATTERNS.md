# Phase 3: Strava Adapter & Refresh Runtime - Pattern Map

**Mapped:** 2026-05-21
**Files analyzed:** 14 planned new/modified files
**Analogs found:** 14 / 14

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/mcp_strava/adapters/strava/__init__.py` | package marker | import boundary | `src/mcp_strava/adapters/sqlite/__init__.py` | exact |
| `src/mcp_strava/adapters/strava/types.py` | contract | dataclasses + enums | `src/mcp_strava/adapters/sqlite/schema.py` (PreflightReport pattern), `src/mcp_strava/types.py` | exact |
| `src/mcp_strava/adapters/strava/token_provider.py` | adapter | atomic file write + flock | `src/mcp_strava/db.py` (load_env/save_env legacy), `src/mcp_strava/adapters/sqlite/backup.py` (atomic file write idiom) | role-match |
| `src/mcp_strava/adapters/strava/rate_limit.py` | adapter | header parsing + budget | `src/mcp_strava/sync.py::RateLimiter` | role-match |
| `src/mcp_strava/adapters/strava/transport.py` | adapter | HTTPS + retry + 401/429 | `src/mcp_strava/db.py::api_request`, `src/mcp_strava/sync.py::_fetch_with_retry` | role-match |
| `src/mcp_strava/refresh/__init__.py` | package marker | import boundary | `src/mcp_strava/adapters/sqlite/__init__.py` | exact |
| `src/mcp_strava/refresh/checkpoints.py` | runtime | stage enum + transitions | `src/mcp_strava/adapters/sqlite/schema.py` (data-as-code inventory) | role-match |
| `src/mcp_strava/refresh/policy.py` | runtime | typed config | `src/mcp_strava/settings.py` (FreshnessSettings) | role-match |
| `src/mcp_strava/refresh/freshness.py` | runtime | pure state machine | `src/mcp_strava/adapters/sqlite/repository.py::daily_load_status` (status-derivation pattern) | role-match |
| `src/mcp_strava/refresh/runtime.py` | runtime | orchestration | `src/mcp_strava/sync.py::sync_activities` | role-match |
| `src/mcp_strava/adapters/sqlite/repository.py` | repository | refresh_state + refresh_requests methods | `src/mcp_strava/adapters/sqlite/repository.py::append_sync_log/read_sync_log` | exact |
| `src/mcp_strava/adapters/sqlite/schema.py` | adapter | REQUIRED_TABLES inventory | `src/mcp_strava/adapters/sqlite/schema.py` (extension) | exact |
| `src/mcp_strava/adapters/sqlite/migrations.py` | adapter | migration v2 | `src/mcp_strava/adapters/sqlite/migrations.py` (extension) | exact |
| `src/mcp_strava/sync.py` | thin wrapper | uses StravaTransport via DI | `src/mcp_strava/sync.py` (refactor) | role-match |
| `src/mcp_strava/db.py` | thin compat | legacy `refresh_token/api_request` redirect to adapter | `src/mcp_strava/db.py` (refactor) | role-match |
| `src/mcp_strava/cli.py` | CLI dispatcher | adds `db-refresh` | `src/mcp_strava/cli.py` (extension) | exact |
| `tests/test_strava_adapter.py` | test | adapter behavior with fakes | `tests/test_sqlite_safety.py` | role-match |
| `tests/test_refresh_runtime.py` | test | runtime behavior with fakes | `tests/test_load_status.py`, `tests/test_sqlite_safety.py` | role-match |
| `tests/test_security_guards.py` | test (extension) | AST/import boundary | `tests/test_security_guards.py::_direct_sqlite_violations` | exact |
| `tests/test_repository_boundary.py` | test (extension) | repository surface assertions | `tests/test_repository_boundary.py` | exact |

## Pattern Assignments

### `src/mcp_strava/adapters/strava/token_provider.py`

**Analog:** `src/mcp_strava/db.py::load_env/save_env` (legacy) + `src/mcp_strava/adapters/sqlite/backup.py` (atomic file write).

**Current pattern to preserve:** Key=value file format (one pair per line). Token reads return a dict-like mapping. Key set: `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_ACCESS_TOKEN`, `STRAVA_REFRESH_TOKEN`. Token path comes from `Settings.token_path`.

**Required deviation:**
- `save_env()` truncates and writes line-by-line — replace with tempfile + `os.fsync` + `os.replace` (atomic rename) like `backup.py` does for SQLite copies.
- Add `fcntl.flock(LOCK_EX)` on a sidecar `.lock` file so concurrent processes serialize OAuth refresh attempts.
- Read-after-lock to absorb the case where another process already refreshed (cooperative single-writer).
- `chmod 0o600` after `os.replace` (preserve existing file mode discipline; `.env` is already gitignored per `tests/test_security_guards.py`).
- Never raise an exception containing the access/refresh token value. Tests must assert.

### `src/mcp_strava/adapters/strava/rate_limit.py`

**Analog:** `src/mcp_strava/sync.py::RateLimiter`.

**Current pattern to preserve:** Server-reported usage via `X-RateLimit-Usage` is more accurate than client-side counters; the existing `update_from_headers()` semantics are correct in spirit.

**Required deviation:**
- Existing `RateLimiter` tracks ONE counter (short overall). New `RateLimitPolicy` tracks FOUR: `(overall_short, overall_long, read_short, read_long)`. Each is a `(used, limit)` pair.
- `decide_next_call()` returns one of: `proceed`, `wait_until(timestamp)`, `exhausted(reason)`. The refresh-runtime acts on this enum rather than calling `wait()`.
- Decision uses `min` of remaining across all four windows.
- Sleeping is delegated to an injected `Sleeper` (so tests fake it).
- No `print(..., file=sys.stderr)` — return values and structured events only. Logging belongs to the runtime, not the policy.

### `src/mcp_strava/adapters/strava/transport.py`

**Analogs:** `src/mcp_strava/db.py::api_request`, `src/mcp_strava/sync.py::_fetch_with_retry`.

**Current pattern to preserve:**
- `urllib.request.Request` + Authorization bearer header.
- 401 → refresh token → retry once.
- 429 → parse `Retry-After`, sleep, retry up to 3 attempts.
- 404 → return None (skip).
- Network errors (URLError/HTTPError/socket.timeout/OSError) → exponential delay schedule `[1, 5, 30]` seconds.

**Required deviation:**
- Token acquisition delegated to injected `TokenProvider.access_token()` (no direct `load_env()`).
- Rate-limit decisions delegated to injected `RateLimitPolicy.decide_next_call()`.
- Sleep delegated to injected `Sleeper.sleep(seconds)`.
- Time read delegated to injected `Clock.now()`.
- Return type becomes typed `StravaResponse(data, rate_info, status)` instead of `(data, rate_info)` tuple — gives tests a clear surface.
- Never include the bearer token value in any error message or log line.
- After 3 failed attempts, raise a typed `StravaUnavailable(reason)` instead of returning `None`; the runtime decides whether to mark `last_error_code='network_unstable'`.

### `src/mcp_strava/refresh/checkpoints.py`

**Analog:** `src/mcp_strava/adapters/sqlite/schema.py` (data-as-code inventory pattern: `REQUIRED_TABLES`, `REQUIRED_COLUMNS`).

**Pattern:** Define a small `Stage` enum (or `str` constants) and a transition table mapping `stage → next_stage`. Each stage knows whether it has a cursor (e.g., `streams` has `last_activity_id`; `schema_validate` does not). The runtime reads `(stage, cursor)` from `refresh_state`, runs that stage, writes `(next_stage, new_cursor)` atomically, and repeats. The same shape as the sequential 5-phase sync in `sync.py::sync_activities`, lifted out of the function body.

### `src/mcp_strava/refresh/policy.py`

**Analog:** `src/mcp_strava/settings.py::FreshnessSettings`.

**Pattern:** A frozen dataclass with typed defaults. Phase 3 adds:
- `lease_duration_seconds` (default ~600, planner discretion).
- `backoff_seconds_on_rate_limit` (default seconds-until-15min-boundary).
- `backoff_seconds_on_network` (default capped at 60).
- `backoff_seconds_on_token_failure` (default ~3600 — token may need operator intervention).

Inputs come from existing `Settings.freshness` plus a new `RefreshPolicy` dataclass exposed through the same `get_settings()` resolver shape.

### `src/mcp_strava/refresh/freshness.py`

**Analog:** `src/mcp_strava/adapters/sqlite/repository.py::daily_load_status` (existing pure-function-over-row pattern that returns a typed status).

**Pattern:** Pure function `evaluate(refresh_state_row, now, policy) -> FreshnessState`. Inputs are dataclass; output is one of the six states per D-05. No I/O. Trivially testable with fixture rows.

### `src/mcp_strava/refresh/runtime.py`

**Analog:** `src/mcp_strava/sync.py::sync_activities`.

**Current pattern to preserve:** Five-phase sequence: summaries → streams → details → schema_validate → kudos. Append a `sync_log` row at the end with counts. Use `DbConn() as conn` and `SQLiteRepository.from_connection(conn)`.

**Required deviation:**
- The five phases become explicit checkpoint stages from `checkpoints.py`.
- Phase entrypoint: `run_once(repo, transport, policy, clock, sleeper) -> RefreshResult`. All collaborators are injected so tests use fakes.
- Before doing work: `repo.acquire_refresh_lease(owner, expires_at)`. If lease unavailable, return `RefreshSkipped(reason='refresh_in_progress')`.
- After each stage: `repo.set_checkpoint(stage, cursor)`. Crash here = resume from this stage next time.
- On `StravaUnavailable` from transport: persist `last_error_code` to one of `token_unavailable`/`rate_limited`/`network_unstable`/`refresh_incomplete` per D-13; mark `last_attempt_at`; set `backoff_until` from policy; release lease.
- On success of all stages: write `last_success_at`, set `checkpoint_stage='complete'`, append a `sync_log` row (preserving the existing audit trail).
- Existing `_sync_kudos`, `_replace_streams`, `_insert_streams` helpers move next to the runtime (refresh-runtime co-owns them with the adapter), or stay where they are if the planner prefers minimal motion.

### `src/mcp_strava/adapters/sqlite/repository.py` (extension)

**Analog:** existing `append_sync_log` / `read_sync_log` / `latest_athlete_zones` methods.

**Pattern (apply to new methods):**
- Parameterized SQL, explicit commit, return typed dataclasses or primitives.
- Tests in `tests/test_repository_boundary.py` enumerate method names — extend that enumeration.
- New methods (planner-renamable):
  - `get_refresh_state() -> RefreshStateRow`
  - `acquire_refresh_lease(owner: str, expires_at: str, now: str) -> bool` — single atomic UPDATE WHERE; returns True if acquired.
  - `release_refresh_lease(owner: str) -> None`
  - `set_checkpoint(stage: str, cursor: str | None) -> None`
  - `record_refresh_attempt(at: str) -> None`
  - `record_refresh_success(at: str) -> None`
  - `record_refresh_failure(at: str, reason_code: str, backoff_until: str | None) -> None`
  - `enqueue_refresh_request(reason: str, requested_for_day: str) -> bool` — uses `INSERT OR IGNORE` over a `(reason, requested_for_day)` unique key; returns True if a new row was created.
  - `pending_refresh_requests() -> list[RefreshRequestRow]`
  - `mark_refresh_requests_consumed(ids: list[int], consumed_at: str) -> None`

### `src/mcp_strava/adapters/sqlite/schema.py` (extension)

**Pattern:** Append two table names to `REQUIRED_TABLES`. Add their column inventories to `REQUIRED_COLUMNS`. Bump implicit `user_version` target to 2 in `migrations.py`. Mirror existing `idx_streams_act` requirement style.

Proposed shape (planner discretion on exact column names/types):
- `refresh_state(id INTEGER PRIMARY KEY, last_success_at TEXT, last_attempt_at TEXT, last_status TEXT, last_error_code TEXT, lease_owner TEXT, lease_expires_at TEXT, backoff_until TEXT, checkpoint_stage TEXT, checkpoint_cursor TEXT)` — single row with `id=1`.
- `refresh_requests(id INTEGER PRIMARY KEY AUTOINCREMENT, reason TEXT NOT NULL, requested_for_day TEXT NOT NULL, requested_at TEXT NOT NULL, consumed_at TEXT)` PLUS `CREATE UNIQUE INDEX idx_refresh_requests_dedupe ON refresh_requests(reason, requested_for_day) WHERE consumed_at IS NULL` (locked by D-19 in 03-DECISIONS.md — SQLite does not support function expressions inside `UNIQUE(...)`, so the dedupe must live in a partial unique index).

### `src/mcp_strava/adapters/sqlite/migrations.py` (extension)

**Analog:** existing `run_preflight` / migration v1 baseline.

**Pattern:** Add migration step `v1 → v2` that CREATEs `refresh_state` and `refresh_requests`, seeds `refresh_state` with `id=1` and empty values. Preflight extends to include these tables. Preserves parity invariants (row counts for old tables unchanged).

### `src/mcp_strava/sync.py` (refactor)

**Analog:** itself (refactor in place).

**Pattern:**
- Top-level `sync_activities(quick=True)` and `backfill_activities()` keep their public names so CLI continues to work, but bodies become wrappers around `refresh.runtime.run_once(...)` (constructed with the production adapter, settings-derived policy, real clock and sleeper).
- Remove direct `from mcp_strava.db import load_env, api_request`; replace with `from mcp_strava.adapters.strava import StravaTransport, FileTokenProvider, RateLimitPolicy`.
- Existing helpers (`_stream_payload`, `_insert_streams`, `_replace_streams`) either stay (purely data-shape) or move next to the runtime — planner discretion.
- Inline `RateLimiter` class deletes; `_fetch_with_retry` deletes (both move to adapter).
- `_sync_kudos` stays callable but is invoked from the runtime's `kudos` checkpoint stage.

### `src/mcp_strava/db.py` (refactor)

**Analog:** itself.

**Pattern:**
- Delete inline `load_env`, `save_env`, `refresh_token`, `api_request`, `_parse_rate_headers`.
- Provide thin compatibility shims `refresh_token()` and `api_request(path, token=None)` that delegate to the Strava adapter. Keep them around only to avoid touching every callsite at once. Phase 4 may remove them.
- Existing `DbConn` and `init_db` (already assertion-only after Phase 2) unchanged.
- `get_zones()` is a borderline case: it currently calls Strava via `api_request`. Either:
  - (a) Move it behind a small `ZonesService(repo, transport)` — preferred; or
  - (b) Keep the function but have it use the adapter via the thin shim — acceptable for Phase 3 if Phase 4 will own the zone service.

### `src/mcp_strava/cli.py` (extension)

**Analog:** existing operator commands `db-preflight`, `db-check`, `db-migrate`.

**Pattern:** Add `db-refresh` to `COMMANDS`. Backed by `refresh.runtime.run_once(...)`. Phase 4 may re-shape but Phase 3 keeps it consistent with the existing operator surface so `tests/test_security_guards.py::test_cli_has_operator_only_sql_and_explicit_db_safety_commands` can be extended to assert `db-refresh` is present.

Existing CLI imports `refresh_token, api_request, get_daily_trimp_history` from `db`; these continue to work through compat shims but the CLI command bodies should preferentially call into `adapters/strava` directly where straightforward (the planner picks the timing).

### `tests/test_strava_adapter.py`

**Analog:** `tests/test_sqlite_safety.py`.

**Pattern:**
- Use `tmp_path` + `monkeypatch` + `reset_settings_cache()` for token paths.
- Never write to the real `.env`.
- Concurrency test for `TokenProvider.refresh_if_needed()`: spawn 2 threads (or subprocesses for stronger flock semantics) that race; assert exactly one fetched-from-Strava call is made via fake transport; assert the final token file contains a single consistent key=value set.
- Crash-injection test: simulate a SIGKILL between tempfile write and `os.replace` (use a thin wrapper test that raises after fsync), assert the original file is unchanged and the temp file is cleaned up.
- Rate-limit policy test: feed synthetic header pairs covering each window pair; assert correct `decide_next_call()` outputs.
- Transport test: inject a fake `urlopen` (via subclassing `Request` or by injecting a callable) that returns canned bodies/headers/exceptions; assert retry schedule, 401 refresh path, 429 backoff.
- Never-log-token test: capture stderr; verify no `STRAVA_ACCESS_TOKEN` value appears in any error formatted by adapter code paths.

### `tests/test_refresh_runtime.py`

**Analog:** `tests/test_load_status.py`, `tests/test_sqlite_safety.py`.

**Pattern:**
- Use a copied or in-memory SQLite fixture pre-populated with the new tables.
- `FakeStravaTransport` returns scripted page payloads, scripted 429 timing, and synthetic empty kudos.
- `FakeClock` and `FakeSleeper` deterministic.
- `test_daily_completion`: empty `refresh_state`, run_once() reaches `complete`.
- `test_resume_from_checkpoint`: pre-set `checkpoint_stage='streams'` with a cursor; assert summaries are NOT refetched; assert streams resumes from cursor; assert final stage = `complete`.
- `test_rate_limit_backoff_then_resume`: fake transport raises rate-limited mid-streams; assert `last_error_code='rate_limited'`, `backoff_until` set, lease released; second call before backoff is `refresh_delayed`; third call after fake clock advance succeeds.
- `test_lease_concurrency`: two `run_once()` invocations interleaved by fake clock; second receives `RefreshSkipped(reason='refresh_in_progress')`.
- `test_freshness_signal`: read-runtime helper enqueues refresh_request on stale; second enqueue with same `(reason, requested_for_day)` is a no-op.
- `test_freshness_state_machine`: parametrized table of fixture rows → expected `FreshnessState` (pure function, no DB).

### `tests/test_security_guards.py` (extension)

**Analog:** existing `_direct_sqlite_violations` AST walker.

**Pattern:** Add `_strava_adapter_import_violations()` walker:
- Read modules: `report.py`, `analytics.py`, `trends.py`, `training.py`, `metrics.py`, `cardiac_drift.py`.
- Forbidden imports: any name under `mcp_strava.adapters.strava` or `mcp_strava.refresh`.
- Allowed exceptions: explicitly none (these read modules must never touch Strava).
- Also assert `cli.py::COMMANDS` includes `db-refresh`.
- Also assert `sync.py` no longer imports `urllib` directly (transport moved to adapter).

### `tests/test_repository_boundary.py` (extension)

**Pattern:** Add tests that:
- Call each new method (`get_refresh_state`, `acquire_refresh_lease`, …) on a temp DB with the v2 schema applied.
- Assert lease atomicity: simulate two acquire calls; only the first returns True.
- Assert `enqueue_refresh_request` is idempotent: repeated calls with same `(reason, requested_for_day)` produce exactly one pending row.
- Assert no new direct `sqlite3` imports outside `adapters/sqlite/` (i.e., the existing `_direct_sqlite_violations()` test still passes after Phase 3 wiring).

## Cross-Cutting Notes

- All Strava IO touches one and only one of: `adapters/strava/transport.py` (calls Strava), `adapters/strava/token_provider.py` (reads/writes token file). All SQLite IO touches one and only one of: `adapters/sqlite/repository.py`, `adapters/sqlite/migrations.py`, `adapters/sqlite/schema.py`, `adapters/sqlite/connection.py`, `adapters/sqlite/backup.py`.
- The `refresh/` package never imports `sqlite3` directly — it only uses the repository. Tests must enforce this.
- The `adapters/strava/` package never imports `sqlite3` — it has nothing to do with mirror state.
- The `read modules` (report, analytics, trends, training, metrics, cardiac_drift) never import `adapters/strava/` or `refresh/`.
- The `freshness` evaluator lives in `refresh/freshness.py` but is pure and can be called from read paths through a thin wrapper in (e.g.) a future `app/freshness_service.py` (Phase 4). For Phase 3, the read-runtime path that enqueues `refresh_requests` lives co-located with whatever module currently triggers report generation; planner picks where (likely `report.py` or a new tiny module).
