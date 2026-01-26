"""
Pytest fixtures for Docker Compose integration tests.

These tests run against the AEL instance running in docker-compose.
The docker-compose environment is automatically started and stopped as part of the test session.
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Generator

import pytest
import requests

# Default docker-compose endpoint
DEFAULT_DOCKER_URL = "http://localhost:8082"

# Path to docker-compose.test.yml relative to repo root
DOCKER_COMPOSE_FILE = "docker-compose.test.yml"


def get_repo_root() -> Path:
    """Get the repository root directory."""
    # Navigate up from this file to find the repo root
    current = Path(__file__).resolve()
    # Go up: conftest.py -> docker -> integration -> tests -> ploston -> packages -> repo_root
    for _ in range(6):
        current = current.parent
    return current


def get_docker_url() -> str:
    """Get the docker-compose AEL URL from environment or default."""
    return os.environ.get(
        "PLOSTON_DOCKER_URL", os.environ.get("AEL_DOCKER_URL", DEFAULT_DOCKER_URL)
    )


class DockerMCPClient:
    """MCP client for testing against docker-compose AEL deployment."""

    def __init__(self, base_url: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._msg_id = 0
        self._session_id: str | None = None

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def health_check(self) -> dict[str, Any]:
        """Check if AEL is healthy."""
        response = requests.get(f"{self.base_url}/health", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a JSON-RPC request via HTTP."""
        msg_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
        }
        if params:
            request["params"] = params

        headers = {"Content-Type": "application/json"}
        if self._session_id:
            headers["X-MCP-Session-ID"] = self._session_id

        response = requests.post(
            f"{self.base_url}/mcp",
            json=request,
            headers=headers,
            timeout=self.timeout,
        )

        if response.status_code == 204:
            return {"jsonrpc": "2.0", "id": msg_id, "result": None}

        if "X-MCP-Session-ID" in response.headers:
            self._session_id = response.headers["X-MCP-Session-ID"]

        return response.json()

    def initialize(self) -> dict[str, Any]:
        """Send initialize request."""
        return self.send(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "docker-test-client", "version": "1.0.0"},
                "capabilities": {},
            },
        )

    def list_tools(self) -> list[dict[str, Any]]:
        """List available tools."""
        response = self.send("tools/list", {})
        if "error" in response:
            raise RuntimeError(f"Error: {response['error']}")
        return response.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool."""
        response = self.send("tools/call", {"name": name, "arguments": arguments})
        if "error" in response:
            raise RuntimeError(f"Error: {response['error']}")
        return response.get("result", {})

    def ping(self) -> bool:
        """Ping the server."""
        response = self.send("ping", {})
        return "result" in response


def _is_docker_available() -> bool:
    """Check if Docker is available on the system."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _wait_for_healthy(url: str, timeout: int = 60) -> bool:
    """Wait for the service to become healthy."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{url}/health", timeout=5)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    return False


@pytest.fixture(scope="module")
def docker_compose_up() -> Generator[bool, None, None]:
    """
    Start docker-compose environment for tests and tear it down after.

    This fixture automatically:
    1. Checks if Docker is available
    2. Builds and starts the docker-compose.test.yml services
    3. Waits for the service to be healthy
    4. Yields control to tests
    5. Tears down the environment after tests complete

    If Docker is not available, yields False and tests should skip.
    """
    if not _is_docker_available():
        print("Docker is not available, skipping docker-compose setup")
        yield False
        return

    repo_root = get_repo_root()
    compose_file = repo_root / DOCKER_COMPOSE_FILE

    if not compose_file.exists():
        print(f"Docker compose file not found: {compose_file}")
        yield False
        return

    docker_url = get_docker_url()

    # Check if already running (e.g., started manually)
    try:
        response = requests.get(f"{docker_url}/health", timeout=5)
        if response.status_code == 200:
            print(f"Docker environment already running at {docker_url}")
            yield True
            return
    except requests.exceptions.RequestException:
        pass

    print(f"Starting docker-compose environment from {compose_file}...")

    try:
        # Build the images first
        build_result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "build"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes for build
        )
        if build_result.returncode != 0:
            print(f"Docker build failed: {build_result.stderr}")
            yield False
            return

        # Start the services
        up_result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "up", "-d"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if up_result.returncode != 0:
            print(f"Docker compose up failed: {up_result.stderr}")
            yield False
            return

        # Wait for healthy
        print(f"Waiting for service to be healthy at {docker_url}...")
        if not _wait_for_healthy(docker_url, timeout=60):
            print("Service did not become healthy in time")
            # Try to get logs for debugging
            logs_result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "logs"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            print(f"Container logs:\n{logs_result.stdout}\n{logs_result.stderr}")
            yield False
            return

        print("Docker environment is ready!")
        yield True

    finally:
        # Tear down the environment
        print("Tearing down docker-compose environment...")
        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "down", "-v"],
            cwd=str(repo_root),
            capture_output=True,
            timeout=60,
        )


@pytest.fixture(scope="module")
def docker_url(docker_compose_up: bool) -> str:
    """Get the docker-compose AEL URL."""
    return get_docker_url()


@pytest.fixture(scope="module")
def docker_client(docker_url: str) -> DockerMCPClient:
    """Create a docker-compose MCP client."""
    return DockerMCPClient(docker_url)


@pytest.fixture(scope="module")
def docker_available(docker_compose_up: bool, docker_url: str) -> bool:
    """Check if docker-compose AEL is available."""
    if not docker_compose_up:
        return False
    try:
        response = requests.get(f"{docker_url}/health", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


@pytest.fixture(scope="module")
def running_mode_available(docker_client: DockerMCPClient, docker_available: bool) -> bool:
    """Check if docker-compose AEL is in running mode (not configuration mode)."""
    if not docker_available:
        return False
    try:
        docker_client.initialize()
        tools = docker_client.list_tools()
        tool_names = [t.get("name") for t in tools]
        # In configuration mode, only config tools are available
        # In running mode, python_exec should be available
        return "python_exec" in tool_names
    except Exception:
        return False


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "requires_running_mode: mark test as requiring running mode (not configuration mode)",
    )


@pytest.fixture(autouse=True)
def skip_if_requires_running_mode(request, running_mode_available):
    """Skip tests marked with requires_running_mode if not in running mode."""
    if request.node.get_closest_marker("requires_running_mode"):
        if not running_mode_available:
            pytest.skip("Test requires running mode (server is in configuration mode)")
