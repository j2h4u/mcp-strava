# Feature Research

**Domain:** Local Strava mirror + read-only MCP training analytics service
**Researched:** 2026-05-20
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (v1 Refactor + Read-Only MCP Surface)

Features users assume exist. Missing these makes analytics feel unreliable or incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Read-only MCP tools for core user goals (`latest_workouts`, `daily_training_report`, `weekly_load_summary`, `readiness_and_recommendation`) | Users ask training questions, not API endpoint questions | MEDIUM | Tools must map to intent-level outcomes, not Strava route wrappers |
| Stable local mirror-backed analytics (works even when Strava API is unavailable at request time) | Local mirror is the core value and resilience promise | MEDIUM | Serve from SQLite mirror first; avoid live API coupling in MCP request path |
| Fitness/Fatigue/Form style load trend outputs | This is baseline in Strava/TrainingPeaks/Intervals-style tools | MEDIUM | Keep labels explicit: this is training load/readiness proxy, not absolute fitness |
| Activity detail analytics with per-session key metrics | Users expect drill-down from summary into specific sessions | MEDIUM | Include pace/power/HR-derived metrics already supported by core modules |
| Explicit data freshness status on every analytics response | Users need to trust if insights reflect recent training | LOW | Return `freshness_state`, `last_sync_at`, `staleness_age` with every report tool |
| Automatic refresh policy behavior (daily minimum + on-request staleness check) | Mirror should stay useful without manual ops commands | MEDIUM | Freshness decisions stay in service layer; MCP stays read-only |
| Missing-data transparency (especially no-HR activities) | Silent drops break trust and distort load interpretation | MEDIUM | Mark missing HR-derived load as unknown/partial; do not treat as rest day |
| Sport-aware aggregation (run/ride/other) | Multi-sport users expect segmented and combined views | LOW | Reuse existing sport registry semantics in output |
| Explainable recommendation output with rationale/warnings | Recommendations without reasons are not actionable | MEDIUM | Include drivers: recent load delta, form trajectory, warning triggers |
| Data-preservation-safe behavior for analytics services | Existing mirrored DB is expensive and must be protected | LOW | Read paths must be migration-safe; no MCP actions can mutate sync/admin state |

### Differentiators (Later Phases)

Features that create clear value beyond baseline load charts.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Goal-oriented microcycle advisor (event/date aware) | Converts metrics into practical next-7-day guidance | HIGH | Extend current weekly plan with event context and conservative guardrails |
| Confidence-scored recommendations | Helps users judge when to trust vs ignore advice | MEDIUM | Attach confidence bands based on data completeness and freshness |
| “What changed” causal insights between periods | Users want explanation, not just numbers | HIGH | Compare periods and attribute shifts (volume, intensity, recovery, missing sensors) |
| Subjective + objective fusion (RPE + HR/power/pace) | Better readiness decisions vs pure load math | HIGH | Uses parsed perceived exertion to fix current model blind spot |
| Outlier/overreach detector with early warning flags | Prevents injury-prone ramp patterns | MEDIUM | Build on ACWR/progressive signals plus per-sport baselines |
| Data quality diagnostics for analytics trust | Distinguishes true training changes from sensor artifacts | MEDIUM | Highlight low confidence when streams are sparse/downsampled/missing |

### Anti-Features (Deliberately Excluded from MCP)

Features that look useful but violate boundary/safety goals.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| MCP `sync` / `backfill` / `force_refresh` tools | “I want newest data now” | Turns MCP into infra control plane; increases rate-limit and failure blast radius | Keep automated refresh policy in service layer and return freshness status |
| MCP raw Strava endpoint passthrough | “I need full flexibility” | Produces endpoint-wrapper surface, schema churn, weak user-level semantics | Add curated analytics/use-case tools only |
| MCP arbitrary SQL/query tools | “Fast debugging and custom analysis” | Security and data-integrity risk; exposes internal schema coupling | Keep SQL local CLI-only for owner debugging |
| MCP auth/token/admin operations | “Need to fix account quickly” | Expands secret-handling attack surface and operational complexity | Keep auth/admin as local operator workflows only |
| Real-time/live polling analytics over MCP | “Always up-to-the-second” | Unnecessary API pressure and noisy recommendations for this local-use case | Daily sync + staleness-triggered refresh checks |
| Social/gamification MCP features (kudos automation, feed ops) | “Feels like Strava app parity” | Distracts from training analytics mission, adds brittle API dependencies | Focus MCP on training insight and planning support |
| Multi-user tenancy/permissions in v1-v1.x | “Future-proof now” | Overengineering for one-primary-user scope | Keep single-user local model; revisit only with real usage pressure |
| Endpoint-by-endpoint MCP mirroring | “Coverage completeness” | Bloated tool catalog with low signal and poor UX | Consolidate by user intent: workouts, load, readiness, recommendations |

