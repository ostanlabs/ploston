"""
Pytest fixtures for homelab integration tests.

These tests run against the AEL instance deployed on the homelab K3s cluster.
"""

import os
from typing import Any

import pytest
import requests

# Default homelab Ploston endpoint
DEFAULT_HOMELAB_URL = "http://ploston.ostanlabs.homelab"


def get_homelab_url() -> str:
    """Get the homelab Ploston URL from environment or default."""
    return os.environ.get("PLOSTON_DEV_URL", os.environ.get("AEL_HOMELAB_URL", DEFAULT_HOMELAB_URL))


class HomelabMCPClient:
    """MCP client for testing against homelab AEL deployment."""

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

        # Store session ID from response if present
        if "X-MCP-Session-ID" in response.headers:
            self._session_id = response.headers["X-MCP-Session-ID"]

        return response.json()

    def initialize(self) -> dict[str, Any]:
        """Send initialize request."""
        return self.send("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "homelab-test-client", "version": "1.0.0"},
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

    def config_done(self) -> dict[str, Any]:
        """Call config_done to transition from config mode to running mode."""
        return self.call_tool("ael:config_done", {})

    def is_in_running_mode(self) -> bool:
        """Check if AEL is in running mode by looking at available tools."""
        tools = self.list_tools()
        tool_names = [t.get("name") for t in tools]
        # In config mode, only config_* tools are available
        # In running mode, python_exec and other tools are available
        return "python_exec" in tool_names


@pytest.fixture(scope="module")
def homelab_url() -> str:
    """Get the homelab AEL URL."""
    return get_homelab_url()


@pytest.fixture(scope="module")
def homelab_client(homelab_url: str) -> HomelabMCPClient:
    """Create a homelab MCP client."""
    return HomelabMCPClient(homelab_url)


@pytest.fixture(scope="module")
def homelab_available(homelab_url: str) -> bool:
    """Check if homelab AEL is available."""
    try:
        response = requests.get(f"{homelab_url}/health", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def skip_if_homelab_unavailable(homelab_available: bool):
    """Skip test if homelab is not available."""
    if not homelab_available:
        pytest.skip(f"Homelab AEL not available at {get_homelab_url()}")


@pytest.fixture(scope="module")
def homelab_client_running(homelab_client: HomelabMCPClient) -> HomelabMCPClient:
    """
    Get a homelab client that is in running mode.

    This fixture initializes the client and calls config_done if needed
    to transition from config mode to running mode.
    """
    # Initialize first
    homelab_client.initialize()

    # Check if already in running mode
    if not homelab_client.is_in_running_mode():
        # Call config_done to transition to running mode
        homelab_client.config_done()

    return homelab_client

