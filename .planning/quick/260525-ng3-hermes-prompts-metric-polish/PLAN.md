---
quick_id: 260525-ng3
slug: hermes-prompts-metric-polish
status: completed
created_at: "2026-05-25T16:53:00+05:00"
---

# Quick Task: Hermes Prompts And Metric Polish

## Goal

Bring over the useful Hermes Strava scenarios as MCP prompts and apply the approved metric/presentation cleanup without adding operational sync/admin surface to MCP.

## Scope

- Restore the progressive cardiac-cost freshness gate so stale CC trends do not look current.
- Round MCP presentation payload floats so agents do not receive noisy raw floats.
- Add MCP surface instructions for factual, non-medical, metric-explaining narratives.
- Document metric caveats in the registry docs.
- Preserve and expose Strava kudos as factual social activity metrics.
- Add markdown-backed MCP prompts for daily report, weekly digest, and shoe-mileage watchdog scenarios.

## Acceptance Criteria

- MCP tool allowlist remains the same five product tools.
- No sync/admin/debug/raw SQL capability is added to MCP.
- Prompt content is loaded from repository content files and copied into the Docker image.
- Kudos facts appear in workout list/detail payloads and the metric registry.
- Focused tests and full test suite pass.

## Result

Completed on 2026-05-25.
