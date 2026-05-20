# Pitfalls Research

**Domain:** Local Strava mirror + training analytics service (SQLite + MCP HTTP)
**Researched:** 2026-05-20
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Silent Data Loss During SQLite Refactor/Migrations

**What goes wrong:**
Migrations rewrite or drop columns/tables (`activities`, `streams`, `sync_log`, `kudos`) without preserving row parity, and hard-earned mirrored Strava history is lost.

**Why it happens:**
Schema changes are moved from inline runtime `ALTER TABLE` checks to migration files without strict preflight, backup, and post-verify gates.

**How to avoid:**
- Add schema version table and forward-only migrations.
- Mandatory pre-migration backup (`.db` copy or `VACUUM INTO`) with checksum.
- Migration preflight: validate required tables/columns before applying.
- Post-migration verification: row counts + key uniqueness + sample report parity.
- Never auto-create a fresh DB if expected tables are missing in an existing file.

**Warning signs:**
- Unexpected row drops in `streams` after migration.
- Daily/weekly report suddenly shows long rest periods.
- Migration succeeds too quickly despite heavy schema changes.

**Phase to address:**
Phase 1 (Repository + migration framework) and Phase 2 (data-preservation validation).

**Tests or smoke checks needed:**
- Migration replay test from a copy of real `data/strava.db`.
- Before/after row-count assertions for all core tables.
- Golden daily-report snapshot comparison before vs after migration.

---

### Pitfall 2: Rate-Limit Exhaustion and Partial Mirror Corruption

**What goes wrong:**
Backfill/sync bursts exceed Strava 15-minute or daily caps, causing long retry loops, incomplete ingest windows, and stale analytics served as if complete.

**Why it happens:**
Retry logic is blocking and local-only; no persistent sync cursor state machine or strict budget-aware throttling.

**How to avoid:**
- Centralize Strava client with header-aware budget tracking (`X-RateLimit-*`, `X-ReadRateLimit-*`).
- Persist sync cursor/checkpoint per run.
- Split sync into resumable chunks (activities, details, streams, kudos).
- Mark mirror freshness status as degraded when sync is interrupted.

**Warning signs:**
- Frequent `429` with repeated retries in logs.
- Sync duration spikes and never reaches “caught up.”
- MCP responses based on old data but no freshness warning.

**Phase to address:**
Phase 2 (Strava adapter hardening) and Phase 3 (sync orchestration/background policy).

**Tests or smoke checks needed:**
- Unit tests for header parsing and throttle math.
- Integration test that simulates 429 then resume from last checkpoint.
- Smoke test proving interrupted sync does not duplicate/skip activities.

---

### Pitfall 3: Sync Policy Leaks Into MCP Tool Surface

**What goes wrong:**
MCP exposes operational tools (`sync`, `backfill`, `raw`, `sql`, `sync_log`) or forces clients to trigger sync manually, coupling analytics UX to infra operations.

**Why it happens:**
CLI-to-MCP porting mirrors commands one-to-one instead of defining user-facing capability boundaries.

**How to avoid:**
- Define MCP tool allowlist early: workouts, analytics, reports, recommendations only.
- Keep sync orchestration internal (scheduler/service layer), not tool-accessible.
- Enforce read-only MCP policy in tool registry tests.

**Warning signs:**
- MCP schema includes admin/debug verbs.
- Product docs instruct agents to “run sync first.”
- Tool handlers directly call sync/backfill paths.

**Phase to address:**
Phase 3 (application service boundaries) and Phase 4 (MCP surface implementation).

**Tests or smoke checks needed:**
- Contract test asserting forbidden tools are absent.
- Static check: MCP handlers cannot import sync orchestration module.
- End-to-end smoke: report tool works when mirror is stale by returning freshness metadata, not sync command.

---

### Pitfall 4: Local HTTP Transport Security Misconfiguration

**What goes wrong:**
MCP HTTP server binds broadly (`0.0.0.0`), ignores `Origin`, or ships without auth in shared network contexts, exposing local data and admin behavior.

**Why it happens:**
“Local service” is treated as inherently safe; transport security rules are deferred.

**How to avoid:**
- Default bind to `127.0.0.1`.
- Validate `Origin` for Streamable HTTP.
- Require explicit opt-in for non-local bind.
- Separate runtime profiles: local dev vs container network.

**Warning signs:**
- Service reachable from non-local host unexpectedly.
- Browser-origin requests accepted without checks.
- Docker compose publishes port publicly by default.

