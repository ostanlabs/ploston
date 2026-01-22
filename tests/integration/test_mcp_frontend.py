"""
MCP Frontend Integration Tests for AEL.

Test IDs: FE-001 to FE-012
Priority: P1

These tests verify AEL's MCP server functionality:
- tools/list endpoint
- tools/call endpoint
- Workflow exposure as tools
- Error handling

Prerequisites:
- Component 11 (MCP Frontend) must be implemented
- Run after Milestone M5
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# These imports will work once components are implemented
try:
    from ploston_core.engine import ExecutionResult, WorkflowEngine
    from ploston_core.errors import AELError, ErrorCategory
    from ploston_core.invoker import ToolCallResult, ToolInvoker
    from ploston_core.registry import ToolRegistry
    from ploston_core.server import MCPFrontend, MCPServerConfig
    from ploston_core.types import ExecutionStatus
    from ploston_core.workflow import WorkflowDefinition, WorkflowRegistry

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.frontend,
]


def check_imports():
    if not IMPORTS_AVAILABLE:
        pytest.skip("AEL server module not yet implemented")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_tool_registry() -> MagicMock:
    """Create mock tool registry."""
    check_imports()

    registry = MagicMock(spec=ToolRegistry)
    registry.get_for_mcp_exposure.return_value = [
        {
            "name": "http_request",
            "description": "Make HTTP request",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "method": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["method", "url"],
            },
        },
        {
            "name": "python_exec",
            "description": "Execute Python code",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                },
                "required": ["code"],
            },
        },
    ]
    return registry


@pytest.fixture
def mock_workflow_registry() -> MagicMock:
    """Create mock workflow registry."""
    check_imports()

    registry = MagicMock(spec=WorkflowRegistry)
    registry.get_for_mcp_exposure.return_value = [
        {
            "name": "workflow:simple-http",
            "description": "Simple HTTP workflow",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
            },
        },
        {
            "name": "workflow:data-pipeline",
            "description": "Data processing pipeline",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "destination": {"type": "string"},
                },
            },
        },
    ]
    registry.get.return_value = WorkflowDefinition(
        name="simple-http",
        version="1.0",
        inputs=[{"name": "url", "type": "string", "required": True}],
        steps=[],
        outputs={},
    )
    return registry


@pytest.fixture
def mock_workflow_engine() -> MagicMock:
    """Create mock workflow engine."""
    check_imports()

    engine = MagicMock(spec=WorkflowEngine)
    engine.execute = AsyncMock(
        return_value=ExecutionResult(
            execution_id="exec-123",
            workflow_id="simple-http",
            workflow_version="1.0",
            status=ExecutionStatus.COMPLETED,
            started_at=datetime.now(UTC),
            outputs={"result": "success"},
        )
    )
    return engine


@pytest.fixture
def mock_tool_invoker() -> MagicMock:
    """Create mock tool invoker."""
    check_imports()

    invoker = MagicMock(spec=ToolInvoker)
    invoker.invoke = AsyncMock(
        return_value=ToolCallResult(
            success=True,
            output={"result": "mock_output"},
            duration_ms=100,
            tool_name="mock_tool",
        )
    )
    return invoker


@pytest.fixture
def mcp_frontend(
    mock_tool_registry,
    mock_workflow_registry,
    mock_workflow_engine,
    mock_tool_invoker,
) -> "MCPFrontend":
    """Create MCP frontend with mocks."""
    check_imports()

    config = MCPServerConfig(
        name="ael",
        version="1.0.0",
    )

    return MCPFrontend(
        workflow_engine=mock_workflow_engine,
        tool_registry=mock_tool_registry,
        workflow_registry=mock_workflow_registry,
        tool_invoker=mock_tool_invoker,
        config=config,
    )


# =============================================================================
# Helper to simulate MCP messages
# =============================================================================


async def send_mcp_message(frontend: "MCPFrontend", method: str, params: dict = None) -> dict:
    """Simulate sending an MCP message and getting response."""
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    }
    response = await frontend._handle_message(message)
    return response


# =============================================================================
# Tools List Tests (FE-001 to FE-003)
# =============================================================================


class TestToolsList:
    """Tests for MCP tools/list endpoint (FE-001 to FE-003)."""

    @pytest.mark.asyncio
    async def test_fe_001_tools_list_returns_tools(
        self,
        mcp_frontend: "MCPFrontend",
        mock_tool_registry: MagicMock,
    ):
        """
        FE-001: Verify tools/list returns available tools.
        """
        check_imports()

        response = await send_mcp_message(mcp_frontend, "tools/list")

        assert "error" not in response
        assert "result" in response
        assert "tools" in response["result"]

        tools = response["result"]["tools"]
        assert len(tools) > 0

        # Verify tool structure
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool

    @pytest.mark.asyncio
    async def test_fe_002_tools_list_includes_workflows(
        self,
        mcp_frontend: "MCPFrontend",
        mock_workflow_registry: MagicMock,
    ):
        """
        FE-002: Verify tools/list includes workflows as tools.
        """
        check_imports()

        response = await send_mcp_message(mcp_frontend, "tools/list")

        tools = response["result"]["tools"]
        tool_names = [t["name"] for t in tools]

        # Workflows should be prefixed with "workflow:"
        workflow_tools = [n for n in tool_names if n.startswith("workflow:")]
        assert len(workflow_tools) >= 1
        assert "workflow:simple-http" in tool_names

    @pytest.mark.asyncio
    async def test_fe_003_tools_list_includes_system_tools(
        self,
        mcp_frontend: "MCPFrontend",
        mock_tool_registry: MagicMock,
    ):
        """
        FE-003: Verify tools/list includes system tools.
        """
        check_imports()

        response = await send_mcp_message(mcp_frontend, "tools/list")

        tools = response["result"]["tools"]
        tool_names = [t["name"] for t in tools]

        assert "python_exec" in tool_names


# =============================================================================
# Tools Call Tests (FE-004 to FE-008)
# =============================================================================


class TestToolsCall:
    """Tests for MCP tools/call endpoint (FE-004 to FE-008)."""

    @pytest.mark.asyncio
    async def test_fe_004_call_tool(
        self,
        mcp_frontend: "MCPFrontend",
    ):
        """
        FE-004: Verify tools/call invokes tool correctly.
        """
        check_imports()

        # Mock tool invocation
        with patch.object(mcp_frontend, "_execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "content": [{"type": "text", "text": '{"body": "response", "status": 200}'}],
                "isError": False,
            }

            response = await send_mcp_message(
                mcp_frontend,
                "tools/call",
                {
                    "name": "http_request",
                    "arguments": {"method": "GET", "url": "https://example.com"},
                },
            )

            assert "error" not in response
            assert "result" in response
            assert response["result"].get("isError") is not True

    @pytest.mark.asyncio
    async def test_fe_005_call_workflow(
        self,
        mcp_frontend: "MCPFrontend",
        mock_workflow_engine: MagicMock,
    ):
        """
        FE-005: Verify tools/call executes workflow.
        """
        check_imports()

        response = await send_mcp_message(
            mcp_frontend,
            "tools/call",
            {
                "name": "workflow:simple-http",
                "arguments": {"url": "https://example.com"},
            },
        )

        assert "error" not in response
        assert response["result"].get("isError") is not True

        # Verify workflow engine was called
        mock_workflow_engine.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_fe_006_call_with_invalid_arguments(
        self,
        mcp_frontend: "MCPFrontend",
        mock_workflow_engine: MagicMock,
    ):
        """
        FE-006: Verify tools/call validates arguments.
        """
        check_imports()

        # Make workflow engine return validation error
        mock_workflow_engine.execute = AsyncMock(
            return_value=ExecutionResult(
                execution_id="exec-err",
                workflow_id="simple-http",
                workflow_version="1.0",
                status=ExecutionStatus.FAILED,
                started_at=datetime.now(UTC),
                error=AELError(
                    code="INPUT_INVALID",
                    category=ErrorCategory.VALIDATION,
                    message="Missing required input: url",
                ),
            )
        )

        # Call workflow without required argument
        response = await send_mcp_message(
            mcp_frontend,
            "tools/call",
            {
                "name": "workflow:simple-http",
                "arguments": {},  # Missing required 'url'
            },
        )

        # Should return error
        result = response.get("result", {})
        assert result.get("isError") is True or "error" in response

    @pytest.mark.asyncio
    async def test_fe_007_call_unknown_tool(
        self,
        mcp_frontend: "MCPFrontend",
        mock_tool_invoker: MagicMock,
    ):
        """
        FE-007: Verify tools/call handles unknown tool gracefully.
        """
        check_imports()

        # Make invoker return error for unknown tool
        mock_tool_invoker.invoke = AsyncMock(
            return_value=ToolCallResult(
                success=False,
                output=None,
                duration_ms=10,
                tool_name="nonexistent_tool_xyz",
                error=AELError(
                    code="TOOL_UNAVAILABLE", category=ErrorCategory.TOOL, message="Tool not found"
                ),
            )
        )

        response = await send_mcp_message(
            mcp_frontend,
            "tools/call",
            {
                "name": "nonexistent_tool_xyz",
                "arguments": {},
            },
        )

        # Should return error
        result = response.get("result", {})
        is_error = result.get("isError", False) or "error" in response
        assert is_error

    @pytest.mark.asyncio
    async def test_fe_008_call_tool_error(
        self,
        mcp_frontend: "MCPFrontend",
        mock_workflow_engine: MagicMock,
    ):
        """
        FE-008: Verify tools/call returns tool errors correctly.
        """
        check_imports()

        # Make engine return error
        mock_workflow_engine.execute = AsyncMock(
            return_value=ExecutionResult(
                execution_id="exec-err",
                workflow_id="simple-http",
                workflow_version="1.0",
                status=ExecutionStatus.FAILED,
                started_at=datetime.now(UTC),
                error=AELError(
                    code="TOOL_FAILED", category=ErrorCategory.TOOL, message="Connection refused"
                ),
            )
        )

        response = await send_mcp_message(
            mcp_frontend,
            "tools/call",
            {
                "name": "workflow:simple-http",
                "arguments": {"url": "https://example.com"},
            },
        )

        result = response.get("result", {})
        assert result.get("isError") is True


# =============================================================================
# MCP Protocol Tests (FE-009 to FE-010)
# =============================================================================


class TestMCPProtocol:
    """Tests for MCP protocol compliance (FE-009 to FE-010)."""

    @pytest.mark.asyncio
    async def test_fe_009_initialize_handshake(
        self,
        mcp_frontend: "MCPFrontend",
    ):
        """
        FE-009: Verify MCP initialize handshake works.
        """
        check_imports()

        response = await send_mcp_message(
            mcp_frontend,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        )

        assert "error" not in response
        assert "result" in response

        result = response["result"]
        assert "protocolVersion" in result
        assert "capabilities" in result
        assert "serverInfo" in result

    @pytest.mark.asyncio
    async def test_fe_010_json_rpc_format(
        self,
        mcp_frontend: "MCPFrontend",
    ):
        """
        FE-010: Verify responses follow JSON-RPC format.
        """
        check_imports()

        # Success response
        response = await send_mcp_message(mcp_frontend, "tools/list")

        assert response.get("jsonrpc") == "2.0"
        assert "id" in response
        assert "result" in response or "error" in response

        # Error response (invalid method)
        response = await send_mcp_message(mcp_frontend, "invalid/method")

        assert response.get("jsonrpc") == "2.0"
        assert "id" in response
        assert "error" in response
        assert "code" in response["error"]
        assert "message" in response["error"]


# =============================================================================
# MCP Response Format Tests
# =============================================================================


class TestMCPResponseFormat:
    """Tests for MCP response formatting."""

    @pytest.mark.asyncio
    async def test_tools_call_content_format(
        self,
        mcp_frontend: "MCPFrontend",
        mock_workflow_engine: MagicMock,
    ):
        """Verify tools/call returns content in correct format."""
        check_imports()

        mock_workflow_engine.execute = AsyncMock(
            return_value=ExecutionResult(
                execution_id="exec-123",
                workflow_id="simple-http",
                workflow_version="1.0",
                status=ExecutionStatus.COMPLETED,
                started_at=datetime.now(UTC),
                outputs={"data": "test result"},
            )
        )

        response = await send_mcp_message(
            mcp_frontend,
            "tools/call",
            {
                "name": "workflow:simple-http",
                "arguments": {"url": "https://example.com"},
            },
        )

        result = response["result"]

        # Should have content array
        assert "content" in result
        assert isinstance(result["content"], list)
        assert len(result["content"]) > 0

        # Content should be text or other valid type
        content_item = result["content"][0]
        assert "type" in content_item
        assert content_item["type"] in ["text", "image", "resource"]

    @pytest.mark.asyncio
    async def test_error_response_format(
        self,
        mcp_frontend: "MCPFrontend",
        mock_tool_invoker: MagicMock,
    ):
        """Verify error responses have correct format."""
        check_imports()

        # Make invoker return error
        mock_tool_invoker.invoke = AsyncMock(
            return_value=ToolCallResult(
                success=False,
                output=None,
                duration_ms=10,
                tool_name="nonexistent_tool",
                error=AELError(
                    code="TOOL_UNAVAILABLE", category=ErrorCategory.TOOL, message="Tool not found"
                ),
            )
        )

        response = await send_mcp_message(
            mcp_frontend,
            "tools/call",
            {
                "name": "nonexistent_tool",
                "arguments": {},
            },
        )

        result = response.get("result", {})

        if result.get("isError"):
            # MCP-style error in result
            assert "content" in result
            content = result["content"]
            assert len(content) > 0
        elif "error" in response:
            # JSON-RPC style error
            error = response["error"]
            assert "code" in error
            assert "message" in error


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_tools_list(
        self,
        mcp_frontend: "MCPFrontend",
        mock_tool_registry: MagicMock,
        mock_workflow_registry: MagicMock,
    ):
        """Verify handling when no tools available."""
        check_imports()

        mock_tool_registry.get_for_mcp_exposure.return_value = []
        mock_workflow_registry.get_for_mcp_exposure.return_value = []

        response = await send_mcp_message(mcp_frontend, "tools/list")

        assert "error" not in response
        assert "result" in response
        # Should return empty list
        tools = response["result"]["tools"]
        assert isinstance(tools, list)

    @pytest.mark.asyncio
    async def test_malformed_request(
        self,
        mcp_frontend: "MCPFrontend",
    ):
        """Verify handling of malformed requests."""
        check_imports()

        # Missing method
        response = await mcp_frontend._handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
            }
        )

        assert "error" in response

    @pytest.mark.asyncio
    async def test_null_arguments(
        self,
        mcp_frontend: "MCPFrontend",
        mock_workflow_engine: MagicMock,
    ):
        """Verify handling of null arguments."""
        check_imports()

        # Ensure engine returns a valid result
        mock_workflow_engine.execute = AsyncMock(
            return_value=ExecutionResult(
                execution_id="exec-123",
                workflow_id="simple-http",
                workflow_version="1.0",
                status=ExecutionStatus.COMPLETED,
                started_at=datetime.now(UTC),
                outputs={"result": "success"},
            )
        )

        response = await send_mcp_message(
            mcp_frontend,
            "tools/call",
            {
                "name": "workflow:simple-http",
                "arguments": None,
            },
        )

        # Should handle gracefully (either validate or use empty dict)
        # Response should be valid JSON-RPC
        assert response.get("jsonrpc") == "2.0"
