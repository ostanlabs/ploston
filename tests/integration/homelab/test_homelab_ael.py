"""
Homelab Ploston Integration Tests.

These tests verify Ploston functionality against the homelab K3s deployment.

Test IDs: HL-001 to HL-020
Priority: P1

Prerequisites:
- Ploston deployed to homelab K3s cluster
- Network access to ploston.ostanlabs.homelab (or PLOSTON_DEV_URL env var)

Note on Configuration Mode:
Ploston starts in "configuration mode" when no valid config with MCP servers is provided.
In configuration mode, only config tools (ael:config_*) are available.
To enable full tool/workflow execution, Ploston needs to be configured with MCP servers
and transitioned to "running mode" via the ael:config_done tool.

Currently, Ploston's MCP client only supports stdio transport, not HTTP. Since native-tools
runs as a separate pod with HTTP transport, Ploston cannot connect to it yet.
Tests that require running mode are marked with @pytest.mark.requires_running_mode.

Usage:
    # Run all dev/homelab tests using the dev config
    pytest -c pytest-dev.ini

    # Run only tests that work in configuration mode
    pytest -c pytest-dev.ini -m "not requires_running_mode"

    # Run with custom URL
    PLOSTON_DEV_URL=http://192.168.68.200:8082 pytest -c pytest-dev.ini

    # Run specific test
    pytest -c pytest-dev.ini tests/integration/homelab/test_homelab_ael.py::TestHomelabHealth
"""

import pytest

from .conftest import HomelabMCPClient, skip_if_homelab_unavailable


pytestmark = [
    pytest.mark.integration,
    pytest.mark.homelab,
]


# =============================================================================
# Health Check Tests (HL-001 to HL-003)
# =============================================================================


class TestHomelabHealth:
    """Tests for AEL health and availability on homelab."""

    def test_hl_001_health_endpoint_responds(self, homelab_available: bool, homelab_client: HomelabMCPClient):
        """HL-001: Verify AEL health endpoint responds."""
        skip_if_homelab_unavailable(homelab_available)

        result = homelab_client.health_check()
        assert result.get("status") == "ok"

    def test_hl_002_mcp_initialize(self, homelab_available: bool, homelab_client: HomelabMCPClient):
        """HL-002: Verify MCP initialize request succeeds."""
        skip_if_homelab_unavailable(homelab_available)

        result = homelab_client.initialize()
        assert "result" in result
        assert "serverInfo" in result["result"]
        assert result["result"]["serverInfo"]["name"] == "ael"

    def test_hl_003_mcp_ping(self, homelab_available: bool, homelab_client: HomelabMCPClient):
        """HL-003: Verify MCP ping request succeeds."""
        skip_if_homelab_unavailable(homelab_available)

        # Initialize first
        homelab_client.initialize()
        result = homelab_client.ping()
        assert result is True


# =============================================================================
# Running Mode Tests (HL-004 to HL-007)
# =============================================================================


class TestHomelabRunningMode:
    """Tests for AEL running mode on homelab.

    AEL in homelab is deployed with a config file, so it starts in running mode.
    In this mode, python_exec and workflows are available.
    """

    def test_hl_004_list_tools_in_running_mode(self, homelab_available: bool, homelab_client: HomelabMCPClient):
        """HL-004: Verify tools are available in running mode."""
        skip_if_homelab_unavailable(homelab_available)

        homelab_client.initialize()
        tools = homelab_client.list_tools()
        tool_names = [t["name"] for t in tools]

        # In running mode, python_exec should be available
        assert "python_exec" in tool_names, "python_exec should be available in running mode"

    def test_hl_005_python_exec_available(self, homelab_available: bool, homelab_client: HomelabMCPClient):
        """HL-005: Verify python_exec tool is available."""
        skip_if_homelab_unavailable(homelab_available)

        homelab_client.initialize()
        tools = homelab_client.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "python_exec" in tool_names

    def test_hl_006_workflow_available(self, homelab_available: bool, homelab_client: HomelabMCPClient):
        """HL-006: Verify at least one workflow is available."""
        skip_if_homelab_unavailable(homelab_available)

        homelab_client.initialize()
        tools = homelab_client.list_tools()
        workflow_tools = [t for t in tools if t["name"].startswith("workflow:")]

        assert len(workflow_tools) >= 1, "At least one workflow should be available"

    def test_hl_007_tool_count_in_running_mode(self, homelab_available: bool, homelab_client: HomelabMCPClient):
        """HL-007: Verify expected number of tools in running mode."""
        skip_if_homelab_unavailable(homelab_available)

        homelab_client.initialize()
        tools = homelab_client.list_tools()

        # In running mode, should have at least python_exec and one workflow
        assert len(tools) >= 2, f"Expected at least 2 tools, got {len(tools)}"