**Phase to address:**
Phase 4 (MCP transport implementation) and Phase 5 (Docker packaging).

**Tests or smoke checks needed:**
- Network smoke: confirm localhost-only by default.
- Security smoke: reject disallowed `Origin`.
- Container smoke: no public host port unless explicitly configured.

---

### Pitfall 5: OAuth Token State Corruption Under Concurrency

**What goes wrong:**
Concurrent refresh/token writes corrupt `.env` token state, leading to repeated 401 cycles and failed sync.

**Why it happens:**
Token refresh and secret persistence are mixed with DB concerns and use mutable plaintext rewrite flow.

**How to avoid:**
- Isolate token provider from repository.
- Use atomic write + file lock for token persistence.
- Single-writer policy for refresh path.
- Prefer secret file/env injection boundary for container runtime.

**Warning signs:**
- Alternating valid/invalid tokens across runs.
- `.env` partially rewritten or malformed.
- Multiple refresh attempts per sync cycle.

**Phase to address:**
Phase 2 (Strava auth adapter) and Phase 5 (container/runtime hardening).

**Tests or smoke checks needed:**
- Concurrency test for simultaneous refresh calls.
- Fault-injection test for interrupted write.
- Smoke test: refresh once, persist once, next request succeeds.

---

### Pitfall 6: SQLite Lock Contention Between Background Sync and Reads

**What goes wrong:**
Background sync writes block report queries (or vice versa), causing latency spikes, intermittent failures, and unreliable MCP responses.

**Why it happens:**
Single-file SQLite used by multiple processes without explicit transaction scope, timeout, and journaling strategy.

**How to avoid:**
- Enable WAL mode and sensible busy timeout.
- Keep write transactions short and chunked.
- Use dedicated repository methods with clear read/write boundaries.
- Serialize heavy sync tasks via job runner lock.

**Warning signs:**
- `database is locked` errors during report requests.
- P95 latency spikes while sync is running.
- Retried writes succeed only after long sleeps.

**Phase to address:**
Phase 1 (repository abstraction) and Phase 3 (background sync runner).

**Tests or smoke checks needed:**
- Contention integration test (concurrent read+write).
- Smoke test with sync running while serving report MCP calls.
- DB pragma verification test at startup.

---

### Pitfall 7: Analytics Regression Hidden by Weak Test Suite

**What goes wrong:**
Refactor changes training metrics outputs (TRIMP history, trend bucketing, HR-missing semantics) without detection; recommendations drift silently.

**Why it happens:**
Current tests are smoke-heavy and do not pin critical analytical invariants or edge cases.

**How to avoid:**
- Add golden tests for daily report, weekly digest, trends.
- Explicit tests for missing-HR sessions and year/week boundaries.
- Add migration + sync retry + freshness policy tests before major module moves.

**Warning signs:**
- “All tests pass” but report/recommendation shape or values noticeably shift.
- No tests fail when known fragile code is changed.
- Trend outputs differ around year rollover.

**Phase to address:**
Phase 0 (test harness upgrade) and Phase 2-4 (regression nets per boundary).

**Tests or smoke checks needed:**
- Snapshot/golden output tests on fixed DB fixture.
- Edge-case suite for missing HR and ISO week boundaries.
- MCP response contract tests for analytics payloads.

---

### Pitfall 8: Docker Packaging Breaks Local Data Durability

**What goes wrong:**
Containerized service starts with empty DB because volume path/mount ownership is wrong; fresh file is created and appears healthy but historical mirror is absent.

**Why it happens:**
Packaging is done before pinning data-path and startup checks; runtime silently bootstraps missing DB.

**How to avoid:**
- Make DB path explicit and required in config.
- Startup guard: fail fast if expected DB missing/unreadable.
- Add backup/restore and mount-permission checks to container entrypoint.
- Separate “first init” path from “existing mirror” path.

**Warning signs:**
- Report returns empty history immediately after deploy.
- New tiny DB file timestamp matches container start.
- Row counts near zero despite known long training history.

**Phase to address:**
Phase 5 (Docker/runtime packaging) with pre-release deployment smoke.

