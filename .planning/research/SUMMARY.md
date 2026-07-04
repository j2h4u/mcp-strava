# Project Research Summary

**Project:** mcp-strava
**Domain:** Local Strava mirror + read-only MCP training analytics service
**Researched:** 2026-05-20
**Confidence:** HIGH

**Status:** historical summary. For the current implementation contract, use `.planning/codebase/STACK.md`, `.planning/codebase/ARCHITECTURE.md`, and `pyproject.toml`; this document records the earlier design rationale only.

## Executive Summary

mcp-strava should be built as a local-first analytics product, not a Strava endpoint wrapper. The product boundary is clear across all research: preserve the existing SQLite mirror as durable state, run user-facing analytics from local data, and expose only intent-level read-only MCP tools for workouts, reports, load trends, and recommendations.

The recommended implementation is a Clean/Hexagonal service refactor on Python 3.13 with the official MCP Python SDK (`mcp==1.27.1`) over Streamable HTTP, SQLAlchemy Core + Alembic for safe schema evolution, and typed application services that own freshness policy. Sync/backfill/admin/debug functions remain CLI/background concerns and must not be exposed through MCP.

The main risks are data loss during migration, stale or misleading recommendations, Strava rate-limit collapse during refresh, and accidental boundary/security leaks (MCP sync tools or public bind). Mitigation is explicit and should be mandatory in roadmap phases: backup + migration parity checks, freshness metadata on every response, resumable checkpointed sync with retry budgets, strict MCP tool allowlist, and localhost-by-default HTTP hardening.

## Key Findings

### Recommended Stack

The stack is conservative and production-pragmatic for a one-user local service: Python 3.13 runtime, official MCP SDK over Streamable HTTP, SQLAlchemy Core for query-centric analytics, and Alembic for reversible migration discipline. Configuration should be centralized with `pydantic-settings`, Strava API access via `httpx` + retry policy (`tenacity`), CLI on Typer, and optional scheduled refresh via APScheduler.

**Core technologies:**
- `Python 3.13.x`: runtime baseline — aligns with modern typing/perf and avoids premature 3.14 adoption.
- `mcp==1.27.1`: MCP server implementation — official SDK with Streamable HTTP support and current protocol semantics.
- `MCP Streamable HTTP (2025-06-18 spec)`: transport standard — required headers/session behavior and modern MCP compatibility.
- `SQLAlchemy Core 2.0.49`: repository/query layer — explicit control for analytics-heavy workloads.
- `Alembic 1.18.4`: migration engine — safe SQLite evolution via batch migration pattern.

### Expected Features

v1 must deliver reliable read-only analytics workflows, not infrastructure controls. Research converges on trust signals as first-class output: freshness state, last sync timestamp, staleness age, and missing-data warnings.

**Must have (table stakes):**
- Read-only intent-level MCP tools (`latest_workouts`, `daily_training_report`, `weekly_load_summary`, `readiness_and_recommendation`) — users ask training questions, not raw API queries.
- Mirror-backed analytics reads — responses must remain available even when Strava API is down/rate-limited.
- Freshness policy + metadata on every analytics response — prevents false confidence in stale outputs.
- Missing-data transparency (especially missing HR/streams) — prevents distorted load/readiness interpretation.
- Explainable recommendations with rationale/warnings — makes guidance actionable.

**Should have (competitive):**
- Confidence-scored recommendations — ties trust directly to freshness and completeness.
- Overreach/ramp early-warning detection — practical injury-risk value.
- “What changed” period-over-period causal insights — improves coaching usefulness.

**Defer (v2+):**
- Event-goal-aware microcycle advisor.
- Deeper subjective/objective fusion (RPE + physiological metrics).
- Advanced anomaly explanation workflows.

### Architecture Approach

Architecture should enforce strict boundaries: interfaces (CLI/MCP/background) call application services; services depend on typed ports; adapters implement SQLite/Strava/runtime side effects; core remains pure analytics logic. Freshness evaluation lives in application policy, and MCP remains read-only by design.

**Major components:**
1. `core` — pure training metrics, trends, recommendations, and report math.
2. `application` — use cases (`GetDailyReport`, `GetWeeklyDigest`, `EnsureFreshMirrorPolicy`, refresh orchestration) and policies.
3. `adapters/sqlite` — repository queries, durable persistence, migrations, backups.
4. `adapters/strava` — OAuth, rate-limit handling, retries, payload mapping.
5. `interfaces/mcp_http` — read-only user tools only; no sync/admin/raw/sql exposure.

### Critical Pitfalls

1. **Silent data loss during migration** — prevent with mandatory preflight backup, versioned Alembic migrations, and row/report parity checks.
2. **Rate-limit-driven partial sync corruption** — prevent with checkpointed incremental sync, backoff/jitter, and resumable state.
3. **MCP boundary collapse (sync/admin tools exposed)** — prevent with strict allowlist and architecture tests blocking forbidden handlers/imports.
4. **Token corruption under concurrent refresh** — prevent with isolated token provider, atomic writes, lock, single-writer refresh path.
5. **SQLite lock contention (sync vs reads)** — prevent with WAL, busy timeout, short write transactions, and serialized heavy sync operations.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation, Safety, and Contracts
**Rationale:** Every later phase depends on stable boundaries and data-safety guarantees.
**Delivers:** `src/` package skeleton, ports/interfaces, settings model, migration runner scaffold, backup preflight, baseline golden-test harness.
**Addresses:** Feature dependencies for service contracts and mirror preservation.
**Avoids:** Migration data-loss pitfall and hidden analytics regressions.