# =============================================================================
# Tool Execution Tests (HL-008 to HL-012) - Requires Running Mode
# =============================================================================


@pytest.mark.requires_running_mode
class TestHomelabToolExecution:
    """Tests for tool execution on homelab.

    These tests require AEL to be in running mode with MCP servers connected.
    """

    def test_hl_008_call_http_request(self, homelab_available: bool, homelab_client_running: HomelabMCPClient):
        """HL-008: Verify http_request tool works via native-tools MCP server.
        """
        skip_if_homelab_unavailable(homelab_available)

        result = homelab_client_running.call_tool("http_request", {
            "url": "https://httpbin.org/get",
            "method": "GET",
        })

        assert "content" in result
        assert result.get("isError") is False

    def test_hl_009_call_python_exec(self, homelab_available: bool, homelab_client_running: HomelabMCPClient):
        """HL-009: Verify python_exec tool works."""
        skip_if_homelab_unavailable(homelab_available)

        result = homelab_client_running.call_tool("python_exec", {
            "code": "result = sum([1, 2, 3, 4, 5])",
        })

        assert "content" in result
        # Result should contain 15
        content = str(result.get("content", []))
        assert "15" in content or result.get("isError") is False

    def test_hl_010_call_nonexistent_tool_fails(self, homelab_available: bool, homelab_client: HomelabMCPClient):
        """HL-010: Verify calling nonexistent tool returns error."""
        skip_if_homelab_unavailable(homelab_available)

        homelab_client.initialize()
        with pytest.raises(RuntimeError, match="[Ee]rror"):
            homelab_client.call_tool("nonexistent_tool_xyz", {})


# =============================================================================
# Workflow Execution Tests (HL-013 to HL-017) - Requires Running Mode
# =============================================================================


@pytest.mark.requires_running_mode
class TestHomelabWorkflowExecution:
    """Tests for workflow execution on homelab.

    These tests require AEL to be in running mode with MCP servers connected.
    """

    def test_hl_013_execute_fetch_url_workflow(self, homelab_available: bool, homelab_client_running: HomelabMCPClient):
        """HL-013: Verify fetch-url workflow executes using http_request from native-tools.
        """
        skip_if_homelab_unavailable(homelab_available)

        result = homelab_client_running.call_tool("workflow:fetch-url", {
            "url": "https://httpbin.org/get",
        })

        assert "content" in result
        assert result.get("isError") is False

    def test_hl_014_execute_python_exec_workflow(self, homelab_available: bool, homelab_client_running: HomelabMCPClient):
        """HL-014: Verify python-exec-explicit workflow executes."""
        skip_if_homelab_unavailable(homelab_available)

        result = homelab_client_running.call_tool("workflow:python-exec-explicit", {
            "numbers": [1, 2, 3, 4, 5],
        })

        assert "content" in result
        assert result.get("isError") is False

    def test_hl_015_workflow_not_found(self, homelab_available: bool, homelab_client_running: HomelabMCPClient):
        """HL-015: Verify nonexistent workflow returns error."""
        skip_if_homelab_unavailable(homelab_available)

        with pytest.raises(RuntimeError, match="[Ee]rror"):
            homelab_client_running.call_tool("workflow:nonexistent-workflow-xyz", {})


# =============================================================================
# Performance Tests (HL-018 to HL-020)
# =============================================================================


class TestHomelabPerformance:
    """Basic performance tests for homelab deployment."""

    def test_hl_018_health_response_time(self, homelab_available: bool, homelab_url: str):
        """HL-018: Verify health endpoint responds within 1 second."""
        import time
        import requests

        skip_if_homelab_unavailable(homelab_available)

        start = time.time()
        response = requests.get(f"{homelab_url}/health", timeout=5)
        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 1.0, f"Health check took {elapsed:.2f}s, expected < 1s"

    def test_hl_019_tool_list_response_time(self, homelab_available: bool, homelab_client: HomelabMCPClient):
        """HL-019: Verify tools/list responds within 5 seconds."""
        import time

        skip_if_homelab_unavailable(homelab_available)

        homelab_client.initialize()

        start = time.time()
        tools = homelab_client.list_tools()
        elapsed = time.time() - start

        assert len(tools) > 0
        assert elapsed < 5.0, f"Tools list took {elapsed:.2f}s, expected < 5s"

    @pytest.mark.requires_running_mode
    def test_hl_020_simple_tool_execution_time(self, homelab_available: bool, homelab_client_running: HomelabMCPClient):
        """HL-020: Verify simple tool execution within 10 seconds."""
        import time

        skip_if_homelab_unavailable(homelab_available)

        start = time.time()
        result = homelab_client_running.call_tool("python_exec", {
            "code": "result = 2 + 2",
        })
        elapsed = time.time() - start

        assert result.get("isError") is False
        assert elapsed < 10.0, f"Tool execution took {elapsed:.2f}s, expected < 10s"
