"""
MCP HTTP Client Integration Tests for AEL.

These tests use the mcp_http_test_client utility to verify AEL's MCP server
functionality over HTTP transport with the internal configuration and native_tools.

Test IDs: MCIH-001 to MCIH-016
Priority: P1

Prerequisites:
- Agent submodule initialized (git submodule update --init)
- internal/ael-config.yaml exists
- AEL installed in virtualenv
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
INTERNAL_DIR = PROJECT_ROOT / "internal"
MCP_HTTP_TEST_CLIENT = INTERNAL_DIR / "mcp_http_test_client.py"
AEL_CONFIG = INTERNAL_DIR / "ael-config.yaml"


pytestmark = [
    pytest.mark.integration,
    pytest.mark.mcp_http_client,
]


def skip_if_no_config():
    """Skip if internal config not available."""
    if not AEL_CONFIG.exists():
        pytest.skip("internal/ael-config.yaml not found")


def skip_if_no_client():
    """Skip if MCP HTTP test client not available."""
    if not MCP_HTTP_TEST_CLIENT.exists():
        pytest.skip("internal/mcp_http_test_client.py not found")


class MCPHTTPClientResult:
    """Wrapper for subprocess result that combines stdout and stderr for assertions."""

    def __init__(self, result: subprocess.CompletedProcess):
        self._result = result
        self.returncode = result.returncode
        self.stdout = result.stdout
        self.stderr = result.stderr
        # Combined output for easier assertions
        self.output = result.stdout + result.stderr


def run_mcp_http_client(*args: str, timeout: int = 90, port: int = 8081) -> MCPHTTPClientResult:
    """Run the MCP HTTP test client with given arguments."""
    cmd = [
        sys.executable,
        str(MCP_HTTP_TEST_CLIENT),
        "-c", str(AEL_CONFIG),
        "--port", str(port),
        *args,
    ]
    env = os.environ.copy()
    # Use installed packages - no need to set PYTHONPATH if packages are installed

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=PROJECT_ROOT,
        env=env,
    )
    return MCPHTTPClientResult(result)


# =============================================================================
# Configuration Tests (MCIH-001 to MCIH-003)
# =============================================================================


class TestMCPHTTPConfiguration:
    """Tests for AEL MCP server configuration over HTTP."""

    def test_mcih_001_server_starts_successfully(self):
        """
        MCIH-001: Verify AEL MCP HTTP server starts and responds to initialize.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client("--list-tools", port=8091)

        assert result.returncode == 0, f"Failed: {result.stderr}"
        # Client logs go to stderr
        assert "Started AEL HTTP server" in result.output
        assert "Connected to:" in result.output

    def test_mcih_002_server_info_correct(self):
        """
        MCIH-002: Verify server info returned in initialize response.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client("--list-tools", port=8092)

        assert result.returncode == 0
        # Server info should include name and version (in stderr logs)
        assert "'name': 'ael'" in result.output or '"name": "ael"' in result.output

    def test_mcih_003_config_loads_native_tools(self):
        """
        MCIH-003: Verify native_tools MCP server is connected via HTTP.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client("--list-tools", port=8093)

        assert result.returncode == 0
        # Should have native tools
        assert "http_request" in result.stdout
        assert "fs_read" in result.stdout
        assert "fs_write" in result.stdout


# =============================================================================
# Tools Discovery Tests (MCIH-004 to MCIH-006)
# =============================================================================


