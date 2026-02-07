# =============================================================================
# Ploston Dockerfile - Multi-stage build for optimized image size
# =============================================================================
# Build: docker build -t ostanlabs/ploston:latest .
# Run:   docker run -p 8080:8080 ostanlabs/ploston:latest
#
# Build with specific ploston-core version:
#   docker build --build-arg PLOSTON_CORE_REF=main -t ostanlabs/ploston:dev .
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

# Copy package source
COPY . ./

# Create virtual environment and install packages using uv
# Determine if PLOSTON_CORE_REF is a PyPI version or git ref
RUN uv venv /app/.venv && \
    if [ -n "$PLOSTON_CORE_REF" ]; then \
      # Check if it looks like a version (contains digits and dots, possibly .dev)
      if echo "$PLOSTON_CORE_REF" | grep -qE '^[0-9]+\.[0-9]+'; then \
        echo "Installing ploston-core from PyPI: $PLOSTON_CORE_REF" && \
        uv pip install --python /app/.venv/bin/python "ploston-core==${PLOSTON_CORE_REF}"; \
      else \
        echo "Installing ploston-core from git ref: $PLOSTON_CORE_REF" && \
        uv pip install --python /app/.venv/bin/python "git+https://github.com/ostanlabs/ploston-core.git@${PLOSTON_CORE_REF}"; \
      fi; \
    fi && \
    uv pip install --python /app/.venv/bin/python .

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
ENV AEL_PORT=8080

# Expose ports
# 8080 - MCP HTTP server
# 9090 - Prometheus metrics (optional)
EXPOSE 8080 9090

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

# Default command: start MCP server with HTTP transport
ENTRYPOINT ["/app/docker-entrypoint.sh"]

