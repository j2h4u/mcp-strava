---
phase: 15-self-invalidating-read-model-source-fingerprint-auto-recompu
plan: 01
subsystem: metric-platform
tags: [fingerprint, read-model, self-invalidation, poka-yoke, tdd]
requires:
  - "metric_registry.py as the compute-surface inventory owner"
  - "read_model_materializer compute path (metrics/training/hr_zones/constants/repository/metric_registry)"
provides:
  - "COMPUTE_SOURCE_MODULES (module-level tuple in metric_registry.py)"
  - "compute_logic_fingerprint() (deterministic sha256 over compute-path source text)"
  - "tests/test_logic_fingerprint.py (determinism, sensitivity, completeness)"
affects:
  - "15-02+ ride this fingerprint to bump metric_version and enqueue recompute"
tech-stack:
  added: []
  patterns:
    - "sha256 over name\\x00source\\x00 pairs (mirrors repository._semantic_json_hash idiom)"
    - "runtime import_module inside the function to avoid repository->schema->metric_registry cycle"
    - "static AST import-closure walk for completeness poka-yoke"
key-files:
  created:
    - "tests/test_logic_fingerprint.py"
  modified:
    - "src/mcp_strava/metric_registry.py"
decisions:
  - "COMPUTE_SOURCE_MODULES is the FULL recursive mcp_strava import closure (14 modules), not the plan's literal 8-module compute subset"
metrics:
  duration: "~10 min"
  completed: "2026-06-03"
---

# Phase 15 Plan 01: Source-text Logic Fingerprint Summary

`compute_logic_fingerprint()` derives a deterministic sha256 from the source text of every `mcp_strava` module reachable from the materializer compute path, replacing the hand-bumped `metric_version` "did the logic change?" judgment with an automatic, source-derived detector (a local dbt `state:modified` analog).

## What Was Built

- **`COMPUTE_SOURCE_MODULES`** — a module-level tuple in `metric_registry.py` listing the full recursive `mcp_strava.*` import closure of `read_model_materializer` (14 modules: connection, read_model_materializer, repository, schema, cardiac_drift, constants, hr_zones, mcp_content, metric_registry, metrics, settings, sports, training, types).
- **`compute_logic_fingerprint()`** — hashes `name\x00source\x00` pairs (module name + `inspect.getsource`), sorted by module name, into a single sha256 hex digest. `import_module` is called at runtime inside the function to avoid the `repository → schema → metric_registry` import cycle. Mirrors the `_semantic_json_hash` sha256/`.hexdigest()` idiom in `repository.py:135`.
- **`tests/test_logic_fingerprint.py`** — 10 tests across three properties:
  - *Determinism*: 64-char hex, stable in-process, equal in a fresh subprocess, and equal under `PYTHONHASHSEED=0/1/random` (proves it is NOT builtin `hash()`).
  - *Coverage-by-construction (sensitivity)*: monkeypatching `inspect.getsource` for a listed module flips the digest; altering an unlisted module (`mcp_strava.cli`) does not.
  - *Completeness (poka-yoke)*: a static AST import-closure walk recomputes the reachable module set and asserts exact equality with `COMPUTE_SOURCE_MODULES`, failing loudly (naming the offender) on either a missing or an extra module; plus an explicit guard that every direct materializer import is listed and that `metric_registry` itself is in the tuple.

## TDD Gate Compliance

- RED commit `28803f4` (`test(15-01)`): tests fail with `ImportError: cannot import name 'COMPUTE_SOURCE_MODULES'` — confirmed before implementation.
- GREEN commit `09e1ba4` (`feat(15-01)`): implementation added; all 10 tests pass.
- REFACTOR: none needed — code was ruff- and pyright-clean at GREEN and already matches the `_semantic_json_hash` idiom.

## Deviations from Plan

### Design clarification (plan explicitly delegated this)

**1. [Rule 3 / plan-delegated] COMPUTE_SOURCE_MODULES is the full recursive closure (14 modules), not the plan's literal 8-module compute subset**

- **Found during:** Task 1 (RED test design) — tracing the materializer's transitive `mcp_strava` import graph.
- **Issue:** The plan's `<implementation>` lists an 8-module tuple, but the materializer directly imports `mcp_strava.settings` (and `settings → hr_zones, mcp_content`; `connection → settings`; `repository → connection, schema, sports, types`), so the real reachable closure is 14 modules. The plan's two stated completeness assertions — (a) a static AST walk compared against the tuple, and (b) "every direct `from mcp_strava import` in the materializer resolves to a tuple member" — are mutually inconsistent with the literal 8-tuple (which omits `settings`). The plan also explicitly instructed: *"adjust the tuple … so the completeness test passes by listing reality, not by weakening the test."*
- **Decision:** Listed the full recursive closure. This is the only self-consistent definition where the AST walk and the direct-import assertion cannot disagree, and it makes coverage automatic-by-construction (no "compute vs plumbing" judgment call can silently drop a module). Over-invalidation (e.g. a `settings.py` env-knob edit flips the fingerprint and triggers a recompute) is safe and cheap — that is the explicit zero-knob design intent; under-invalidation is the bug this prevents.
- **Files modified:** `src/mcp_strava/metric_registry.py`, `tests/test_logic_fingerprint.py`
- **Commit:** `09e1ba4`

## Verification

- `uv run pytest -q tests/test_logic_fingerprint.py` — 10 passed.
- Full suite `uv run pytest -q` — 358 passed (no regressions).
- `uv run ruff check src tests` — clean.
- `uv run ruff format --check src tests` — clean (105 files formatted).
- `uv run pyright src` — 0 errors, 0 warnings.
- `PYTHONPATH=src python -c "...compute_logic_fingerprint()"` — printed `49187d14…0b37d3` (64-char hex), proving no top-level import cycle.

## Known Stubs

None.

## Threat Flags

None — `import_module` targets come from a hard-coded in-repo tuple, never from runtime or Strava input (matches the plan's threat register T-15-02 disposition).

## Self-Check: PASSED

- FOUND: `src/mcp_strava/metric_registry.py` (modified — `COMPUTE_SOURCE_MODULES` + `compute_logic_fingerprint`)
- FOUND: `tests/test_logic_fingerprint.py` (created)
- FOUND commit: `28803f4` (RED)
- FOUND commit: `09e1ba4` (GREEN)
