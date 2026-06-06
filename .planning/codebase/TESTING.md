---
analysis_date: 2026-06-01
last_mapped_commit: d16b5fd
scope: full-repo
---
# Testing Patterns

**Analysis Date:** 2026-06-01

## Test Framework

**Runner:**
- pytest 9+
- Config: `pyproject.toml` `[tool.pytest.ini_options]`
  - `testpaths = ["tests"]`
  - `pythonpath = ["src"]`

**Assertion Library:**
- pytest built-in (`assert` statements — no unittest-style `self.assert*`)

**Run Commands:**
```bash
uv run pytest -q                              # Run all 357 tests as of Phase 14 UAT
uv run pytest -q tests/test_mcp_surface.py   # Single file
just unit                                     # Pytest only
just check                                    # Static quality gate
just runtime                                  # Docker build/start + MCP smoke only
just verify                                   # Static quality gate + pytest + runtime smoke
```

## Test File Organization

**Location:** All tests in `tests/` — flat directory, no subdirectories except `tests/fixtures/`

**Naming:**
- `test_<domain>_<aspect>.py` — `test_mcp_surface.py`, `test_duckdb_repository.py`
- `test_<phase>_<scope>.py` for phase validation tests — `test_phase01_validation.py`, `test_phase4_e2e.py`
- Shared fixtures: `tests/_fixtures_duckdb.py` (underscore-prefixed, not a test file)
- Long-lived fake servers: `tests/fixtures/fake_mcp_server.py`

**Structure:**
```
tests/
├── conftest.py               # Session/function autouse fixtures
├── _fixtures_duckdb.py       # DuckDB seed helpers (not collected by pytest)
├── fixtures/
│   └── fake_mcp_server.py    # Standalone fake MCP stdio server
├── test_application_services.py
├── test_application_reports.py
├── test_application_workouts.py
├── test_cli_surface.py
├── test_docker_runtime.py
├── test_duckdb_concurrency_guards.py
├── test_duckdb_repository.py
├── test_full_fidelity_mirror.py
├── test_hr_zones.py
├── test_load_status.py
├── test_maintenance_compact.py
├── test_mcp_latency_gate.py
├── test_mcp_sdk_contract.py
├── test_mcp_surface.py
├── test_mcp_test_client.py
├── test_metric_registry.py
├── test_metric_services.py
├── test_metrics_pure.py
├── test_phase01_validation.py
├── test_phase4_e2e.py
├── test_product_fact_bundles.py
├── test_read_model_materialization.py
├── test_read_model_queries.py
├── test_refresh_health.py
├── test_refresh_runtime.py
├── test_repo_hygiene.py
├── test_repository_boundary.py
├── test_schema_drift.py
├── test_security_guards.py
├── test_settings.py
├── test_smoke.py
├── test_strava_adapter.py
├── test_strava_client.py
└── test_training_aggregates.py
```

## Test Structure

**Suite Organization — no class grouping:**
All test functions are module-level. No `class Test*` grouping is used anywhere. Shared setup is done through pytest fixtures.

```python
# Standard pattern: fixture + function-level test
@pytest.fixture
def repo(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    create_empty_fixture_db(db_path)
    with DuckDBRepository.from_path(db_path) as opened:
        # seed rows directly via opened.conn.execute(...)
        yield opened


def test_APP_04_D_08_D_12_freshness_metadata_distinguishes_refresh_and_activity(
    repo: DuckDBRepository,
) -> None:
    metadata = build_freshness_metadata(repo, ...)
    assert metadata.freshness_state == "fresh"
    assert metadata.refresh_age_seconds == 10_800
```

**Patterns:**
- Setup: pytest `@pytest.fixture` — DuckDB `tmp_path` DB, monkeypatched env, fake collaborators
- Teardown: `yield`-based fixtures with cleanup in `finally` blocks or monkeypatch auto-revert
- Assertions: plain `assert` with descriptive messages on failure cases; `assert x == y` on happy path

## Session-Wide Autouse Fixtures (conftest.py)

