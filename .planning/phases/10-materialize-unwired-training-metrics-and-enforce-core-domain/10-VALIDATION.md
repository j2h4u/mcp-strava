---
phase: 10
slug: materialize-unwired-training-metrics-and-enforce-core-domain
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-29
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `PYTHONPATH=src python -m pytest tests/test_metrics_pure.py tests/test_security_guards.py -x -q` |
| **Full suite command** | `just test` (≡ `PYTHONPATH=src python -m pytest -q`) |
| **Estimated runtime** | ~30–60 seconds (quick); full suite a few minutes |

---

## Sampling Rate

- **After every task commit:** Run `PYTHONPATH=src python -m pytest tests/test_metrics_pure.py tests/test_security_guards.py -x -q`
- **After every plan wave:** Run `just test`
- **Before `/gsd-verify-work`:** Full suite must be green (no regression in TRIMP / zones / cardiac_cost)
- **Max feedback latency:** 60 seconds (quick), full suite at wave merges

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | Core/domain separation | T-10-01 | Domain modules import no `mcp_strava.db` / `mcp_strava.adapters.duckdb` (RED then GREEN) | unit (AST) | `PYTHONPATH=src python -m pytest tests/test_security_guards.py -k storage_strava_or_refresh -x` | ⚠ extend existing | ⬜ pending |
| 10-02-01 | 02 | 1 | fix unmaterialized metrics | — | `calc_hr_recovery`/`calc_vertical_speed` compute from plain rows; return None on insufficient data | unit (tdd) | `PYTHONPATH=src python -m pytest tests/test_metrics_pure.py -x` | ❌ W0 | ⬜ pending |
| 10-02-02 | 02 | 1 | fix unmaterialized metrics | — | `calc_cardiac_drift(rows, sport)` + `calc_hrr_pct(median, rest, max)` correct | unit (tdd) | `PYTHONPATH=src python -m pytest tests/test_metrics_pure.py -x` | ❌ W0 | ⬜ pending |
| 10-03-01 | 03 | 2 | fix unmaterialized metrics | T-10-DI | `_activity_fact` calls pure fns via repo fetch; 13 columns non-default | integration | `PYTHONPATH=src python -m pytest tests/test_read_model_materialization.py -k populat -x` | ⚠ extend existing | ⬜ pending |
| 10-03-02 | 03 | 2 | fix unmaterialized metrics; Core/domain separation | T-10-DI | hrr_pct reuses `hr_max_observed` (line 141); rolling medians auto-populate; no TRIMP/zones/cc regression | integration/regression | `PYTHONPATH=src python -m pytest tests/test_read_model_materialization.py tests/test_metric_registry.py -x` | ✅ existing | ⬜ pending |
| 10-04-01 | 04 | 3 | Core/domain separation | — | Dead symbols removed from metrics.py; test_smoke imports updated; suite green | unit | `PYTHONPATH=src python -m pytest tests/test_smoke.py -x -q` | ✅ existing | ⬜ pending |
| 10-04-02 | 04 | 3 | Core/domain separation | — | `db.py::get_daily_trimp_history` removed; no `src/` importer; suite green | unit | `just test` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_metrics_pure.py` — RED stubs for `calc_hr_recovery`, `calc_vertical_speed`, `calc_cardiac_drift`, `calc_hrr_pct` (pure, plain-data inputs).
- [ ] Extend `tests/test_security_guards.py` — storage-boundary guard test (must fail RED while `metrics.py` still imports `mcp_strava.db`).
- [ ] Extend `tests/test_read_model_materialization.py` — assert the 13 fact columns are non-default after materialization (existing `_seed_dirty_activity_with_streams` already seeds 180 rows incl. altitude).
- [ ] No framework install needed — pytest + duckdb already present.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live DuckDB returns real (non-null) hr_recovery / vertical_speed / cardiac_drift / hrr_pct + rolling medians via MCP after re-materialize | fix unmaterialized metrics (LIVE OPS) | Operator-run post-deploy data migration on the live single-writer DuckDB; not reproducible in CI | 1. Confirm read-only backup `~/backups/mcp-strava-safe/` intact. 2. Owner-driven re-materialize of the read model. 3. Call MCP `get_workout_detail` / `compare_periods`; assert metrics return real values. |

*All in-code behaviors have automated verification; only the live re-materialize is manual by design.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test_metrics_pure.py + boundary extension + materializer assertion)
- [x] No watch-mode flags
- [x] Feedback latency < 60s (quick run)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
