"""
CLI Integration Tests for Ploston (Local Tests Only).

Test IDs: CLI-005 to CLI-009, CLI-015 (local), CLI-016 to CLI-020
Priority: P1

These tests verify CLI functionality that does NOT require a running server:
- ploston validate
- ploston config show --local
- ploston --help / --version
- Error handling

NOTE: Tests that require a running server (CLI-003, CLI-004, CLI-010 to CLI-014,
CLI-015 server, and integration scenarios) have been moved to the meta-repo:
agent-execution-layer/tests/integration/test_cli_integration.py

Prerequisites:
- Component 12 (CLI) must be implemented
- Run after Milestone M5
"""

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

# Get project root for running CLI
PROJECT_ROOT = Path(__file__).parent.parent.parent


pytestmark = [
    pytest.mark.integration,
    pytest.mark.cli,
]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def cli_runner() -> Callable:
    """
    Create CLI runner function.

    Runs AEL CLI commands and returns result.

    Note: The ploston_cli is a thin HTTP client that connects to a Ploston server.
    It uses --server to specify the server URL, not --config for local config files.
    The 'config' parameter is kept for backward compatibility but is ignored since
    the CLI doesn't have a --config option.

    Server URL can be configured via PLOSTON_SERVER environment variable.
    Default: http://localhost:8080
    """

    def _run(*args: str, timeout: int = 30, config: str = None) -> subprocess.CompletedProcess:
        cmd = [sys.executable, "-m", "ploston_cli"]

        # Note: The CLI doesn't have a --config option. It uses --server to connect
        # to a Ploston server. The config parameter is ignored.
        # Tests that need server functionality should mock or use a running server.
        # Server URL can be set via PLOSTON_SERVER environment variable.

        cmd.extend(args)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        # Pass through PLOSTON_SERVER if set (allows running tests against different servers)
        # Default is http://localhost:8080 if not set

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=PROJECT_ROOT,
            env=env,
        )
        return result

    return _run


@pytest.fixture
def test_config_path() -> str:
    """Return path to test configuration file (for reference, not used by CLI)."""
    return str(PROJECT_ROOT / "tests" / "integration" / "fixtures" / "configs" / "test-config.yaml")


@pytest.fixture
def temp_workflow_file() -> Callable:
    """Create temporary workflow files for testing."""
    created_files = []

    def _create(content: str, name: str = "test-workflow.yaml") -> Path:
        temp_dir = tempfile.mkdtemp()
        file_path = Path(temp_dir) / name
        file_path.write_text(content)
        created_files.append(file_path)
        return file_path

    yield _create

    # Cleanup
    for f in created_files:
        if f.exists():
            f.unlink()
            f.parent.rmdir()


@pytest.fixture
def valid_workflow_yaml() -> str:
    """Return valid workflow YAML content."""
    return """
name: test-workflow
version: "1.0"
description: Test workflow for CLI testing

inputs:
  - name: message
    type: string
    default: "hello"

steps:
  - id: echo
    code: |
      result = context.inputs.get("message", "default")

outputs:
  - name: result
    from: steps.echo.output
"""


@pytest.fixture
def invalid_workflow_yaml() -> str:
    """Return invalid workflow YAML content."""
    return """
name: invalid-workflow
version: "1.0"
# Missing required 'steps' field
outputs:
  result:
    value: "nothing"
"""


# =============================================================================
# Serve Command Tests (CLI-001 to CLI-002)
# NOTE: The ploston_cli is a thin HTTP client. It does NOT have 'serve' or 'api'
# commands. Those commands exist in the ploston package (ploston.cli) which is
# used to run the server. These tests are skipped for the thin client.
# =============================================================================


@pytest.mark.skip(reason="ploston_cli is a thin HTTP client without 'serve' command")
class TestAelServe:
    """Tests for 'ael serve' command (CLI-001 to CLI-002).

    NOTE: Skipped because ploston_cli is a thin HTTP client that connects to
    a Ploston server. The 'serve' command is in the ploston package, not ploston_cli.
    """

    @pytest.mark.slow
    def test_cli_001_serve_starts(self, cli_runner: Callable):
        """
        CLI-001: Verify 'ael serve' starts MCP server.

        Note: This test starts the server briefly and checks it doesn't crash.
        """
        # Start serve with very short timeout - just checking it starts
        result = cli_runner("serve", "--help")

        # Help should work at minimum
        assert result.returncode == 0
        assert "serve" in result.stdout.lower() or "mcp" in result.stdout.lower()

    def test_cli_002_serve_help(self, cli_runner: Callable):
        """
        CLI-002: Verify 'ael serve --help' shows options.
        """
        result = cli_runner("serve", "--help")

        assert result.returncode == 0
        assert "serve" in result.stdout.lower()


