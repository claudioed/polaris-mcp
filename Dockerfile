# Multi-stage build: build the wheel, install it into a clean venv, ship only that.
FROM python:3.13-slim AS build
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir --quiet build \
    && python -m build --wheel \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --quiet dist/*.whl

FROM python:3.13-slim
RUN useradd --system --create-home --uid 10001 polaris \
    && mkdir /data && chown polaris:polaris /data
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    POLARIS_MCP_TRANSPORT=streamable-http \
    POLARIS_MCP_HOST=0.0.0.0 \
    POLARIS_MCP_PORT=8000 \
    POLARIS_CREDENTIALS_FILE=/data/credentials.json
USER polaris
WORKDIR /data
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, socket; socket.create_connection(('127.0.0.1', int(os.environ.get('POLARIS_MCP_PORT', '8000'))), timeout=4).close()"]
ENTRYPOINT ["polaris-mcp"]
CMD ["serve"]
