# Review Remediation Plan

**Source:** Expert-panel review (Architect, Code Health, QA, SRE, Security) at HEAD `c80c39e`, 2026-05-31.
**Mandate:** Fix everything. Speed is not the constraint — correctness and cleanliness are.
**Out of scope (operator):** `.env` relocation, Alloy/Grafana observability wiring.

## Operator decisions folded in
- `api_schema.py` + `strava_api_reference.py` are **NOT dead code** — a planned-but-unwired feature
  (capture unknown Strava fields). Keep them; mark intent. Do **not** delete.
- WR-03 test placement was an agent over-read, not a deliberate design — place each regression
  test where the guard actually lives.

## Working method
- One atomic commit per fix, conventional-commit style (`fix(...)`, `test(...)`, `refactor(...)`).
- Gate every change: `just lint` + `just typecheck` clean, `just test` green before commit.
- Verify each panel claim against code at implementation time (panel gave file:line; trust but check).

---

## Group A — Correctness: regress the named bugs  *(highest value, self-contained)*
| ID | Fix | Where | Test |
|----|-----|-------|------|
| A1 | WR-04: `calc_hrr_pct` with `Decimal`/non-float inputs (the type the materializer passes) | `metrics.py` | `tests/test_metrics_pure.py` |
| A2 | WR-03: no-HR-in-pause-window guard regression | guard lives in `read_model_materializer.py:136` → test in `test_read_model_materialization.py` (placement per actual guard) |
| A3 | WR-06: nullable-rate sync regression | `metrics.py:176` | `test_metrics_pure.py` |
| A4 | `calc_cardiac_drift`: replace `hasattr` smoke test with value assertions on a deterministic fixture | `cardiac_drift.py` | `test_metrics_pure.py:259` |

## Group B — Correctness: stop the silent swallow  *(3-expert consensus)*
| ID | Fix | Where |
|----|-----|-------|
| B1 | Narrow `_ensure_schema_extensions` `except Exception: pass` to expected `duckdb.CatalogException`; log everything else at WARNING | `adapters/duckdb/repository.py:178-184` + test injecting a failing `ensure_provenance_columns` |

## Group C — Reliability / observability
| ID | Fix | Where |
|----|-----|-------|
| C1 | Add `last_attempt_at` staleness check to `check_refresh_health` (closes silent refresh-thread death) | `refresh/health.py` + test |
| C2 | Fix `_lease_active` naive-vs-aware datetime compare; catch `TypeError` not just `ValueError` (verify first) | `deploy/preflight.py:101` + test |
| C3 | Thread rate-limit quota/usage into `refresh_failed` log event on `StravaUnavailable("rate_limited")` | `adapters/strava/transport.py` → `refresh/runtime.py` |

## Group D — Architecture: break the dependency inversion  *(the #1 structural finding)*
| ID | Fix | Where |
|----|-----|-------|
| D1 | Extract window/bucket constants (`SUPPORTED_ROLLING_WINDOW_DAYS`, `MATERIALIZED_ROLLING_WINDOW_DAYS`, `SUPPORTED_AGGREGATE_BUCKETS`) out of `application/metric_registry.py` into a core module (`metric_schema.py` or `types.py`) so adapters stop importing upward | `adapters/duckdb/aggregate_queries.py:11-19`, `read_model_materializer.py:9` |

## Group E — Architecture: layering follow-ons  *(smaller)*
| ID | Fix | Where |
|----|-----|-------|
| E1 | `application/freshness.py` should accept an injected `ReadConn`/repo instead of opening `MirrorConn` itself | `application/freshness.py:8-9` |
| E2 | Route `cli.py cmd_mirror_coverage` through `application/mirror_coverage.py` instead of opening `DuckDBRepository` directly | `cli.py:200` |

## Group F — Tidiness  *(rot the linter can't see)*
| ID | Fix | Where |
|----|-----|-------|
| F1 | Drop unused `MCP_PROMPT_NAMES` import; remove the now-needless `# noqa: F401` | `interfaces/mcp_http.py:26` |
| F2 | Remove phantom params `missing_code` / `day_column` and their `del` statements | `aggregate_queries.py:279, 1088` |
| F3 | Merge identical `_render_daily_report` / `_render_weekly_summary` | `cli.py:452-462` |
| F4 | Autouse conftest fixture to reset `_TOOL_RESPONSE_CACHE` (replace per-test manual `.clear()`) | `tests/conftest.py`, `interfaces/mcp_http.py:51` |

## Group G — Defensive / low  *(harden, don't over-build)*
| ID | Fix | Where |
|----|-----|-------|
| G1 | Internal table/column-name allowlist for `_upsert_fact` / `_next_id` (mirror existing `_column_expression` pattern) | `repository.py:285,299,582-590` |
| G2 | Create `.env.lock` via `os.open(..., O_CREAT, 0o600)` instead of umask-inherited 644 (does **not** touch `.env` itself) | `adapters/strava/token_provider.py` `_FileLock` |
| G3 | Mark `api_schema.py` intent: module docstring / TODO noting "planned: unknown-field capture, not yet wired"; open a backlog item for the actual feature | `api_schema.py` |
| G4 | Document MCP no-auth single-user threat model in code (short SECURITY note/comment) | `interfaces/mcp_http.py` |

## Migrate the `constants` → `sports` re-export (CONCERNS debt)
| ID | Fix | Where |
|----|-----|-------|
| H1 | Repoint `repository.py` / `aggregate_queries.py` sports-symbol imports to `mcp_strava.sports`, then drop the `# noqa: E402,F401,I001` re-export shim in `constants.py:118` | follows after D1 (touches same files) |

---

## Explicitly NOT doing (panel proposed, overruled)
- Splitting `repository.py` / `metric_registry.py` by line count — Architect: cohesive, splitting adds import surface without clarity. Split only on a real responsibility seam.
- Splitting `mcp_http.py` — 409 lines of thin delegations, not a god object.
- Deleting `api_schema.py` / `strava_api_reference.py` — planned feature per operator.
- Relocating `.env`, Alloy/Grafana wiring — operator deferred.

## Order of execution
A → B → C → D → H → E → F → G. (D before H because both touch the same adapter import blocks.)