class TestHTTPToolsDiscovery:
    """Tests for MCP tools/list functionality over HTTP."""

    def test_mcih_004_lists_native_tools(self):
        """
        MCIH-004: Verify native tools are discovered and listed via HTTP.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client("--list-tools", port=8094)

        assert result.returncode == 0

        # Core native tools should be present
        expected_tools = [
            "http_request",
            "fs_read",
            "fs_write",
            "fs_list",
            "network_ping",
            "python_exec",
        ]
        for tool in expected_tools:
            assert tool in result.stdout, f"Missing tool: {tool}"

    def test_mcih_005_lists_workflows_as_tools(self):
        """
        MCIH-005: Verify workflows are exposed as tools with workflow: prefix via HTTP.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client("--list-tools", port=8095)

        assert result.returncode == 0

        # Workflows should be prefixed
        assert "workflow:fetch-url" in result.stdout
        assert "workflow:file-operations" in result.stdout
        assert "workflow:python-exec-explicit" in result.stdout


    def test_mcih_006_tool_count_matches_expected(self):
        """
        MCIH-006: Verify expected number of tools are discovered via HTTP.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client("--list-tools", port=8096)

        assert result.returncode == 0
        # Should have ~30 native tools + 4 workflows = ~34 total
        assert "Available Tools" in result.stdout
        # Extract count from output like "Available Tools (34)"
        import re
        match = re.search(r"Available Tools \((\d+)\)", result.stdout)
        assert match, "Could not find tool count in output"
        count = int(match.group(1))
        assert count >= 30, f"Expected at least 30 tools, got {count}"


# =============================================================================
# Tool Call Tests (MCIH-007 to MCIH-009)
# =============================================================================


class TestHTTPToolCalls:
    """Tests for MCP tools/call functionality over HTTP."""

    def test_mcih_007_call_http_request_tool(self):
        """
        MCIH-007: Verify http_request tool can be called directly via HTTP.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client(
            "--call", "http_request",
            '{"url": "https://httpbin.org/get", "method": "GET"}',
            timeout=60,
            port=8097,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "Tool: http_request" in result.stdout
        # Should have successful response
        assert '"isError": false' in result.stdout or '"isError":false' in result.stdout

    def test_mcih_008_call_network_ping_tool(self):
        """
        MCIH-008: Verify network_ping tool works via HTTP.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client(
            "--call", "network_ping",
            '{"host": "localhost"}',
            timeout=60,
            port=8098,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "Tool: network_ping" in result.stdout

    def test_mcih_009_call_nonexistent_tool_fails(self):
        """
        MCIH-009: Verify calling nonexistent tool returns error via HTTP.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client(
            "--call", "nonexistent_tool_xyz",
            '{}',
            timeout=60,
            port=8099,
        )

        # Should fail with error
        assert result.returncode != 0 or "Error" in result.stdout or "error" in result.stdout.lower()


# =============================================================================
# Workflow Execution Tests (MCIH-010 to MCIH-012)
# =============================================================================


class TestHTTPWorkflowExecution:
    """Tests for workflow execution via MCP over HTTP."""

    def test_mcih_010_execute_fetch_url_workflow(self):
        """
        MCIH-010: Verify fetch-url workflow executes successfully via HTTP.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client(
            "--workflow", "fetch-url",
            '{"url": "https://httpbin.org/get"}',
            timeout=90,
            port=8100,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "Workflow: fetch-url" in result.stdout
        assert '"isError": false' in result.stdout or '"isError":false' in result.stdout

    def test_mcih_011_execute_file_operations_workflow(self):
        """
        MCIH-011: Verify file-operations workflow executes successfully via HTTP.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client(
            "--workflow", "file-operations",
            '{"filename": "test-mcp-http-integration.txt", "content": "MCP HTTP test content"}',
            timeout=60,
            port=8101,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "Workflow: file-operations" in result.stdout

        # Cleanup test file
        test_file = PROJECT_ROOT / "test-mcp-http-integration.txt"
        if test_file.exists():
            test_file.unlink()

    def test_mcih_012_execute_python_exec_workflow(self):
        """
        MCIH-012: Verify python-exec-explicit workflow executes successfully via HTTP.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client(
            "--workflow", "python-exec-explicit",
            '{"numbers": [1, 2, 3, 4, 5]}',
            timeout=60,
            port=8102,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "Workflow: python-exec-explicit" in result.stdout
        assert '"isError": false' in result.stdout or '"isError":false' in result.stdout


# =============================================================================
# Error Handling Tests (MCIH-013 to MCIH-015)
# =============================================================================


class TestHTTPErrorHandling:
    """Tests for error handling in MCP HTTP communication."""

    def test_mcih_013_invalid_json_arguments(self):
        """
        MCIH-013: Verify invalid JSON arguments are handled gracefully via HTTP.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client(
            "--call", "http_request",
            'not valid json',
            timeout=60,
            port=8103,
        )

        # Should fail with JSON error
        assert result.returncode != 0
        assert "JSON" in result.stderr or "json" in result.stderr.lower()

    def test_mcih_014_missing_required_workflow_input(self):
        """
        MCIH-014: Verify missing required inputs are reported via HTTP.
        """
        skip_if_no_config()
        skip_if_no_client()

        # fetch-url requires 'url' input
        result = run_mcp_http_client(
            "--workflow", "fetch-url",
            '{}',  # Missing required 'url'
            timeout=60,
            port=8104,
        )

        # Should fail or return error
        # The workflow may fail at execution time
        assert result.returncode != 0 or "error" in result.stdout.lower()

    def test_mcih_015_workflow_not_found(self):
        """
        MCIH-015: Verify nonexistent workflow returns error via HTTP.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_http_client(
            "--workflow", "nonexistent-workflow-xyz",
            '{}',
            timeout=60,
            port=8105,
        )

        # Should fail
        assert result.returncode != 0 or "error" in result.stdout.lower()