FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MCP_STRAVA_RUNTIME_PROFILE=container \
    MCP_STRAVA_HTTP_HOST=0.0.0.0 \
    MCP_STRAVA_HTTP_PORT=8080 \
    MCP_STRAVA_ALLOW_CONTAINER_BIND=1 \
    MCP_STRAVA_DB_PATH=/runtime/data/strava.db \
    MCP_STRAVA_TOKEN_PATH=/runtime/.env

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src
RUN pip install --no-cache-dir /app

RUN groupadd --system --gid 10001 mcp && useradd --system --uid 10001 --gid 10001 --create-home mcp
USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -m mcp_strava.deploy.preflight --db "$MCP_STRAVA_DB_PATH" --quick --quiet

ENTRYPOINT ["python", "-m", "mcp_strava.deploy.entrypoint"]
