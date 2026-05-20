# Technology Stack

**Analysis Date:** 2026-05-20

## Languages

**Primary:**
- Python 3.13.5 - All runtime code in `scripts/strava_lib/*.py`, the CLI in `scripts/cli.py`, and smoke tests in `tests/test_smoke.py`.

**Secondary:**
- Bash - `Justfile` task runner syntax and shell execution.

## Runtime

**Environment:**
- CPython 3.13.5 in this workspace.
- Standard-library-only runtime; imports under `scripts/` and `tests/` are `sqlite3`, `urllib.request`, `json`, `dataclasses`, `typing`, and other stdlib modules.

**Package Manager:**
- Not detected.
- No `requirements.txt`, `pyproject.toml`, `poetry.lock`, `Pipfile`, or other Python lockfile is present.
- Execution is driven directly with `python3` and `just`.

## Frameworks

**Core:**
- None detected.
- The codebase uses a custom package layout under `scripts/strava_lib/` instead of a web or app framework.

**Testing:**
- None detected.
- Verification uses the custom runner in `scripts/run_tests.py` with tests in `tests/test_smoke.py`; `pytest` is intentionally not the primary entrypoint.

**Build/Dev:**
- `just` - Local command runner defined in `Justfile`.
- `python3` - Direct script execution for CLI and tests.

## Key Dependencies

**Critical:**
- `sqlite3` (stdlib) - Local persistence layer used by `scripts/strava_lib/db.py` against `data/strava.db`.
- `urllib.request` / `urllib.error` / `urllib.parse` (stdlib) - Direct HTTP client for Strava OAuth and API requests in `scripts/strava_lib/db.py` and `scripts/strava_lib/sync.py`.
- `json` (stdlib) - Serialization for API payloads, DB blobs, and CLI output across `scripts/cli.py`, `scripts/strava_lib/db.py`, `scripts/strava_lib/sync.py`, and `scripts/strava_lib/types.py`.

**Infrastructure:**
- Local filesystem state - `.env` for secrets/config, `data/strava.db` for SQLite persistence, and `references/` for supporting research notes.
- `dataclasses` / `typing` (stdlib) - Data contracts in `scripts/strava_lib/types.py` and `scripts/strava_lib/api_schema.py`.

## Configuration

**Environment:**
- Environment variables are loaded manually from `.env` in `scripts/strava_lib/db.py::load_env()`.
- Token refresh writes updated values back to `.env` in `scripts/strava_lib/db.py::save_env()`.
- Required Strava auth variables: `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`, `STRAVA_ACCESS_TOKEN`.

**Build:**
- `Justfile` defines the local command surface.
- `scripts/run_tests.py` is the verification harness.
- `.gitignore` excludes `.env` and `data/*.db*`.

## Platform Requirements

**Development:**
- Python 3.13.x with access to the repo checkout.
- Writable `data/` directory for SQLite files.
- Network access to `https://www.strava.com` for token refresh and API calls.

**Production:**
- No separate deployment target is detected.
- The code runs as a local CLI process against a checked-in repo plus local SQLite state.

---

*Stack analysis: 2026-05-20*
