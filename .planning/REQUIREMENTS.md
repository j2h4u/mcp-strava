# Requirements: mcp-strava

**Defined:** 2026-05-20
**Core Value:** Preserve the local Strava mirror and keep trusted training analytics working while the service is refactored into clean core, repository, adapter, CLI, and MCP boundaries.

## v1 Requirements

Requirements for the initial refactor milestone. Each requirement maps to roadmap phases and must preserve the existing `data/strava.db` mirror.

### Foundation

- [ ] **FOUND-01**: Operator can install and run the service as a Python package instead of relying on ad hoc `scripts/` paths
- [ ] **FOUND-02**: Developer can configure database path, token path, runtime mode, HTTP bind settings, and freshness thresholds through one typed settings layer
- [ ] **FOUND-03**: Developer can run the existing smoke behavior through `just test` after the package refactor

### Data Safety

- [ ] **SAFE-01**: Operator can run a migration preflight that verifies required SQLite tables, schema version, row counts, and database readability before any schema change
- [ ] **SAFE-02**: Operator gets a timestamped backup of `data/strava.db` before any migration that can alter the schema
- [ ] **SAFE-03**: Developer can verify post-migration row-count parity and key report parity against the pre-migration database state
- [ ] **SAFE-04**: Service fails closed instead of silently creating an empty replacement database when an existing mirror is expected but missing or invalid

### Repository

- [ ] **REPO-01**: Application services can read activities, streams, zones, kudos, and sync metadata through a SQLite repository port instead of direct `sqlite3` calls in core logic
- [ ] **REPO-02**: SQLite adapter keeps reads and writes behind explicit repository methods with WAL, busy timeout, and short transaction discipline
- [ ] **REPO-03**: Missing-HR and missing-stream activities are represented explicitly as partial or unknown data instead of being treated as rest days

### Strava Adapter

- [ ] **STRAVA-01**: Strava OAuth refresh, token persistence, HTTP requests, retry policy, and rate-limit handling live in a Strava adapter outside the repository layer
- [ ] **STRAVA-02**: Token persistence uses an isolated provider with atomic write and single-writer protection
- [ ] **STRAVA-03**: Incremental sync can resume safely from checkpoints after rate limits, network failures, or partial fetches

### Application Services

- [ ] **APP-01**: Application service can return a daily training report from the local mirror with freshness, completeness, warnings, and recommendation rationale
- [ ] **APP-02**: Application service can return a weekly load summary from the local mirror with sport-aware aggregation and trend context
- [ ] **APP-03**: Application service can return recent workouts and per-workout analytics without calling Strava at request time
- [ ] **APP-04**: Application service can evaluate mirror freshness and expose freshness metadata without exposing sync as a user-facing operation

### CLI

- [ ] **CLI-01**: Operator can access report, weekly summary, recent workouts, freshness status, sync, backfill, SQL, and raw/debug workflows through the local CLI
- [ ] **CLI-02**: CLI commands use application services and adapters instead of owning business logic directly
- [ ] **CLI-03**: CLI command names and JSON shapes may change, but every retained operator capability has a documented replacement

### MCP

- [ ] **MCP-01**: MCP HTTP server exposes only read-only intent-level training tools for workouts, daily report, weekly load, readiness, and recommendations
- [ ] **MCP-02**: MCP tool registry excludes sync, backfill, raw Strava API calls, arbitrary SQL, token/admin operations, and sync-log inspection
- [ ] **MCP-03**: MCP responses include freshness and data-completeness metadata when analytics may be stale or partial
- [ ] **MCP-04**: MCP HTTP transport defaults to local/container-network-safe binding and rejects unsafe origin/bind configurations unless explicitly enabled

### Refresh Runtime

- [ ] **REFRESH-01**: Mirror refresh runs automatically at least once per day through a background or scheduled runtime path
- [ ] **REFRESH-02**: Request-time freshness checks can mark data stale and schedule or signal refresh work without making MCP clients trigger sync
- [ ] **REFRESH-03**: Background refresh uses locks/checkpoints so concurrent CLI, MCP, and refresh reads do not corrupt SQLite state

### Docker Readiness

