# Phase 09: Product factual bundles and CLI read-model consolidation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-26
**Phase:** 09-product-factual-bundles-and-cli-read-model-consolidation
**Areas discussed:** panel sufficiency, product factual bundles, safety/status facts, CLI cleanup, gear/kudos facts

---

## Panel Sufficiency

| Option | Description | Selected |
|--------|-------------|----------|
| Discuss product bundles | Re-open daily/weekly/historical bundle shape with the user. | |
| Discuss safety/status facts | Re-open factual warning/status semantics with the user. | |
| Discuss CLI cleanup | Re-open CLI product/admin split and dead-handler cleanup with the user. | |
| Use panel synthesis | Treat the prior audit and expert panel as sufficient product input. | x |

**User's choice:** The user clarified that the expert panel had already decided the product direction and asked why additional points needed discussion.
**Notes:** The resulting decision is that no additional business/product answers are required before planning. Phase 9 context should lock the panel synthesis and let the planner handle implementation details.

---

## Product Factual Bundles

| Option | Description | Selected |
|--------|-------------|----------|
| Preserve old CLI shape | Keep old report/weekly JSON and command semantics. | |
| Restore factual product value | Recover useful old facts into registry/read-model-backed MCP/CLI services without preserving old shapes. | x |
| Add new interpretation tools | Add coaching/recommendation tools to MCP. | |

**User's choice:** Restore factual product value.
**Notes:** This follows earlier decisions: no backward compatibility obligation, factual-only MCP, and no server-side interpretation.

---

## Safety And Status Facts

| Option | Description | Selected |
|--------|-------------|----------|
| Drop old warnings | Remove warning logic entirely. | |
| Preserve as factual flags | Keep threshold/status facts with code, threshold, evidence, and completeness. | x |
| Preserve advice text | Keep old recommendation or warning prose as server output. | |

**User's choice:** Preserve as factual flags.
**Notes:** Threshold categories are valid derived facts when registered and documented; advice text remains for the consuming agent, not the service.

---

## CLI Cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| Keep legacy CLI code | Keep dead handlers and old direct computations for compatibility. | |
| Thin CLI over services | Keep CLI as an alternative product/admin surface over the same core services. | x |
| Remove CLI entirely | MCP only. | |

**User's choice:** Thin CLI over services.
**Notes:** The user previously stated CLI is still needed for users who do not want MCP, but must be thin like MCP.

---

## Gear And Kudos

| Option | Description | Selected |
|--------|-------------|----------|
| Ignore gear/kudos | Keep them out of product facts. | |
| Expose factual context | Preserve kudos and shoe-mileage facts where local mirror data supports them. | x |
| Add aggregate gear filters now | Make gear a full aggregate grouping/filtering dimension. | |

**User's choice:** Expose factual context.
**Notes:** Kudos are already mirrored and intentionally product-visible. Gear/shoe mileage is relevant because the MCP prompt surface includes a shoe-mileage scenario, but Phase 8 excluded gear filters from aggregate queries.

## The Agent's Discretion

- Exact JSON field names, bundle section names, and service method names are planner discretion.
- Planner may decide where gear facts fit best, as long as MCP remains factual and product-only.
- Planner may choose exact deletion order for dead CLI handlers after product facts are recovered.

## Deferred Ideas

- Training model redesign.
- Coaching/recommendation interpretation.
- Medical advice or diagnosis.
- Raw SQL/raw Strava/sync/admin exposure through MCP.
