"""Server smoke tests for Ploston.

These tests verify that the actual server starts correctly and responds
to basic requests. Unlike other integration tests that use mocks, these
tests start the real server to catch initialization issues.

This test was added after discovering that the server entry point was
creating empty registries instead of properly initializing components.
"""

import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest

# Mark all tests in this module as integration and smoke tests
pytestmark = [pytest.mark.integration, pytest.mark.smoke]

# Minimal config template for smoke tests (workflows.directory will be replaced)
MINIMAL_CONFIG_TEMPLATE = """
# Minimal config for smoke tests
logging:
  level: INFO
  format: colored
  options:
    show_params: false
    show_results: false
    truncate_at: 200
  components:
    workflow: true
    step: true
    tool: true
    sandbox: true

mcp:
  servers: []

tools:
  system:
    python_exec:
      enabled: false

workflows:
  directory: {workflows_dir}

telemetry:
  enabled: false
  metrics:
    enabled: false
  tracing:
    enabled: false
  logs:
    enabled: false
"""


def find_free_port() -> int:
    """Find a free port to use for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server_port() -> int:
    """Get a free port for the test server."""
    return find_free_port()


@pytest.fixture
def config_file():
    """Create a temporary config file for testing."""
    # Create a temp directory for workflows
    workflows_dir = tempfile.mkdtemp()
    config_content = MINIMAL_CONFIG_TEMPLATE.format(workflows_dir=workflows_dir)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_content)
        f.flush()
        yield Path(f.name)
    # Cleanup
    Path(f.name).unlink(missing_ok=True)
    import shutil
    shutil.rmtree(workflows_dir, ignore_errors=True)


@pytest.fixture
def server_process(server_port: int, config_file: Path):
    """Start the actual ploston server and yield the process.

    This starts the real server binary, not a mocked version.
    """
    # Start server as subprocess
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "ploston.server",
            "--port",
            str(server_port),
            "--host",
            "127.0.0.1",
            "--config",
            str(config_file),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    # Wait for server to be ready (max 10 seconds)
    start_time = time.time()
    server_ready = False
    
    while time.time() - start_time < 10:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(("127.0.0.1", server_port))
                if result == 0:
                    server_ready = True
                    break
        except Exception:
            pass
        time.sleep(0.1)
    
    if not server_ready:
        process.kill()
        stdout, stderr = process.communicate(timeout=5)
        pytest.fail(f"Server failed to start.\nstdout: {stdout}\nstderr: {stderr}")
    
    yield process
    
    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


class TestServerSmoke:
    """Smoke tests for the ploston server."""

    def test_server_starts(self, server_process, server_port):
        """Test that the server starts without errors."""
        assert server_process.poll() is None, "Server process should be running"

    def test_health_endpoint(self, server_process, server_port):
        """Test that /health endpoint responds."""
        response = httpx.get(f"http://127.0.0.1:{server_port}/health", timeout=5)
        assert response.status_code == 200

    def test_mcp_endpoint_exists(self, server_process, server_port):
        """Test that /mcp endpoint exists and accepts POST."""
        # Send MCP initialize request
        response = httpx.post(
            f"http://127.0.0.1:{server_port}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "smoke-test", "version": "1.0.0"},
                },
            },
            timeout=5,
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert data["result"]["protocolVersion"] == "2024-11-05"

    def test_rest_api_workflows_endpoint(self, server_process, server_port):
        """Test that REST API /api/v1/workflows endpoint responds.

        This is the critical test that would have caught the dual-mode issue.
        """
        response = httpx.get(
            f"http://127.0.0.1:{server_port}/api/v1/workflows",
            timeout=5,
        )
        # Should return 200 with paginated response
        assert response.status_code == 200
        data = response.json()
        # API returns paginated response with items/workflows key
        assert isinstance(data, dict)
        assert "items" in data or "workflows" in data or "page" in data

    def test_rest_api_tools_endpoint(self, server_process, server_port):
        """Test that REST API /api/v1/tools endpoint responds."""
        response = httpx.get(
            f"http://127.0.0.1:{server_port}/api/v1/tools",
            timeout=5,
        )
        assert response.status_code == 200
        data = response.json()
        # API returns response with tools key
        assert isinstance(data, dict)
        assert "tools" in data
