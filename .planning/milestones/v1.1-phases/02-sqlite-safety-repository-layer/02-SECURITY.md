---
phase: 02
slug: sqlite-safety-repository-layer
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-21
verified: 2026-05-21
register_authored_at_plan_time: true
---

# Phase 02 - Security

Per-phase security contract for the SQLite safety and repository layer. This audit was created from the Phase 02 plan-time STRIDE registers plus execution summaries, then verified against the implemented code and tests.

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Filesystem -> SQLite adapter | Local mirror DB path may be missing, corrupt, stale, or accidentally pointed at a fixture. | SQLite database path and local mirror contents |
| Migration tooling -> durable mirror | Explicit operator migrations can alter `data/strava.db`; they must preflight, back up, migrate, post-check, and preserve parity. | Schema metadata, row counts, backup files, training-load signals |
| Application modules -> SQLite repository | Application, analytics, sync, and future service surfaces must not acquire arbitrary SQLite access directly. | Activity summaries, stream rows, load history, zones, kudos, sync metadata |
| Strava ingest -> repository writes | External Strava payloads enter local storage through sync/backfill paths. | Activity JSON, stream samples, detail JSON, kudos |
| CLI operator -> local escape hatches | Operator SQL is intentionally local CLI only and must not become a service/MCP capability. | Arbitrary SQL result sets from the local mirror |
| Default tests -> durable mirror | Default verification must not mutate the user's real mirror or call live Strava network. | Temp fixtures, copied DB scenarios, local filesystem metadata |

## Threat Register

| Plan | Threat ID | Category | Component | Disposition | Mitigation | Status | Evidence |
|------|-----------|----------|-----------|-------------|------------|--------|----------|
| 02-01 | T-02-01 | Tampering | `connection.py` | mitigate | Expected mirror opens fail closed with SQLite URI `mode=rw`; fixture creation remains explicit. | closed | `connection.py:14-24`; `db.py:27-41`; `tests/test_sqlite_safety.py:144-155` |
| 02-01 | T-02-02 | Denial of Service | SQLite connection policy | mitigate | Central connection policy sets WAL, autocheckpoint, and busy timeout. | closed | `connection.py:7-11`; `tests/test_repository_boundary.py:143-152` |
| 02-01 | T-02-03 | Tampering | `migrations.py` | mitigate | Migration gate runs preflight, timestamped backup, migration, post-check, row parity, and load-parity helpers. | closed | `migrations.py:67-137`; `backup.py:17-49`; `tests/test_sqlite_safety.py:242-338` |
| 02-01 | T-02-04 | Information Disclosure | backup files | mitigate | Backups are stored under the data-area backup directory, integrity-checked, retained, and chmodded to `0600` where supported. | closed | `backup.py:17-59`; `tests/test_sqlite_safety.py:181-202`, `tests/test_sqlite_safety.py:205-239` |
| 02-02 | T-02-04 | Tampering | repository writes | mitigate | Repository exposes focused parameterized methods; no generic SQL service method was added. | closed | `repository.py:103-155`, `repository.py:525-689`; `tests/test_repository_boundary.py:155-259` |
| 02-02 | T-02-05 | Denial of Service | stream inserts | mitigate | Stream writes preserve chunked `executemany`, explicit commits, and atomic replace rollback. | closed | `repository.py:525-612`; `sync.py:110-123`; `tests/test_repository_boundary.py:177-240` |
| 02-02 | T-02-06 | Elevation of Privilege | operator SQL | mitigate | `cmd_sql` remains a local CLI function and is excluded from repository/application/MCP reuse. | closed | `cli.py:83-100`; `tests/test_security_guards.py:130-140`; `tests/test_repository_boundary.py:80-103` |
| 02-03 | T-02-06 | Tampering | daily load status | mitigate | Repository separates `observed_trimp` from `effective_trimp` and never classifies activity-present missing data as `REST`. | closed | `repository.py:261-375`; `tests/test_load_status.py:86-125` |
| 02-03 | T-02-07 | Repudiation | parity checks | mitigate | Numeric parity tests compare observed TRIMP, Banister series, EWMA, and weekly-plan inputs after repository delegation. | closed | `tests/test_load_status.py:128-174`; `tests/test_sqlite_safety.py:256-338` |
| 02-04 | T-02-07 | Tampering | `db-migrate` command | mitigate | `db-migrate` is explicit, routes through `run_migrations`, reports backup metadata, and preflight/check commands are read-only. | closed | `cli.py:315-357`; `cli.py:379-381`; `migrations.py:115-137` |
| 02-04 | T-02-08 | Information Disclosure | operator SQL | accept | Local operator SQL remains accepted only as CLI-local functionality; source guards reject service/MCP reuse. | closed | `cli.py:83-100`; `tests/test_security_guards.py:122-140` |
| 02-04 | T-02-09 | Denial of Service | default tests | mitigate | Default tests use temp fixtures or metadata-only checks and avoid live Strava network. | closed | `tests/test_sqlite_safety.py:144-338`; `tests/test_repository_boundary.py:262-277`; `02-04-SUMMARY.md` real-mirror metadata invariance |
| all | T-02-SC | Tampering | package installs | accept | No package-manager installs were planned or performed in Phase 02. | closed | `02-01-SUMMARY.md` through `02-04-SUMMARY.md` show `tech-stack.added: []`; git history contains no dependency-change task for Phase 02 |

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-02-01 | T-02-08 | Arbitrary SQL is useful for local operator inspection during development, but remains CLI-local and guarded from service/MCP reuse. | Phase 02 plan | 2026-05-21 |
| AR-02-02 | T-02-SC | Supply-chain risk is accepted because Phase 02 performed no package-manager installs and added no dependencies. | Phase 02 plan | 2026-05-21 |

## Summary Threat Flags

No additional threat flags were found in `02-01-SUMMARY.md` through `02-04-SUMMARY.md` beyond the plan-time STRIDE registers.

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-21 | 13 | 13 | 0 | Codex inline security audit |

## Sign-Off

- [x] All threats have a disposition: mitigate or accept.
- [x] Accepted risks documented in Accepted Risks Log.
- [x] `threats_open: 0` confirmed.
- [x] `status: verified` set in frontmatter.

**Approval:** verified 2026-05-21