Four autouse fixtures active for every test — defined in `tests/conftest.py`:

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `set_hr_rest_env` | session | Sets `MCP_STRAVA_HR_REST=53` if not present |
| `reset_settings` | function | Clears settings cache before and after each test |
| `isolate_refresh_health_path` | function | Redirects health JSON to `tmp_path` |
| `reset_read_connections` | function | Closes thread-local DuckDB read connections |

These are always active — test authors do not need to reference them. They prevent state leakage between tests that modify env vars or open DuckDB connections.

## DuckDB Test Fixtures

Seeding helpers live in `tests/_fixtures_duckdb.py` — import directly in test files:

```python
from tests._fixtures_duckdb import create_fixture_db, create_empty_fixture_db

@pytest.fixture
def repo(tmp_path: Path):
    db_path = tmp_path / "my-test.duckdb"
    create_empty_fixture_db(db_path)   # schema only, no rows
    # OR
    create_fixture_db(db_path)         # 42 Run activities + streams + sync log
    with DuckDBRepository.from_path(db_path) as opened:
        yield opened
```

`create_fixture_db` seeds:
- 42 daily Run activities (2026-01-01 through 2026-02-11)
- 10 stream points per activity (heartrate/velocity/altitude/cadence/GPS)
- 1 athlete-zones row, 1 sync-log row, 1 kudos row

For custom data needs, open the fixture DB and insert directly via `repo.conn.execute()`.

## Mocking

**Framework:** `monkeypatch` (pytest built-in) — no `unittest.mock` or `pytest-mock`

**Patterns:**

```python
# Patch a module-level attribute
def test_mcp_tools_have_annotations(monkeypatch) -> None:
    from mcp_strava.interfaces import mcp_http
    monkeypatch.setattr(mcp_http, "get_fitness_state_service", lambda **_: _envelope({"fitness": 1.0}))

# Patch environment variables
def test_load_settings_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(tmp_path / "test.duckdb"))

# Block live network (used in refresh_runtime tests)
@pytest.fixture(autouse=True)
def forbid_live_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise RuntimeError("live network forbidden")
    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
```

**Fake collaborators — hand-rolled, not mocked:**
Tests that exercise the refresh runtime use `FakeClock`, `FakeSleeper`, and `FakeTransport` classes defined inline in `tests/test_refresh_runtime.py`. These are stateful fakes with `advance()` methods, not mocks with assertion expectations.

```python
class FakeClock:
    def __init__(self, value: float = 1_716_206_400.0):
        self.value = value
    def now(self) -> float: return self.value
    def advance(self, seconds: float) -> None: self.value += seconds
    def iso(self) -> str: ...
```

**`SimpleNamespace` for lightweight stubs:**
```python
from types import SimpleNamespace
fake_settings = SimpleNamespace(database_path=tmp_path / "test.duckdb", ...)
```

**What to mock:** External I/O (network, file paths), time/clock, DuckDB path (via `tmp_path`)

**What NOT to mock:** DuckDB itself — always use real DuckDB with `tmp_path`. Repository, schema, and SQL behavior must be tested against the real driver.

## Parametrize

Used sparingly — only where the same assertion must hold for a fixed enumeration:

```python
EXPECTED_BUCKETS = ("day", "week", "month", "year", "all_time")

@pytest.mark.parametrize("bucket", EXPECTED_BUCKETS)
def test_supported_buckets_return_factual_half_open_bounds(tmp_path: Path, bucket: str) -> None:
    ...
```

Other uses: settings validation edge cases, CLI command name checks, maintenance compact scenarios.

## Fixtures and Data Builders

**Builder helpers** — module-level private functions in test files named `_make_*` or `_create_*`:

```python
def _make_hr_vel_time_rows(n, velocity=3.0, heartrate=140, time_offset_start=0):
    """Build n stream rows with {time_offset, heartrate, velocity}."""
    return [{"time_offset": time_offset_start + i, "heartrate": heartrate, "velocity": velocity} for i in range(n)]

def _activity_fact_values(activity_id: int = 100) -> dict[str, object]:
    return {"activity_id": activity_id, "sport_type": "Run", "trimp": 42.5, ...}
```

**Envelope builder** for MCP surface tests:
```python
def _envelope(data: dict, *, unavailable: bool = False) -> ServiceEnvelope:
    return ServiceEnvelope(data=data, freshness=FreshnessMetadata(...), completeness=CompletenessMetadata(...))
```