- [ ] **DOCKER-01**: Container runtime uses an explicit persistent volume for `data/` and fails startup if an expected mirror database is absent or unreadable
- [ ] **DOCKER-02**: Container runtime runs as non-root by default and avoids public host-port exposure unless explicitly configured
- [ ] **DOCKER-03**: Local MCP gateway integration path is documented without requiring gateway rollout in the first implementation phase

### Testing

- [ ] **TEST-01**: Tests cover migration backup/preflight/post-check behavior against a copied SQLite database
- [ ] **TEST-02**: Tests cover Strava rate-limit/retry/checkpoint behavior without live Strava API calls
- [ ] **TEST-03**: Tests cover MCP tool allowlist and prove forbidden sync/admin/debug tools are absent
- [ ] **TEST-04**: Tests cover freshness metadata, missing-HR handling, and core daily/weekly report parity

## v2 Requirements

Deferred to future release. Tracked but not in the current roadmap.

### Advanced Analytics

- **ANALYTICS-01**: User receives confidence-scored recommendations based on freshness, data completeness, and sensor quality
- **ANALYTICS-02**: User receives overreach/ramp early-warning detection tuned per sport
- **ANALYTICS-03**: User can ask what changed between rolling periods and receive causal explanations
- **ANALYTICS-04**: User can include subjective RPE/recovery signals in readiness recommendations
- **ANALYTICS-05**: User can plan toward an event/date-aware microcycle advisor

### Operations

- **OPS-01**: Operator can integrate the service into the shared local MCP gateway with validated auth/bind/runtime policy
- **OPS-02**: Operator can use a durable token store beyond `.env` mutation if the local deployment needs stronger secret handling

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Exact compatibility with old CLI command names and JSON shapes | No external compatibility obligation; clean service boundaries are more valuable |
| MCP sync/backfill/force-refresh tools | Sync is core/application policy and background infrastructure, not an agent-facing action |
| MCP raw Strava endpoint passthrough | Turns the server into an API wrapper instead of a training analytics product |
| MCP arbitrary SQL tools | Exposes internal schema and creates security/data-integrity risk |
| MCP token/admin/sync-log tools | Expands secret and operational blast radius outside the user-facing analytics boundary |
| Public multi-user SaaS or account management | Project is local-first for one primary user |
| Full Docker/gateway rollout before core boundaries are stable | Runtime hardening should follow data-safety and service-boundary work |
| Training model overhaul before refactor | Analytics model improvements should happen after boundaries and regression coverage are in place |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-01 | TBD | Pending |
| FOUND-02 | TBD | Pending |
| FOUND-03 | TBD | Pending |
| SAFE-01 | TBD | Pending |
| SAFE-02 | TBD | Pending |
| SAFE-03 | TBD | Pending |
| SAFE-04 | TBD | Pending |
| REPO-01 | TBD | Pending |
| REPO-02 | TBD | Pending |
| REPO-03 | TBD | Pending |
| STRAVA-01 | TBD | Pending |
| STRAVA-02 | TBD | Pending |
| STRAVA-03 | TBD | Pending |
| APP-01 | TBD | Pending |
| APP-02 | TBD | Pending |
| APP-03 | TBD | Pending |
| APP-04 | TBD | Pending |
| CLI-01 | TBD | Pending |
| CLI-02 | TBD | Pending |
| CLI-03 | TBD | Pending |
| MCP-01 | TBD | Pending |
| MCP-02 | TBD | Pending |
| MCP-03 | TBD | Pending |
| MCP-04 | TBD | Pending |
| REFRESH-01 | TBD | Pending |
| REFRESH-02 | TBD | Pending |
| REFRESH-03 | TBD | Pending |
| DOCKER-01 | TBD | Pending |
| DOCKER-02 | TBD | Pending |
| DOCKER-03 | TBD | Pending |
| TEST-01 | TBD | Pending |
| TEST-02 | TBD | Pending |
| TEST-03 | TBD | Pending |
| TEST-04 | TBD | Pending |

**Coverage:**
- v1 requirements: 34 total
- Mapped to phases: 0
- Unmapped: 34 (pending roadmap)

---
*Requirements defined: 2026-05-20*
*Last updated: 2026-05-20 after initial definition*
