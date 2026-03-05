# =============================================================================
# Ploston Dockerfile - Multi-stage build for optimized image size
# =============================================================================
# Build from PyPI (default, used by CI/release):
#   docker build -t ploston:latest .
#
# Build from local source (used by `ploston bootstrap --build-from-source`):
#   docker build --build-arg INSTALL_SOURCE=local \
#     -f packages/ploston/Dockerfile -t ploston:local .
#   (build context = meta-repo root)
#
# Build with specific ploston-core version:
#   docker build --build-arg PLOSTON_CORE_REF=main -t ploston:dev .
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
# For pypi: only the ploston package (build context = packages/ploston/)
# For local: the full meta-repo (build context = repo root)
COPY . ./

# Create virtual environment and install packages
RUN uv venv /app/.venv && \
    if [ "$INSTALL_SOURCE" = "local" ]; then \
      echo "Installing from local source" && \
      uv pip install --python /app/.venv/bin/python ./packages/ploston-core && \
      uv pip install --python /app/.venv/bin/python ./packages/ploston; \
    else \
      if [ -n "$PLOSTON_CORE_REF" ]; then \
        if echo "$PLOSTON_CORE_REF" | grep -qE '^[0-9]+\.[0-9]+'; then \
          if [ "$CORE_SOURCE" = "test-pypi" ]; then \
            echo "Installing ploston-core==$PLOSTON_CORE_REF from Test PyPI (no-deps)" && \
            ATTEMPT=1 && MAX_ATTEMPTS=5 && \
            while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do \
              echo "Attempt $ATTEMPT of $MAX_ATTEMPTS..." && \
              if uv pip install --python /app/.venv/bin/python \
                --index-url https://test.pypi.org/simple \
                --extra-index-url https://pypi.org/simple \
                --index-strategy unsafe-best-match \
                --no-deps \
                --refresh \
                "ploston-core==${PLOSTON_CORE_REF}"; then \
                break; \
              fi && \
              if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then \
                echo "Failed after $MAX_ATTEMPTS attempts" && exit 1; \
              fi && \
              echo "Waiting 10s for CDN propagation..." && \
              sleep 10 && \
              ATTEMPT=$((ATTEMPT + 1)); \
            done; \
          else \
            echo "Installing ploston-core==$PLOSTON_CORE_REF from PyPI" && \
            uv pip install --python /app/.venv/bin/python "ploston-core==${PLOSTON_CORE_REF}"; \
          fi; \
        else \
          echo "Installing ploston-core from git ref: $PLOSTON_CORE_REF" && \
          uv pip install --python /app/.venv/bin/python "git+https://github.com/ostanlabs/ploston-core.git@${PLOSTON_CORE_REF}"; \
        fi; \
      fi && \
      uv pip install --python /app/.venv/bin/python .; \
    fi

# -----------------------------------------------------------------------------
# Stage 2: Runtime - Minimal production image
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Mark as running in Docker (for host detection)
ENV DOCKER_CONTAINER=1

# Default configuration
ENV AEL_HOST=0.0.0.0
ENV AEL_PORT=8022

# Expose ports
# 8022 - MCP HTTP server
# 9090 - Prometheus metrics (optional)
EXPOSE 8022 9090

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${AEL_PORT}/health || exit 1

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash ploston && \
    chown -R ploston:ploston /app
USER ploston

# Copy entrypoint script
COPY --chown=ploston:ploston docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Labels for GitHub Container Registry
# This links the package to the ploston repo, allowing GITHUB_TOKEN to push
LABEL org.opencontainers.image.source=https://github.com/ostanlabs/ploston
LABEL org.opencontainers.image.description="Ploston - Agent Execution Layer"
LABEL org.opencontainers.image.licenses=MIT

# Default command: start MCP server with HTTP transport
ENTRYPOINT ["/app/docker-entrypoint.sh"]
