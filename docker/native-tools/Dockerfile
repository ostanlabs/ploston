# =============================================================================
# Native Tools Dockerfile - MCP server with filesystem, network, data tools
# =============================================================================
# Build: docker build -t ostanlabs/native-tools:latest -f docker/native-tools/Dockerfile .
# Run:   docker run -p 8081:8081 ostanlabs/native-tools:latest
# =============================================================================
# This Dockerfile is for CI/publishing - it installs from PyPI.
# For local development, use the Dockerfile in the meta-repo which builds
# from local source packages.
# =============================================================================
# Target size: <400MB
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies from PyPI
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment and install packages from PyPI
# ploston[native-tools] includes ploston-core and fastmcp
RUN python -m venv /app/.venv && \
    . /app/.venv/bin/activate && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "ploston[native-tools]"

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

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Mark as running in Docker
ENV DOCKER_CONTAINER=1

# Native tools configuration
ENV NATIVE_TOOLS_HOST=0.0.0.0
ENV NATIVE_TOOLS_PORT=8081

# Redis configuration store (optional)
ENV REDIS_URL=""
ENV REDIS_CONFIG_PREFIX="ploston:config"
ENV REDIS_CONFIG_CHANNEL="ploston:config:changed"
ENV REDIS_SERVICE_NAME="native-tools"

# Optional service endpoints (can be overridden via Redis config)
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
CMD ["python", "-m", "ploston.native_tools.server"]
