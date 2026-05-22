---
analysis_date: 2026-05-22
last_mapped_commit: b207e64f8293ddb0b3432562705b96a0a0264082
---
# Testing Patterns

**Analysis Date:** 2026-05-22

## Test Framework

**Runner:**
- `pytest` 9.0.3 is declared as the test extra in `pyproject.toml` and pinned in `uv.lock`.
- Pytest is configured in `pyproject.toml` with `testpaths = ["tests"]` and `pythonpath = ["src"]`.

**Assertion Library:**
- `pytest` assertions are the configured test path.

**Run Commands:**
```bash
pytest
python -m pytest
```

## Test File Organization

**Location:**
- Pytest is configured to discover tests under `tests/`, not under `src/`.
- No `test_*.py` or `spec_*.py` modules are present inside the scoped `src/` tree; the only in-tree smoke-style executable is `src/mcp_strava/deploy/smoke.py`.

**Naming:**
- Follow standard pytest naming: `test_*.py`, `*_test.py`, and `test_*` functions.

**Structure:**
```text
tests/
├── test_*.py
└── ...
```

## Test Structure

**Suite Organization:**
- The scoped source tree does not contain pytest suites to mirror directly.
- The repository instead exposes validation-oriented runtime checks in `src/mcp_strava/deploy/preflight.py` and `src/mcp_strava/deploy/smoke.py`.

**Observed Smoke Pattern:**
```python
async with streamable_http_client(url) as (read_stream, write_stream, _):
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        tools_result = await session.list_tools()
```

**Patterns:**
- Unit-style logic is concentrated in pure helpers and dataclass transforms under `src/mcp_strava/types.py`, `src/mcp_strava/refresh/freshness.py`, `src/mcp_strava/adapters/strava/rate_limit.py`, and `src/mcp_strava/adapters/sqlite/repository.py`.
- Runtime validation is separated from normal code paths so it can be executed as a health check without mixing it into business logic.

## Mocking

**Framework:**
- No dedicated mocking framework is configured in the scoped files; `pytest` plus dependency injection is the visible pattern.

**Patterns:**
```python
def build_mcp_server(settings: Settings | None = None) -> FastMCP:
    ...

def sync_activities(quick: bool = False):
    ...
    with DbConn() as conn:
        repo = SQLiteRepository.from_connection(conn)
        return refresh_runtime.run_once(
            repo,
            transport,
            refresh_policy,
            clock,
            sleeper,
            force=quick,
        )
```

```python
class StravaTransport:
    def __init__(..., http: Callable | None = None, ...):
        ...
```

**What to Mock:**
- Prefer replacing external collaborators: HTTP calls via `http` callables in `src/mcp_strava/adapters/strava/transport.py` and `src/mcp_strava/adapters/strava/token_refresh.py`, plus `clock` and `sleeper` protocols in `src/mcp_strava/adapters/strava/types.py`.
- Prefer fixture SQLite connections over monkeypatching SQL helpers when validating repository or service behavior.

**What NOT to Mock:**
- Do not mock the live MCP smoke path in `src/mcp_strava/deploy/smoke.py`; it is meant to exercise a real endpoint.
- Do not mock repository semantics when the point of the test is SQL shape, migration parity, or envelope completeness.

## Fixtures and Factories

**Test Data:**
- The scoped files do not define pytest fixtures or factory helpers.
- The code instead uses constructor injection and `SQLiteRepository.from_connection()` to make fixture-backed tests straightforward.

**Location:**
- No fixture directory is detected under the scoped prefixes.

## Coverage

**Requirements:**
- No coverage threshold or `coverage.py` configuration is detected in `pyproject.toml` or `uv.lock`.

**View Coverage:**
```bash
pytest --cov
```

## Test Types

**Unit Tests:**
- Should target the pure helpers and dataclass transforms in `src/mcp_strava/types.py`, `src/mcp_strava/refresh/freshness.py`, `src/mcp_strava/adapters/strava/rate_limit.py`, and the repository/query helpers in `src/mcp_strava/adapters/sqlite/repository.py`.

**Integration Tests:**
- Should exercise the SQLite repository, migration/preflight flow, and application services with a temporary or fixture database.
- The repo already includes deployment-oriented integration checks in `src/mcp_strava/deploy/preflight.py` and `src/mcp_strava/deploy/smoke.py`.

**E2E Tests:**
- Not detected in the scoped tree.
- The closest in-repo equivalent is the live MCP smoke check in `src/mcp_strava/deploy/smoke.py`, which validates tool exposure and can call `get_fitness_state`.

## Common Patterns

**Async Testing:**
```python
async with streamable_http_client(url) as (read_stream, write_stream, _):
    async with ClientSession(read_stream, write_stream) as session:
        ...
```

**Error Testing:**
```python
try:
    validate_runtime_db(Path(args.db), quick=args.quick)
except Exception as exc:
    print(f"preflight failed: {exc}", file=sys.stderr)
    return 1
```

**Boundary Testing:**
- Validate `ValueError` for unsafe HTTP settings in `src/mcp_strava/interfaces/mcp_http.py`.
- Validate `RuntimeError` for schema, backup, and DB parity failures in `src/mcp_strava/adapters/sqlite/migrations.py`, `src/mcp_strava/adapters/sqlite/backup.py`, and `src/mcp_strava/deploy/preflight.py`.
- Validate product-safe adapter failures through `StravaUnavailable` in `src/mcp_strava/adapters/strava/types.py`.

---

*Testing analysis: 2026-05-22*
