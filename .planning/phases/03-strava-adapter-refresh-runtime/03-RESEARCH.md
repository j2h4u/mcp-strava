# Phase 3: Strava Adapter & Refresh Runtime - Research

**Researched:** 2026-05-21
**Domain:** Strava OAuth/HTTP adapter isolation, refresh runtime, mirror freshness state machine
**Confidence:** HIGH (verified against current code, Strava docs, Python stdlib)

## Summary

Phase 3 must lift Strava OAuth/HTTP/retry/rate-limit behavior out of `src/mcp_strava/db.py` and `src/mcp_strava/sync.py` into a dedicated Strava adapter and refresh runtime. The MCP/read runtime must never call Strava, refresh tokens, or trigger sync; it may only inspect SQLite refresh-state and write idempotent `refresh_requests` rows. Token persistence must be atomic and single-writer safe (the current `save_env()` is not). Incremental sync must checkpoint between summary/stream/detail/kudos phases so 429/network/partial-fetch interruptions resume rather than restart. Rate-limit handling must track both overall and read/non-upload Strava limits, enforce the stricter remaining budget, and persist product-safe reason states (`token_unavailable`, `rate_limited`, `network_unstable`, `refresh_incomplete`, `sync_in_progress`).

**Primary recommendation:** Introduce `src/mcp_strava/adapters/strava/` (transport + token provider + rate-limit policy) and `src/mcp_strava/refresh/` (runtime orchestration + state machine + lease/backoff). Extend `SQLiteRepository` with `refresh_state` and `refresh_requests` methods (no direct sqlite3 access outside the adapter). Use stdlib `urllib`, `fcntl.flock`, and `tempfile` + `os.replace` — no new external dependencies.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Split into read-runtime and refresh-runtime. MCP/report read paths read SQLite mirror data and refresh metadata; refresh-runtime owns Strava API calls, token refresh, sync execution, checkpointing, leases, and mirror writes.
- **D-02:** MCP/read-runtime must not call Strava, refresh tokens, execute sync/backfill, expose sync tools, or show sync logs, even when the mirror is stale.
- **D-03:** MCP/read-runtime may write only an idempotent local signal into SQLite (e.g., `refresh_requests(reason=first_use_of_day, requested_for_day=...)`) when the daily refresh has not completed.
- **D-04:** Repeated MCP queries inside a short interval must be served from SQLite state and must not spend Strava quota. Dedupe, lease, backoff, and refresh-state rows prevent thundering-herd refresh scheduling.
- **D-05:** Replace magic freshness windows with explicit mirror states: `fresh`, `aging`, `stale`, `refresh_in_progress`, `refresh_failed`, `refresh_delayed`. Responses include `data_as_of`, `last_successful_refresh_at`, freshness state, and advisory metadata.
- **D-06:** Automatic refresh must run at least once per local calendar day; first-use-of-day handling lives in SQLite refresh-state inspection plus idempotent refresh requests.
- **D-07:** A refresh is successful only when required summaries, details, streams, and kudos are fetched or explicitly represented as `partial`, `unknown`, or `unavailable`.
- **D-08:** Missing HR/streams/details/kudos must never be silently interpreted as rest, zero load, or complete data.
- **D-09:** Partial refresh progress must be checkpointed so interruptions after summaries, streams, details, or kudos resume without corrupting or replacing the existing mirror.
- **D-10:** Token persistence belongs to an isolated Strava token provider with atomic write and single-writer protection.
- **D-11:** On token failure, Strava rate limit, network failure, or partial fetch interruption, fail closed for freshness while keeping old mirror reads available.
- **D-12:** Historical reads, workout lists, and stale-labeled reports may continue from the old mirror. High-confidence readiness/recommendation outputs must be blocked or degraded when freshness is failed/stale.
- **D-13:** Refresh-runtime must persist product-safe reason states: `token_unavailable`, `rate_limited`, `network_unstable`, `refresh_incomplete`, `sync_in_progress`. MCP may surface them as freshness metadata without exposing operational sync controls.
- **D-14:** The Strava adapter must track both overall and read/non-upload rate-limit headers and enforce the stricter remaining budget before continuing refresh work.

### Agent Discretion
- Exact SQLite schema and enum names for `refresh_state`, `refresh_requests`, checkpoint rows, leases, and backoff state can be chosen by the planner.
- Exact debounce/backoff values can be chosen by the planner provided quota protection and read-runtime isolation are testable.

