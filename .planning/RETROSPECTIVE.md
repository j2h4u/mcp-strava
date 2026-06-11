# Retrospective

Living retrospective across milestones. Newest milestone first.

## Milestone: v1.1 — DuckDB Analytics

**Shipped:** 2026-06-11
**Phases:** 16 | **Plans:** 71 | **Tasks:** 131 | **Tests:** 427 passing

### What Was Built

Refactored a CLI-first script into a layered service (package → settings → repository →
Strava adapter → application/read-model services → CLI + HTTP MCP), then migrated primary
storage SQLite → DuckDB, materialized derived training metrics into versioned read-model
facts below the MCP boundary, exposed a fixed six-tool factual product surface with
bucketed aggregate analytics, made the read model self-invalidating via a source-logic
fingerprint, and finished by removing SQLite-era legacy for DuckDB-native types.

### What Worked

- **Boundary-first sequencing.** Establishing package/repository/adapter/MCP boundaries
  early (Phases 1–5) kept later storage and metric work from cementing coupling.
- **Read-model below MCP.** Keeping recompute/invalidation under the MCP surface meant the
  product tool contract stayed stable through the SQLite→DuckDB cutover and native cleanup.
- **Zero-knob invalidation (Phase 15).** A source-fingerprint over the compute closure
  removed a whole class of "forgot to bump metric_version" staleness bugs by construction.
- **Goal-backward verification.** Catching that `/gsd-stats` keys off VERIFICATION.md let
  phases 7/8 be closed honestly (retrospective synthesis + a real code pass) rather than
  re-running already-passing UAT.

### What Was Inefficient

- **Tracking drift.** STATE.md performance tables accumulated duplicate/early-phase rows
  (`Phase 7` and `7` both listed); cosmetic but noisy.
- **Phases 7/8 left `Executed` for weeks** because the older UAT+validate+secure close path
  never produced a VERIFICATION.md — a doc-shaped gap, not a work gap.
- **Post-migration dead shims** (date|str unions, ALTER-TABLE self-heal, str-parse
  fallbacks) survived several phases until the Phase 16 review swept them.

### Patterns Established

- No-backward-compat is enforced hard: one-shot migrations are deleted once run; their
  tests (DROP COLUMN "legacy DB" cases) are deleted too.
- Reviewer findings are leads, not facts — re-derived against code before acting (the
  Phase 16 review's 3 "criticals" did not hold as blockers).
- `just check` (whole-repo) + `just unit` are the canonical green gates before any close.

### Key Lessons

- A stats/label discrepancy almost always traces to a single missing artifact — check the
  artifact contract before assuming work is incomplete.
- Subagents on Sonnet for mechanical/well-planned execution; reserve Opus reasoning for
  genuinely hard calls (review triage, architecture).

### Cost Observations

- Model mix: orchestration on Opus; executor + reviewer + verifier subagents on Sonnet.
- Notable: per-plan executor isolation auto-degraded to sequential (origin/HEAD unresolved,
  #683); fine here since the phase serialized on shared schema files anyway.
