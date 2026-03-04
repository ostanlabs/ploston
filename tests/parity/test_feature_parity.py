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
