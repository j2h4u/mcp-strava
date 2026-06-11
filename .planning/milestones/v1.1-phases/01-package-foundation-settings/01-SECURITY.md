---
status: SECURED
threats_open: 0
asvs_level: 1
audit_date: 2026-05-20
phase: 01-package-foundation-settings
---

## SECURED

**Phase:** 01 — package-foundation-settings  
**Threats Closed:** 15/15  
**ASVS Level:** 1

### Threat Verification
| Threat ID | Category | Disposition | Evidence |
|-----------|----------|-------------|----------|
| 01-01-T01 | Tampering | mitigate | `tests/test_security_guards.py:25-35` asserts existing `data/strava.db` keeps inode and size; `tests/test_smoke.py:44-52` uses read-only DB checks before report path. |
| 01-01-T02 | Information disclosure | mitigate | `.gitignore:2-5` ignores `.env` and `.planning/config.json`; `.gitignore:30-35` ignores local DB files; `tests/test_security_guards.py:16-23` enforces ignored + untracked for `.env`, `.planning/config.json`, `data/strava.db`. |
| 01-01-T03 | Spoofing/import confusion | mitigate | Package imports use `mcp_strava.*` in CLI/runtime (`src/mcp_strava/cli.py:7-19`, `src/mcp_strava/db.py:11-12`); smoke import resolution checks package path in `tests/test_smoke.py:36-39`. |
| 01-01-T04 | Boundary regression | mitigate | Module entrypoint exists and calls CLI main (`src/mcp_strava/__main__.py:1-5`); CLI usage contract is `python -m mcp_strava` (`src/mcp_strava/cli.py:325-335`); no console script in `pyproject.toml:5-22`. |
| 01-01-T05 | Verification false negative | mitigate | Source-tree guard executes `python -m mcp_strava` with `PYTHONPATH=src` and asserts usage output (`tests/test_security_guards.py:38-51`). |
| 01-02-T01 | Information disclosure | mitigate | Settings parser only accepts `MCP_STRAVA_*` keys (`src/mcp_strava/settings.py:30-39`, `src/mcp_strava/settings.py:58-59`); settings tests avoid real `STRAVA_*` secret keys (`tests/test_settings.py:40-96`). |
| 01-02-T02 | Tampering | mitigate | Settings path handling is path-resolution only (`src/mcp_strava/settings.py:130-132`); DB path usage is lazy resolution via settings (`src/mcp_strava/db.py:15-20`, `src/mcp_strava/db.py:28-35`). |
| 01-02-T03 | Denial of service | mitigate | Integer/range validation in settings (`src/mcp_strava/settings.py:63-81`, `src/mcp_strava/settings.py:135-145`) with invalid-value tests (`tests/test_settings.py:134-157`). |
| 01-02-T04 | Configuration confusion | mitigate | Deterministic precedence env -> env file -> defaults in resolver (`src/mcp_strava/settings.py:123-128`); precedence test present (`tests/test_settings.py:97-107`). |
| 01-02-T05 | Test pollution | mitigate | Cached API with explicit reset (`src/mcp_strava/settings.py:159-171`) and reset behavior tests (`tests/test_settings.py:110-131`). |
| 01-03-T01 | Tampering | mitigate | Daily smoke test is read-only and skip-guarded for missing DB/table (`tests/test_smoke.py:44-52`) and performs no sync/backfill call in that path (`tests/test_smoke.py:55-67`). |
| 01-03-T02 | Information disclosure | mitigate | Smoke suite does not read `.planning/config.json` and only checks/report fields (`tests/test_smoke.py:42-67`); settings loader scope remains `MCP_STRAVA_*` (`src/mcp_strava/settings.py:30-39`). |
| 01-03-T03 | Repudiation | mitigate | Primary test workflow is explicit and singular: `just test` runs `python3 -m pytest` (`Justfile:6-10`). |
| 01-03-T04 | Boundary regression | mitigate | Package-path assertion validates `mcp_strava.types` resolves to `src/mcp_strava/types.py` (`tests/test_smoke.py:36-39`). |
| 01-03-T05 | Clean-checkout fragility | mitigate | Smoke test fail-closed skip behavior on missing DB or missing activities table (`tests/test_smoke.py:45-46`, `tests/test_smoke.py:52`). |

### Unregistered Flags
None. `01-02-SUMMARY.md` and `01-03-SUMMARY.md` declare `Threat Flags: None`; no unmapped flags were found.
