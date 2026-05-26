---
analysis_date: 2026-05-26
last_mapped_commit: ab203ab
---
# Testing Patterns

**Analysis Date:** 2026-05-26

## Scope

- This incremental map is scoped to `README.md`, `mcp-content/`, and `tests/`, with minimal command/config context from `pyproject.toml` and `Justfile`.
- The suite under `tests/` is the authoritative source for testing patterns in this scoped remap.

## Test Framework

**Runner:**
- `pytest` is declared as the optional test dependency in `pyproject.toml`.
- Pytest discovery is configured in `pyproject.toml` with `testpaths = ["tests"]` and `pythonpath = ["src"]`.
- `Justfile` routes `just test` to Docker build/start plus an MCP smoke call against `http://127.0.0.1:8080/mcp`.

**Assertion Library:**
- Use plain `pytest` assertions throughout `tests/`; no separate assertion library is detected in `pyproject.toml`.

**Run Commands:**
```bash
uv run pytest -q              # Run all Python tests from README.md
just test                     # Build/start Docker runtime and run basic MCP smoke from Justfile
just mcp-smoke-full           # Run live MCP smoke inside the container from Justfile
just mcp-read-model-perf      # Run read-model p95 latency gate from Justfile
```

- Watch mode: Not detected in `README.md`, `pyproject.toml`, or `Justfile`.
- Coverage command: Not detected; `pyproject.toml` has no coverage or `pytest-cov` configuration.

## Test File Organization

**Location:**
- Tests live under `tests/`; examples include `tests/test_mcp_surface.py`, `tests/test_refresh_runtime.py`, `tests/test_duckdb_repository.py`, and `tests/test_security_guards.py`.
- Test fixtures live under `tests/fixtures/`, currently `tests/fixtures/fake_mcp_server.py`.
- MCP prompt content lives under `mcp-content/prompts/` and is tested from `tests/test_mcp_surface.py`.

**Naming:**
- Use `test_*.py` files and `test_*` functions under `tests/`.
- Use helper names beginning with `_` for module-local fixture construction, for example `_create_fixture_db()` in `tests/test_application_services.py`.
- Use `Fake*` class names for in-memory collaborators, for example `FakeClock` in `tests/test_refresh_runtime.py` and `FakeStravaHttp` in `tests/test_strava_adapter.py`.

**Structure:**
```text
tests/
├── fixtures/
│   └── fake_mcp_server.py
├── test_application_services.py
├── test_cli_surface.py
├── test_docker_runtime.py
├── test_mcp_surface.py
├── test_refresh_runtime.py
├── test_security_guards.py
└── test_*.py
```

## Test Structure

**Suite Organization:**
```python
@pytest.fixture
def repo(tmp_path: Path):
    db_path = tmp_path / "application-services.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("...")
    run_migrations(db_path)

    with SQLiteRepository.from_path(db_path) as opened:
        yield opened


def test_APP_04_get_freshness_service_returns_shared_envelope(repo: SQLiteRepository) -> None:
    envelope = get_freshness_service(..., connection=repo.conn)
    payload = dc_to_dict(envelope)

    assert set(payload) == {"data", "freshness", "completeness", "warnings", "rationale"}
```

**Patterns:**
- Build temporary SQLite/DuckDB databases with `tmp_path` and explicit schema helpers in `tests/test_application_services.py`, `tests/test_read_model_queries.py`, `tests/test_training_aggregates.py`, and `tests/test_duckdb_repository.py`.
- Run migrations against fixture databases before testing application services, as in `tests/test_application_services.py` and `tests/test_read_model_materialization.py`.
- Use dataclass-to-dict conversion with `dc_to_dict()` before asserting service envelopes in `tests/test_product_fact_bundles.py` and `tests/test_training_aggregates.py`.
- Use strict allowlists and forbidden-term walks for MCP/product surfaces in `tests/test_mcp_surface.py`, `tests/test_metric_services.py`, and `tests/test_training_aggregates.py`.
- Use AST/source guard tests for architecture constraints in `tests/test_repository_boundary.py`, `tests/test_cli_surface.py`, `tests/test_security_guards.py`, and `tests/test_read_model_queries.py`.

## Mocking

**Framework:** `pytest` `monkeypatch`, fake classes, and dependency injection.

**Patterns:**
```python
@pytest.fixture(autouse=True)
def forbid_live_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise RuntimeError("live network forbidden")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
```

```python
class FakeStravaTransport:
    def __init__(self, failures: dict[str, Exception] | None = None):
        self.failures = failures or {}
        self.calls_by_path: dict[str, int] = defaultdict(int)

    def fetch(self, path: str) -> StravaResponse:
        self.calls_by_path[path] += 1
        ...
```

**What to Mock:**
- Mock external network access by blocking `urllib.request.urlopen`, as in `tests/test_refresh_runtime.py` and `tests/test_strava_adapter.py`.
- Mock clocks and sleepers with `FakeClock` and `FakeSleeper` for rate-limit, retry, and refresh scheduling behavior in `tests/test_refresh_runtime.py` and `tests/test_strava_adapter.py`.
- Mock CLI/service collaborators with `monkeypatch.setattr()` when verifying routing rather than implementation, as in `tests/test_cli_surface.py` and `tests/test_mcp_surface.py`.
- Use fake MCP clients/servers for protocol behavior in `tests/test_mcp_test_client.py` and `tests/fixtures/fake_mcp_server.py`.

