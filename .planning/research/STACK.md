# Stack Research

**Domain:** Local Python Strava mirror + read-only MCP analytics service over HTTP
**Researched:** 2026-05-20
**Confidence:** HIGH

**Status:** historical/superseded. Use `.planning/codebase/STACK.md` for the current stack contract and `pyproject.toml` for the live dependency/source of truth. The SQLAlchemy/Alembic/SQLite recommendations below reflect an earlier design pass and are not the current implementation path.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| Python | 3.13.x | Runtime | Matches current codebase runtime and gives modern typing/perf without forcing bleeding-edge 3.14 adoption. | HIGH |
| `mcp` (official Python SDK) | 1.27.1 | MCP server implementation | Official MCP Python SDK (Tier 1) with `FastMCP` and Streamable HTTP support; aligns with current MCP transport standard. | HIGH |
| MCP Streamable HTTP transport | Spec `2025-06-18` | MCP over HTTP | Current spec transport; replaces legacy HTTP+SSE model and defines required HTTP/session/version headers. | HIGH |
| SQLAlchemy Core | 2.0.49 | SQLite repository layer | Historical recommendation from the design pass; not current for this repo. | HIGH |
| Alembic | 1.18.4 | Schema migrations | Historical recommendation from the design pass; not current for this repo. | HIGH |

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| `pydantic-settings` | 2.14.1 | Typed settings + env/secrets loading | Use for one authoritative config object (db path, Strava creds, runtime mode, refresh policy). | HIGH |
| `httpx` | 0.28.1 | Strava API adapter HTTP client | Use for OAuth refresh + API calls with structured timeouts and cleaner sync/async options than stdlib urllib. | MEDIUM |
| `tenacity` | 9.1.4 | Retry/backoff policy | Use for Strava rate-limit and transient error handling in adapter/service layer. | MEDIUM |
| `Typer` | 0.20.x | Installable CLI surface | Use for clean command grouping and typed CLI over application services; keep `project.scripts` entry point. | MEDIUM |
| `APScheduler` | 3.11.2 | Background mirror refresh | Use for at-least-daily refresh + staleness-triggered scheduling without exposing sync controls via MCP. | MEDIUM |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv` | Python env + dependency + lockfile management | Single tool replacing pip/pip-tools/virtualenv workflows; keep lockfile committed. |
| `ruff` | Lint + format | Single fast linter/formatter with `pyproject.toml` config. |
| `pytest` | Test runner | Add focused tests for migrations, repository queries, sync retry behavior, and MCP read-only tools. |

## Installation

```bash
# Bootstrap project
uv init --package
uv python pin 3.13

# Runtime dependencies
uv add mcp==1.27.1 sqlalchemy==2.0.49 alembic==1.18.4 \
  pydantic-settings==2.14.1 httpx==0.28.1 tenacity==9.1.4 \
  typer apscheduler==3.11.2

