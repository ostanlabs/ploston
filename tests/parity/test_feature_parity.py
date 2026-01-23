"""Feature parity tests between AEL and Ploston.

These tests ensure that the Ploston packages provide the same
functionality as the original AEL codebase.

Run with: pytest tests/parity/ -v
"""

import pytest

# Mark all tests as parity tests
pytestmark = [pytest.mark.parity]


class TestCoreModuleParity:
    """Test that ploston-core has all modules from ael."""

    REQUIRED_MODULES = [
        "api",
        "config",
        "engine",
        "errors",
        "invoker",
        "logging",
        "mcp",
        "mcp_frontend",
        "plugins",
        "registry",
        "sandbox",
        "telemetry",
        "template",
        "types",
        "utils",
        "workflow",
    ]

    @pytest.mark.parametrize("module", REQUIRED_MODULES)
    def test_module_exists(self, module):
        """Test that required module exists in ploston_core."""
        try:
            __import__(f"ploston_core.{module}")
        except ImportError as e:
            pytest.fail(f"Module ploston_core.{module} not found: {e}")

    def test_mcp_frontend_has_dual_mode_support(self):
        """Test that MCPFrontend supports dual-mode (MCP + REST)."""
        import inspect

        from ploston_core.mcp_frontend import MCPFrontend

        sig = inspect.signature(MCPFrontend.__init__)
        params = list(sig.parameters.keys())

        assert "rest_app" in params, "MCPFrontend should accept rest_app parameter"
        assert "rest_prefix" in params, "MCPFrontend should accept rest_prefix parameter"

    def test_rest_api_create_function_exists(self):
        """Test that create_rest_app function exists."""
        import inspect

        from ploston_core.api.app import create_rest_app

        sig = inspect.signature(create_rest_app)
        params = list(sig.parameters.keys())

        assert "workflow_registry" in params
        assert "workflow_engine" in params
        assert "tool_registry" in params
        assert "tool_invoker" in params


class TestServerEntryPointParity:
    """Test that server entry points have required functionality."""

    def test_ploston_server_has_main(self):
        """Test that ploston.server has main() function."""
        from ploston.server import main

        assert callable(main)

    def test_ploston_server_has_plost_application(self):
        """Test that ploston.server exports PlostApplication."""
        from ploston.server import PlostApplication

        assert PlostApplication is not None


class TestComponentInitializationParity:
    """Test that components can be properly initialized."""

    def test_plost_application_can_be_created(self):
        """Test PlostApplication can be instantiated."""
        from ploston_core import PlostApplication
        from ploston_core.types import MCPTransport

        app = PlostApplication(
            transport=MCPTransport.HTTP,
            http_host="127.0.0.1",
            http_port=9999,
            with_rest_api=True,
        )
        assert app is not None

    def test_mcp_frontend_can_be_created_with_http(self):
        """Test MCPFrontend can be created with HTTP transport."""
        from ploston_core.config import MCPHTTPConfig
        from ploston_core.mcp_frontend import MCPFrontend, MCPServerConfig
        from ploston_core.types import MCPTransport

        http_config = MCPHTTPConfig(host="127.0.0.1", port=8080)
        config = MCPServerConfig()

        frontend = MCPFrontend(
            workflow_engine=None,
            tool_registry=None,
            workflow_registry=None,
            tool_invoker=None,
            config=config,
            transport=MCPTransport.HTTP,
            http_config=http_config,
        )
        assert frontend is not None


class TestAPIEndpointParity:
    """Test that REST API has required endpoints."""

    def test_rest_app_can_be_created(self):
        """Test REST app can be created with None dependencies."""
        from ploston_core.api.app import create_rest_app
        from ploston_core.api.config import RESTConfig

        config = RESTConfig()
        app = create_rest_app(
            workflow_registry=None,
            workflow_engine=None,
            tool_registry=None,
            tool_invoker=None,
            config=config,
        )
        assert app is not None

    def test_rest_app_has_routes(self):
        """Test REST app has expected routes."""
        from ploston_core.api.app import create_rest_app
        from ploston_core.api.config import RESTConfig

        config = RESTConfig()
        app = create_rest_app(
            workflow_registry=None,
            workflow_engine=None,
            tool_registry=None,
            tool_invoker=None,
            config=config,
        )

        # Check routes exist
        routes = [route.path for route in app.routes]
        assert any("/workflows" in route for route in routes), (
            f"No workflows route found in {routes}"
        )
        assert any("/tools" in route for route in routes), f"No tools route found in {routes}"
