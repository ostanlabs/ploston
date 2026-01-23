# =============================================================================
# Ploston Dockerfile - Multi-stage build for optimized image size
# =============================================================================
# Build: docker build -t ostanlabs/ploston:latest .
# Run:   docker run -p 8080:8080 ostanlabs/ploston:latest
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy package source
COPY . ./

# Create virtual environment and install packages using pip
# Install from local source (which pulls ploston-core from PyPI)
RUN python -m venv /app/.venv && \
    . /app/.venv/bin/activate && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

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