**Location:** Builder functions are defined at the top of the test module that uses them, not in shared fixture files (except for DuckDB seeding which is shared via `_fixtures_duckdb.py`).

## Test Types

**Pure unit tests** (`test_metrics_pure.py`, `test_hr_zones.py`, `test_training_aggregates.py`):
- No DB, no fixtures — plain Python function calls
- Test boundary conditions using `Config.*` constants, not magic numbers

**Repository / DB integration tests** (`test_duckdb_repository.py`, `test_read_model_queries.py`):
- Real DuckDB in `tmp_path`, seeded via `_fixtures_duckdb.py` helpers
- Test SQL correctness, schema constraints, and boundary behaviors

**Application service tests** (`test_application_services.py`, `test_metric_services.py`):
- Real DuckDB + service layer called directly
- No MCP protocol — test the Python function return values

**MCP surface / contract tests** (`test_mcp_surface.py`, `test_mcp_sdk_contract.py`):
- Services monkeypatched; test MCP tool schema, payload shape, and envelope structure
- `asyncio.run()` used to drive async MCP tool calls in sync test context

**Hygiene / policy tests** (`test_repo_hygiene.py`, `test_security_guards.py`, `test_docker_runtime.py`):
- Static analysis via `ast.parse()` of source files — no imports, no execution
- `.gitignore` content assertions, CLI registry shape, forbidden SQL surface checks

**E2E / CLI smoke tests** (`test_phase4_e2e.py`, `test_smoke.py`):
- `subprocess.run()` against the installed package with a seeded `tmp_path` DB
- Assert exit codes and stdout/stderr content

**Docker runtime tests** (`test_docker_runtime.py`):
- Imports and runs preflight checks in-process against `tmp_path`
- Validates Python + duckdb version pins from `pyproject.toml` via `tomllib`

## Coverage

**Requirements:** No coverage target enforced — no `--cov` flag in default `just unit` invocation

**View Coverage:**
```bash
uv run pytest --cov=src/mcp_strava --cov-report=term-missing
```

## Common Patterns

**Async testing:**
```python
import asyncio

def test_mcp_tool_returns_structured_output(monkeypatch) -> None:
    # MCP tools are async; drive them synchronously in tests
    result = asyncio.run(some_mcp_tool(arg="value"))
    assert result[0].text is not None
```

**Error / exception testing:**
```python
def test_expected_duckdb_open_fails_closed_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Expected DuckDB mirror does not exist"):
        open_expected_mirror_db(tmp_path / "missing.duckdb")
```

**Subprocess / CLI testing:**
```python
import subprocess, sys, os

def test_module_entrypoint_runs(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    result = subprocess.run(
        [sys.executable, "-m", "mcp_strava"],
        check=False, text=True, capture_output=True, env=env,
    )
    assert result.returncode != 0
    assert "Usage:" in result.stdout + result.stderr
```

**Static source analysis in tests:**
```python
import ast
from pathlib import Path

def _source_text(rel_path: str) -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / rel_path).read_text(encoding="utf-8")

def test_cli_has_explicit_command_registry() -> None:
    source = _source_text("src/mcp_strava/cli.py")
    module = ast.parse(source)
    # walk AST to verify COMMANDS dict shape
```

**DuckDB state manipulation in tests** (when `create_fixture_db` isn't sufficient):
```python
def _set_refresh_state(repo: DuckDBRepository, **values: str | None) -> None:
    assignments = ", ".join(f"{key} = ?" for key in values)
    repo.conn.execute(f"UPDATE refresh_state SET {assignments} WHERE id = 1", tuple(values.values()))
    repo.conn.commit()
```

## What Not To Do

- Do not use `unittest.TestCase` — all tests are functions
- Do not use `pytest-mock` / `MagicMock` — use `monkeypatch.setattr` and hand-rolled fakes
- Do not skip tests with `@pytest.mark.skip` — no skips detected anywhere in the suite
- Do not share DuckDB connections across tests — `tmp_path` gives each test its own DB file
- Do not call `reset_settings_cache()` manually — the autouse `reset_settings` fixture handles it

---

*Testing analysis: 2026-06-01*
