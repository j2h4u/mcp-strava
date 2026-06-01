---
analysis_date: 2026-06-01
last_mapped_commit: d16b5fd
scope: full-repo
---
# Coding Conventions

**Analysis Date:** 2026-06-01

## Naming Patterns

**Files:**
- `snake_case.py` throughout — `training.py`, `cardiac_drift.py`, `hr_zones.py`
- Test files prefixed `test_` — `test_metrics_pure.py`, `test_mcp_surface.py`
- Shared test helpers use underscore-prefix or descriptive noun — `_fixtures_duckdb.py`
- Adapter subdirectories use the external system name — `adapters/duckdb/`, `adapters/strava/`

**Functions:**
- `snake_case` everywhere — `calc_banister`, `build_freshness_metadata`, `open_fixture_db`
- Pure domain functions prefixed `calc_` — `calc_cardiac_drift`, `calc_hr_recovery`, `calc_hrr_pct`
- Builder functions prefixed `build_` — `build_refresh_collaborators`, `build_aggregate_query`
- Predicate/guard functions use `is_` or `has_` — `is_significant`, `has_heartrate`
- Private module helpers prefixed `_` — `_form_zone`, `_read_env_file`, `_parse_int`

**Variables:**
- `snake_case` throughout; single-letter locals only for short loops (`d`, `f`, `fa`)
- Constants in `Config` hierarchy use `UPPER_SNAKE` — `Config.Drift.THRESHOLD_DEFAULT`
- Date strings always named `*_str` or `ds` when a local loop variable — `date_str`, `today_str`, `ds`

**Types / Classes:**
- `PascalCase` for dataclasses and classes — `StravaActivity`, `DuckDBRepository`, `BanisterResult`
- `UPPER_SNAKE` for module-level constants — `ACTIVITY_COUNT`, `CANONICAL_DUCKDB_RUNTIME_PATH`
- `UPPER_SNAKE` for registry constants exported from modules — `METRIC_REGISTRY`, `SUPPORTED_AGGREGATE_BUCKETS`

**Tests:**
- Most tests: `test_<noun>_<verb>_<condition>` — `test_expected_duckdb_open_fails_closed_on_missing_file`
- Spec-coded tests: `test_<DOMAIN_CODE>_<description>` — `test_APP_04_D_08_D_12_freshness_metadata_distinguishes_refresh_and_activity`
  These codes (`APP_`, `INFRA_`, `SEC_`, `PERF_`) are traceability refs to the planning spec, not categories to invent. Use plain descriptive names for new tests unless a phase explicitly assigns codes.

## Code Style

**Formatter:** ruff format
- `quote-style = "double"` — always double-quoted strings
- `line-length = 120` — hard limit enforced by ruff format
- No trailing commas in single-value tuples unless intentional

**Linter:** ruff check with `select = ["E4", "E7", "E9", "F", "I", "B", "UP"]`
- E4/E7/E9: syntax/logic pycodestyle errors
- F: pyflakes (unused imports, undefined names)
- I: isort import ordering
- B: flake8-bugbear likely-bug patterns
- UP: pyupgrade → modern Python 3.14 idioms

**Static typing:** pyright `typeCheckingMode = "standard"`, `pythonVersion = "3.14"`
- `include = ["src"]` — only source tree is checked, not tests
- New functions in `src/` must satisfy standard-mode pyright

**Runtime:** Python 3.14 required (`requires-python = ">=3.14"`)

## Import Organization

**Order (enforced by ruff I):**
1. Standard library (`from __future__`, `import os`, `from pathlib import Path`)
2. Third-party (`import duckdb`, `import pytest`)
3. First-party (`from mcp_strava.constants import Config`)
4. Relative (avoided — prefer absolute `mcp_strava.*` imports)

**`from __future__ import annotations`:**
- Used selectively, not universally — present in `types.py`, `sync.py`, `mcp_content.py`, and most test files
- Add when forward references are needed in dataclass fields or when `X | Y` union syntax would fail at runtime

**Path aliases:** None — `src/` is on `PYTHONPATH` via `pyproject.toml` `[tool.pytest.ini_options]` and `uv run`

## Section Dividers

Heavy use of Unicode box-drawing comment dividers to partition modules logically:

```python
# ─── Section Name ───           (thin, within a class or short block)
# ═══════════════════════════    (thick, top-level module sections)
```

