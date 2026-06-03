---
phase: 15
slug: self-invalidating-read-model-source-fingerprint-auto-recompu
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-03
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 9 (`[tool.pytest.ini_options]`, `pythonpath=["src"]`) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest -q tests/<touched_file>.py` |
| **Full suite command** | `uv run pytest -q` (unit) ; `just test` (unit + Docker build + live MCP smoke) for the phase gate |
| **Estimated runtime** | ~10-30s unit; `just test` adds Docker build + smoke (~1-2 min) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q tests/<touched_file>.py`
- **After every plan wave:** Run `uv run pytest -q` + `uv run ruff check src tests` + `uv run ruff format --check src tests` + `uv run pyright src`
- **Before `/gsd-verify-work`:** `just test` must be green (unit + Docker build + live MCP smoke)
- **Max feedback latency:** 30 seconds (unit)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 15-01-* | 01 | 1 | REQ-ZEROKNOB | T-15-02 | `import_module` only over hard-coded `COMPUTE_SOURCE_MODULES` tuple; never input-derived | unit | `uv run pytest -q tests/test_logic_fingerprint.py -k determinism` | ❌ W0 | ⬜ pending |
| 15-01-* | 01 | 1 | REQ-ZEROKNOB | — | Completeness: every materializer compute module is listed | unit | `uv run pytest -q tests/test_logic_fingerprint.py -k completeness` | ❌ W0 | ⬜ pending |
| 15-02-* | 02 | 1 | REQ-ZEROKNOB | T-15-01 | Sidecar writes use parameterized SQL / `_safe_identifier` for any identifier | integration | `uv run pytest -q tests/test_logic_fingerprint.py -k "zero_knob or seed_no_recompute"` | ❌ W0 | ⬜ pending |
| 15-03-* | 03 | 2 | REQ-ZEROKNOB | — | Aggregate reads pin `metric_version = current` (R11); no version blend | integration | `uv run pytest -q tests/test_metric_services.py -k no_blend` | ⚠️ extend | ⬜ pending |
| 15-04-* | 04 | 3 | REQ-WALK | — | Walk-sport TRIMP discounted per-sport; non-walk days unaffected; Banister consumes discounted value | unit+integration | `uv run pytest -q tests/test_metrics_pure.py tests/test_duckdb_repository.py -k walk_discount` | ⚠️ extend | ⬜ pending |
| 15-05-* | 05 | 3 | REQ-TIME | — | `start_time_local` materialized from `start_date_local`; `relative_time` boundary at 24h | unit+integration | `uv run pytest -q tests/test_metric_services.py -k "relative_time or start_time"` | ⚠️ extend | ⬜ pending |

*Task IDs are placeholders pending the planner's final plan/wave assignment. Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_logic_fingerprint.py` — new file: zero-knob proof, completeness guard, determinism (cross-process / PYTHONHASHSEED), migration seed-no-recompute (REQ-ZEROKNOB)
- [ ] Extend `tests/test_metric_services.py` — no-blend (R11), relative_time formatting, start_time_local in payload (REQ-ZEROKNOB, REQ-TIME)
- [ ] Extend `tests/test_metrics_pure.py` + `tests/test_duckdb_repository.py` — walk discount per-sport daily aggregation (REQ-WALK)
- [ ] Packaged-install getsource smoke — fold into `tests/test_docker_runtime.py` or `just test` Docker smoke (REQ-ZEROKNOB / A1)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live MCP smoke after recompute | REQ-ZEROKNOB | end-to-end against the running container | `just test` (runs `smoke-basic` against the live container) — automated within `just test`, surfaced here for the phase gate |

*`human_verify_mode: end-of-phase` is set — use `<verify><human-check>` blocks, not `checkpoint:human-verify` tasks. All core behaviors above have automated coverage; the live smoke runs inside `just test`.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
