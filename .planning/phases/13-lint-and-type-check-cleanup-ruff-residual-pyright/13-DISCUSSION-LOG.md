# Phase 13: Lint and type-check cleanup (ruff residual + pyright) - Discussion Log (Assumptions Mode)

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the analysis.

**Date:** 2026-05-30
**Phase:** 13-lint-and-type-check-cleanup-ruff-residual-pyright
**Mode:** assumptions
**Areas analyzed:** Row-typing strategy, None-guards, dc_to_dict annotation, Genuine one-offs, pyright config/scope/hygiene/DoD

## Scope finding (pre-analysis)

The orchestrator verified live tool state before analysis: `uv run ruff check src tests` → "All checks passed!" (ruff portion of the ROADMAP scope already absorbed by Phase 11 autofix `b27a167` + Phase 12 repo-wide format). `uv run pyright` → 359 errors, 0 warnings, all in `src/`. The phase therefore collapses to pyright cleanup. pyright error breakdown by rule: 220 reportArgumentType, 53 reportAttributeAccessIssue, 21 reportIndexIssue, 21 reportCallIssue, 20 reportOptionalSubscript, 12 reportOptionalMemberAccess, 5 reportGeneralTypeIssues, 3 reportOptionalOperand, 2 reportReturnType, 1 reportOperatorIssue, 1 reportPrivateImportUsage.

## Assumptions Presented

### Row-typing strategy
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Widen DuckDB fetch boundary to `dict[str, Any]` (`_fetchone`/`_fetchall`/`_scalar` + `Row` alias); no coercion helpers, no TypedDicts | Confident | repository.py:245-267 (dict synthesis), 517-520/548-550/678/884/1129/2251-2262 (int/str casts), 326-339/396/1810-1811/2105 (attr access) |

### None-guards
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Widening clears casts but Optional subscript/member-access on fetchone results still need explicit guards/asserts; sweep genuine sites | Confident | preflight.py:118 (real reportOptionalSubscript Any won't fix); guarded sites repository.py:396/680-685/986/1298/1504/1568/2048; assert sites 1427/1458 |

### dc_to_dict annotation
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Annotate `dc_to_dict -> Any`; resolves reportReturnType + setitem reportCallIssue cluster | Confident | types.py:818 (no return annotation → inferred recursive union); aggregate_services.py:86-90, product_facts.py:127/312/314/379/522-523, cli.py:139-151 |

### Genuine one-offs
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Fix individually: mcp_http.py:12 public import swap; connection.py:113 conn cast; devtools client.py:255-258 None filter; confirm iterable/operator one-offs post-widening | Likely | mcp.server.transport_security.TransportSecuritySettings verified importable; repository.py:156 conn:object; aggregate_queries.py:1105, repository.py:685, metric_services.py:551 |

### pyright config/scope/hygiene/DoD
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Pin typeCheckingMode="standard"; keep src-only scope; drop 3 vestigial BLE001 noqa; DoD = just check + just test green; CI gate deferred | Confident | pyproject.toml [tool.pyright] minimal/no mode; Justfile typecheck=pyright src; select set excludes BLE; no .pre-commit-config.yaml |

## Corrections Made

No corrections — all assumptions accepted as locked decisions. Per the developer's standing preference, technical-implementation decisions in a pure-tooling phase are decided by Claude (assumptions mode) and surfaced for review, not presented as questions. No business/product decisions arose in this phase.

## External Research

None performed — `needs_research` was empty. The one external touchpoint (`mcp.server.transport_security.TransportSecuritySettings` public import path) was verified directly against the installed package; pyright "standard" mode behavior is stable and version-pinned via the lockfile.
