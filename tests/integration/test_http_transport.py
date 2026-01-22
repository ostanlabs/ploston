"""Integration tests for HTTP transport.

Tests the HTTP transport with actual HTTP requests and MCP protocol handling.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient

from ploston_core.config import MCPHTTPConfig, Mode, ModeManager
from ploston_core.mcp_frontend import MCPFrontend, MCPServerConfig
from ploston_core.mcp_frontend.http_transport import HTTPTransport
from ploston_core.types import MCPTransport


class TestHTTPTransportIntegration:
    """Integration tests for HTTP transport with MCPFrontend."""

    @pytest.fixture
    def mock_tool_registry(self):
        """Create mock tool registry."""
        registry = MagicMock()
        registry.get_for_mcp_exposure.return_value = [
            {
                "name": "test_tool",
                "description": "A test tool",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]
        return registry

    @pytest.fixture
    def mock_workflow_registry(self):
        """Create mock workflow registry."""
        registry = MagicMock()
        registry.get_for_mcp_exposure.return_value = [
            {
                "name": "workflow:test_workflow",
                "description": "A test workflow",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]
        return registry

    @pytest.fixture
    def mock_tool_invoker(self):
        """Create mock tool invoker."""
        invoker = MagicMock()
        result = MagicMock()
        result.success = True
        result.output = {"result": "success"}
        result.structured_content = None
        invoker.invoke = AsyncMock(return_value=result)
        return invoker

    @pytest.fixture
    def mock_workflow_engine(self):
        """Create mock workflow engine."""
        return MagicMock()

    @pytest.fixture
    def mode_manager(self):
        """Create mode manager in running mode."""
        return ModeManager(initial_mode=Mode.RUNNING)

    @pytest.fixture
    def http_config(self):
        """Create HTTP config."""
        return MCPHTTPConfig(
            host="127.0.0.1",
            port=8080,
            cors_origins=["*"],
        )

    @pytest.fixture
    def frontend(
        self,
        mock_workflow_engine,
        mock_tool_registry,
        mock_workflow_registry,
        mock_tool_invoker,
        mode_manager,
        http_config,
    ):
        """Create MCPFrontend with HTTP transport."""
        return MCPFrontend(
            workflow_engine=mock_workflow_engine,
            tool_registry=mock_tool_registry,
            workflow_registry=mock_workflow_registry,
            tool_invoker=mock_tool_invoker,
            config=MCPServerConfig(),
            mode_manager=mode_manager,
            transport=MCPTransport.HTTP,
            http_config=http_config,
        )

    @pytest.fixture
    def client(self, frontend):
        """Create test client for the frontend's HTTP transport."""
        # Access the internal HTTP transport
        frontend._http_transport = HTTPTransport(
            message_handler=frontend._handle_message,
            host=frontend._http_config.host,
            port=frontend._http_config.port,
            cors_origins=frontend._http_config.cors_origins,
        )
        frontend._http_transport.start()
        return TestClient(frontend._http_transport.app)

    # MCP Protocol Tests

    def test_initialize_request(self, client):
        """Test MCP initialize request."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        }
        response = client.post("/mcp", json=request)

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert "result" in data
        assert data["result"]["protocolVersion"] == "2024-11-05"
        assert "capabilities" in data["result"]

    def test_tools_list_request(self, client):
        """Test MCP tools/list request."""
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
        response = client.post("/mcp", json=request)

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 2
        assert "result" in data
        assert "tools" in data["result"]
        # Should have test_tool and workflow:test_workflow
        tool_names = [t["name"] for t in data["result"]["tools"]]
        assert "test_tool" in tool_names
        assert "workflow:test_workflow" in tool_names

    def test_tools_call_request(self, client, mock_tool_invoker):
        """Test MCP tools/call request."""
        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "test_tool",
                "arguments": {"arg1": "value1"},
            },
        }
        response = client.post("/mcp", json=request)

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 3
        assert "result" in data
        assert data["result"]["isError"] is False
        mock_tool_invoker.invoke.assert_called_once()

    def test_ping_request(self, client):
        """Test MCP ping request."""
        request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "ping",
        }
        response = client.post("/mcp", json=request)

        assert response.status_code == 200
        data = response.json()
        assert data["result"]["pong"] is True

    def test_unknown_method_error(self, client):
        """Test error response for unknown method."""
        request = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "unknown/method",
        }
        response = client.post("/mcp", json=request)

        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32601
        assert "Method not found" in data["error"]["message"]

    def test_notification_no_response(self, client):
        """Test that notifications don't get a response."""
        request = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        response = client.post("/mcp", json=request)

        # Notifications return 204 No Content
        assert response.status_code == 204

    # Error Handling Tests

    def test_invalid_json_error(self, client):
        """Test error response for invalid JSON."""
        response = client.post(
            "/mcp",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == -32700

    def test_missing_tool_name_error(self, client):
        """Test error response for missing tool name."""
        request = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"arguments": {}},
        }
        response = client.post("/mcp", json=request)

        assert response.status_code == 200
        data = response.json()
        assert "error" in data


class TestHTTPTransportModeAwareness:
    """Test HTTP transport with mode-aware behavior."""

    @pytest.fixture
    def mock_config_tool_registry(self):
        """Create mock config tool registry."""
        registry = MagicMock()
        registry.get_for_mcp_exposure.return_value = [
            {"name": "ael:config_get", "description": "Get config"},
        ]
        registry.get_configure_tool_for_mcp_exposure.return_value = {
            "name": "ael:configure",
            "description": "Switch to config mode",
        }
        registry.call = AsyncMock(
            return_value={"content": [{"type": "text", "text": "ok"}]}
        )
        return registry

    @pytest.fixture
    def frontend_config_mode(self, mock_config_tool_registry):
        """Create frontend in configuration mode with HTTP transport."""
        mode_manager = ModeManager(initial_mode=Mode.CONFIGURATION)
        http_config = MCPHTTPConfig(host="127.0.0.1", port=8080)

        return MCPFrontend(
            workflow_engine=None,
            tool_registry=None,
            workflow_registry=None,
            tool_invoker=None,
            config=MCPServerConfig(),
            mode_manager=mode_manager,
            config_tool_registry=mock_config_tool_registry,
            transport=MCPTransport.HTTP,
            http_config=http_config,
        )

    @pytest.fixture
    def client_config_mode(self, frontend_config_mode):
        """Create test client for config mode frontend."""
        frontend_config_mode._http_transport = HTTPTransport(
            message_handler=frontend_config_mode._handle_message,
            host=frontend_config_mode._http_config.host,
            port=frontend_config_mode._http_config.port,
        )
        frontend_config_mode._http_transport.start()
        return TestClient(frontend_config_mode._http_transport.app)

    def test_config_mode_tools_list(self, client_config_mode):
        """Test tools/list in config mode returns only config tools."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }
        response = client_config_mode.post("/mcp", json=request)

        assert response.status_code == 200
        data = response.json()
        tool_names = [t["name"] for t in data["result"]["tools"]]
        assert "ael:config_get" in tool_names
        # Regular tools should not be present
        assert "test_tool" not in tool_names