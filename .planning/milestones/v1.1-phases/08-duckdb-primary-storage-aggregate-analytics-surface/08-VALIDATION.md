---
phase: 08
slug: duckdb-primary-storage-aggregate-analytics-surface
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-25
---

# Phase 08 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pyproject.toml` with `testpaths = ["tests"]` and `pythonpath = ["src"]` |
| **Quick run command** | `uv run pytest tests/test_duckdb_storage.py tests/test_training_aggregates.py tests/test_mcp_surface.py tests/test_mcp_latency_gate.py -q` after Wave 0 creates files |
| **Full suite command** | `uv run pytest -q` plus Docker smoke/perf gates |
| **Docker smoke command** | `just test` |
| **100 ms p95 command** | `just mcp-read-model-perf 20 2 100` or the no-arg default, which also uses 100 ms |
| **Estimated runtime** | Targeted tests under 60s; Docker smoke/perf depends on image build and live runtime |

---

## Sampling Rate

- **After every task commit:** Run the targeted `uv run pytest ... -q` command for the touched subsystem.
- **After every plan wave:** Run `uv run pytest -q`.
- **Before `$gsd-verify-work`:** Run `just test`, `just mcp-smoke-full`, and `just mcp-read-model-perf 20 2 100`.
- **Max feedback latency:** Keep local targeted test feedback under 60 seconds where possible; Docker gates are phase acceptance gates.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 0 | P8-SC-01 | T-08-01 | Migration cannot drop mirror rows or stream/channel facts silently | integration | `uv run pytest tests/test_duckdb_migration.py -q` | W0 | pending |
| 08-02-01 | 02 | 0 | P8-SC-02 | T-08-02 | Runtime DuckDB owner prevents concurrent read-write file opens | unit/integration | `uv run pytest tests/test_duckdb_repository.py tests/test_duckdb_concurrency_guards.py -q` | W0 | pending |
| 08-03-02 | 03 | 3 | P8-SC-02 | T-08-02 | Read-model materializer writes activity, daily, model, and rolling facts into DuckDB after cutover | unit/integration | `uv run pytest tests/test_read_model_materialization.py tests/test_duckdb_repository.py -q` | exists/W0 refit | pending |
| 08-03-01 | 03 | 0 | P8-SC-03 | T-08-03 | Aggregate query builder validates product params and never exposes raw SQL | unit/integration | `uv run pytest tests/test_training_aggregates.py -q` | W0 | pending |
| 08-04-01 | 04 | 0 | P8-SC-04 | T-08-03 | `compare_periods` uses aggregate layer and preserves metadata | unit | `uv run pytest tests/test_metric_services.py -q` | partial | pending |
| 08-05-01 | 05 | 0 | P8-SC-05 | T-08-04 | Docker runtime uses Python 3.14 and imports pinned DuckDB | smoke | `docker compose -f deploy/docker-compose.yml exec -T mcp-strava python -c "import sys, duckdb; print(sys.version, duckdb.__version__)"` | command | pending |
| 08-06-01 | 06 | 0 | P8-D-15 | T-08-05 | MCP exposes `get_training_aggregates` and excludes admin/raw/sql tools | unit/smoke | `uv run pytest tests/test_mcp_surface.py tests/test_mcp_latency_gate.py -q && just mcp-list-tools` | partial | pending |
| 08-08-01 | 08 | 6 | P8-SC-01/P8-SC-02 | T-08-01/T-08-02 | Live/Docker runtime pins `/runtime/data/strava.duckdb` and rollback tags the pre-cutover image | smoke/docs | `uv run pytest tests/test_docker_runtime.py -q` | exists/refit | pending |

*Status: pending, green, red, flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_duckdb_migration.py` - migration, casts, parity, rollback boundary.
- [ ] `tests/test_duckdb_repository.py` - DuckDB repository contract and no runtime SQLite writes.
- [ ] Update `tests/test_read_model_materialization.py` - DuckDB materializer/refit writes derived facts and clears dirty rows in DuckDB.
- [ ] `tests/test_training_aggregates.py` - bucket/metric/bundle/metadata semantics.
- [ ] `tests/test_duckdb_concurrency_guards.py` - single-owner process, healthcheck, CLI/live DB guards.
- [ ] Update `tests/test_metric_registry.py` - compare-periods registry coverage resolves through aggregate-layer metadata instead of removed handler maps.
- [ ] Update `tests/test_mcp_surface.py`, `tests/test_mcp_latency_gate.py`, and MCP client expected tool lists for six tools.
- [ ] Update Docker runtime tests to expect DuckDB path/import and Python 3.14.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| DuckDB package legitimacy checkpoint | P8-SC-05 | `slopcheck` was unavailable during research, so dependency trust needs explicit operator review before install | Verify PyPI project metadata, release files, source repo, wheel tags, and install/import in `python:3.14-slim`; record result in plan summary before adding `duckdb` |
| Live cutover acceptance | P8-SC-01/P8-SC-02 | Live `/opt/docker/mcp-strava` DB migration touches valuable data and must be operator-visible | Stop runtime writers, verify no active lease, create pinned SQLite backup, migrate from copy/backup, run parity, Docker smoke, MCP smoke, and 100 ms p95 gate before accepting cutover |

---

## Security Threat References

| Threat Ref | Threat | Mitigation |
|------------|--------|------------|
| T-08-01 | Silent data loss during SQLite to DuckDB casts | Controlled casts, cast-failure reports, source row parity, stream/channel/GPS/kudos/read-model parity |
| T-08-02 | Live DuckDB corruption or outage from multiple read-write processes | Single DuckDB owner process; healthcheck/smoke through owner process or HTTP path |
| T-08-03 | Raw SQL injection or table exposure through aggregate MCP params | Enum validation and whitelisted query templates only |
| T-08-04 | Unsafe dependency or Python/DuckDB runtime drift | Human package checkpoint, pinned DuckDB range, Docker Python 3.14 import smoke |
| T-08-05 | Admin/debug/sync/raw functionality leaks into MCP | Exact MCP allowlist and forbidden surface tests |

---

## Validation Sign-Off

- [ ] All tasks have automated verify commands or Wave 0 dependencies.
- [ ] Sampling continuity: no 3 consecutive tasks without automated verification.
- [ ] Wave 0 covers all missing test files.
- [ ] No watch-mode flags.
- [ ] Docker acceptance includes `just test`, `just mcp-smoke-full`, and `just mcp-read-model-perf 20 2 100`.
- [ ] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