**Tests or smoke checks needed:**
- Container smoke with mounted real/copy DB.
- Startup negative test for missing mount.
- Post-start parity check on row counts vs host DB copy.

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keep migrations as inline startup `ALTER TABLE` checks | Fast refactor start | Non-reproducible schema evolution, high data-loss risk | Never |
| Expose legacy CLI ops as MCP tools for parity | Faster MCP launch | Boundary collapse, security and policy leaks | Never |
| Treat sync freshness as client responsibility | Simpler server code | Stale analytics and inconsistent user trust | Never |
| Skip backup preflight “just this once” | Faster release | Irrecoverable local mirror loss | Never |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Strava API | Ignore rate-limit headers and rely only on retry sleeps | Budget-aware throttling + checkpointed resumable sync |
| Strava OAuth | Rewrite `.env` naively during refresh | Isolated token manager with atomic write/lock |
| MCP HTTP | Assume local = safe and bind on all interfaces | Localhost default + `Origin` validation + explicit auth profile |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-request recomputation of heavy metrics | Slow reports, high CPU on repeated queries | Cache derived metrics, precompute daily aggregates | Hundreds of activities with streams |
| Blocking sync retries in foreground process | MCP/CLI stalls during 429 windows | Background job model with persisted checkpoints | Backfill periods or API pressure |
| SQLite write/read contention | `database is locked`, request timeouts | WAL + short transactions + sync serialization | Concurrent sync + report usage |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Exposing `sql`/`raw` surfaces through MCP | Data exfiltration and destructive command execution | Keep admin/debug operations non-MCP and local-only |
| Plaintext token lifecycle without lock/atomicity | Token theft/corruption, service instability | Harden secret handling and persistence flow |
| Default public bind in Docker | Unintended remote access to personal training data | Bind-local by default, explicit publish only |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Serving stale reports without freshness metadata | User trusts wrong training recommendations | Return explicit `mirror_freshness` and last-sync timestamp |
| Hard failure on partial sync state | Analytics unavailable during temporary API limits | Degraded-but-explicit mode with warnings |
| Sync/admin language visible in user tools | Confusing agent/user workflow | Keep MCP tools domain-focused (training questions only) |

## "Looks Done But Isn't" Checklist

- [ ] **Migrations:** DB opens after upgrade, but row parity and report parity were not verified.
- [ ] **MCP surface:** Tools work, but forbidden ops (`sync`, `backfill`, `raw`, `sql`, `sync_log`) are still exposed.
- [ ] **Sync policy:** Background scheduler exists, but request-time freshness gate is missing.
- [ ] **Security:** HTTP transport responds, but localhost bind and `Origin` checks are untested.
- [ ] **Docker:** Container runs, but it created a fresh DB instead of using preserved mirror data.
- [ ] **Testing:** Smoke tests pass, but no migration/rate-limit/freshness regression tests exist.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Migration data loss | HIGH | Stop writes, restore backup, replay verified migrations, run parity checks |
| Rate-limit exhaustion mid-sync | MEDIUM | Persist checkpoint, delay by rate window, resume chunked sync, mark freshness degraded until catch-up |
| MCP boundary leak | MEDIUM | Remove tool exposure, rotate runtime config, add contract tests to prevent reintroduction |
| Public transport exposure | HIGH | Restrict bind immediately, rotate tokens, inspect access logs, redeploy hardened config |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Silent data loss in migrations | Phase 1-2 | Migration replay + row/report parity checks pass |
| Rate-limit/partial-sync corruption | Phase 2-3 | 429-resume integration and checkpoint tests pass |
| Sync policy leaks into MCP | Phase 3-4 | MCP allowlist contract test passes |
| HTTP transport misconfiguration | Phase 4-5 | Local-bind + `Origin` security smokes pass |
| Token corruption under concurrency | Phase 2 & 5 | Atomic refresh concurrency tests pass |
| SQLite lock contention | Phase 1 & 3 | Concurrent read/write integration smoke stable |
| Analytics regression due to weak tests | Phase 0-4 | Golden analytics snapshots stable across refactor |
| Docker mounts causing empty DB | Phase 5 | Mounted DB parity smoke passes in container |

## Sources

- Project context: `.planning/PROJECT.md`
- Codebase concerns: `.planning/codebase/CONCERNS.md`
- Current testing shape: `.planning/codebase/TESTING.md`
- Integration surface: `.planning/codebase/INTEGRATIONS.md`
- Strava rate limits (official): https://developers.strava.com/docs/rate-limits/
- SQLite ALTER TABLE limitations (official): https://www.sqlite.org/lang_altertable.html
- MCP Streamable HTTP transport/security warning (official): https://modelcontextprotocol.io/specification/2025-06-18/basic/transports

---
*Pitfalls research for: local Strava mirror + MCP analytics refactor*
*Researched: 2026-05-20*
