# Architecture Research

**Domain:** Local Strava mirror + training analytics service (single-user, local-first)
**Researched:** 2026-05-20
**Confidence:** HIGH

## Standard Architecture

### System Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Interface Layer                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  CLI Commands            MCP HTTP Tools           Background Runner  │
│  (local ops + debug)     (read-only analytics)    (scheduled refresh)│
└───────────────┬───────────────────────┬──────────────────────────────┘
                │                       │
                ▼                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Application Layer (Use Cases / Policies)                            │
├──────────────────────────────────────────────────────────────────────┤
│ GetDailyReport  GetWeeklyDigest  GetTrends  GetActivities            │
│ EnsureFreshMirrorPolicy  RunIncrementalRefresh  RunBackfill          │
└───────────────┬──────────────────────────────────────┬───────────────┘
                │                                      │
                ▼                                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Core Layer (Pure Domain Logic)                                      │
├──────────────────────────────────────────────────────────────────────┤
│ Training model · Metrics · Recommendations · Trend math · Entities  │
└───────────────┬──────────────────────────────────────┬───────────────┘
                │ ports only                           │ ports only
                ▼                                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Adapters Layer (Infrastructure)                                     │
├──────────────────────────────────────────────────────────────────────┤
│ SQLite Repository Adapter   Strava API Adapter   Scheduler/Clock     │
│ (data/strava.db)            (OAuth + rate-limit)  (daily trigger)    │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Core domain | Training math and analytics rules, no I/O | Pure Python modules under `src/mcp_strava/core/` |
| Application services | Orchestrate use cases and freshness policy | `src/mcp_strava/application/services/*.py` |
| Ports | Contracts for repository, Strava client, clock, lock | `typing.Protocol` in `src/mcp_strava/application/ports/` |
| SQLite adapter | Persist mirror data, migrations, query models | `src/mcp_strava/adapters/sqlite/` |
| Strava adapter | OAuth refresh, request/retry/rate-limits, payload mapping | `src/mcp_strava/adapters/strava/` |
| CLI interface | Operator/local commands (including sync/admin/debug) | `src/mcp_strava/interfaces/cli/` |
| MCP HTTP interface | Read-only user tools (activities/reports/analytics) | `src/mcp_strava/interfaces/mcp_http/` |
| Background refresh | Trigger incremental mirror updates on policy schedule | `src/mcp_strava/interfaces/background/` |

## Recommended Project Structure

```text
src/
└── mcp_strava/
    ├── core/                      # Pure domain entities and analytics logic
    │   ├── entities.py
    │   ├── metrics.py
    │   ├── training.py
    │   ├── report.py
    │   └── trends.py
    ├── application/               # Use-cases and dependency-injected services
    │   ├── ports/
    │   │   ├── repository.py
    │   │   ├── strava_client.py
    │   │   ├── scheduler.py
    │   │   └── clock.py
    │   ├── services/
    │   │   ├── report_service.py
    │   │   ├── analytics_service.py
    │   │   ├── mirror_refresh_service.py
    │   │   └── sync_admin_service.py
    │   └── policies/
    │       └── freshness_policy.py
    ├── adapters/                  # Infrastructure implementations of ports
    │   ├── sqlite/
    │   │   ├── migrations/
    │   │   ├── repository.py
    │   │   └── backup.py
    │   ├── strava/
    │   │   ├── oauth.py
    │   │   ├── client.py
    │   │   └── mapper.py
    │   └── runtime/
    │       ├── scheduler.py
    │       └── clock.py
    ├── interfaces/                # Transport and user entrypoints only
    │   ├── cli/
    │   │   ├── main.py
    │   │   └── commands/
    │   ├── mcp_http/
    │   │   ├── server.py
    │   │   └── tools.py
    │   └── background/
    │       └── worker.py
    └── bootstrap/                 # Composition root / DI wiring
        ├── settings.py
        └── container.py
```

### Structure Rationale

- **`core/`:** keeps model and analytics stable and testable; no SQLite, no Strava HTTP, no CLI/MCP code.
- **`application/`:** owns workflows and policies, including “when to refresh mirror,” without owning transport details.
- **`adapters/`:** all side effects (DB, API, scheduling/runtime) live here, replaceable without touching core math.
- **`interfaces/`:** CLI and MCP are thin shells over application services; MCP does not gain sync/admin affordances.
- **`bootstrap/`:** single place where real adapters are bound to application ports.

## Architectural Patterns

### Pattern 1: Clean/Hexagonal Boundary

**What:** Core and application depend only on ports; adapters depend inward.
**When to use:** When the same business logic must power multiple interfaces (CLI + MCP + background worker).
**Trade-offs:** More files and wiring, but strong isolation and easier migration/testing.

**Example:**
```python
class ActivityRepository(Protocol):
    def list_recent(self, days: int) -> list[Activity]: ...

class ReportService:
    def __init__(self, repo: ActivityRepository) -> None:
        self.repo = repo
```

### Pattern 2: Policy-Driven Refresh (Not Tool-Driven Sync)

**What:** Freshness check is called by read use-cases; refresh executes in background/admin paths.
**When to use:** Mirror-backed analytics where sync should stay operational, not user-facing.
**Trade-offs:** Slightly more orchestration, but keeps MCP surface read-only and safe.

**Example:**
```python
def ensure_fresh_mirror(now: datetime, last_sync: datetime | None) -> FreshnessDecision:
    if last_sync is None or now - last_sync > timedelta(hours=24):
        return FreshnessDecision.STALE
    return FreshnessDecision.FRESH
```

