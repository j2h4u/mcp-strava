FROM python:3.14-slim

# uv provides fast, lockfile-faithful installs (pinned to the host's uv 0.11.x for parity).
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    MCP_STRAVA_RUNTIME_PROFILE=container \
    MCP_STRAVA_HTTP_HOST=0.0.0.0 \
    MCP_STRAVA_HTTP_PORT=8080 \
    MCP_STRAVA_ALLOW_CONTAINER_BIND=1 \
    MCP_STRAVA_DB_PATH=/runtime/data/strava.duckdb \
    MCP_STRAVA_PROJECT_ROOT=/runtime \
    MCP_STRAVA_REFRESH_INTERVAL_SECONDS=3600

WORKDIR /app

# 1) Dependency layer — rebuilds only when pyproject.toml / uv.lock change, NOT on src
#    edits (--no-install-project). `--frozen` resolves from uv.lock's pinned URLs+hashes,
#    pulling wheels from files.pythonhosted.org and never touching the pypi.org index — so
#    it is byte-reproducible and survives index outages. The cache mount keeps the uv
#    download cache across builds, so re-installs stay fast.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# 2) Project layer — rebuilds only when application source changes.
COPY src ./src
COPY mcp-content ./mcp-content
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

RUN groupadd --gid 1000 mcp \
    && useradd --uid 1000 --gid 1000 --create-home mcp
USER 1000:1000

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -m mcp_strava.deploy.healthcheck

ENTRYPOINT ["python", "-m", "mcp_strava.deploy.entrypoint"]
