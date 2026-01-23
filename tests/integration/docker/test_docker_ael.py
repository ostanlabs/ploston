"""
Integration tests for Ploston running in Docker Compose.

These tests verify that the docker-compose deployment works correctly.
Run with: pytest -c pytest-docker.ini
Or: make test-docker (after make test-docker-up)
"""

import time

import pytest
import requests

from .conftest import DockerMCPClient


class TestDockerHealth:
    """Health and connectivity tests for docker-compose deployment."""

    def test_dc_001_health_endpoint_responds(self, docker_url: str, docker_available: bool):
        """Verify health endpoint responds."""
        if not docker_available:
            pytest.skip(f"Docker AEL not available at {docker_url}")

        response = requests.get(f"{docker_url}/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        # Accept both "ok" and "healthy" status values
        assert data.get("status") in ("ok", "healthy")

    def test_dc_002_mcp_initialize(self, docker_client: DockerMCPClient, docker_available: bool):
        """Verify MCP initialize works."""
        if not docker_available:
            pytest.skip("Docker AEL not available")

        result = docker_client.initialize()
        assert "result" in result
        assert "protocolVersion" in result["result"]

    def test_dc_003_mcp_ping(self, docker_client: DockerMCPClient, docker_available: bool):
        """Verify MCP ping works."""
        if not docker_available:
            pytest.skip("Docker AEL not available")

        docker_client.initialize()
        assert docker_client.ping() is True


class TestDockerRunningMode:
    """Tests for docker-compose deployment in running mode."""

    @pytest.mark.requires_running_mode
    def test_dc_004_list_tools_in_running_mode(
        self, docker_client: DockerMCPClient, docker_available: bool
    ):
        """Verify tools are listed in running mode."""
        if not docker_available:
            pytest.skip("Docker AEL not available")

        docker_client.initialize()
        tools = docker_client.list_tools()
        assert len(tools) > 0
        tool_names = [t.get("name") for t in tools]
        # Should have python_exec in running mode
        assert "python_exec" in tool_names

    @pytest.mark.requires_running_mode
    def test_dc_005_python_exec_available(
        self, docker_client: DockerMCPClient, docker_available: bool
    ):
        """Verify python_exec tool is available."""
        if not docker_available:
            pytest.skip("Docker AEL not available")

        docker_client.initialize()
        tools = docker_client.list_tools()
        tool_names = [t.get("name") for t in tools]
        assert "python_exec" in tool_names

    @pytest.mark.requires_running_mode
    def test_dc_006_ael_configure_available(
        self, docker_client: DockerMCPClient, docker_available: bool
    ):
        """Verify ael:configure tool is available in running mode."""
        if not docker_available:
            pytest.skip("Docker AEL not available")

        docker_client.initialize()
        tools = docker_client.list_tools()
        tool_names = [t.get("name") for t in tools]
        assert "ael:configure" in tool_names


class TestDockerPerformance:
    """Performance tests for docker-compose deployment."""

    def test_dc_010_health_response_time(self, docker_url: str, docker_available: bool):
        """Verify health endpoint responds within acceptable time."""
        if not docker_available:
            pytest.skip("Docker AEL not available")

        start = time.time()
        response = requests.get(f"{docker_url}/health", timeout=10)
        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 1.0, f"Health check took {elapsed:.2f}s, expected < 1s"

    def test_dc_011_tool_list_response_time(
        self, docker_client: DockerMCPClient, docker_available: bool
    ):
        """Verify tool list responds within acceptable time."""
        if not docker_available:
            pytest.skip("Docker AEL not available")

        docker_client.initialize()

        start = time.time()
        tools = docker_client.list_tools()
        elapsed = time.time() - start

        assert len(tools) > 0
        assert elapsed < 2.0, f"Tool list took {elapsed:.2f}s, expected < 2s"