### Deferred Ideas (OUT OF SCOPE)
- Exact MCP tool schemas and allowlist tests belong to Phase 5.
- CLI replacement mapping belongs to Phase 4 (Phase 3 may expose operator refresh entrypoints below the application layer).
- Docker/service supervision details belong to Phase 5; Phase 3 keeps refresh-runtime shape container-friendly.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STRAVA-01 | Strava OAuth refresh, token persistence, HTTP requests, retry policy, and rate-limit handling live in a Strava adapter outside the repository layer | Architecture Patterns section assigns these to `adapters/strava/`. AST/import guards (Common Pitfalls) ensure they leave `db.py`/`sync.py`. |
| STRAVA-02 | Token persistence uses an isolated provider with atomic write and single-writer protection | Token Provider Pattern section specifies `fcntl.flock` + tempfile+`os.replace` atomic write. |
| STRAVA-03 | Incremental sync can resume safely from checkpoints after rate limits, network failures, or partial fetches | Checkpoint State Machine section maps the 5 current sync phases to durable checkpoint stages. |
| REFRESH-01 | Mirror refresh runs automatically at least once per day through a background or scheduled runtime path | Refresh Runtime Entrypoint section defines `refresh.run_once()` and the daily completion semantics; operator entrypoint + scheduler-friendly shape. |
| REFRESH-02 | Request-time freshness checks can mark data stale and schedule or signal refresh work without making MCP clients trigger sync | `refresh_requests` append-only table with `(reason, requested_for_day)` dedupe key. Read-runtime never calls Strava. |
| REFRESH-03 | Background refresh uses locks/checkpoints so concurrent CLI, MCP, and refresh reads do not corrupt SQLite state | Lease + Backoff section uses `refresh_state.lease_owner` + `lease_expires_at` and atomic `UPDATE ... WHERE` for single-writer leases. |
| TEST-02 | Tests cover Strava rate-limit/retry/checkpoint behavior without live Strava API calls | Validation Architecture: fake adapter, fake token provider, fake clock/sleeper; AST/import boundary guards in `tests/test_security_guards.py`. |

## Project Constraints (from AGENTS.md)

- Preserve existing `data/strava.db` mirror.
- No live Strava network calls in tests.
- Default tests use hermetic SQLite fixtures or copied DB scenarios.
- Direct `sqlite3` import constrained to `adapters/sqlite/`, `db.py`, and narrow tests (already enforced in `tests/test_security_guards.py`).
- Runtime remains Python 3.13 + stdlib only; no new ORM or framework.
- `metrics.py` and other runtime modules must not gain direct sqlite3 imports.
- MCP must not expose sync/admin/debug surfaces.

