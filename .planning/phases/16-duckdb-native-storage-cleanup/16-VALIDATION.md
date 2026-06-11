---
phase: 16
slug: duckdb-native-storage-cleanup
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-11
planned: 2026-06-11
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
| W0-kudos-test | 16-01 | 0 | kudos window_days branch (UNtested dead branch) | xfail marks broken SQL; window_days=None path passes | unit | `pytest tests/test_duckdb_repository.py -q -k kudos` | ✅ green |
| T1-date-drop | 16-02 | 1 | activities.date column removed; kudos native DuckDB | activity_date alias still YYYY-MM-DD; window_days filter correct | unit | `pytest tests/test_duckdb_repository.py tests/test_application_services.py -q -x` | ✅ green |
| T1-row-rename | 16-02 | 1 | RepositoryActivityRow.date → activity_day | projection_services payload shape unchanged | unit + pyright | `just check` | ✅ green |
| T2-requested-for-day | 16-03 | 2 | requested_for_day VARCHAR → DATE | str(datetime.date) == "YYYY-MM-DD"; RefreshRequestRow unchanged | unit | `pytest tests/test_application_services.py -q -x` | ✅ green |
| T3a-is-moving | 16-04 | 2 | streams.is_moving BIGINT → BOOLEAN | stream insert/read unchanged; no arithmetic on bool | unit | `pytest tests/test_duckdb_repository.py -q -k stream` | ✅ green |
| T3b-cardiac-drift | 16-04 | 2 | cardiac_drift_significant BIGINT → BOOLEAN; fingerprint flip | status query returns correct result; fingerprint test passes | unit | `pytest tests/test_read_model_queries.py tests/test_logic_fingerprint.py -q -x` | ✅ green |
| T4-varchar-array | 16-05 | 3 | missing_reasons_json VARCHAR → VARCHAR[]; no json.loads | MCP missing_reasons payload is list[str]; aggregate produces flat list | unit | `pytest tests/test_read_model_materialization.py tests/test_read_model_queries.py -q -x` | ✅ green |
| T5a-cast-removal | 16-06 | 4 | schema_views CAST(x AS DATE) no-ops removed | view output identical | unit | `pytest tests/test_read_model_queries.py -q -x` | ✅ green |
| T5b-json-predicate | 16-06 | 4 | stream coverage uses SQL predicate not Python loop | activities_missing_stream_channels returns same results | unit | `pytest tests/test_duckdb_repository.py -q -k coverage` | ✅ green |
| phase-gate | 16-06 | 4 | full suite + linter | all behaviors preserved end-to-end | integration | `just check && uv run pytest -n auto -q` | ✅ green |

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