# Dev dependencies
uv add --dev pytest ruff
```

## Prescriptive Architecture Choices For This Refactor

1. Use `src/` package layout with explicit boundaries:
- `core/` (training domain logic only)
- `application/` (use-cases: reports, analytics, recommendations, freshness policy)
- `infrastructure/sqlite/` (repositories + migrations + backup)
- `infrastructure/strava/` (OAuth + API adapter)
- `interfaces/cli/` (Typer commands)
- `interfaces/mcp_http/` (read-only MCP tools)

2. MCP surface must be read-only and user-facing:
- Expose: workouts, analytics, reports, recommendations.
- Do not expose: `sync`, `backfill`, `raw`, `sql`, sync logs.

3. Run MCP via Streamable HTTP on local bind only:
- Bind `127.0.0.1` by default.
- Serve one MCP endpoint path (e.g., `/mcp`).
- Enforce origin checks and protocol/session headers per MCP spec.

4. Preserve `data/strava.db` as durable mirror state:
- No destructive resync by default.
- No automatic full rebuild migration path.

## SQLite Migration + Backup Standards (Data Safety Contract)

Before any schema migration on `data/strava.db`:

1. Preflight:
- Verify DB file exists and is readable.
- Record row counts for critical tables (`activities`, `streams`, `kudos`, `sync_log`).
- Verify current schema version (`PRAGMA user_version` or Alembic version table).

2. Backup:
- Create backup using Python `sqlite3.Connection.backup()` to a timestamped file.
- Optionally create compact snapshot with `VACUUM INTO` for cold backup artifacts.

3. Migration execution:
- Use Alembic revisions only.
- For SQLite table-altering migrations, use Alembic batch operations.
- Require explicit transaction + post-migration integrity checks.

4. Post-check:
- Re-check row counts and key report queries.
- Abort release if counts regress unexpectedly.

## Docker/Runtime Recommendation (Local, One User)

- Base image: `python:3.13-slim`.
- Run as non-root user.
- Mount persistent volume for `/app/data` so `strava.db` survives container recreation.
- Keep container filesystem read-only except explicit writable paths (`/app/data`, temp dirs).
- Use restart policy `unless-stopped` for local reliability.
- Default network bind remains local-only unless user explicitly opts in.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Official `mcp` Python SDK | Custom FastAPI JSON-RPC implementation | Only if you need non-standard protocol behavior not supported by official SDK. |
| SQLAlchemy Core | Raw `sqlite3` everywhere | Only for very small scripts; not ideal once boundaries/migrations/adapters are formalized. |
| Alembic | Handwritten ad-hoc SQL migration scripts | Only for one-off manual repair; not acceptable as primary migration workflow. |
| APScheduler in-process | External cron/systemd timer only | Use external scheduler if you want strict process isolation for sync jobs. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Legacy MCP HTTP+SSE transport as primary | Replaced by Streamable HTTP in modern MCP spec. | Streamable HTTP transport. |
| Destructive “drop and resync” DB reset flows | Risks irreversible loss of mirrored Strava history and expensive rate-limited re-fetch. | Migration + backup + verification pipeline. |
| Treating this research file as the live stack contract | It is a historical recommendation set and will drift from the implementation. | `.planning/codebase/STACK.md` plus `pyproject.toml`. |
| Storing refreshed tokens by rewriting generic `.env` ad hoc | Fragile and easy to corrupt under concurrency/process interruption. | Typed settings + dedicated token persistence strategy (atomic write/lock or dedicated secrets path). |
| Exposing SQL/sync/backfill via MCP tools | Violates read-only analytics boundary and increases accidental destructive risk. | Keep ops/admin commands CLI-only. |
| ORM-heavy domain model for analytics queries | Adds state complexity with little benefit for query-centric reporting workloads. | SQLAlchemy Core repositories + explicit domain DTOs. |

## Stack Patterns by Variant

**If running directly on host (no Docker):**
- Use `uv run` entrypoints.
- Use in-process APScheduler.
- Keep MCP bind on `127.0.0.1`.

**If running in Docker with local MCP gateway:**
- Keep service private on container network.
- Mount `data/` volume for DB durability.
- Keep same code paths/config model; only transport/addressing changes.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `mcp==1.27.1` | MCP Streamable HTTP spec family (2025 versions) | Use transport `streamable-http`; keep protocol-version header handling enabled. |
| `sqlalchemy==2.0.49` | `alembic==1.18.4` | Current stable pairing; supports SQLite batch migration workflow. |
| `uvicorn==0.47.0` | ASGI apps mounted from MCP SDK | If using mounted ASGI mode, default host in docs is `127.0.0.1` (local-safe default). |

## Sources

- MCP Transports spec (2025-06-18): https://modelcontextprotocol.io/specification/2025-06-18/basic/transports — verified Streamable HTTP as standard, security/session/protocol header requirements (HIGH)
- MCP SDK index: https://modelcontextprotocol.io/docs/sdk — verified Python SDK is Tier 1 official SDK (HIGH)
- MCP Python SDK docs: https://py.sdk.modelcontextprotocol.io/ — verified `FastMCP` and `mcp.run(transport="streamable-http")` quickstart (HIGH)
- MCP Python SDK repo/releases: https://github.com/modelcontextprotocol/python-sdk and https://github.com/modelcontextprotocol/python-sdk/releases — verified current release line (`v1.27.1`) and Streamable HTTP mounting patterns (HIGH)
- SQLAlchemy docs: https://docs.sqlalchemy.org/en/20/intro.html — verified 2.0.49 current release and Core architecture model (HIGH)
- Alembic batch migrations: https://alembic.sqlalchemy.org/en/latest/batch.html — verified SQLite migration constraints and batch workflow (HIGH)
- Python sqlite3 docs: https://docs.python.org/3/library/sqlite3.html — verified live backup API via `Connection.backup()` (HIGH)
- SQLite VACUUM docs: https://sqlite.org/lang_vacuum.html — verified `VACUUM INTO` backup behavior and caveats (HIGH)
- SQLite PRAGMA docs: https://www.sqlite.org/pragma.html — verified `user_version` ownership by application (HIGH)
- uv docs: https://docs.astral.sh/uv/ — verified unified package/project manager positioning and lockfile model (MEDIUM)
- Ruff docs: https://docs.astral.sh/ruff/ — verified linter+formatter role (MEDIUM)
- Pydantic Settings docs: https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/ — verified settings/env/secrets model (HIGH)
- Uvicorn settings: https://www.uvicorn.org/settings/ — verified local-bind default host behavior (MEDIUM)
- Docker restart policy docs: https://docs.docker.com/engine/containers/start-containers-automatically/ and https://docs.docker.com/reference/compose-file/services/ — verified `unless-stopped` semantics (HIGH)

---
*Stack research for: Local Strava mirror MCP analytics service*
*Researched: 2026-05-20*