### Phase 2: SQLite Repository + Strava Adapter Isolation
**Rationale:** Freshness and analytics reliability are impossible without clean persistence and API boundaries.
**Delivers:** SQLAlchemy-based repository over existing DB, Alembic migration path, isolated Strava OAuth/retry/rate-limit adapter, sync checkpoints.
**Uses:** SQLAlchemy Core, Alembic, `httpx`, `tenacity`.
**Implements:** Adapter layer and application ports.
**Avoids:** Rate-limit corruption, token corruption, and lock-contention failures.

### Phase 3: Application Services + CLI Refit
**Rationale:** Build user-value paths before MCP transport so behavior is testable and stable.
**Delivers:** Daily/weekly/trend/readiness services, freshness policy engine, explainable recommendation payloads, CLI mapped to new services (no legacy compatibility requirement).
**Addresses:** P1 features: freshness metadata, missing-data transparency, explainable outputs.
**Avoids:** Stale-response trust failures and business logic leaking into interfaces.

### Phase 4: Read-Only MCP HTTP Surface
**Rationale:** Expose MCP only after core read paths and policies are proven.
**Delivers:** Streamable HTTP MCP server with intent-level tools only, strict tool allowlist tests, origin/local-bind security defaults.
**Uses:** `mcp==1.27.1` + Streamable HTTP transport.
**Implements:** Interface boundary for agent consumption.
**Avoids:** MCP control-plane sprawl and local HTTP security misconfiguration.

### Phase 5: Background Refresh + Docker Runtime Hardening
**Rationale:** Operational reliability should follow feature-correct behavior, not precede it.
**Delivers:** Daily scheduled refresh worker, sync lock discipline, Docker packaging with explicit durable `data/` volume and startup DB guards.
**Addresses:** Ongoing mirror freshness and deployment durability.
**Avoids:** Empty-DB container startups and public exposure by default.

### Phase Ordering Rationale

- This order follows hard dependencies: contracts and safety first, then adapters, then use-cases, then MCP interface, then runtime packaging.
- It matches architecture boundaries, so each phase leaves a testable seam and reduces coupling before new surface area is added.
- It front-loads highest-cost failure risks (data loss, rate limits, stale trust) before public MCP consumption and container rollout.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Strava adapter retry/rate-limit envelope and checkpoint resume semantics under real 429 behavior.
- **Phase 4:** MCP Streamable HTTP security posture (origin validation, session/version header handling) in the exact runtime shape.
- **Phase 5:** Container durability and local gateway integration details (mount guarantees, startup guards, bind policy).

Phases with standard patterns (skip research-phase):
- **Phase 1:** Python packaging, DI wiring, and baseline migration scaffold are well-established.
- **Phase 3:** Application-service extraction and CLI-over-service refit follow standard clean-architecture practice.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Anchored in official MCP/SDK/spec docs and mature Python data tooling docs. |
| Features | HIGH | Strong convergence with project constraints and known analytics product expectations. |
| Architecture | HIGH | Clear boundary model with direct mapping to current codebase concerns. |
| Pitfalls | HIGH | Risks are concrete, recurring, and tied to explicit prevention/tests per phase. |

**Overall confidence:** HIGH

### Gaps to Address

- Exact token persistence mechanism choice (file-lock strategy vs dedicated secret path abstraction) should be finalized during Phase 2 design.
- Concrete MCP gateway deployment topology and auth posture for non-local-bind scenarios should be validated in Phase 5.
- Confidence-score formula for recommendations is intentionally deferred; define only after freshness/completeness telemetry is stable.

## Sources

### Primary (HIGH confidence)
- `.planning/research/STACK.md` — runtime/tooling recommendations, version pinning, transport and migration standards.
- `.planning/research/FEATURES.md` — table stakes vs differentiators, anti-features, feature dependencies.
- `.planning/research/ARCHITECTURE.md` — target boundaries, data flows, build-order dependencies.
- `.planning/research/PITFALLS.md` — critical failure modes, prevention patterns, phase-to-risk mapping.
- MCP specification (Streamable HTTP, 2025-06-18): https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- MCP Python SDK docs/releases: https://py.sdk.modelcontextprotocol.io/ and https://github.com/modelcontextprotocol/python-sdk/releases
- SQLAlchemy/Alembic/SQLite official docs: https://docs.sqlalchemy.org/ , https://alembic.sqlalchemy.org/ , https://sqlite.org/

### Secondary (MEDIUM confidence)
- `support.strava.com` feature terminology references (fitness/freshness framing).
- TrainingPeaks / Intervals.icu / GoldenCheetah public docs used for market baseline comparisons.

### Tertiary (LOW confidence)
- None.

---
*Research completed: 2026-05-20*
*Ready for roadmap: yes*
