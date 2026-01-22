"""
Tool Registry Integration Tests for AEL.

Test IDs: TR-001 to TR-011
Priority: P0 (Critical)

These tests verify the tool registry functionality:
- Tool discovery from MCP servers
- Schema caching
- Tool refresh
- System tool registration

Prerequisites:
- Components 3 (Config), 4 (MCP Client), 5 (Tool Registry) must be implemented
- Run after Milestone M1
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

# These imports will work once components are implemented
try:
    from ploston_core.errors import AELError
    from ploston_core.mcp import MCPClientManager, MCPConnection, ServerStatus, ToolSchema
    from ploston_core.registry import ToolRegistry
    from ploston_core.types import ConnectionStatus, ToolSource, ToolStatus

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.registry,
]


def check_imports():
    if not IMPORTS_AVAILABLE:
        pytest.skip("AEL registry module not yet implemented")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_tool_schemas() -> list["ToolSchema"]:
    """Create mock tool schemas with proper structure."""
    check_imports()
    return [
        ToolSchema(
            name="firecrawl_scrape",
            description="Scrape content from URL",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to scrape"},
                },
                "required": ["url"],
            },
        ),
        ToolSchema(
            name="http_request",
            description="Make HTTP request",
            input_schema={
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["GET", "POST"]},
                    "url": {"type": "string"},
                },
                "required": ["method", "url"],
            },
        ),
    ]


@pytest.fixture
def mock_mcp_connection(mock_tool_schemas) -> MagicMock:
    """Create mock MCP connection."""
    check_imports()

    connection = MagicMock(spec=MCPConnection)
    connection.name = "native_tools"
    connection.status = ConnectionStatus.CONNECTED
    connection.list_tools.return_value = mock_tool_schemas
    connection.refresh_tools = AsyncMock(return_value=mock_tool_schemas)
    connection.get_status.return_value = ServerStatus(
        name="native_tools",
        status=ConnectionStatus.CONNECTED,
        tools=["firecrawl_scrape", "http_request"],
    )
    return connection


@pytest.fixture
def mock_mcp_manager(mock_mcp_connection, mock_tool_schemas) -> MagicMock:
    """Create mock MCP client manager."""
    check_imports()

    manager = MagicMock(spec=MCPClientManager)
    manager._connections = {"native_tools": mock_mcp_connection}
    manager.list_connections.return_value = [mock_mcp_connection]
    manager.get_connection.return_value = mock_mcp_connection
    manager.connect_all = AsyncMock(
        return_value={
            "native_tools": ServerStatus(
                name="native_tools",
                status=ConnectionStatus.CONNECTED,
                tools=["firecrawl_scrape", "http_request"],
            ),
        }
    )
    # Use mock_tool_schemas to ensure proper schema structure is preserved
    manager.refresh_all = AsyncMock(
        return_value={
            "native_tools": mock_tool_schemas,
        }
    )
    manager.get_all_tools.return_value = {
        "native_tools": mock_tool_schemas,
    }
    return manager


@pytest.fixture
def mock_tools_config() -> MagicMock:
    """Create mock tools config."""
    check_imports()

    config = MagicMock()
    config.system_tools = MagicMock()
    config.system_tools.python_exec_enabled = True
    return config


@pytest.fixture
def tool_registry(mock_mcp_manager, mock_tools_config) -> "ToolRegistry":
    """Create tool registry with mocks."""
    check_imports()

    return ToolRegistry(
        mcp_manager=mock_mcp_manager,
        config=mock_tools_config,
        logger=None,
    )


# =============================================================================
# Tool Discovery Tests (TR-001 to TR-003)
# =============================================================================


class TestToolDiscovery:
    """Tests for tool discovery from MCP servers (TR-001 to TR-003)."""

    @pytest.mark.asyncio
    async def test_tr_001_discover_tools_from_mcp_server(
        self,
        tool_registry: "ToolRegistry",
        mock_mcp_manager: MagicMock,
    ):
        """
        TR-001: Verify tools are discovered from configured MCP servers.

        Flow: Config → MCP Client → Tool Registry
        """
        check_imports()

        # Initialize registry (triggers tool discovery)
        result = await tool_registry.initialize()

        # Verify MCP manager was called
        mock_mcp_manager.connect_all.assert_called_once()

        # Verify tools were discovered
        assert result.total_tools >= 2  # At least the mock tools

        # Verify specific tools exist
        firecrawl = tool_registry.get("firecrawl_scrape")
        assert firecrawl is not None
        assert firecrawl.name == "firecrawl_scrape"
        assert firecrawl.source == ToolSource.MCP
        assert firecrawl.server_name == "native_tools"

    @pytest.mark.asyncio
    async def test_tr_002_tool_schema_captured(
        self,
        tool_registry: "ToolRegistry",
    ):
        """
        TR-002: Verify tool input schemas are captured correctly.
        """
        check_imports()

        await tool_registry.initialize()

        http_tool = tool_registry.get("http_request")
        assert http_tool is not None
        assert http_tool.input_schema is not None
        assert http_tool.input_schema.get("type") == "object"
        assert "properties" in http_tool.input_schema
        assert "url" in http_tool.input_schema["properties"]

    @pytest.mark.asyncio
    async def test_tr_003_multiple_mcp_servers(
        self,
        mock_tools_config: MagicMock,
    ):
        """
        TR-003: Verify tools from multiple MCP servers are aggregated.
        """
        check_imports()

        # Create tool schemas for each server
        tools_server_1 = [
            ToolSchema(name="tool_a", description="Tool A", input_schema={"type": "object"}),
        ]
        tools_server_2 = [
            ToolSchema(name="tool_b", description="Tool B", input_schema={"type": "object"}),
        ]

        # Create mock connections
        connection1 = MagicMock(spec=MCPConnection)
        connection1.name = "server_1"
        connection1.status = ConnectionStatus.CONNECTED
        connection1.list_tools.return_value = tools_server_1

        connection2 = MagicMock(spec=MCPConnection)
        connection2.name = "server_2"
        connection2.status = ConnectionStatus.CONNECTED
        connection2.list_tools.return_value = tools_server_2

        # Create manager with both connections
        manager = MagicMock(spec=MCPClientManager)
        manager._connections = {
            "server_1": connection1,
            "server_2": connection2,
        }
        manager.list_connections.return_value = [connection1, connection2]
        manager.connect_all = AsyncMock(return_value={})
        # refresh_all is called by initialize() -> refresh()
        manager.refresh_all = AsyncMock(
            return_value={
                "server_1": tools_server_1,
                "server_2": tools_server_2,
            }
        )
        manager.get_all_tools.return_value = {
            "server_1": tools_server_1,
            "server_2": tools_server_2,
        }

        registry = ToolRegistry(
            mcp_manager=manager,
            config=mock_tools_config,
        )
        await registry.initialize()

        # Verify tools from both servers
        tool_a = registry.get("tool_a")
        tool_b = registry.get("tool_b")

        assert tool_a is not None
        assert tool_a.server_name == "server_1"

        assert tool_b is not None
        assert tool_b.server_name == "server_2"


# =============================================================================
# Tool Caching Tests (TR-004 to TR-005)
# =============================================================================


class TestToolCaching:
    """Tests for tool schema caching (TR-004 to TR-005)."""

    @pytest.mark.asyncio
    async def test_tr_004_schemas_cached_after_fetch(
        self,
        tool_registry: "ToolRegistry",
        mock_mcp_manager: MagicMock,
    ):
        """
        TR-004: Verify tool schemas are cached after initial fetch.
        """
        check_imports()

        await tool_registry.initialize()

        # First access
        tools1 = tool_registry.list_tools()

        # Second access (should use cache, not call MCP again)
        tools2 = tool_registry.list_tools()

        # Both should return same tools
        assert len(tools1) == len(tools2)

        # refresh_all should only be called once during initialize
        assert mock_mcp_manager.refresh_all.call_count == 1

    @pytest.mark.asyncio
    async def test_tr_005_cache_survives_reconnect(
        self,
        tool_registry: "ToolRegistry",
        mock_mcp_connection: MagicMock,
        mock_mcp_manager: MagicMock,
    ):
        """
        TR-005: Verify tools marked unavailable (not removed) when server disconnects.
        """
        check_imports()

        await tool_registry.initialize()

        # Verify tool exists and is available
        tool = tool_registry.get("firecrawl_scrape")
        assert tool is not None
        assert tool.status == ToolStatus.AVAILABLE

        # Simulate server disconnect - update refresh_all to return empty
        mock_mcp_connection.status = ConnectionStatus.DISCONNECTED
        mock_mcp_manager.refresh_all = AsyncMock(
            return_value={
                "native_tools": [],
            }
        )

        # Refresh should mark tools unavailable, not remove them
        await tool_registry.refresh()

        # Tool should still exist but be unavailable
        tool = tool_registry.get("firecrawl_scrape")
        assert tool is not None  # Not removed
        assert tool.status == ToolStatus.UNAVAILABLE  # But marked unavailable


# =============================================================================
# Tool Refresh Tests (TR-006 to TR-007)
# =============================================================================


class TestToolRefresh:
    """Tests for tool refresh functionality (TR-006 to TR-007)."""

    @pytest.mark.asyncio
    async def test_tr_006_refresh_fetches_new_tools(
        self,
        tool_registry: "ToolRegistry",
        mock_mcp_connection: MagicMock,
        mock_mcp_manager: MagicMock,
        mock_tool_schemas: list["ToolSchema"],
    ):
        """
        TR-006: Verify refresh discovers newly added tools.
        """
        check_imports()

        await tool_registry.initialize()

        # Verify initial tools
        initial_tools = tool_registry.list_tools()
        initial_names = {t.name for t in initial_tools}
        assert "new_tool" not in initial_names

        # Add new tool to mock server
        new_tool = ToolSchema(
            name="new_tool", description="New tool", input_schema={"type": "object"}
        )
        new_tools = mock_tool_schemas + [new_tool]
        mock_mcp_manager.refresh_all = AsyncMock(
            return_value={
                "native_tools": new_tools,
            }
        )

        # Refresh
        result = await tool_registry.refresh()

        # Verify new tool was added
        assert "new_tool" in result.added

        found_tool = tool_registry.get("new_tool")
        assert found_tool is not None

    @pytest.mark.asyncio
    async def test_tr_007_refresh_updates_schemas(
        self,
        tool_registry: "ToolRegistry",
        mock_mcp_connection: MagicMock,
        mock_mcp_manager: MagicMock,
    ):
        """
        TR-007: Verify refresh updates changed tool schemas.
        """
        check_imports()

        await tool_registry.initialize()

        # Get original tool
        tool = tool_registry.get("http_request")
        assert tool is not None

        # Update schema in mock - note the changed description
        updated_tools = [
            ToolSchema(
                name="firecrawl_scrape", description="Scrape", input_schema={"type": "object"}
            ),
            ToolSchema(
                name="http_request",
                description="HTTP - Updated",
                input_schema={
                    "type": "object",
                    "properties": {
                        "method": {"type": "string"},
                        "url": {"type": "string"},
                        "headers": {"type": "object"},  # New property
                    },
                },
            ),
        ]
        mock_mcp_manager.refresh_all = AsyncMock(
            return_value={
                "native_tools": updated_tools,
            }
        )

        # Refresh
        await tool_registry.refresh()

        # Verify schema was updated
        tool = tool_registry.get("http_request")
        assert tool.description == "HTTP - Updated"
        assert "headers" in tool.input_schema.get("properties", {})


# =============================================================================
# System Tools Tests (TR-008)
# =============================================================================


class TestSystemTools:
    """Tests for system tool registration (TR-008)."""

    @pytest.mark.asyncio
    async def test_tr_008_python_exec_always_available(
        self,
        tool_registry: "ToolRegistry",
    ):
        """
        TR-008: Verify python_exec system tool is always available.
        """
        check_imports()

        await tool_registry.initialize()

        # python_exec should exist
        python_exec = tool_registry.get("python_exec")
        assert python_exec is not None
        assert python_exec.name == "python_exec"
        assert python_exec.source == ToolSource.SYSTEM
        assert python_exec.status == ToolStatus.AVAILABLE

        # Should have proper schema
        assert python_exec.input_schema is not None
        assert "code" in python_exec.input_schema.get("properties", {})

    @pytest.mark.asyncio
    async def test_tr_008b_system_tools_no_mcp_servers(
        self,
        mock_tools_config: MagicMock,
    ):
        """
        TR-008b: Verify system tools available even without MCP servers.
        """
        check_imports()

        # Manager with no connections
        manager = MagicMock(spec=MCPClientManager)
        manager._connections = {}
        manager.list_connections.return_value = []
        manager.connect_all = AsyncMock(return_value={})
        manager.refresh_all = AsyncMock(return_value={})
        manager.get_all_tools.return_value = {}

        registry = ToolRegistry(
            mcp_manager=manager,
            config=mock_tools_config,
        )
        await registry.initialize()

        # python_exec should still be available
        python_exec = registry.get("python_exec")
        assert python_exec is not None


# =============================================================================
# Tool Lookup Tests (TR-009 to TR-011)
# =============================================================================


class TestToolLookup:
    """Tests for tool lookup methods (TR-009 to TR-011)."""

    @pytest.mark.asyncio
    async def test_tr_009_get_tool_by_name(
        self,
        tool_registry: "ToolRegistry",
    ):
        """
        TR-009: Verify get() returns correct tool by name.
        """
        check_imports()

        await tool_registry.initialize()

        # Existing tool
        tool = tool_registry.get("firecrawl_scrape")
        assert tool is not None
        assert tool.name == "firecrawl_scrape"

        # Non-existent tool
        tool = tool_registry.get("nonexistent_tool")
        assert tool is None

    @pytest.mark.asyncio
    async def test_tr_009b_get_or_raise(
        self,
        tool_registry: "ToolRegistry",
    ):
        """
        TR-009b: Verify get_or_raise() raises for unknown tool.
        """
        check_imports()

        await tool_registry.initialize()

        # Existing tool should work
        tool = tool_registry.get_or_raise("python_exec")
        assert tool is not None

        # Non-existent tool should raise
        with pytest.raises(AELError) as exc_info:
            tool_registry.get_or_raise("nonexistent_tool")

        # Check error - accept various formats
        error_str = str(exc_info.value).lower()
        assert any(x in error_str for x in ["tool_unavailable", "not found", "unavailable"])

    @pytest.mark.asyncio
    async def test_tr_010_list_tools_by_source(
        self,
        tool_registry: "ToolRegistry",
    ):
        """
        TR-010: Verify listing tools filtered by source.
        """
        check_imports()

        await tool_registry.initialize()

        # List MCP tools only
        mcp_tools = tool_registry.list_tools(source=ToolSource.MCP)
        assert all(t.source == ToolSource.MCP for t in mcp_tools)

        # List system tools only
        system_tools = tool_registry.list_tools(source=ToolSource.SYSTEM)
        assert all(t.source == ToolSource.SYSTEM for t in system_tools)
        assert any(t.name == "python_exec" for t in system_tools)

    @pytest.mark.asyncio
    async def test_tr_010b_list_tools_by_server(
        self,
        tool_registry: "ToolRegistry",
    ):
        """
        TR-010b: Verify listing tools filtered by server.
        """
        check_imports()

        await tool_registry.initialize()

        # List tools from specific server
        native_tools = tool_registry.list_tools(server_name="native_tools")
        assert all(t.server_name == "native_tools" for t in native_tools)

    @pytest.mark.asyncio
    async def test_tr_011_search_tools(
        self,
        tool_registry: "ToolRegistry",
    ):
        """
        TR-011: Verify tool search functionality.
        """
        check_imports()

        await tool_registry.initialize()

        # Search by name
        results = tool_registry.search("fire")
        assert any(t.name == "firecrawl_scrape" for t in results)

        # Search by description
        results = tool_registry.search("HTTP")
        assert any(t.name == "http_request" for t in results)

        # Search with no matches
        results = tool_registry.search("xyznonexistent")
        assert len(results) == 0


# =============================================================================
# Tool Router Tests
# =============================================================================


class TestToolRouter:
    """Tests for tool routing."""

    @pytest.mark.asyncio
    async def test_tr_router_mcp_tool(
        self,
        tool_registry: "ToolRegistry",
    ):
        """Verify router returns correct info for MCP tools."""
        check_imports()

        await tool_registry.initialize()

        router = tool_registry.get_router("firecrawl_scrape")
        assert router is not None
        assert router.source == ToolSource.MCP
        assert router.server_name == "native_tools"

    @pytest.mark.asyncio
    async def test_tr_router_system_tool(
        self,
        tool_registry: "ToolRegistry",
    ):
        """Verify router returns correct info for system tools."""
        check_imports()

        await tool_registry.initialize()

        router = tool_registry.get_router("python_exec")
        assert router is not None
        assert router.source == ToolSource.SYSTEM
        assert router.server_name is None

    @pytest.mark.asyncio
    async def test_tr_router_unknown_tool(
        self,
        tool_registry: "ToolRegistry",
    ):
        """Verify router returns None for unknown tools."""
        check_imports()

        await tool_registry.initialize()

        router = tool_registry.get_router("nonexistent_tool")
        assert router is None


# =============================================================================
# MCP Exposure Tests
# =============================================================================


class TestMCPExposure:
    """Tests for MCP exposure formatting."""

    @pytest.mark.asyncio
    async def test_tr_mcp_exposure_format(
        self,
        tool_registry: "ToolRegistry",
    ):
        """Verify get_for_mcp_exposure returns correct format."""
        check_imports()

        await tool_registry.initialize()

        mcp_tools = tool_registry.get_for_mcp_exposure()

        assert isinstance(mcp_tools, list)
        assert len(mcp_tools) > 0

        # Check format
        for tool in mcp_tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool

    @pytest.mark.asyncio
    async def test_tr_mcp_exposure_only_available(
        self,
        tool_registry: "ToolRegistry",
        mock_mcp_connection: MagicMock,
        mock_mcp_manager: MagicMock,
    ):
        """Verify get_for_mcp_exposure only returns available tools."""
        check_imports()

        await tool_registry.initialize()

        # Mark a tool unavailable
        tool = tool_registry.get("firecrawl_scrape")
        tool.status = ToolStatus.UNAVAILABLE

        mcp_tools = tool_registry.get_for_mcp_exposure()
        tool_names = [t["name"] for t in mcp_tools]

        # Unavailable tool should not be in exposure list
        assert "firecrawl_scrape" not in tool_names
