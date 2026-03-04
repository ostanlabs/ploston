# =============================================================================
# Native Tools Dockerfile - MCP server with filesystem, network, data tools
# =============================================================================
# Build from PyPI (default, used by CI/release):
#   docker build -t native-tools:latest -f docker/native-tools/Dockerfile .
#
# Build from local source (used by `ploston bootstrap --build-from-source`):
#   docker build --build-arg INSTALL_SOURCE=local \
#     -f packages/ploston/docker/native-tools/Dockerfile -t native-tools:local .
#   (build context = meta-repo root)
#
# Build with specific ploston-core version:
#   docker build --build-arg PLOSTON_CORE_REF=main -t native-tools:dev .
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies using uv
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Install source: "pypi" (default) or "local" (from meta-repo checkout)
ARG INSTALL_SOURCE="pypi"
# Optional: ploston-core version or git ref (only used when INSTALL_SOURCE=pypi)
ARG PLOSTON_CORE_REF=""
# Source for dev versions: "test-pypi" or "pypi" (default)
ARG CORE_SOURCE="pypi"

WORKDIR /app

# Install build dependencies (git needed if installing from git ref)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy source — what we copy depends on INSTALL_SOURCE
COPY . ./

# Create virtual environment and install packages
RUN uv venv /app/.venv && \
    if [ "$INSTALL_SOURCE" = "local" ]; then \
      echo "Installing from local source" && \
      uv pip install --python /app/.venv/bin/python ./packages/ploston-core && \
      uv pip install --python /app/.venv/bin/python "./packages/ploston[native-tools]"; \
    else \
      if [ -n "$PLOSTON_CORE_REF" ]; then \
        if echo "$PLOSTON_CORE_REF" | grep -qE '^[0-9]+\.[0-9]+'; then \
          if [ "$CORE_SOURCE" = "test-pypi" ]; then \
            echo "Installing ploston-core==$PLOSTON_CORE_REF from Test PyPI (no-deps)" && \
            uv pip install --python /app/.venv/bin/python \
              --index-url https://test.pypi.org/simple \
              --extra-index-url https://pypi.org/simple \
              --index-strategy unsafe-best-match \
              --no-deps \
              "ploston-core==${PLOSTON_CORE_REF}"; \
          else \
            echo "Installing ploston-core==$PLOSTON_CORE_REF from PyPI" && \
            uv pip install --python /app/.venv/bin/python "ploston-core==${PLOSTON_CORE_REF}"; \
          fi; \
        else \
          echo "Installing ploston-core from git ref: $PLOSTON_CORE_REF" && \
          uv pip install --python /app/.venv/bin/python "git+https://github.com/ostanlabs/ploston-core.git@${PLOSTON_CORE_REF}"; \
        fi; \
      fi && \
      uv pip install --python /app/.venv/bin/python ".[native-tools]"; \
    fi

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

# Labels for GitHub Container Registry
# This links the package to the ploston repo, allowing GITHUB_TOKEN to push
LABEL org.opencontainers.image.source=https://github.com/ostanlabs/ploston
LABEL org.opencontainers.image.description="Ploston Native Tools - MCP server with filesystem, network, data tools"
LABEL org.opencontainers.image.licenses=MIT

# Default command: start native tools MCP server in HTTP mode
CMD ["python", "-m", "ploston.native_tools.server"]
