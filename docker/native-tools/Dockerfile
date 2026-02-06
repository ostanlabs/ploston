# =============================================================================
# Native Tools Dockerfile - MCP server with filesystem, network, data tools
# =============================================================================
# Build: docker build -t ostanlabs/native-tools:latest -f docker/native-tools/Dockerfile .
# Run:   docker run -p 8081:8081 ostanlabs/native-tools:latest
#
# Build with specific ploston-core version:
#   docker build --build-arg PLOSTON_CORE_REF=main -t ostanlabs/native-tools:dev .
# =============================================================================
# Target size: <400MB
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies using uv
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Optional: ploston-core version or git ref
# - If looks like a version (e.g., 1.4.0.dev1738800000), install from PyPI
# - If looks like a git ref (branch, tag, SHA), install from git
# - If not set, uses ploston-core from PyPI (default for releases)
ARG PLOSTON_CORE_REF=""

WORKDIR /app

# Install build dependencies (git needed if installing from git ref)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy package source (needed for local ploston install)
COPY . ./

# Create virtual environment and install packages using uv
# Determine if PLOSTON_CORE_REF is a PyPI version or git ref
# Includes retry logic for PyPI propagation delays
RUN uv venv /app/.venv && \
    if [ -n "$PLOSTON_CORE_REF" ]; then \
      # Check if it looks like a version (contains digits and dots, possibly .dev)
      if echo "$PLOSTON_CORE_REF" | grep -qE '^[0-9]+\.[0-9]+'; then \
        echo "Installing ploston-core from PyPI: $PLOSTON_CORE_REF" && \
        # Retry loop for PyPI propagation delays (up to 5 minutes)
        MAX_ATTEMPTS=30 && \
        ATTEMPT=1 && \
        while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do \
          echo "Attempt $ATTEMPT/$MAX_ATTEMPTS: Installing ploston-core==$PLOSTON_CORE_REF" && \
          if uv pip install --python /app/.venv/bin/python "ploston-core==${PLOSTON_CORE_REF}"; then \
            echo "Successfully installed ploston-core==$PLOSTON_CORE_REF" && \
            break; \
          fi && \
          if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then \
            echo "Failed to install ploston-core==$PLOSTON_CORE_REF after $MAX_ATTEMPTS attempts" && \
            exit 1; \
          fi && \
          echo "Package not yet available, waiting 10s before retry..." && \
          sleep 10 && \
          ATTEMPT=$((ATTEMPT + 1)); \
        done; \
      else \
        echo "Installing ploston-core from git ref: $PLOSTON_CORE_REF" && \
        uv pip install --python /app/.venv/bin/python "git+https://github.com/ostanlabs/ploston-core.git@${PLOSTON_CORE_REF}"; \
      fi; \
    fi && \
    uv pip install --python /app/.venv/bin/python ".[native-tools]"

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
