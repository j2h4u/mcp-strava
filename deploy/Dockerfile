FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MCP_STRAVA_RUNTIME_PROFILE=container \
    MCP_STRAVA_HTTP_HOST=0.0.0.0 \
    MCP_STRAVA_HTTP_PORT=8080 \
    MCP_STRAVA_ALLOW_CONTAINER_BIND=1 \
    MCP_STRAVA_DB_PATH=/runtime/data/strava.db \
    MCP_STRAVA_TOKEN_PATH=/runtime/.env \
    MCP_STRAVA_REFRESH_INTERVAL_SECONDS=3600 \
    MCP_STRAVA_STREAM_BACKFILL_BATCH_SIZE=50

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src
RUN pip install --no-cache-dir /app

RUN groupadd --gid 1000 mcp \
    && useradd --uid 1000 --gid 1000 --create-home mcp
USER 1000:1000

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -m mcp_strava.deploy.healthcheck

ENTRYPOINT ["python", "-m", "mcp_strava.deploy.entrypoint"]