Examples in `types.py`: `# ─── Strava API Response Contracts ───`, `# ─── Per-Activity Metrics ───`
Examples in `constants.py`: `# ═══════════════════════════════════════`

Use these when a module has ≥2 clearly distinct concerns. Do not add them for single-concern files.

## Constants Pattern

All tunable parameters live in the `Config` class hierarchy in `src/mcp_strava/constants.py`:

```python
class Config:
    class Drift:
        THRESHOLD_DEFAULT = 10.0
        MIN_CLUSTER_SIZE = 30
    class Thresholds:
        VEL_STOP = 0.15
    class Metrics:
        MIN_STREAM_POINTS = 120
```

Import always as `from mcp_strava.constants import Config`, then reference `Config.Drift.THRESHOLD_DEFAULT`.
Never scatter magic numbers in domain functions — add to `Config` first.

## Docstrings

**Module-level:** Required. One-line summary + blank line + paragraph if needed:
```python
"""Per-activity metrics: pure domain functions over plain stream data.

All functions take pre-fetched plain dict rows and return dataclasses or None.
No storage imports — callers are responsible for fetching rows via the repository.
"""
```

**Function-level:** One-line imperative summary. Elaborate inline if contract is non-obvious:
```python
def calc_cardiac_drift(rows, sport_type=None):
    """Pure: Intra-activity cardiac drift using Jenks pace clustering.

    Takes pre-fetched stream rows ({heartrate, velocity}) and returns
    a CardiacDriftResult, or None if insufficient data.
    """
```

No NumPy/Google-style Args/Returns sections — prose is preferred.

## Type Annotations

**Source (`src/`):**
- Return type annotations present on public functions — `-> None`, `-> Settings`, `-> DuckDBRepository`
- Parameter annotations on public functions; omitted on short private helpers
- Dataclasses use full field annotations (`str | None`, `list[str]`, `tuple[str, ...]`)
- `field(default=None, repr=False)` for private/repr-excluded fields

**Tests:**
- Test functions annotated `-> None` consistently
- Fixture functions often unannotated or use `-> Path` / `-> DuckDBRepository`

## Error Handling

**Domain/validation errors:** Raise `ValueError` with a descriptive message including the env key name:
```python
raise ValueError(f"Invalid integer for {key}: {raw}") from exc
raise ValueError("Invalid integer for MCP_STRAVA_HTTP_PORT: out of range")
```

**Infrastructure errors:** Raise `RuntimeError` with full context:
```python
raise RuntimeError("Expected DuckDB mirror does not exist")
```

**Named domain exceptions:** Custom exception classes for specific infrastructure states, e.g. `MirrorDbLocked` in `cli.py` — caught specifically, not as bare `Exception`

**Resource cleanup:** Always `try/finally` around DuckDB connections:
```python
conn = open_fixture_db(db_path)
try:
    create_schema(conn)
finally:
    conn.close()
```

**Bare `except Exception`:** Used only in statistical/algorithmic fallback paths (`cardiac_drift.py`) where a failed cluster is recovered, not in I/O or service code.

## Dataclass Design

- `@dataclass` (mutable) for repository contracts and result objects
- `@dataclass(frozen=True)` for settings/config objects (`AthleteSettings`, `Settings`)
- `field(default_factory=list)` for mutable defaults
- `dc_to_dict()` utility in `types.py` for serialization — do not implement `__dict__` or `asdict()` manually

## Pure Function Design

Metric functions in `src/mcp_strava/metrics.py` are pure — they:
- Take plain `dict` rows (no repository arguments)
- Return dataclasses or `None`
- Have zero storage imports
- Guard with `if len(rows) < Config.Metrics.MIN_STREAM_POINTS: return None`

This is the canonical pattern for any new per-activity metric.

## Module Exports

`__all__` used when a module re-exports from submodules (`sync.py`). Otherwise not required.
Avoid star imports (`from module import *`) — explicit named imports always.

## Logging

No structured logging framework — not detected in source. CLI output via `print()` / `sys.stdout`. Background worker state written to a JSON health file (`MCP_STRAVA_REFRESH_HEALTH_PATH`), not logs.

## Comments

- Inline comments used for non-obvious math or threshold rationale, e.g.:
  ```python
  alpha = 1 - pow(0.5, 1.0 / tau)  # EWMA decay for tau-day half-life
  ```
- `# 💰 Summit` marks Strava premium-only fields in `types.py`
- TODO/FIXME not used in source (none detected)

---

*Convention analysis: 2026-06-01*