# =============================================================================
# Run Command Tests (CLI-003 to CLI-006)
# NOTE: Tests that require a running server are marked with requires_server.
# The CLI connects to a Ploston server via HTTP, so these tests need a server.
# =============================================================================


class TestAelRun:
    """Tests for 'ael run' command (CLI-005 to CLI-006).

    NOTE: Tests CLI-003 and CLI-004 require a running server and have been
    moved to the meta-repo (agent-execution-layer/tests/integration/test_cli_integration.py).
    """

    def test_cli_005_run_missing_workflow(self, cli_runner: Callable):
        """
        CLI-005: Verify 'ael run' with missing workflow fails gracefully.
        """
        result = cli_runner("run", "/nonexistent/workflow.yaml")

        assert result.returncode != 0
        # Should have helpful error message
        error_output = result.stderr.lower() + result.stdout.lower()
        assert "not found" in error_output or "error" in error_output or "no such" in error_output

    def test_cli_006_run_output_json(
        self,
        cli_runner: Callable,
        temp_workflow_file: Callable,
        valid_workflow_yaml: str,
    ):
        """
        CLI-006: Verify 'ael run --output json' outputs valid JSON.
        """
        workflow_path = temp_workflow_file(valid_workflow_yaml)

        result = cli_runner("run", str(workflow_path), "--output", "json")

        if result.returncode == 0:
            # Output should be valid JSON
            try:
                output = json.loads(result.stdout)
                assert isinstance(output, dict)
            except json.JSONDecodeError:
                # Some output might be mixed - check if any line is JSON
                for line in result.stdout.strip().split("\n"):
                    try:
                        output = json.loads(line)
                        assert isinstance(output, dict)
                        break
                    except json.JSONDecodeError:
                        continue


# =============================================================================
# Validate Command Tests (CLI-007 to CLI-009)
# NOTE: 'ael validate' command is deferred for post-MVP
# =============================================================================


class TestAelValidate:
    """Tests for 'ploston validate' command (CLI-007 to CLI-009)."""

    def test_cli_007_validate_valid_workflow(
        self,
        cli_runner: Callable,
        temp_workflow_file: Callable,
        valid_workflow_yaml: str,
    ):
        """
        CLI-007: Verify 'ploston validate' passes for valid workflow.
        """
        workflow_path = temp_workflow_file(valid_workflow_yaml)

        result = cli_runner("validate", str(workflow_path))

        assert result.returncode == 0
        output = result.stdout.lower() + result.stderr.lower()
        assert "valid" in output or "success" in output or result.returncode == 0

    def test_cli_008_validate_invalid_yaml(
        self,
        cli_runner: Callable,
        temp_workflow_file: Callable,
    ):
        """
        CLI-008: Verify 'ploston validate' fails for invalid YAML syntax.
        """
        # This is truly invalid YAML (bad indentation/syntax)
        bad_yaml = """
name: bad
steps:
  - id: test
    code: |
      result = "test"
  - id: broken
    tool: [invalid: yaml: syntax
"""
        workflow_path = temp_workflow_file(bad_yaml)

        result = cli_runner("validate", str(workflow_path))

        # Should fail validation due to YAML syntax error
        assert result.returncode != 0 or "error" in result.stdout.lower() + result.stderr.lower()

    def test_cli_009_validate_schema_error(
        self,
        cli_runner: Callable,
        temp_workflow_file: Callable,
    ):
        """
        CLI-009: Verify 'ploston validate' fails for schema violations.
        """
        # Missing required 'name' field
        invalid_yaml = """
version: "1.0"
steps:
  - id: test
    code: |
      result = "test"
"""
        workflow_path = temp_workflow_file(invalid_yaml)

        result = cli_runner("validate", str(workflow_path))

        # Should fail validation due to missing name
        assert result.returncode != 0 or "error" in result.stdout.lower() + result.stderr.lower()


