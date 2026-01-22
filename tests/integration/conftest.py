"""
Integration test fixtures and configuration.

These fixtures are specific to integration tests and build on top of
the base fixtures in tests/conftest.py.
"""

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest

# Ensure src is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# =============================================================================
# Import Availability Check
# =============================================================================

# Try to import AEL modules - tests will skip if not available
try:
    from ploston_core.types import BackoffType  # noqa: F401

    AEL_TYPES_AVAILABLE = True
except ImportError:
    AEL_TYPES_AVAILABLE = False

try:
    from ploston_core.errors import AELError  # noqa: F401

    AEL_ERRORS_AVAILABLE = True
except ImportError:
    AEL_ERRORS_AVAILABLE = False

try:
    from ploston_core.config import AELConfig  # noqa: F401

    AEL_CONFIG_AVAILABLE = True
except ImportError:
    AEL_CONFIG_AVAILABLE = False


# =============================================================================
# Path Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the project root directory."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def tests_dir() -> Path:
    """Return the tests directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def integration_dir() -> Path:
    """Return the integration tests directory."""
    return Path(__file__).parent


@pytest.fixture(scope="session")
def integration_fixtures_dir(integration_dir: Path) -> Path:
    """Return the integration fixtures directory."""
    return integration_dir / "fixtures"


@pytest.fixture(scope="session")
def workflows_dir(integration_fixtures_dir: Path) -> Path:
    """Return the test workflows directory."""
    return integration_fixtures_dir / "workflows"


@pytest.fixture(scope="session")
def configs_dir(integration_fixtures_dir: Path) -> Path:
    """Return the test configs directory."""
    return integration_fixtures_dir / "configs"


# =============================================================================
# CLI Runner Fixtures
# =============================================================================


@pytest.fixture
def ael_cli(project_root: Path) -> Callable[..., subprocess.CompletedProcess]:
    """
    Fixture to run Ploston CLI commands.

    Usage:
        result = ael_cli("tools", "list")
        result = ael_cli("run", "workflow.yaml", "--input", "key=value")
    """

    def _run_cli(
        *args: str,
        config: Path | None = None,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess:
        cmd = [sys.executable, "-m", "ploston_cli"]

        if config and config.exists():
            cmd.extend(["--config", str(config)])

        cmd.extend(args)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(project_root / "src")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_root,
            env=env,
        )
        return result

    return _run_cli


@pytest.fixture
def workflow_runner(
    ael_cli: Callable[..., subprocess.CompletedProcess],
    workflows_dir: Path,
) -> Callable[..., subprocess.CompletedProcess]:
    """
    Fixture to run workflows via CLI.

    Usage:
        result = workflow_runner("simple-linear.yaml", inputs={"url": "https://example.com"})
    """

    def _run_workflow(
        workflow_name: str,
        inputs: dict[str, str] | None = None,
        timeout: int = 60,
    ) -> subprocess.CompletedProcess:
        workflow_path = workflows_dir / workflow_name
        args = ["run", str(workflow_path)]

        if inputs:
            for key, value in inputs.items():
                args.extend(["--input", f"{key}={value}"])

        return ael_cli(*args, timeout=timeout)

    return _run_workflow


# =============================================================================
# Mock Tool Data
# =============================================================================


@pytest.fixture(scope="session")
def mock_tool_definitions() -> list[dict[str, Any]]:
    """Return mock tool definitions for testing."""
    return [
        {
            "name": "mock_http_request",
            "description": "Mock HTTP request tool for testing",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "DELETE"],
                    },
                    "url": {"type": "string"},
                },
                "required": ["method", "url"],
            },
        },
        {
            "name": "mock_file_read",
            "description": "Mock file read tool for testing",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
        {
            "name": "mock_transform",
            "description": "Mock data transformation tool",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "data": {"type": "object"},
                    "operation": {"type": "string"},
                },
                "required": ["data"],
            },
        },
    ]


# =============================================================================
# Security Test Data
# =============================================================================


@pytest.fixture(scope="session")
def blocked_imports() -> list[str]:
    """List of imports that should be blocked by the sandbox."""
    return [
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
        "ctypes",
        "multiprocessing",
        "threading",
        "signal",
        "resource",
        "pty",
        "tty",
        "termios",
        "fcntl",
        "mmap",
        "gc",
    ]


@pytest.fixture(scope="session")
def allowed_imports() -> list[str]:
    """List of imports that should be allowed by the sandbox."""
    return [
        "json",
        "re",
        "math",
        "datetime",
        "typing",
        "collections",
        "itertools",
        "functools",
        "dataclasses",
        "enum",
        "copy",
        "uuid",
        "hashlib",
        "base64",
        "urllib.parse",
    ]


@pytest.fixture(scope="session")
def blocked_builtins() -> list[str]:
    """List of builtins that should be blocked by the sandbox."""
    return [
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
    ]


# =============================================================================
# Async Utilities
# =============================================================================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def async_timeout() -> int:
    """Default timeout for async operations in seconds."""
    return 30


@pytest.fixture
def workflow_timeout() -> int:
    """Default timeout for workflow execution in seconds."""
    return 60


# =============================================================================
# Result Parsing Helpers
# =============================================================================


@pytest.fixture
def parse_json_output() -> Callable[[str], dict[str, Any] | None]:
    """Helper to parse JSON from CLI output."""

    def _parse(output: str) -> dict[str, Any] | None:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            # Try to find JSON in output (might have other text)
            for line in output.strip().split("\n"):
                line = line.strip()
                if line.startswith("{") or line.startswith("["):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue
            return None

    return _parse


@pytest.fixture
def assert_workflow_success() -> Callable[[dict[str, Any]], None]:
    """Helper to assert workflow execution succeeded."""

    def _assert(result: dict[str, Any]) -> None:
        assert result is not None, "Result is None"
        assert result.get("success") is True, f"Workflow failed: {result.get('error')}"

    return _assert


@pytest.fixture
def assert_workflow_failure() -> Callable[[dict[str, Any], str | None], None]:
    """Helper to assert workflow execution failed with expected error."""

    def _assert(result: dict[str, Any], expected_error: str | None = None) -> None:
        assert result is not None, "Result is None"
        assert result.get("success") is False, "Workflow should have failed"
        if expected_error:
            error_msg = str(result.get("error", {})).lower()
            assert expected_error.lower() in error_msg, (
                f"Expected error containing '{expected_error}', got: {result.get('error')}"
            )

    return _assert


# =============================================================================
# Test Environment Validation
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def validate_test_environment(project_root: Path):
    """Validate that the test environment is properly configured."""
    # Check that ploston package exists
    ploston_path = project_root / "src" / "ploston"
    if not ploston_path.exists():
        pytest.skip("Ploston source not found - skipping integration tests")

    yield


# =============================================================================
# Cleanup Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_test_state():
    """Clean up any test state before and after each test."""
    # Pre-test setup
    yield
    # Post-test cleanup


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment variables after each test."""
    original_env = dict(os.environ)
    yield
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


# =============================================================================
# Skip Helpers
# =============================================================================


def skip_if_no_types():
    """Skip test if AEL types module not available."""
    if not AEL_TYPES_AVAILABLE:
        pytest.skip("AEL types module not yet implemented")


def skip_if_no_errors():
    """Skip test if AEL errors module not available."""
    if not AEL_ERRORS_AVAILABLE:
        pytest.skip("AEL errors module not yet implemented")


def skip_if_no_config():
    """Skip test if AEL config module not available."""
    if not AEL_CONFIG_AVAILABLE:
        pytest.skip("AEL config module not yet implemented")