## Standard Stack

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `urllib.request` | Python 3.13 stdlib | Strava HTTPS calls | Already used in `db.py`; zero new dependency cost. [VERIFIED: codebase] [CITED: docs.python.org/3/library/urllib.request.html] |
| `fcntl.flock` | Python 3.13 stdlib (Unix/Linux) | Single-writer lock for token file | Standard advisory POSIX file lock; supported on the target deployment (Debian 13 / Docker). [CITED: docs.python.org/3/library/fcntl.html] |
| `tempfile.NamedTemporaryFile` + `os.replace` | Python 3.13 stdlib | Atomic token file write | `os.replace` is atomic on POSIX same-filesystem renames. [CITED: docs.python.org/3/library/os.html#os.replace] |
| `sqlite3` | Python 3.13 stdlib | Refresh state/requests tables | Reuse existing connection adapter and WAL discipline from Phase 2. [VERIFIED: codebase] |
| `pytest` | already-installed | Hermetic tests | Existing convention. [VERIFIED: pyproject.toml] |

**Alternatives considered:**

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `urllib.request` | `httpx` or `requests` | Adds dependency. `urllib` already handles current Strava traffic. Reject. |
| `fcntl.flock` | `portalocker` package | Cross-platform but adds dependency. Target is Linux/Docker. Reject. |
| Custom retry loop | `tenacity` | Adds dependency. Existing inline `_fetch_with_retry` is simple. Wrap behind adapter port and keep stdlib. |
| `apscheduler` for daily refresh | systemd timer / docker entrypoint loop | Phase 5 owns container/supervisor. Phase 3 provides `refresh.run_once()` callable + thin while loop. Reject scheduler libs. |

**Version verification:** All listed modules are Python 3.13 stdlib. No external package installs planned in this phase.

## Package Legitimacy Audit

No external packages are installed in this phase. All recommended dependencies are Python 3.13 stdlib modules:

| Package | Registry | Disposition |
|---------|----------|-------------|
| `urllib.request` | stdlib | Approved (already used) |
| `fcntl` | stdlib | Approved |
| `tempfile` / `os` | stdlib | Approved |
| `sqlite3` | stdlib | Approved (already used) |

slopcheck not needed (no third-party installs).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Strava OAuth token refresh | refresh-runtime / strava adapter | persistence (token provider) | D-10/STRAVA-02 require isolation from read paths. |
| Strava HTTPS request execution + retry + rate-limit policy | strava adapter | — | D-01/STRAVA-01 require single owner for transport. |
| Refresh orchestration (phases, checkpoints, kudos) | refresh-runtime | strava adapter, repository | D-01/D-09 require orchestration outside `sync.py` legacy shape. |
| Mirror writes during refresh | repository (SQLiteRepository) | — | Phase 2 boundary preserved. |
| Refresh state (last_success_at, lease, backoff, checkpoint) | repository (new methods) | — | Read-runtime reads same rows for freshness metadata. |
| Refresh request signal (first-use-of-day) | repository (new methods) | — | D-03: only writes the read-runtime is allowed to perform. |
| Freshness state evaluation (`fresh`/`aging`/`stale`/...) | read-runtime / freshness module | repository | D-05 keeps read paths off Strava. |
| Daily refresh trigger | operator CLI / scheduler entrypoint | refresh-runtime | D-06 requires daily completion. |

## Architecture Patterns

### System Architecture Diagram

```
                       ┌─────────────────────────┐
                       │   MCP / Read-Runtime    │
                       │  (report, recent, etc.) │
                       └───────────┬─────────────┘
                                   │ reads
                                   ▼
                       ┌─────────────────────────┐
                       │   SQLiteRepository      │
                       │  (activities, streams,  │
                       │   refresh_state,        │
                       │   refresh_requests)     │
                       └────────▲────────┬───────┘
              write refresh_req │        │ reads
              (idempotent only) │        ▼
                       ┌────────┴─────────────────┐
                       │  Freshness Evaluator     │
                       │  (state machine →        │
                       │   fresh/aging/stale/...) │
                       └──────────────────────────┘

  ┌──────────────────────────┐
  │  Refresh-Runtime         │     ┌────────────────────────┐
  │  refresh.run_once()      │────▶│  Strava Adapter        │
  │  - lease/backoff         │     │  - StravaTransport     │
  │  - checkpoint stages     │     │  - TokenProvider       │
  │  - writes mirror via repo│     │  - RateLimitPolicy     │
  │  - persists reason codes │     └────────────┬───────────┘
  └────────────┬─────────────┘                  │
               │                                │ HTTPS
               │ writes refresh_state &         ▼
               │ activities/streams/...   ┌──────────────────┐
               ▼                          │  Strava API      │
        SQLite (data/strava.db)           │ (api.strava.com) │
                                          └──────────────────┘
```

### Recommended Project Structure

```
src/mcp_strava/
├── adapters/
│   ├── sqlite/                   # Existing (Phase 2)
│   └── strava/                   # NEW: Phase 3
│       ├── __init__.py
│       ├── transport.py          # Strava HTTPS + retry + 429/401 logic
│       ├── token_provider.py     # Atomic token persistence + flock
│       ├── rate_limit.py         # Tracks short+long, read+overall windows
│       └── types.py              # StravaRateInfo, StravaResponse, RefreshReason
├── refresh/                      # NEW: Phase 3
│   ├── __init__.py
│   ├── runtime.py                # run_once(), wave orchestrator
│   ├── checkpoints.py            # Stage enum + state machine
│   ├── freshness.py              # state machine: fresh/aging/stale/…
│   └── policy.py                 # Default debounce/backoff/lease durations
├── adapters/sqlite/
│   ├── repository.py             # Extend: refresh_state + refresh_requests
│   └── schema.py                 # Add tables to REQUIRED_TABLES inventory
└── (sync.py / db.py become thin compatibility/operator entrypoints)
```

### Pattern 1: Single-Writer Token Provider

**What:** Token provider owns reading and writing the credentials file. Uses an advisory file lock (`fcntl.flock(LOCK_EX)`) to serialize concurrent refresh attempts; writes go to a same-directory temp file and `os.replace()` swaps atomically.

**When to use:** Anywhere a process might race another process to refresh the access token. Mandatory per D-10/STRAVA-02.

**Example:**

```python
# Source: docs.python.org/3/library/fcntl.html, docs.python.org/3/library/os.html#os.replace
import fcntl, os, tempfile
from pathlib import Path

class FileTokenProvider:
    def __init__(self, path: Path):
        self._path = path
        self._lock_path = path.with_suffix(path.suffix + ".lock")

    def with_exclusive_lock(self):
        # Context manager: acquire LOCK_EX, yield, release.
        # The lock file is separate so the lock holder can rewrite token file atomically.
        ...

    def atomic_write(self, mapping: dict[str, str]) -> None:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False,
            dir=str(self._path.parent), prefix=self._path.name + ".",
        )
        try:
            for k, v in mapping.items():
                tmp.write(f"{k}={v}\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        os.replace(tmp.name, self._path)  # atomic rename on POSIX same-fs
        os.chmod(self._path, 0o600)
```

### Pattern 2: Rate-Limit Policy (overall + read/non-upload)

**What:** Strava publishes two limit pairs in `X-RateLimit-Limit` and `X-ReadRateLimit-Limit` headers (and matching `*-Usage`). Each pair has a 15-min and daily figure. Policy must track both and refuse to spend when either is exhausted.

**When to use:** Every Strava call. Refresh-runtime asks the policy before each fetch; the adapter updates the policy after each response.

**Reference:**

```
# Source: developers.strava.com/docs/rate-limits/
Headers from Strava:
  X-RateLimit-Limit: 200,2000        # overall: 15-min, daily
  X-RateLimit-Usage: 134,1342
  X-ReadRateLimit-Limit: 100,1000    # read/non-upload: 15-min, daily
  X-ReadRateLimit-Usage: 67,824
```

Policy decision:
- For each window (short=15min, long=daily) and each scope (overall, read), compute `remaining = limit - usage`.
- The effective budget is `min(remaining_overall_short, remaining_read_short, remaining_overall_long, remaining_read_long)`.
- If effective budget <= 0, set `refresh_state.last_error_code='rate_limited'` and `backoff_until` to the next 15-min boundary (short) or end of day local (long). Refuse further calls.

### Pattern 3: Lease + Backoff in SQLite

**What:** A single `refresh_state` row holds `lease_owner`, `lease_expires_at`, `backoff_until`, `last_success_at`, `last_attempt_at`, `last_status`, `last_error_code`, `checkpoint_stage`, `checkpoint_cursor`. Acquiring a lease is an atomic conditional UPDATE.

**When to use:** Any refresh entrypoint (`refresh.run_once`). MCP read-runtime never acquires this.

**Example acquisition:**

```sql
-- Lease acquisition (single writer)
UPDATE refresh_state
SET lease_owner=?, lease_expires_at=?
WHERE id=1
  AND (lease_expires_at IS NULL OR lease_expires_at < ?);
-- If conn.total_changes == 0, another worker holds the lease.
```

This is the same pattern used by `append_sync_log` (Phase 2 repository) for explicit single-row writes.

### Pattern 4: Checkpoint State Machine

**What:** The 5 current sync phases in `sync.py` (summaries, streams, details, schema-validation, kudos) become explicit checkpoint stages. Each stage transition writes `refresh_state.checkpoint_stage` and (when relevant) `checkpoint_cursor` (e.g., last activity_id processed in stream fetch). A resume reads stage+cursor and skips completed stages.

**Stages (canonical names — planner may rename in `refresh.checkpoints`):**

| Stage | Cursor meaning | On interrupt resume |
|-------|----------------|---------------------|
| `summaries` | last page completed | Continue from next page |
| `streams` | last activity_id with streams fetched | Continue iterating SELECT-missing |
| `details` | last activity_id with detail_json | Continue iterating |
| `schema_validate` | n/a | Re-run (cheap) |
| `kudos` | last activity_id processed | Continue iterating |
| `complete` | n/a | No-op for the day |

### Pattern 5: Freshness State Machine (D-05)

**What:** A pure function over `refresh_state` rows + clock returns one of `fresh`, `aging`, `stale`, `refresh_in_progress`, `refresh_failed`, `refresh_delayed`. Read-runtime calls this; it never touches Strava.

**Transitions (default policy — planner may tune):**

| Condition | State |
|-----------|-------|
| `last_success_at` within `warn_age_hours` AND no lease | `fresh` |
| `last_success_at` between `warn_age_hours` and `max_age_hours` | `aging` |
| `last_success_at` older than `max_age_hours` AND no active lease | `stale` |
| `lease_expires_at > now()` | `refresh_in_progress` |
| `last_status='failed'` AND `last_attempt_at` more recent than `last_success_at` | `refresh_failed` |
| `backoff_until > now()` | `refresh_delayed` |

The existing `Settings.freshness.warn_age_hours` and `max_age_hours` remain as numeric thresholds — they are preserved as policy inputs rather than behavior drivers. This preserves backward-compatibility while shifting decisions into the state machine.

### Anti-Patterns to Avoid

- **Read-runtime calling Strava on stale data.** This re-introduces request-time thundering-herd refresh and burns quota. Use idempotent `refresh_requests` rows instead.
- **Token file writes without atomic rename.** Mid-write crash leaves a half-truncated file; subsequent reads fail to refresh and the mirror permanently stales out. Always tempfile+rename.
- **Restart-on-interrupt sync.** Today, a 429 mid-`_sync_kudos` makes the next run redo work and risk replacing complete data with partial data. Phase 3 mandates stage/cursor checkpoint.
- **Single rate-limit counter.** Tracking only one of overall/read limits leaves the bot vulnerable to exceeding the other. Track both pairs.
- **Implicit sync triggered from CLI report / MCP read.** Move all sync invocations to operator `db-refresh` / scheduled `refresh.run_once`. Read paths never trigger refresh.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-process file lock | A pidfile + sleep | `fcntl.flock(LOCK_EX)` | Kernel-enforced advisory lock; no race on stale pidfiles. |
| Atomic file replace | Truncate-and-write | `tempfile` + `os.fsync` + `os.replace` | `os.replace` is atomic on POSIX same-fs; truncate-and-write is not. |
| Retry/backoff library | Custom global state | A small typed `RetryPolicy` dataclass passed to the transport | Stays stdlib, easy to fake in tests. |
| Distributed lock | etcd/Redis | Single-row SQLite UPDATE with `WHERE lease_expires_at < now` | One process, one DB. SQLite is sufficient and already present. |
| HTTP client | Add `httpx` | Wrap existing `urllib.request` behind `StravaTransport` | Avoid new dependency; `urllib` already used. |

**Key insight:** Phase 2 demonstrated that careful boundaries + AST guards on the existing stdlib stack are enough for safety. Phase 3 keeps that discipline.

## Runtime State Inventory

> Phase 3 is a code-structure refactor that introduces new SQLite tables. There is some runtime state to account for.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Existing tables `activities`, `streams`, `athlete_zones`, `sync_log`, `kudos` in `data/strava.db`. Strava tokens currently inside `.env` (`STRAVA_ACCESS_TOKEN`, `STRAVA_REFRESH_TOKEN`, `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`). | Add new tables `refresh_state`, `refresh_requests` via explicit migration v2 (Phase 2 migration gate). Token file location (`Settings.token_path`, default `.env`) is preserved; the new `TokenProvider` reads/writes the same file. |
| Live service config | None — service is local-only, no UI-side config. | None. |
| OS-registered state | None — no current systemd/launchd/Task Scheduler entry for refresh. Phase 5 owns operator scheduler. | Phase 3 ships `refresh.run_once()` and a CLI hook; Phase 5 wires a systemd timer / docker entrypoint. Phase 3 does NOT add a systemd unit. |
| Secrets / env vars | `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`, `STRAVA_ACCESS_TOKEN` in `.env` (or `MCP_STRAVA_TOKEN_PATH`). | Code changes only: token reads/writes move from `db.load_env/save_env` to `adapters/strava/token_provider.py`. Key names are preserved. |
| Build artifacts | None — stdlib only, no new package installs. | None. |

**Canonical question answered:** After all files are updated, the only runtime state newly introduced is the two new SQLite tables managed by the Phase 2 migration gate. No external systems hold "old name" state because the rename is purely internal-module-level.

## Common Pitfalls

### Pitfall 1: Token race on concurrent refresh attempts
**What goes wrong:** Two processes attempt OAuth refresh simultaneously. Both read the old refresh_token. Strava invalidates the old refresh_token on use; the slower process now has a permanently invalid refresh_token, and `.env` is left half-written.
**Why it happens:** `save_env()` truncates and writes line-by-line. There is no inter-process lock.
**How to avoid:** `fcntl.flock(LOCK_EX)` on a sidecar `.env.lock` file, atomic `os.replace` for write, re-read after lock acquisition (the other process may have already refreshed).
**Warning signs:** "Strava OAuth token refresh failed: HTTP 400/401" after a recent successful refresh; truncated `.env`.

### Pitfall 2: Read-runtime accidentally importing the Strava adapter
**What goes wrong:** A report path imports `adapters.strava.transport` directly for "convenience" and now MCP calls Strava at request time.
**Why it happens:** Python imports are transitive; refactor sweeps can miss one call site.
**How to avoid:** AST/import boundary tests in `tests/test_security_guards.py` enumerate forbidden imports from read modules. Same shape as the existing `_direct_sqlite_violations()` walker.
**Warning signs:** MCP latency spikes when mirror is stale; Strava quota burn proportional to MCP traffic.

### Pitfall 3: Resume that overwrites complete data with partial
**What goes wrong:** Streams partially fetched for activity X. Interrupt. Resume calls `replace_stream_rows_chunked` again from page 1, but only the first page is fetched before another interrupt — net result: the previously complete activity now has only the first chunk.
**Why it happens:** No checkpoint per activity; the `WHERE NOT EXISTS` query skips activities already populated, but if streams were partial-deleted the activity reappears.
**How to avoid:** Phase 3 ships `_replace_streams` calls inside a single transaction per activity (atomic). Checkpoint cursor tracks "last completed activity_id" so resume skips it. Never delete existing streams before successful fetch.
**Warning signs:** Activities flipping between has-streams / no-streams across runs.

### Pitfall 4: Single-counter rate limiting
**What goes wrong:** Tracker watches `X-RateLimit-Usage` (overall) but ignores `X-ReadRateLimit-Usage`. Read calls keep firing until the read window throws 429; backoff is unnecessarily strict for the next overall window.
**Why it happens:** Existing `RateLimiter` only parses one pair of headers.
**How to avoid:** Parse both `X-RateLimit-*` and `X-ReadRateLimit-*` from every response (Strava sends them on all endpoints). Maintain four counters: short-overall, long-overall, short-read, long-read.
**Warning signs:** 429 with `X-ReadRateLimit-Usage` at limit even though `X-RateLimit-Usage` is well below.

### Pitfall 5: `refresh_requests` thundering herd
**What goes wrong:** Every MCP request appends a refresh_request row on first-stale-read. Twenty MCP queries in a minute = twenty rows. Refresh-runtime sees twenty signals and re-runs.
**Why it happens:** Append-only without dedupe.
**How to avoid:** Use `(reason, requested_for_day)` unique constraint OR `INSERT OR IGNORE` on a composite key. Refresh-runtime treats "any row with `consumed_at IS NULL`" as one trigger.
**Warning signs:** `refresh_requests` row count proportional to MCP RPS.

## Code Examples

### Atomic token write (stdlib)

```python
# Source: docs.python.org/3/library/os.html#os.replace, docs.python.org/3/library/fcntl.html
import fcntl, os, tempfile
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def exclusive_file_lock(lock_path: Path):
    lock_path.touch(mode=0o600, exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

def atomic_write_kv(path: Path, mapping: dict[str, str]) -> None:
    parent = path.parent
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for k, v in mapping.items():
                f.write(f"{k}={v}\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        os.chmod(path, 0o600)
    except Exception:
        try: os.unlink(tmp_name)
        except OSError: pass
        raise
```

### Parsing both rate-limit header pairs

```python
# Source: developers.strava.com/docs/rate-limits/
def parse_rate_headers(headers) -> dict:
    def pair(s: str | None) -> tuple[int | None, int | None]:
        if not s: return (None, None)
        parts = [p.strip() for p in s.split(",")]
        try: short = int(parts[0])
        except (ValueError, IndexError): short = None
        try: long_ = int(parts[1])
        except (ValueError, IndexError): long_ = None
        return (short, long_)

    s_lim, l_lim = pair(headers.get("X-RateLimit-Limit"))
    s_use, l_use = pair(headers.get("X-RateLimit-Usage"))
    rs_lim, rl_lim = pair(headers.get("X-ReadRateLimit-Limit"))
    rs_use, rl_use = pair(headers.get("X-ReadRateLimit-Usage"))
    return {
        "overall_short": (s_use, s_lim),
        "overall_long": (l_use, l_lim),
        "read_short": (rs_use, rs_lim),
        "read_long": (rl_use, rl_lim),
    }
```

### AST import-boundary guard (extends existing test pattern)

```python
# Source: tests/test_security_guards.py pattern
import ast
from pathlib import Path

FORBIDDEN_IN_READ = {"mcp_strava.adapters.strava", "mcp_strava.refresh"}

READ_PATH_PREFIXES = (
    "src/mcp_strava/report.py",
    "src/mcp_strava/analytics.py",
    "src/mcp_strava/trends.py",
    "src/mcp_strava/training.py",
    "src/mcp_strava/metrics.py",
)

def _module_imports(py_path: Path) -> set[str]:
    tree = ast.parse(py_path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.add(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `db.load_env/save_env` line-by-line truncate-write | `TokenProvider` with flock + atomic replace | Phase 3 | Concurrent refresh safety. |
| Single 15-min `RateLimiter` counter | Dual-window dual-scope rate policy | Phase 3 | Read-window safety. |
| `_fetch_with_retry` inline in `sync.py` | `StravaTransport.fetch()` with `RetryPolicy` | Phase 3 | Single owner; fakeable in tests. |
| `init_db()` direct schema creation | Phase 2 migration v1 | Phase 2 (done) | Carried forward; v2 adds refresh tables. |
| Implicit refresh inside CLI report / sync | Explicit `refresh.run_once()` + `refresh_requests` signal | Phase 3 | Read-runtime/refresh-runtime split. |
| `freshness.warn_age_hours / max_age_hours` magic windows | Freshness state machine over `refresh_state` rows | Phase 3 | Named states; hours remain as thresholds. |

**Deprecated/outdated:**
- Calling `refresh_token()` from CLI directly (`cli.py:104`): replace with `TokenProvider.refresh_if_needed()` or operator CLI subcommand backed by adapter.
- `from mcp_strava.db import api_request, load_env`: replace with `StravaTransport` injection.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Strava sends `X-ReadRateLimit-*` headers on all endpoints (not just read endpoints) | Rate-Limit Policy | [ASSUMED] If only on read endpoints, code must handle missing headers gracefully (already does: `if not s: return (None, None)`). Low risk. |
| A2 | Daily Strava limits roll over at UTC midnight (per docs) | Rate-Limit Policy | [ASSUMED from training; CITED: developers.strava.com/docs/rate-limits/ states UTC]. If wrong, backoff_until calc is off by hours. Mitigation: Re-check on first 429. |
| A3 | `fcntl.flock` is sufficient against forked python workers on same host | Token Provider | [ASSUMED] Per `fcntl(2)`, advisory locks are per-file-description and propagate across forked siblings safely. Low risk for single-host deployment. |

**If this table seems short:** All headline architecture choices (split runtime, dual rate-limit, checkpoint stages, lease in SQLite, freshness state machine) come directly from CONTEXT.md locked decisions or current Strava docs. The few [ASSUMED] items are about exact header semantics, not architecture.

## Open Questions

1. **Should `refresh_state` be a single row (id=1) or per-scope (one row per refresh kind)?**
   - What we know: only one refresh kind in this phase (daily-mirror).
   - What's unclear: whether future phases (token-only refresh? per-athlete?) need scope.
   - Recommendation: start single-row; design schema so a `scope` column can be added later without migration drama.

2. **Should the read-runtime's `refresh_requests` write require a lease check?**
   - What we know: D-03 says read-runtime may write idempotent requests; D-04 says repeated reads must not spend Strava quota.
   - What's unclear: whether the read-runtime writes once per process boot, once per first-stale-read, or both.
   - Recommendation: Write only when freshness state is `aging` or `stale` AND no `refresh_requests` row for the same `(reason, requested_for_day)`. Use `INSERT OR IGNORE`.

3. **CLI subcommand surface for Phase 3.**
   - What we know: Phase 4 owns CLI mapping; Phase 3 may expose operator entrypoints below the application layer.
   - What's unclear: whether to add `db-refresh` now or defer the CLI wiring.
   - Recommendation: Add minimal `db-refresh` to `cli.py::COMMANDS` (consistent with existing `db-preflight`/`db-check`/`db-migrate`), backed by `refresh.run_once()`. Phase 4 can re-shape later.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python `urllib.request` | Strava transport | ✓ | 3.13 stdlib | — |
| `fcntl` | Token provider | ✓ | 3.13 stdlib (POSIX) | Platform: Linux/Docker assumed (per AGENTS.md). |
| `sqlite3` | Refresh state tables | ✓ | 3.13 stdlib | — |
| Strava OAuth credentials | Live token refresh | ✓ (in `.env`) | — | Phase 3 default tests use fake provider; live test only via operator command. |
| Strava API connectivity | Live runtime | ✓ at runtime | — | Tests use fake transport; live calls only from operator `db-refresh`. |
| pytest | Tests | ✓ | from `pyproject.toml` | — |

**Missing dependencies with no fallback:** none.

**Missing dependencies with fallback:** none.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (from `pyproject.toml`) |
| Config file | `pyproject.toml` (existing) |
| Quick run command | `python3 -m pytest tests/test_strava_adapter.py tests/test_refresh_runtime.py tests/test_security_guards.py -q` |
| Full suite command | `just test` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STRAVA-01 | OAuth/HTTP/retry/rate-limit isolated in adapter; no Strava imports outside adapter/refresh | unit + AST guard | `python3 -m pytest tests/test_strava_adapter.py tests/test_security_guards.py -q` | ❌ Wave 0 |
| STRAVA-02 | Token provider locks exclusively, writes atomically; concurrent attempt is serialized | unit | `python3 -m pytest tests/test_strava_adapter.py::test_token_provider_is_single_writer -x` | ❌ Wave 0 |
| STRAVA-03 | Resume after rate_limit / network / partial-fetch interrupt completes prior work without re-doing it | unit | `python3 -m pytest tests/test_refresh_runtime.py::test_resume_from_checkpoint -x` | ❌ Wave 0 |
| REFRESH-01 | `refresh.run_once()` reaches `complete` stage when ≥1 successful pass per local day | unit | `python3 -m pytest tests/test_refresh_runtime.py::test_daily_completion -x` | ❌ Wave 0 |
| REFRESH-02 | Read path may write `refresh_requests` idempotently; never imports Strava | unit + AST guard | `python3 -m pytest tests/test_refresh_runtime.py::test_freshness_signal -x tests/test_security_guards.py -q` | ❌ Wave 0 |
| REFRESH-03 | Lease acquisition is atomic; second worker observes `refresh_in_progress` | unit | `python3 -m pytest tests/test_refresh_runtime.py::test_lease_concurrency -x` | ❌ Wave 0 |
| TEST-02 | All adapter/runtime tests pass without live network | unit | `python3 -m pytest tests/test_strava_adapter.py tests/test_refresh_runtime.py -q` (no internet required) | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `python3 -m pytest tests/test_strava_adapter.py tests/test_refresh_runtime.py -q`
- **Per wave merge:** `just test`
- **Phase gate:** Full suite green before `/gsd-verify-work`.

### Wave 0 Gaps

- [ ] `tests/test_strava_adapter.py` — covers STRAVA-01, STRAVA-02, TEST-02 (token provider, transport, rate-limit policy with fakes)
- [ ] `tests/test_refresh_runtime.py` — covers STRAVA-03, REFRESH-01, REFRESH-02, REFRESH-03 (checkpoint, lease, freshness state, refresh_requests)
- [ ] Extend `tests/test_security_guards.py` — add boundary tests for `mcp_strava.adapters.strava` and `mcp_strava.refresh` imports from read paths
- [ ] Extend `tests/test_repository_boundary.py` — assert new `refresh_state` / `refresh_requests` repository methods exist and use the connection adapter

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Strava OAuth refresh token rotation; never log access/refresh tokens. |
| V3 Session Management | no | No user sessions; one bot user. |
| V4 Access Control | yes | Token file mode 0o600; refresh runtime gated behind operator CLI/scheduler, never MCP. |
| V5 Input Validation | yes | Validate Strava response shapes via `types.py` parsers (existing). |
| V6 Cryptography | partial | Tokens at rest in plain file mode 0o600. Operator may relocate via `MCP_STRAVA_TOKEN_PATH`. Future secret store deferred to OPS-02. |
| V7 Error Handling & Logging | yes | Never log tokens. Persist product-safe `last_error_code` in SQLite, not stack traces. |
| V8 Data Protection | partial | Mirror is local; no PII export. |
| V11 Business Logic | yes | Refresh lease prevents thundering-herd; backoff prevents quota exhaustion. |

### Known Threat Patterns for {python stdlib + sqlite + urllib}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Token race / partial write | Tampering | `fcntl.flock` + tempfile + `os.replace` atomic rename. |
| Token leakage in logs | Information Disclosure | Adapter never includes Authorization header value in error messages; tests assert. |
| Strava 401 storm | Denial of Service (self) | Backoff on 401 → mark `token_unavailable`, do not loop. |
| 429 rate-limit storm | Denial of Service (self) | Dual-window rate policy; `backoff_until` persisted; read-runtime never triggers. |
| Read-runtime exfiltrating quota | Spoofing / DoS | AST/import guard preventing read modules from importing adapter. |
| Stale lease | Tampering / DoS | `lease_expires_at` short (~10 min); acquisition is atomic UPDATE WHERE. |
| Half-written `.env` from crash | Tampering | tempfile+rename ensures all-or-nothing. |

## Sources

### Primary (HIGH confidence)
- Python 3.13 docs — `os.replace` (atomic POSIX rename): docs.python.org/3/library/os.html#os.replace
- Python 3.13 docs — `fcntl.flock` (advisory file locks): docs.python.org/3/library/fcntl.html
- Python 3.13 docs — `urllib.request` (HTTP client): docs.python.org/3/library/urllib.request.html
- Python 3.13 docs — `sqlite3` (Connection.backup, row_factory, PRAGMA): docs.python.org/3/library/sqlite3.html
- Strava API docs — rate limits: developers.strava.com/docs/rate-limits/
- Strava API docs — OAuth/getting started: developers.strava.com/docs/getting-started/
- Codebase: `src/mcp_strava/db.py`, `src/mcp_strava/sync.py`, `src/mcp_strava/settings.py`, `src/mcp_strava/adapters/sqlite/repository.py`, `tests/test_security_guards.py`, `.planning/phases/02-sqlite-safety-repository-layer/*.md`

### Secondary (MEDIUM confidence)
- None required — architecture is grounded in CONTEXT.md decisions and the verified primary sources above.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all stdlib, all verified in codebase or Python docs.
- Architecture: HIGH — directly follows CONTEXT.md D-01..D-14.
- Pitfalls: HIGH — grounded in current `db.py`/`sync.py` defects and Strava docs.
- Rate-limit header semantics: MEDIUM — `X-ReadRateLimit-*` presence on all endpoints is the only soft point (A1).

**Research date:** 2026-05-21
**Valid until:** 2026-06-20 (estimate — Strava rate-limit headers and Python stdlib APIs are stable; revisit if Strava docs change).
