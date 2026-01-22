"""
MCP Client Integration Tests for AEL.

These tests use the mcp_test_client utility to verify AEL's MCP server
functionality with the internal configuration and native_tools.

Test IDs: MCI-001 to MCI-016
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
MCP_TEST_CLIENT = INTERNAL_DIR / "mcp_test_client.py"
AEL_CONFIG = INTERNAL_DIR / "ael-config.yaml"


pytestmark = [
    pytest.mark.integration,
    pytest.mark.mcp_client,
]


def skip_if_no_config():
    """Skip if internal config not available."""
    if not AEL_CONFIG.exists():
        pytest.skip("internal/ael-config.yaml not found")


def skip_if_no_client():
    """Skip if MCP test client not available."""
    if not MCP_TEST_CLIENT.exists():
        pytest.skip("internal/mcp_test_client.py not found")


class MCPClientResult:
    """Wrapper for subprocess result that combines stdout and stderr for assertions."""

    def __init__(self, result: subprocess.CompletedProcess):
        self._result = result
        self.returncode = result.returncode
        self.stdout = result.stdout
        self.stderr = result.stderr
        # Combined output for easier assertions
        self.output = result.stdout + result.stderr


def run_mcp_client(*args: str, timeout: int = 60) -> MCPClientResult:
    """Run the MCP test client with given arguments."""
    cmd = [
        sys.executable,
        str(MCP_TEST_CLIENT),
        "-c", str(AEL_CONFIG),
        *args,
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=PROJECT_ROOT,
        env=env,
    )
    return MCPClientResult(result)


# =============================================================================
# Configuration Tests (MCI-001 to MCI-003)
# =============================================================================


class TestMCPConfiguration:
    """Tests for AEL MCP server configuration."""

    def test_mci_001_server_starts_successfully(self):
        """
        MCI-001: Verify AEL MCP server starts and responds to initialize.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client("--list-tools")

        assert result.returncode == 0, f"Failed: {result.stderr}"
        # Client logs go to stderr
        assert "Started AEL" in result.output
        assert "Connected to:" in result.output

    def test_mci_002_server_info_correct(self):
        """
        MCI-002: Verify server info returned in initialize response.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client("--list-tools")

        assert result.returncode == 0
        # Server info should include name and version (in stderr logs)
        assert "'name': 'ael'" in result.output or '"name": "ael"' in result.output

    def test_mci_003_config_loads_native_tools(self):
        """
        MCI-003: Verify native_tools MCP server is connected.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client("--list-tools")
        
        assert result.returncode == 0
        # Should have native tools
        assert "http_request" in result.stdout
        assert "fs_read" in result.stdout
        assert "fs_write" in result.stdout


# =============================================================================
# Tools Discovery Tests (MCI-004 to MCI-006)
# =============================================================================