## Data-Preservation and Freshness Policy Behaviors

| Behavior | Requirement | Why It Matters |
|----------|-------------|----------------|
| Preserve mirror as durable state | Never treat local DB as disposable cache | Prevents expensive refetch and analytics regressions |
| Read-first analytics | Serve user responses from local mirror | Keeps MCP reliable under API outages/rate limits |
| Freshness metadata in every response | Include last successful mirror update and staleness | Makes recommendation trust explicit |
| Staleness-aware service logic | If stale threshold exceeded, mark response degraded and schedule refresh path outside MCP action space | Avoids hidden stale outputs without exposing sync controls |
| Partial-data annotation | Mark sessions/periods with missing streams/HR | Prevents false confidence in load/readiness metrics |

## Feature Dependencies

```text
Mirror freshness policy + status model
    └──requires──> Service-layer freshness evaluator
                       └──requires──> Repository abstraction over SQLite mirror

Intent-level MCP analytics tools
    └──requires──> Stable application service contracts
                       └──requires──> Typed report/analytics response models

Explainable recommendations
    └──requires──> Reliable load/history computation
                       └──requires──> Missing-data transparency

Differentiator: confidence-scored recommendations
    └──enhances──> Explainable recommendations
    └──requires──> Freshness metadata + data-quality diagnostics

Anti-feature conflict:
MCP sync/admin/debug exposure
    └──conflicts──> Read-only analytics boundary
```

### Dependency Notes

- **Intent-level MCP tools require service contracts:** MCP should call stable use-cases, not compose SQL or Strava payloads directly.
- **Explainable recommendations require data-quality handling first:** otherwise recommendation logic overstates certainty on incomplete streams.
- **Freshness metadata is foundational:** differentiators are lower value if users cannot trust data recency.
- **Sync/admin MCP exposure conflicts with product boundary:** it shifts the product from analytics assistant to operations surface.

## MVP Definition

### Launch With (v1)

- [ ] Intent-level read-only MCP tools for workouts, daily report, weekly load summary, and readiness recommendation
- [ ] Service-layer freshness policy with automatic daily refresh target and request-time staleness evaluation
- [ ] Response-level trust metadata (`freshness`, `data_completeness`, `warnings`)
- [ ] Missing-HR/missing-stream transparency in summaries and recommendations
- [ ] Sport-aware aggregation and drill-down outputs

### Add After Validation (v1.x)

- [ ] Confidence-scored recommendations based on freshness + completeness
- [ ] Overreach/ramp early warning detector tuned per sport
- [ ] “What changed” analytics between rolling periods

### Future Consideration (v2+)

- [ ] Event-goal-aware microcycle advisor with scenario simulation
- [ ] Deeper subjective/objective fusion including RPE trend learning
- [ ] Advanced anomaly explanation for sensor and physiological drift

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Intent-level read-only MCP analytics tools | HIGH | MEDIUM | P1 |
| Freshness status + policy-aware analytics responses | HIGH | MEDIUM | P1 |
| Missing-data transparency for load/recommendation paths | HIGH | MEDIUM | P1 |
| Explainable recommendation rationale/warnings | HIGH | MEDIUM | P1 |
| Confidence scoring | MEDIUM | MEDIUM | P2 |
| Overreach/ramp detection | MEDIUM | MEDIUM | P2 |
| Goal-aware microcycle advisor | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have once core is stable
- P3: Future expansion

## Sources

- Project context and constraints: `.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/CONCERNS.md`
- Strava Support: Relative Effort, Fitness/Freshness behavior and terminology (`support.strava.com`)
- TrainingPeaks documentation and guides on CTL/ATL/TSB and performance management chart (`trainingpeaks.com`)
- Intervals.icu feature docs (load, decoupling, interval analytics) (`intervals.icu/features`)
- GoldenCheetah official feature overview (Banister/PMC and deep metrics) (`goldencheetah.org`)

---
*Feature research for: Local Strava mirror + MCP training analytics*
*Researched: 2026-05-20*
