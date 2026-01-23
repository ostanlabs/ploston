# Ploston

Ploston OSS - Deterministic Agent Execution Layer

## Overview

This package provides the open-source server, plugins, and workflows for the Ploston agent execution platform.

## Installation

### From PyPI

```bash
pip install ploston
```

### From Source

```bash
git clone https://github.com/ostanlabs/ploston.git
cd ploston
make install
```

## Usage

### Start the Server

```bash
# Using the CLI
ploston-server --host 0.0.0.0 --port 8080

# Or using make
make serve
```

### Server Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `0.0.0.0` | Host to bind to |
| `--port` | `8080` | Port for MCP HTTP server |
| `--metrics-port` | `9090` | Port for Prometheus metrics |
| `--reload` | `false` | Enable auto-reload for development |

## Docker

### Pull from Docker Hub

```bash
docker pull ostanlabs/ploston:latest
```

### Run with Docker

```bash
docker run -d \
  --name ploston \
  -p 8080:8080 \
  -p 9090:9090 \
  ostanlabs/ploston:latest
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PLOSTON_HOST` | `0.0.0.0` | Server host |
| `PLOSTON_PORT` | `8080` | MCP HTTP port |
| `PLOSTON_METRICS_PORT` | `9090` | Prometheus metrics port |
| `PLOSTON_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |

### Docker Compose Example

```yaml
version: '3.8'
services:
  ploston:
    image: ostanlabs/ploston:latest
    ports:
      - "8080:8080"
      - "9090:9090"
    environment:
      - PLOSTON_LOG_LEVEL=INFO
    restart: unless-stopped
```

### Build Locally

```bash
make docker-build
make docker-run
```

## Development

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

```bash
make install
```

### Commands

```bash
make help         # Show all commands
make test         # Run all tests
make test-unit    # Run unit tests only
make lint         # Run linter
make format       # Format code
make check        # Run lint + tests
make serve        # Start server locally
make docker-build # Build Docker image
make docker-run   # Run in Docker
```

## Features

- Workflow execution engine
- Plugin system
- MCP (Model Context Protocol) support
- REST API
- Prometheus metrics

## License

Apache-2.0
