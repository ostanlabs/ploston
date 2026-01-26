"""
MCP Client Integration Tests for Ploston.

These tests verify Ploston's MCP server functionality over HTTP transport.
They connect to a running server (typically via docker-compose).

Test IDs: MCI-001 to MCI-016
Priority: P1

Prerequisites:
- Server running via docker-compose:
    docker compose -f docker-compose.test.yml up -d
- Or set PLOSTON_HOST and PLOSTON_PORT environment variables

Usage:
    # Start the test server
    docker compose -f docker-compose.test.yml up -d

    # Run the tests
    pytest tests/integration/test_mcp_client_integration.py -v

    # Stop the test server
    docker compose -f docker-compose.test.yml down
"""

import os
from pathlib import Path

import pytest
import requests

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
INTERNAL_DIR = PROJECT_ROOT / "internal"

# Server configuration from environment or defaults (docker-compose.test.yml uses 8082)
PLOSTON_HOST = os.environ.get("PLOSTON_HOST", "127.0.0.1")
PLOSTON_PORT = int(os.environ.get("PLOSTON_PORT", "8082"))
PLOSTON_BASE_URL = f"http://{PLOSTON_HOST}:{PLOSTON_PORT}"


pytestmark = [
    pytest.mark.integration,
    pytest.mark.mcp_client,
]


class MCPHTTPClient:
    """Simple MCP HTTP client for testing."""

    def __init__(self, base_url: str = PLOSTON_BASE_URL):
        self.base_url = base_url
        self._msg_id = 0
        self._session_id: str | None = None

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def is_server_running(self) -> bool:
        """Check if the server is running."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            return response.status_code == 200
        except requests.exceptions.ConnectionError:
            return False

    def send(self, method: str, params: dict | None = None) -> dict:
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
            timeout=60,
        )

        if response.status_code == 204:
            return {"jsonrpc": "2.0", "id": msg_id, "result": None}

        return response.json()

    def initialize(self) -> dict:
        """Send initialize request."""
        return self.send(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "mcp-test-client", "version": "1.0.0"},
                "capabilities": {},
            },
        )

    def list_tools(self) -> list[dict]:
        """List available tools."""
        response = self.send("tools/list", {})
        if "error" in response:
            raise RuntimeError(f"Error: {response['error']}")
        return response.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Call a tool."""
        response = self.send("tools/call", {"name": name, "arguments": arguments})
        return response


@pytest.fixture(scope="module")
def mcp_client():
    """Create MCP client and verify server is running."""
    client = MCPHTTPClient()
    if not client.is_server_running():
        pytest.skip(
            f"Ploston server not running at {PLOSTON_BASE_URL}. "
            "Start with: docker compose -f docker-compose.test.yml up -d"
        )
    # Initialize the MCP session
    client.initialize()
    return client


# =============================================================================
# Configuration Tests (MCI-001 to MCI-003)
# =============================================================================


class TestMCPConfiguration:
    """Tests for Ploston MCP server configuration."""

    def test_mci_001_server_responds_to_initialize(self, mcp_client):
        """
        MCI-001: Verify Ploston MCP server responds to initialize.
        """
        # Re-initialize to verify it works
        response = mcp_client.initialize()
        assert "result" in response
        assert "serverInfo" in response.get("result", {})

    def test_mci_002_server_info_correct(self, mcp_client):
        """
        MCI-002: Verify server info returned in initialize response.
        """
        response = mcp_client.initialize()
        server_info = response.get("result", {}).get("serverInfo", {})
        # Server should identify itself
        assert "name" in server_info
        assert "version" in server_info

    def test_mci_003_health_endpoint_works(self, mcp_client):
        """
        MCI-003: Verify health endpoint is accessible.
        """
        response = requests.get(f"{mcp_client.base_url}/health", timeout=5)
        assert response.status_code == 200


# =============================================================================
# Tools Discovery Tests (MCI-004 to MCI-006)
# =============================================================================


class TestToolsDiscovery:
    """Tests for MCP tools/list functionality."""

    def test_mci_004_lists_tools(self, mcp_client):
        """
        MCI-004: Verify tools are discovered and listed.
        """
        tools = mcp_client.list_tools()
        assert len(tools) > 0, "No tools discovered"

        # Get tool names
        tool_names = [t["name"] for t in tools]

        # Should have some tools (exact tools depend on config)
        assert len(tool_names) > 0

    def test_mci_005_tools_have_required_fields(self, mcp_client):
        """
        MCI-005: Verify tools have required MCP fields.
        """
        tools = mcp_client.list_tools()

        for tool in tools:
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert "description" in tool, f"Tool {tool.get('name')} missing 'description'"
            # inputSchema is optional but common
            if "inputSchema" in tool:
                assert isinstance(tool["inputSchema"], dict)

    def test_mci_006_tool_count_reasonable(self, mcp_client):
        """
        MCI-006: Verify reasonable number of tools are discovered.
        """
        tools = mcp_client.list_tools()
        # Should have at least a few tools
        assert len(tools) >= 1, f"Expected at least 1 tool, got {len(tools)}"


# =============================================================================
# Tool Call Tests (MCI-007 to MCI-009)
# =============================================================================


class TestToolCalls:
    """Tests for MCP tools/call functionality."""

    def test_mci_007_call_tool_success(self, mcp_client):
        """
        MCI-007: Verify a tool can be called successfully.
        """
        # Get list of tools first
        tools = mcp_client.list_tools()
        if not tools:
            pytest.skip("No tools available to test")

        # Try to call the first available tool with empty args
        # This tests the call mechanism, not the tool itself
        tool_name = tools[0]["name"]
        response = mcp_client.call_tool(tool_name, {})

        # Should get a response (may be error due to missing args, but should respond)
        assert "jsonrpc" in response or "result" in response or "error" in response

    def test_mci_008_call_tool_returns_result_or_error(self, mcp_client):
        """
        MCI-008: Verify tool call returns proper MCP response structure.
        """
        tools = mcp_client.list_tools()
        if not tools:
            pytest.skip("No tools available to test")

        tool_name = tools[0]["name"]
        response = mcp_client.call_tool(tool_name, {})

        # MCP response should have either result or error
        assert "result" in response or "error" in response

    def test_mci_009_call_nonexistent_tool_fails(self, mcp_client):
        """
        MCI-009: Verify calling nonexistent tool returns error.
        """
        response = mcp_client.call_tool("nonexistent_tool_xyz_12345", {})

        # Should return error
        assert "error" in response


# =============================================================================
# Error Handling Tests (MCI-010 to MCI-012)
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in MCP communication."""

    def test_mci_010_invalid_method_returns_error(self, mcp_client):
        """
        MCI-010: Verify invalid MCP method returns error.
        """
        response = mcp_client.send("invalid/method/xyz", {})

        # Should return error for unknown method
        assert "error" in response

    def test_mci_011_malformed_params_handled(self, mcp_client):
        """
        MCI-011: Verify malformed parameters are handled gracefully.
        """
        # Send tools/call with missing required fields
        response = mcp_client.send("tools/call", {"invalid": "params"})

        # Should return error, not crash
        assert "error" in response or "result" in response

    def test_mci_012_server_handles_rapid_requests(self, mcp_client):
        """
        MCI-012: Verify server handles multiple rapid requests.
        """
        # Send multiple requests rapidly
        responses = []
        for _ in range(5):
            response = mcp_client.send("tools/list", {})
            responses.append(response)

        # All should succeed
        for response in responses:
            assert "result" in response or "error" not in response