### Pattern 3: Expand-and-Migrate SQLite Evolution

**What:** Versioned migrations with preflight backup and idempotent steps.
**When to use:** Existing durable local DB (`data/strava.db`) with valuable historical data.
**Trade-offs:** Slower schema iteration, but avoids destructive rewrites and rate-limit-heavy refetches.

## Data Flow

### Request Flow (CLI/MCP read path)

```text
User (CLI or MCP tool)
    ↓
Interface handler
    ↓
Application read service (GetDailyReport/GetWeeklyDigest/...)
    ↓
Freshness policy check (read-only decision)
    ├── fresh: continue
    └── stale: emit refresh-needed signal (no sync RPC in MCP)
    ↓
Repository port query
    ↓
Core analytics/training computation
    ↓
DTO mapping at interface boundary
    ↓
CLI JSON/text or MCP tool response
```

### Background Mirror Refresh Flow

```text
Scheduler trigger (daily) or local CLI admin command
    ↓
MirrorRefreshService (application)
    ↓
Acquire sync lock (port) + load cursor/last_sync
    ↓
Strava adapter incremental fetch (OAuth refresh, retries, rate-limit)
    ↓
SQLite adapter transactional upsert (activities/streams/details/kudos/sync_log)
    ↓
Update sync metadata + release lock
    ↓
Observability event (status, counts, error if failed)
```

### Key Data Flows

1. **Analytics/report flow:** SQLite mirror is authoritative for reads; core computes metrics from local data only.
2. **Refresh flow:** Strava API data enters only through the Strava adapter and lands in SQLite through repository/ingest adapters.
3. **Boundary enforcement flow:** MCP tools call only read services; sync/backfill/raw/sql remain CLI/background-only.

## Migration Strategy (Preserve `data/strava.db`)

1. Introduce package skeleton and ports first, reusing existing DB file path.
2. Wrap current `db.py` in a compatibility adapter so core/application can switch without data movement.
3. Add schema-version table and migration runner with mandatory preflight backup (`strava.db.bak.<timestamp>`).
4. Convert inline `ALTER TABLE` logic into numbered idempotent migrations.
5. Migrate one use-case at a time (`daily_report` first), validating row counts and output parity against current CLI.
6. Move Strava HTTP/token logic from `db.py` into Strava adapter; keep same token source initially to avoid auth breakage.
7. After parity, retire old `scripts/strava_lib/*` entrypoints and keep a thin compatibility CLI shim if needed.

## Build Order and Phase Dependencies

1. **Phase A: Composition + structure foundation**
   - Create `src/mcp_strava/{core,application,adapters,interfaces,bootstrap}`.
   - Define ports and service interfaces.
   - Dependency: none.

2. **Phase B: SQLite adapter + migrations safety**
   - Implement repository adapter on existing `data/strava.db`.
   - Add backup + schema versioning/migration runner.
   - Dependency: Phase A.

3. **Phase C: Strava adapter + refresh orchestration**
   - Isolate OAuth, rate-limit, retry, parsing in Strava adapter.
   - Implement `MirrorRefreshService` and sync lock.
   - Dependency: Phases A-B.

4. **Phase D: Read use-cases + CLI refit**
   - Port report/weekly/trends/activity reads to application services and new CLI commands.
   - Keep sync/admin/debug commands CLI-only.
   - Dependency: Phases A-C.

5. **Phase E: MCP HTTP read-only surface**
   - Expose only user-facing analytics tools through MCP HTTP server.
   - Enforce no sync/backfill/raw/sql tool registration.
   - Dependency: Phase D.

6. **Phase F: Background worker + Docker boundary**
   - Add scheduled daily refresh worker and container packaging.
   - Keep local-network binding and explicit volume for `data/`.
   - Dependency: Phases C-E.

## Anti-Patterns

### Anti-Pattern 1: “Smart MCP” that owns sync/admin

**What people do:** expose `sync`, `backfill`, `raw`, `sql`, token/admin operations as MCP tools.
**Why it's wrong:** breaks operational boundary, increases blast radius, and couples agent prompts to infra tasks.
**Do this instead:** keep sync/admin in CLI/background interfaces; MCP stays read-only analytics.

### Anti-Pattern 2: Core depending on SQLite/HTTP details

**What people do:** import `sqlite3`/Strava client directly inside training/report logic.
**Why it's wrong:** blocks testing and forces rewrites when transport/storage changes.
**Do this instead:** core/application consume typed domain inputs via ports and DTO mappers.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Strava REST API | Adapter with OAuth refresh + rate-limit-aware retries | No direct calls outside adapter |
| Local filesystem | SQLite DB + backup files | `data/strava.db` is durable mirror state |
| Docker runtime (future) | Container with mounted `data/` volume and local binding | Keep service local-first, not public |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Interfaces → Application | Direct service calls with DTOs | No business logic in handlers |
| Application → Core | In-process function/module calls | Pure logic only |
| Application → Adapters | Port interfaces | Dependency inversion enforced |
| MCP interface ↔ sync logic | No direct link | Sync policy signal only, no sync command |

## Sources

- `.planning/PROJECT.md` (project requirements and constraints)
- `.planning/codebase/ARCHITECTURE.md` (current coupling and data flows)
- `.planning/codebase/STRUCTURE.md` (current module layout)
- `.planning/codebase/CONCERNS.md` (known fragility and debt)
- `references/architecture-review-2026-05.md` (boundary and module health findings)
- `references/sync-review-2026-05.md` (sync reliability and rate-limit behavior)

---
*Architecture research for: local Strava mirror + MCP training analytics service*
*Researched: 2026-05-20*
