"""
Pytest fixtures for Docker Compose integration tests.

These tests run against the AEL instance running in docker-compose.
"""

import os
from typing import Any

import pytest
import requests


# Default docker-compose endpoint
DEFAULT_DOCKER_URL = "http://localhost:8082"


def get_docker_url() -> str:
    """Get the docker-compose AEL URL from environment or default."""
    return os.environ.get("PLOSTON_DOCKER_URL", os.environ.get("AEL_DOCKER_URL", DEFAULT_DOCKER_URL))


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
        return self.send("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "docker-test-client", "version": "1.0.0"},
            "capabilities": {},
        })

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


@pytest.fixture(scope="module")
def docker_url() -> str:
    """Get the docker-compose AEL URL."""
    return get_docker_url()


@pytest.fixture(scope="module")
def docker_client(docker_url: str) -> DockerMCPClient:
    """Create a docker-compose MCP client."""
    return DockerMCPClient(docker_url)


@pytest.fixture(scope="module")
def docker_available(docker_url: str) -> bool:
    """Check if docker-compose AEL is available."""
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
        "markers", "requires_running_mode: mark test as requiring running mode (not configuration mode)"
    )


@pytest.fixture(autouse=True)
def skip_if_requires_running_mode(request, running_mode_available):
    """Skip tests marked with requires_running_mode if not in running mode."""
    if request.node.get_closest_marker("requires_running_mode"):
        if not running_mode_available:
            pytest.skip("Test requires running mode (server is in configuration mode)")