**What NOT to Mock:**
- Do not mock repository SQL behavior when testing migrations, read-model queries, parity, or transaction semantics; use fixture DBs in `tests/test_sqlite_safety.py`, `tests/test_read_model_materialization.py`, `tests/test_duckdb_migration.py`, and `tests/test_duckdb_repository.py`.
- Do not mock the Docker smoke path covered by `just test`; `Justfile` intentionally exercises the built container and MCP HTTP endpoint.
- Do not allow tests to hit live Strava/network paths; scoped tests use autouse network blockers and fake transports in `tests/test_refresh_runtime.py` and `tests/test_strava_adapter.py`.

## Fixtures and Factories

**Test Data:**
```python
def _aggregate_fixture(path: Path) -> Path:
    conn = open_fixture_db(path)
    create_schema(conn)
    _insert_activity(...)
    _insert_activity_fact(...)
    _insert_daily_fact(...)
    conn.close()
    return path
```

**Location:**
- Database fixture helpers are module-local in `tests/test_application_services.py`, `tests/test_read_model_queries.py`, `tests/test_training_aggregates.py`, `tests/test_sqlite_safety.py`, and `tests/test_full_fidelity_mirror.py`.
- Cross-test fixture helpers are imported deliberately from `tests/test_training_aggregates.py`, `tests/test_read_model_queries.py`, and `tests/test_sqlite_safety.py` when a later suite needs the same contract shape.
- Protocol fixtures live in `tests/fixtures/fake_mcp_server.py`.
- Prompt fixtures are real markdown files under `mcp-content/prompts/`; `tests/test_mcp_surface.py` verifies the prompt names and content-backed exposure.

## Coverage

**Requirements:** Not detected. `pyproject.toml` contains no coverage threshold, no coverage omit/include settings, and no `pytest-cov` dependency.

**View Coverage:**
```bash
# Not configured in scoped files.
```

## Test Types

**Unit Tests:**
- Pure computation, settings, and registry behavior is tested in `tests/test_smoke.py`, `tests/test_settings.py`, `tests/test_metric_registry.py`, and `tests/test_mcp_latency_gate.py`.
- Error and validation branches use `pytest.raises` with exact exception types or message fragments in `tests/test_settings.py`, `tests/test_mcp_surface.py`, and `tests/test_training_aggregates.py`.

**Integration Tests:**
- Repository and migration integration tests use temporary SQLite/DuckDB files in `tests/test_repository_boundary.py`, `tests/test_sqlite_safety.py`, `tests/test_full_fidelity_mirror.py`, `tests/test_read_model_materialization.py`, `tests/test_duckdb_migration.py`, and `tests/test_duckdb_repository.py`.
- Application service integration tests call real service functions with fixture connections in `tests/test_application_services.py`, `tests/test_metric_services.py`, `tests/test_product_fact_bundles.py`, and `tests/test_training_aggregates.py`.

**E2E Tests:**
- CLI subprocess smoke is covered in `tests/test_phase4_e2e.py` and `tests/test_security_guards.py`.
- MCP protocol smoke/client behavior is covered in `tests/test_mcp_test_client.py`, `tests/test_mcp_surface.py`, and `tests/fixtures/fake_mcp_server.py`.
- Docker/runtime smoke and performance gates are commanded from `Justfile` and documented in `README.md`.

**Contract/Security Tests:**
- Product-vs-admin CLI boundaries are locked in `tests/test_cli_surface.py` and `tests/test_security_guards.py`.
- MCP tool and prompt allowlists are locked in `tests/test_mcp_surface.py`.
- Secret redaction and local-state policy are locked in `tests/test_strava_adapter.py`, `tests/test_cli_surface.py`, `tests/test_docker_runtime.py`, and `tests/test_repo_hygiene.py`.
- Runtime deployment contracts are locked in `tests/test_docker_runtime.py` and `tests/test_duckdb_concurrency_guards.py`.

## Common Patterns

**Async Testing:**
```python
async def run() -> list[dict]:
    async with StdioMcpClient(_fake_server_command()) as client:
        return await client.list_tools()

tools = asyncio.run(run())
```

Use this pattern for MCP client calls in `tests/test_mcp_test_client.py` and server tool calls in `tests/test_mcp_surface.py`.

**Error Testing:**
```python
with pytest.raises(ValueError, match="allowed_hosts"):
    mcp_http.build_transport_security(unsafe_host)
```

Use `pytest.raises(..., match=...)` for unsafe settings, invalid product parameters, fail-closed preflight behavior, token errors, and cutover failures in `tests/test_mcp_surface.py`, `tests/test_settings.py`, `tests/test_docker_runtime.py`, `tests/test_strava_adapter.py`, and `tests/test_duckdb_migration.py`.

**Boundary Testing:**
```python
module = ast.parse(Path("src/mcp_strava/cli.py").read_text(encoding="utf-8"))
violations: list[str] = []
...
assert violations == []
```

Use AST/source guards when the contract is "this dependency/surface must not exist", as in `tests/test_repository_boundary.py`, `tests/test_cli_surface.py`, `tests/test_security_guards.py`, and `tests/test_read_model_queries.py`.

**Performance Testing:**
- Use warm-sample latency gates through the MCP test client in `tests/test_mcp_latency_gate.py`.
- Use `just mcp-read-model-perf` from `Justfile` for the containerized read-model p95 gate.

---

*Testing analysis: 2026-05-26*
