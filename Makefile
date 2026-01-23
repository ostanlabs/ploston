# Ploston OSS Server
# ==================
# Development commands for local testing and Docker builds
#
# Quick start:
#   make install    # Install dependencies
#   make test       # Run tests
#   make serve      # Start server locally
#   make docker-run # Run in Docker

# Configuration
PYTHON = uv run python
PYTEST = uv run pytest
IMAGE_NAME = ostanlabs/ploston
IMAGE_TAG ?= dev

# Colors
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
RESET := \033[0m

.PHONY: help install test lint format serve docker-build docker-run clean

# =============================================================================
# HELP
# =============================================================================

help:
	@echo ""
	@echo "$(CYAN)Ploston OSS Server$(RESET)"
	@echo "==================="
	@echo ""
	@echo "$(GREEN)Development:$(RESET)"
	@echo "  make install      Install dependencies with uv"
	@echo "  make test         Run all tests"
	@echo "  make test-unit    Run unit tests only"
	@echo "  make lint         Run ruff linter"
	@echo "  make format       Format code with ruff"
	@echo "  make check        Run lint + format check + tests"
	@echo ""
	@echo "$(GREEN)Server:$(RESET)"
	@echo "  make serve        Start server locally (port 8080)"
	@echo "  make serve-dev    Start server with auto-reload"
	@echo ""
	@echo "$(GREEN)Docker:$(RESET)"
	@echo "  make docker-build Build Docker image"
	@echo "  make docker-run   Run server in Docker"
	@echo "  make docker-shell Shell into Docker container"
	@echo ""
	@echo "$(GREEN)Maintenance:$(RESET)"
	@echo "  make clean        Remove build artifacts"
	@echo ""

# =============================================================================
# DEVELOPMENT
# =============================================================================

## Install dependencies
install:
	@echo "$(CYAN)Installing dependencies...$(RESET)"
	uv sync --all-extras
	@echo "$(GREEN)Done!$(RESET)"

## Run all tests
test:
	@echo "$(CYAN)Running all tests...$(RESET)"
	$(PYTEST) tests/ -v

## Run unit tests only
test-unit:
	@echo "$(CYAN)Running unit tests...$(RESET)"
	$(PYTEST) tests/unit/ -v

## Run tests with coverage
test-cov:
	@echo "$(CYAN)Running tests with coverage...$(RESET)"
	$(PYTEST) tests/ -v --cov=ploston --cov-report=html --cov-report=term

## Run linter
lint:
	@echo "$(CYAN)Running linter...$(RESET)"
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

## Format code
format:
	@echo "$(CYAN)Formatting code...$(RESET)"
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

## Run all checks
check: lint test
	@echo "$(GREEN)All checks passed!$(RESET)"

# =============================================================================
# SERVER
# =============================================================================

## Start server locally
serve:
	@echo "$(CYAN)Starting Ploston server on port 8080...$(RESET)"
	uv run ploston-server --host 0.0.0.0 --port 8080

## Start server with auto-reload (for development)
serve-dev:
	@echo "$(CYAN)Starting Ploston server with auto-reload...$(RESET)"
	uv run ploston-server --host 0.0.0.0 --port 8080 --reload

# =============================================================================
# DOCKER
# =============================================================================

## Build Docker image
docker-build:
	@echo "$(CYAN)Building Docker image $(IMAGE_NAME):$(IMAGE_TAG)...$(RESET)"
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .
	@echo "$(GREEN)Build complete!$(RESET)"

## Run server in Docker
docker-run:
	@echo "$(CYAN)Running Ploston in Docker...$(RESET)"
	docker run --rm -p 8080:8080 -p 9090:9090 $(IMAGE_NAME):$(IMAGE_TAG)

## Shell into Docker container
docker-shell:
	@echo "$(CYAN)Starting shell in Docker container...$(RESET)"
	docker run --rm -it $(IMAGE_NAME):$(IMAGE_TAG) /bin/bash

## Run tests in Docker
docker-test:
	@echo "$(CYAN)Running tests in Docker...$(RESET)"
	docker run --rm $(IMAGE_NAME):$(IMAGE_TAG) uv run pytest tests/ -v

# =============================================================================
# MAINTENANCE
# =============================================================================

## Remove build artifacts
clean:
	@echo "$(CYAN)Cleaning build artifacts...$(RESET)"
	rm -rf build/ dist/ *.egg-info/
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)Clean!$(RESET)"

