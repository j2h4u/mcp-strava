# Phase 13: Lint and type-check cleanup (ruff residual + pyright) - Context

**Gathered:** 2026-05-30 (assumptions mode)
**Status:** Ready for planning

<domain>
## Phase Boundary

Clear the deferred lint/type findings from when ruff + pyright were introduced in Phase 11 side-work. End state: `just check` (= `lint` + `fmt-check` + `typecheck`) and `just test` both green.

**Scope reframe (verified 2026-05-30):** The ruff portion of the original ROADMAP scope is **already done** — `uv run ruff check src tests` reports "All checks passed!". The ~40 F401 and ~17 manual bugbear/pyupgrade fixes were absorbed by Phase 11's autofix (`b27a167`) and Phase 12's repo-wide `ruff format` + executor B904/import fixes. **This phase is now entirely about pyright: 359 errors, 0 warnings, all in `src/`.** The ruff rule set (`select = ["E4","E7","E9","F","I","B","UP"]`, line-length 120) is a locked project choice and is NOT being expanded here.
</domain>

<decisions>
## Implementation Decisions

### Row-typing strategy (the dominant ~326-error cluster)
- **D-01:** Widen the DuckDB fetch boundary to `Any`. Change `_fetchone()` → `dict[str, Any] | None`, `_fetchall()` → `list[dict[str, Any]]`, `_scalar()` → `Any | None` in `src/mcp_strava/adapters/duckdb/repository.py`, and introduce a module-level `Row = dict[str, Any]` alias used on every method currently returning `dict[str, object]`. **Do NOT** add runtime coercion helpers (`_int()/_float()/_str()`) and **do NOT** add per-query TypedDicts.
  - Rationale: `_fetchone`/`_fetchall` synthesize dicts from `result.description` + raw tuples (`repository.py:245-267`); values are genuinely untyped external data, so `Any` is the honest type, not a concession. `int(object)`/`str(object)` is illegal but `int(Any)`/`str(Any)` is legal — widening clears the 220 `reportArgumentType`, 53 `reportAttributeAccessIssue`, 21 `reportIndexIssue`, 20 `reportOptionalSubscript`, 12 `reportOptionalMemberAccess` clusters at the source. Coercion helpers would touch ~100 call sites for runtime safety the explicit `int()/str()/float()` casts already provide and still wouldn't catch column-name typos. TypedDicts are over-engineering for an adapter using `SELECT *` / dynamic column lists (`repository.py:478, 534, 814`) that can't be statically typed anyway.

### None-guards (independent fix surface — survives the alias change)
- **D-02:** Widening clears the cast errors, but `reportOptionalSubscript`/`reportOptionalMemberAccess` on `_fetchone()` results (`... | None`) still require explicit `is None` / truthiness guards (or deliberate `assert ... is not None`) at the genuine sites — e.g. `src/mcp_strava/preflight.py:118`, which `Any` will NOT fix because the None comes from the optional itself. Sweep these explicitly; do not assume the alias covers them. (Most call sites already guard, e.g. `repository.py:396, 680-685, 986, 1298, 1504, 1568, 2048`; two intentionally `assert` for no-GROUP-BY aggregates at `repository.py:1427, 1458`.)

