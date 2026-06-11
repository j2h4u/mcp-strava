---
phase: 16
slug: duckdb-native-storage-cleanup
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-11
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Detail in 16-RESEARCH.md "## Validation Architecture". Planner fills the Per-Task Map.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Python 3.14) |
| **Config file** | pyproject.toml |
| **Quick run command** | `.venv/bin/python -m pytest <touched test files> -q` |
| **Full suite command** | `just check && .venv/bin/python -m pytest -q -n auto` |
| **Estimated runtime** | ~70 seconds (full suite) |

---

## Sampling Rate

- **After every task commit:** Run the quick command on the touched test files.
- **After every plan wave:** Run the full suite command (`just check` + `pytest -n auto`).
- **Before `/gsd-verify-work`:** Full suite must be green AND a fresh resync/rematerialization must produce identical payloads.
- **Max feedback latency:** ~70 seconds.

---

## Per-Task Verification Map

*Planner fills this from 16-RESEARCH.md "## Validation Architecture". Core invariant for every task: external behavior (MCP/CLI payloads, freshness semantics, read-model values) is byte-for-byte unchanged after the type conversion.*

| Task ID | Plan | Wave | Requirement | Behavior preserved | Test Type | Automated Command | Status |
|---------|------|------|-------------|--------------------|-----------|-------------------|--------|
| 16-… | … | 0 | kudos window_days branch (currently UNtested) | native date filter returns same ids | unit | `pytest tests/test_duckdb_repository.py -q` | ⬜ pending |
| 16-… | … | 1+ | per conversion | payload/value identical before/after | unit + e2e | `pytest <files> -q` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_duckdb_repository.py` — add `test_activities_missing_kudos_with_window_days` (the dead branch that hid the SQLite `date('now')` bug; must exist BEFORE Task 1 rewrites it).
- [ ] Otherwise existing infrastructure covers the phase: conversions are verified by existing repository/aggregate/surface tests plus before/after payload assertions.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Container rebuilds healthy, MCP surface intact (6 tools / 3 prompts / 2 resources) | phase success criteria | needs docker build + live probe | `docker compose --project-directory deploy -f deploy/docker-compose.yml build && up -d`; in-container `list_resources/list_tools/list_prompts` probe |
| Fresh resync/rematerialization yields identical payloads | no-external-behavior-change | needs real mirror + Strava | resync a fixture mirror, diff envelopes vs pre-phase |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers the untested kudos `window_days` branch
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter (planner sets when Per-Task Map complete)

**Approval:** pending
