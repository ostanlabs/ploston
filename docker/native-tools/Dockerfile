# =============================================================================
# Native Tools Dockerfile - MCP server with filesystem, network, data tools
# =============================================================================
# Build: docker build -t native-tools:latest -f docker/native-tools/Dockerfile .
# Run:   docker run native-tools:latest
# =============================================================================
# Target size: <400MB
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency files from agent submodule
COPY agent/pyproject.toml agent/uv.lock* ./

# Create virtual environment and install dependencies
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv sync --frozen --no-dev 2>/dev/null || \
    pip install --no-cache-dir \
        click>=8.2.1 \
        structlog>=25.4.0 \
        aiohttp>=3.8.0 \
        httpx>=0.24.0 \
        pydantic>=2.0.0 \
        pyyaml>=6.0 \
        fastmcp>=2.0.0

# -----------------------------------------------------------------------------
# Stage 2: Runtime - Minimal production image
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    dnsutils \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy native tools source code
COPY agent/src/ ./src/

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Mark as running in Docker
ENV DOCKER_CONTAINER=1

# Native tools configuration
ENV NATIVE_TOOLS_HOST=0.0.0.0
ENV NATIVE_TOOLS_PORT=8081

# Optional service endpoints (can be overridden)
ENV FIRECRAWL_BASE_URL=""
ENV FIRECRAWL_API_KEY=""
ENV KAFKA_BOOTSTRAP_SERVERS=""
ENV OLLAMA_HOST=""

# Expose port for MCP server
EXPOSE 8081

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${NATIVE_TOOLS_PORT}/health || exit 1

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash nativetools && \
    mkdir -p /data && \
    chown -R nativetools:nativetools /app /data
USER nativetools

# Working directory for filesystem operations
WORKDIR /data

# Default command: start native tools MCP server in HTTP mode
# FastMCP supports both stdio and HTTP transports
# For HTTP mode, we use a Python command to run with transport="http"
CMD ["python", "-c", "from native_tools.server import mcp; mcp.run(transport='http', host='0.0.0.0', port=8081)"]