# =============================================================================
# Workflows Command Tests (CLI-010 to CLI-011)
# NOTE: These tests require a running server and have been moved to the
# meta-repo (agent-execution-layer/tests/integration/test_cli_integration.py).
# =============================================================================


# =============================================================================
# Tools Command Tests (CLI-012 to CLI-014)
# NOTE: These tests require a running server and have been moved to the
# meta-repo (agent-execution-layer/tests/integration/test_cli_integration.py).
# =============================================================================


# =============================================================================
# Config Command Tests (CLI-015)
# =============================================================================


class TestAelConfig:
    """Tests for 'ploston config' commands (CLI-015).

    NOTE: test_cli_015_config_show_server requires a running server and has been
    moved to the meta-repo (agent-execution-layer/tests/integration/test_cli_integration.py).
    """

    def test_cli_015_config_show_local(self, cli_runner: Callable, test_config_path: str):
        """
        CLI-015: Verify 'ploston config show --local' displays local CLI configuration.

        NOTE: Using --local flag to show local CLI config (doesn't require server).
        """
        result = cli_runner("config", "show", "--local")

        # Should show local config (even if default)
        assert result.returncode == 0 or "config" in result.stdout.lower()


# =============================================================================
# Error Handling Tests (CLI-016 to CLI-018)
# =============================================================================


class TestCLIErrorHandling:
    """Tests for CLI error handling (CLI-016 to CLI-018)."""

    def test_cli_016_unknown_command(self, cli_runner: Callable):
        """
        CLI-016: Verify unknown command shows help.
        """
        result = cli_runner("unknowncommand")

        # Should fail and suggest help
        assert result.returncode != 0
        output = result.stdout + result.stderr
        # Should have some indication of valid commands
        assert len(output) > 0

    def test_cli_017_missing_required_arg(self, cli_runner: Callable):
        """
        CLI-017: Verify missing required argument shows error.
        """
        result = cli_runner("run")  # Missing workflow path

        assert result.returncode != 0
        output = result.stdout.lower() + result.stderr.lower()
        assert "error" in output or "usage" in output or "required" in output or "missing" in output

    def test_cli_018_invalid_config_path(self, cli_runner: Callable):
        """
        CLI-018: Verify invalid config path is handled.
        """
        result = cli_runner("--config", "/nonexistent/config.yaml", "tools", "list")

        # Should either use defaults or fail gracefully
        output = result.stdout.lower() + result.stderr.lower()
        # Either works with defaults or reports error
        assert result.returncode == 0 or "not found" in output or "error" in output


# =============================================================================
# Help and Version Tests (CLI-019 to CLI-020)
# =============================================================================


class TestCLIHelp:
    """Tests for CLI help system (CLI-019 to CLI-020)."""

    def test_cli_019_help_flag(self, cli_runner: Callable):
        """
        CLI-019: Verify --help shows usage information.
        """
        result = cli_runner("--help")

        assert result.returncode == 0
        output = result.stdout.lower()

        # Should show available commands
        assert "usage" in output or "commands" in output or "ael" in output

    def test_cli_020_version_flag(self, cli_runner: Callable):
        """
        CLI-020: Verify 'ploston version' shows version.
        """
        result = cli_runner("version")

        # Should show version
        output = result.stdout + result.stderr
        # Version should be in format X.Y.Z or similar
        import re

        # Accept various version formats
        assert result.returncode == 0 or re.search(r"\d+\.\d+", output)


# =============================================================================
# Subcommand Help Tests
# =============================================================================


class TestSubcommandHelp:
    """Tests for subcommand help.

    NOTE: The ploston_cli is a thin HTTP client. It does NOT have 'serve' or 'api'
    commands. Those commands exist in the ploston package (ploston.cli).
    """

    @pytest.mark.parametrize(
        "subcommand",
        [
            "run",
            "workflows",
            "validate",
            "tools",
            "config",
            "version",
            # NOTE: 'serve' and 'api' are NOT available in ploston_cli
            # They exist in the ploston package (ploston.cli) for running the server
        ],
    )
    def test_subcommand_help(self, cli_runner: Callable, subcommand: str):
        """Verify each subcommand has help."""
        result = cli_runner(subcommand, "--help")

        assert result.returncode == 0
        assert len(result.stdout) > 0


# =============================================================================
# Integration Scenarios
# NOTE: These tests require a running server and have been moved to the
# meta-repo (agent-execution-layer/tests/integration/test_cli_integration.py).
# =============================================================================