### `dc_to_dict` return annotation (the reportReturnType + setitem sub-cluster)
- **D-03:** Annotate `dc_to_dict` (`src/mcp_strava/types.py:818`) `-> Any`. It currently has no return type, so pyright infers a deeply-nested recursive union (the verbatim `reportReturnType` "float is not assignable to dict[str, object]" errors). Downstream `payload[key] = ...` / `evidence[target] = evidence[source]` mutations then fail as `reportCallIssue` (`__setitem__`/`__getitem__` overloads don't match the inferred union) in `aggregate_services.py:86-90`, `product_facts.py:127, 312, 314, 379, 522-523`, and the `cli.py:139-151` getitem chain. `-> Any` collapses all of them at the converter. This is a **distinct** fix from D-01 — do not conflate.

### Genuine one-offs (not absorbed by D-01/D-03)
- **D-04:** Fix individually:
  1. **reportPrivateImportUsage** — change `src/mcp_strava/interfaces/mcp_http.py:12` from `from mcp.server.fastmcp.server import TransportSecuritySettings` to `from mcp.server.transport_security import TransportSecuritySettings` (public path, verified importable against the installed `mcp` package — no version pin needed).
  2. **connection.py:113** — `conn: object` has no `.close()`; add a localized cast/narrowing rather than importing duckdb types (preserves the deliberate "don't depend on duckdb types" choice at `repository.py:156`).
  3. **devtools/mcp_client/client.py:255,258** — `sorted(set[Any | None])` fails (None not comparable); filter None or annotate.
  4. **Iterable/operator one-offs** (`reportGeneralTypeIssues` "object is not iterable" at `aggregate_queries.py:1105`, `repository.py:685`, `metric_services.py:551`; `reportOperatorIssue`) — expected to clear under D-01; **confirm post-change**, fix per-site (1-line guard/cast) only if any remain.

### pyright config, scope, hygiene, definition-of-done
- **D-05:** Pin `typeCheckingMode = "standard"` explicitly in `[tool.pyright]` (currently relies on the implicit default) so the green state is reproducible and version-drift-proof.
- **D-06:** Keep type-check scope **src-only** (`just typecheck` = `pyright src`). Do NOT add `tests/` to type-checking this phase — tests are green and dynamically loose (fixtures, monkeypatch); expanding scope would manufacture new errors for no phase benefit.
- **D-07:** Remove the 3 vestigial `# noqa: BLE001` (`refresh/worker.py:108, 248`, `refresh/health.py:62`) — `BLE001` is not in the ruff select set, so they suppress nothing. **Keep** the live re-export noqa: `# noqa: F401` (`interfaces/mcp_http.py:26`) and `# noqa: E402, F401, I001` (`constants.py:118`).
- **D-08:** Definition of done: `just check` (lint + fmt-check + typecheck) and `just test` both exit green. A standing pre-commit/CI gate is **out of scope** (no `.pre-commit-config.yaml` exists) → see Deferred Ideas.

### Claude's Discretion
- Exact ordering of edits and per-file commit granularity is the planner/executor's call. Recommended sequence: D-03 + D-01 first (clears the bulk), re-run pyright, then sweep D-02 None-guards and D-04 one-offs against the residual list, then D-05/D-07 config+hygiene, then verify D-08.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs/ADRs. The canonical sources of truth for this phase are in-repo config and code:
- `pyproject.toml` — `[tool.ruff.lint]` (locked select set; do not expand) and `[tool.pyright]` (mode + include to edit per D-05/D-06)
- `Justfile` — `lint` / `fmt-check` / `typecheck` / `check` / `test` targets (the definition-of-done gates, D-08)
- `src/mcp_strava/adapters/duckdb/repository.py` — `_fetchone`/`_fetchall`/`_scalar` (D-01 edit surface) and the row call sites
- `src/mcp_strava/types.py` — `dc_to_dict` at L818 (D-03)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `repository.py:245-267` `_fetchone()`/`_fetchall()` and `_scalar()` — single boundary where the `Row` alias lands (D-01); widening here propagates to all consumers.
- `types.py:818` `dc_to_dict` — single dataclass→dict converter feeding aggregate/product/cli payloads (D-03).
- `Justfile` targets `check` (= `lint` + `fmt-check` + `typecheck`) and `test` — the authoritative green gates.

### Established Patterns
- **Deliberate duckdb-type avoidance:** `DuckDBRepository.conn` and module-level conn params are typed `object` on purpose (`repository.py:156`) — honor this; prefer local casts over importing duckdb types (D-04.2).
- **Namespace re-export modules with `__all__`:** `constants.py` re-exports under `# noqa: E402, F401, I001` (Phase 12); these noqa are live and must stay (D-07).
- **Honest-`Any` for external/dynamic data:** rows from DuckDB and JSON-safe `dc_to_dict` output are genuinely dynamic; `Any` at those boundaries is correct, not lazy.

### Integration Points
- `[tool.pyright]` in `pyproject.toml` (mode pin + scope, D-05/D-06).
- `# noqa` comments in `refresh/worker.py`, `refresh/health.py`, `interfaces/mcp_http.py`, `constants.py` (D-07).
</code_context>

<specifics>
## Specific Ideas

Prefer the smallest honest type at each boundary (`Any` for untyped external data) over either suppression (`# type: ignore`, lowering pyright mode) or over-typing (per-query TypedDicts). The goal is a green, reproducible `just check` — not maximal type strictness on dynamically-sourced data.
</specifics>

<deferred>
## Deferred Ideas

- **Standing lint/type gate** — add a `.pre-commit-config.yaml` (or CI step) running `ruff check` + `ruff format --check` + `pyright src` so the green state can't silently regress. Out of scope for Phase 13 (this phase makes it green; enforcement infra is its own small phase).
- **Type-check `tests/`** — extend pyright `include` to cover `tests/` and clean the resulting errors. Separate follow-up; tests are intentionally loose today.
- **Runtime row-coercion helpers / TypedDict row models** — if column-name-typo safety or stronger row guarantees are ever wanted, revisit `_int()/_float()` helpers or per-fixed-shape-query TypedDicts (explicitly rejected for D-01 as over-engineering now).

### Reviewed Todos (not folded)
None — no pending todos matched Phase 13.
</deferred>
