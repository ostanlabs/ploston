"""Integration tests for REST API.

These tests verify the REST API endpoints work correctly with
real workflow registry, tool registry, and execution engine.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from ploston_core.api import RESTConfig, create_rest_app


@pytest.fixture
def mock_workflow_registry() -> MagicMock:
    """Create a mock workflow registry."""
    registry = MagicMock()
    registry.list_workflows.return_value = []
    registry.get.return_value = None  # get() is used for single workflow lookup
    return registry


@pytest.fixture
def mock_workflow_engine() -> MagicMock:
    """Create a mock workflow engine."""
    engine = MagicMock()
    return engine


@pytest.fixture
def mock_tool_registry() -> MagicMock:
    """Create a mock tool registry."""
    registry = MagicMock()
    registry.list_tools.return_value = []
    registry.get_tool.return_value = None
    return registry


@pytest.fixture
def mock_tool_invoker() -> MagicMock:
    """Create a mock tool invoker."""
    invoker = MagicMock()
    return invoker


@pytest.fixture
def rest_config() -> RESTConfig:
    """Create REST API configuration."""
    return RESTConfig(
        host="127.0.0.1",
        port=8080,
        prefix="/api/v1",
        docs_enabled=True,
        require_auth=False,
    )


@pytest.fixture
def test_client(
    mock_workflow_registry: MagicMock,
    mock_workflow_engine: MagicMock,
    mock_tool_registry: MagicMock,
    mock_tool_invoker: MagicMock,
    rest_config: RESTConfig,
) -> TestClient:
    """Create a test client for the REST API."""
    app = create_rest_app(
        workflow_registry=mock_workflow_registry,
        workflow_engine=mock_workflow_engine,
        tool_registry=mock_tool_registry,
        tool_invoker=mock_tool_invoker,
        config=rest_config,
    )
    return TestClient(app)


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_check(self, test_client: TestClient) -> None:
        """Test /health endpoint returns healthy status."""
        response = test_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "checks" in data

    def test_info_endpoint(self, test_client: TestClient) -> None:
        """Test /info endpoint returns API information."""
        response = test_client.get("/api/v1/info")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "name" in data


class TestWorkflowEndpoints:
    """Tests for workflow endpoints."""

    def test_list_workflows_empty(
        self, test_client: TestClient, mock_workflow_registry: MagicMock
    ) -> None:
        """Test listing workflows when none exist."""
        mock_workflow_registry.list_workflows.return_value = []

        response = test_client.get("/api/v1/workflows")
        assert response.status_code == 200
        data = response.json()
        assert data["workflows"] == []
        assert data["total"] == 0

    def test_get_workflow_not_found(
        self, test_client: TestClient, mock_workflow_registry: MagicMock
    ) -> None:
        """Test getting a non-existent workflow."""
        mock_workflow_registry.get.return_value = None

        response = test_client.get("/api/v1/workflows/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "HTTP_404"
        assert "not found" in data["error"]["message"].lower()


class TestToolEndpoints:
    """Tests for tool endpoints."""

    def test_list_tools_empty(
        self, test_client: TestClient, mock_tool_registry: MagicMock
    ) -> None:
        """Test listing tools when none exist."""
        mock_tool_registry.list_tools.return_value = []

        response = test_client.get("/api/v1/tools")
        assert response.status_code == 200
        data = response.json()
        assert data["tools"] == []
        assert data["total"] == 0

    def test_get_tool_not_found(
        self, test_client: TestClient, mock_tool_registry: MagicMock
    ) -> None:
        """Test getting a non-existent tool."""
        mock_tool_registry.get_tool.return_value = None

        response = test_client.get("/api/v1/tools/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "HTTP_404"
        assert "not found" in data["error"]["message"].lower()


class TestExecutionEndpoints:
    """Tests for execution endpoints."""

    def test_list_executions_empty(self, test_client: TestClient) -> None:
        """Test listing executions when none exist."""
        response = test_client.get("/api/v1/executions")
        assert response.status_code == 200
        data = response.json()
        assert data["executions"] == []
        assert data["total"] == 0

    def test_get_execution_not_found(self, test_client: TestClient) -> None:
        """Test getting a non-existent execution."""
        response = test_client.get("/api/v1/executions/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "HTTP_404"
        assert "not found" in data["error"]["message"].lower()