class TestToolsDiscovery:
    """Tests for MCP tools/list functionality."""

    def test_mci_004_lists_native_tools(self):
        """
        MCI-004: Verify native tools are discovered and listed.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client("--list-tools")
        
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

    def test_mci_005_lists_workflows_as_tools(self):
        """
        MCI-005: Verify workflows are exposed as tools with workflow: prefix.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client("--list-tools")
        
        assert result.returncode == 0
        
        # Workflows should be prefixed
        assert "workflow:fetch-url" in result.stdout
        assert "workflow:file-operations" in result.stdout
        assert "workflow:python-exec-explicit" in result.stdout

    def test_mci_006_tool_count_matches_expected(self):
        """
        MCI-006: Verify expected number of tools are discovered.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client("--list-tools")

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
# Tool Call Tests (MCI-007 to MCI-009)
# =============================================================================


class TestToolCalls:
    """Tests for MCP tools/call functionality."""

    def test_mci_007_call_http_request_tool(self):
        """
        MCI-007: Verify http_request tool can be called directly.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client(
            "--call", "http_request",
            '{"url": "https://httpbin.org/get", "method": "GET"}',
            timeout=30,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "Tool: http_request" in result.stdout
        # Should have successful response
        assert '"isError": false' in result.stdout or '"isError":false' in result.stdout

    def test_mci_008_call_network_ping_tool(self):
        """
        MCI-008: Verify network_ping tool works.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client(
            "--call", "network_ping",
            '{"host": "localhost"}',
            timeout=30,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "Tool: network_ping" in result.stdout

    def test_mci_009_call_nonexistent_tool_fails(self):
        """
        MCI-009: Verify calling nonexistent tool returns error.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client(
            "--call", "nonexistent_tool_xyz",
            '{}',
            timeout=30,
        )

        # Should fail with error
        assert result.returncode != 0 or "Error" in result.stdout or "error" in result.stdout.lower()


# =============================================================================
# Workflow Execution Tests (MCI-010 to MCI-012)
# =============================================================================


class TestWorkflowExecution:
    """Tests for workflow execution via MCP."""

    def test_mci_010_execute_fetch_url_workflow(self):
        """
        MCI-010: Verify fetch-url workflow executes successfully.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client(
            "--workflow", "fetch-url",
            '{"url": "https://httpbin.org/get"}',
            timeout=60,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "Workflow: fetch-url" in result.stdout
        assert '"isError": false' in result.stdout or '"isError":false' in result.stdout

    def test_mci_011_execute_file_operations_workflow(self):
        """
        MCI-011: Verify file-operations workflow executes successfully.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client(
            "--workflow", "file-operations",
            '{"filename": "test-mcp-integration.txt", "content": "MCP test content"}',
            timeout=30,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "Workflow: file-operations" in result.stdout

        # Cleanup test file
        test_file = PROJECT_ROOT / "test-mcp-integration.txt"
        if test_file.exists():
            test_file.unlink()

    def test_mci_012_execute_python_exec_workflow(self):
        """
        MCI-012: Verify python-exec-explicit workflow executes successfully.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client(
            "--workflow", "python-exec-explicit",
            '{"numbers": [1, 2, 3, 4, 5]}',
            timeout=30,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "Workflow: python-exec-explicit" in result.stdout
        assert '"isError": false' in result.stdout or '"isError":false' in result.stdout

    @pytest.mark.skipif(
        os.environ.get("SKIP_KAFKA_TESTS", "").lower() in ("1", "true", "yes"),
        reason="Kafka tests skipped via SKIP_KAFKA_TESTS env var"
    )
    def test_mci_016_execute_fetch_and_publish_workflow(self):
        """
        MCI-016: Verify fetch-and-publish workflow executes successfully.

        This test requires Kafka to be running on localhost:29092.
        Set SKIP_KAFKA_TESTS=1 to skip this test if Kafka is not available.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client(
            "--workflow", "fetch-and-publish",
            '{"url": "https://httpbin.org/get", "topic": "test-events"}',
            timeout=60,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "Workflow: fetch-and-publish" in result.stdout
        # Check for success - either no error or successful publish
        output = result.stdout
        if '"isError": true' in output or '"isError":true' in output:
            # If there's an error, it should be about Kafka not being available
            assert "Kafka" in output, f"Unexpected error: {output}"
        else:
            # Success case - should have published message
            assert "published" in output.lower() or '"isError": false' in output


# =============================================================================
# Error Handling Tests (MCI-013 to MCI-015)
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in MCP communication."""

    def test_mci_013_invalid_json_arguments(self):
        """
        MCI-013: Verify invalid JSON arguments are handled gracefully.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client(
            "--call", "http_request",
            'not valid json',
            timeout=30,
        )

        # Should fail with JSON error
        assert result.returncode != 0
        assert "JSON" in result.stderr or "json" in result.stderr.lower()

    def test_mci_014_missing_required_workflow_input(self):
        """
        MCI-014: Verify missing required inputs are reported.
        """
        skip_if_no_config()
        skip_if_no_client()

        # fetch-url requires 'url' input
        result = run_mcp_client(
            "--workflow", "fetch-url",
            '{}',  # Missing required 'url'
            timeout=30,
        )

        # Should fail or return error
        # The workflow may fail at execution time
        assert result.returncode != 0 or "error" in result.stdout.lower()

    def test_mci_015_workflow_not_found(self):
        """
        MCI-015: Verify nonexistent workflow returns error.
        """
        skip_if_no_config()
        skip_if_no_client()

        result = run_mcp_client(
            "--workflow", "nonexistent-workflow-xyz",
            '{}',
            timeout=30,
        )

        # Should fail
        assert result.returncode != 0 or "error" in result.stdout.lower()

