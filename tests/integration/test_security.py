"""
Security Integration Tests for AEL.

Test IDs: SEC-001 to SEC-012
Priority: P0 (Critical)

These tests verify the security controls of the Python execution sandbox:
- Import restrictions
- Builtin restrictions
- Rate limiting
- Resource limits
- Code injection prevention

Prerequisites:
- Components 8 (Sandbox) and 9 (Invoker) must be implemented
- Run after Milestone M3
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# These imports will work once components are implemented
# For now, we use try/except to allow test discovery
try:
    from ploston_core.sandbox import (
        CodeExecutionResult,
        PythonExecSandbox,
        SandboxConfig,
        SandboxContext,
        ToolCallInterface,
    )
    from ploston_core.types import StepOutput

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    # Define placeholders for type hints
    PythonExecSandbox = None
    SandboxConfig = None
    SandboxContext = None
    CodeExecutionResult = None


pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
]


# Skip all tests if imports not available
def check_imports():
    if not IMPORTS_AVAILABLE:
        pytest.skip("AEL sandbox module not yet implemented")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sandbox_config() -> "SandboxConfig":
    """Create default sandbox configuration."""
    check_imports()
    return SandboxConfig(
        timeout=30,
        max_tool_calls=10,
        allowed_imports=None,  # Use defaults
    )


@pytest.fixture
def mock_tool_caller() -> AsyncMock:
    """Create mock tool caller that always succeeds."""
    caller = AsyncMock()
    caller.call = AsyncMock(return_value={"result": "mock_result"})
    return caller


@pytest.fixture
def sandbox_context(mock_tool_caller) -> "SandboxContext":
    """Create sandbox context with mock tools."""
    check_imports()
    return SandboxContext(
        inputs={"test_input": "test_value"},
        steps={},
        config={"test_config": "config_value"},
        tools=ToolCallInterface(
            tool_caller=mock_tool_caller,
            max_calls=10,
            blocked_tools=["python_exec"],
        ),
    )


@pytest.fixture
def sandbox_context_dict(sandbox_context) -> dict:
    """Convert SandboxContext to dict for MVP implementation.

    NOTE: MVP implementation of PythonExecSandbox.execute() accepts dict[str, Any]
    instead of SandboxContext object as per spec. See MVP_SPEC_DEVIATIONS.md.
    """
    return {"context": sandbox_context}


@pytest.fixture
def sandbox(sandbox_config) -> "PythonExecSandbox":
    """Create sandbox instance."""
    check_imports()
    return PythonExecSandbox(
        tool_caller=None,
        allowed_imports=set(sandbox_config.allowed_imports)
        if sandbox_config.allowed_imports
        else None,
        timeout=sandbox_config.timeout,
        max_output_size=1024 * 1024,  # 1MB default
    )


# =============================================================================
# Import Restriction Tests (SEC-001 to SEC-004)
# =============================================================================


class TestImportRestrictions:
    """Tests for import restriction enforcement (SEC-001 to SEC-004)."""

    @pytest.mark.parametrize(
        "blocked_module",
        [
            "os",
            "sys",
            "subprocess",
            "socket",
            "shutil",
            "ctypes",
            "multiprocessing",
            "threading",
            "signal",
            "pty",
            "fcntl",
        ],
    )
    @pytest.mark.asyncio
    async def test_sec_001_blocked_imports(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_context_dict: dict,
        blocked_module: str,
    ):
        """
        SEC-001: Verify dangerous imports are blocked.

        Security Requirement: Only whitelisted imports are allowed.
        """
        check_imports()

        code = f"""
import {blocked_module}
result = "imported successfully"
"""
        result = await sandbox.execute(code, sandbox_context_dict)

        assert result.success is False, f"Import of '{blocked_module}' should be blocked"
        assert result.error is not None
        # Error should mention import restriction
        error_msg = str(result.error).lower()
        assert "import" in error_msg or "restricted" in error_msg or "not allowed" in error_msg

    @pytest.mark.parametrize(
        "from_import",
        [
            ("os", "system"),
            ("os", "popen"),
            ("os", "listdir"),
            ("subprocess", "Popen"),
            ("subprocess", "run"),
            ("subprocess", "call"),
            ("socket", "socket"),
            ("shutil", "rmtree"),
            ("shutil", "copy"),
        ],
    )
    @pytest.mark.asyncio
    async def test_sec_002_blocked_from_imports(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_context_dict: dict,
        from_import: tuple,
    ):
        """
        SEC-002: Verify 'from X import Y' style imports are blocked.
        """
        check_imports()

        module, name = from_import
        code = f"""
from {module} import {name}
result = "imported successfully"
"""
        result = await sandbox.execute(code, sandbox_context_dict)

        assert result.success is False, f"from {module} import {name} should be blocked"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_sec_003_dunder_import_blocked(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_context_dict: dict,
    ):
        """
        SEC-003: Verify __import__ is blocked.
        """
        check_imports()

        code = """
os = __import__('os')
result = os.getcwd()
"""
        result = await sandbox.execute(code, sandbox_context_dict)

        assert result.success is False, "__import__ should be blocked"
        assert result.error is not None

    @pytest.mark.parametrize(
        "allowed_module",
        [
            "json",
            "re",
            "math",
            "datetime",
            "typing",
            "collections",
            "itertools",
            "functools",
            "hashlib",
            "uuid",
            # Note: base64 is NOT in default allowed imports per spec
        ],
    )
    @pytest.mark.asyncio
    async def test_sec_004_allowed_imports(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_context_dict: dict,
        allowed_module: str,
    ):
        """
        SEC-004: Verify safe imports are allowed.
        """
        check_imports()

        code = f"""
import {allowed_module}
result = "imported {allowed_module}"
"""
        result = await sandbox.execute(code, sandbox_context_dict)

        assert result.success is True, f"Import of '{allowed_module}' should be allowed"
        assert result.result == f"imported {allowed_module}"


# =============================================================================
# Builtin Restriction Tests (SEC-005 to SEC-008)
# =============================================================================


class TestBuiltinRestrictions:
    """Tests for builtin function restrictions (SEC-005 to SEC-008)."""

    @pytest.mark.asyncio
    async def test_sec_005_eval_blocked(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_context_dict: dict,
    ):
        """
        SEC-005: Verify eval() is blocked.
        """
        check_imports()

        code = """
result = eval('1 + 1')
"""
        result = await sandbox.execute(code, sandbox_context_dict)

        assert result.success is False, "eval() should be blocked"
        assert result.error is not None
        error_msg = str(result.error).lower()
        assert "eval" in error_msg or "builtin" in error_msg or "not allowed" in error_msg

    @pytest.mark.asyncio
    async def test_sec_006_exec_blocked(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_context_dict: dict,
    ):
        """
        SEC-006: Verify exec() is blocked.
        """
        check_imports()

        code = """
exec('x = 42')
result = x
"""
        result = await sandbox.execute(code, sandbox_context_dict)

        assert result.success is False, "exec() should be blocked"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_sec_007_compile_blocked(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_context_dict: dict,
    ):
        """
        SEC-007: Verify compile() is blocked.
        """
        check_imports()

        code = """
code_obj = compile('x = 1', '<string>', 'exec')
result = code_obj
"""
        result = await sandbox.execute(code, sandbox_context_dict)

        assert result.success is False, "compile() should be blocked"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_sec_008_open_blocked(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_context_dict: dict,
    ):
        """
        SEC-008: Verify open() is blocked.
        """
        check_imports()

        code = """
with open('/etc/passwd', 'r') as f:
    result = f.read()
"""
        result = await sandbox.execute(code, sandbox_context_dict)

        assert result.success is False, "open() should be blocked"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_sec_008b_globals_blocked(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_context_dict: dict,
    ):
        """
        SEC-008b: Verify globals() is blocked.
        """
        check_imports()

        code = """
result = globals()
"""
        result = await sandbox.execute(code, sandbox_context_dict)

        assert result.success is False, "globals() should be blocked"

    @pytest.mark.asyncio
    async def test_sec_008c_locals_blocked(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_context_dict: dict,
    ):
        """
        SEC-008c: Verify locals() is blocked.
        """
        check_imports()

        code = """
result = locals()
"""
        result = await sandbox.execute(code, sandbox_context_dict)

        assert result.success is False, "locals() should be blocked"


# =============================================================================
# Rate Limiting Tests (SEC-009)
# =============================================================================


class TestRateLimiting:
    """Tests for rate limiting enforcement (SEC-009)."""

    @pytest.mark.asyncio
    async def test_sec_009_tool_call_rate_limiting(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_config: "SandboxConfig",
    ):
        """
        SEC-009: Verify rate limiting prevents excessive tool calls.

        Security Requirement: Max tool calls per execution (default 10).

        Note: The sandbox uses exec() which doesn't support top-level await.
        This test verifies the ToolCallInterface rate limiting directly.
        """
        check_imports()

        # Create a tool caller that counts calls
        call_count = 0

        async def counting_caller(tool_name: str, params: dict[str, Any]) -> Any:
            nonlocal call_count
            call_count += 1
            return {"count": call_count}

        mock_caller = MagicMock()
        mock_caller.call = counting_caller

        # Create ToolCallInterface with low limit
        tool_interface = ToolCallInterface(
            tool_caller=mock_caller,
            max_calls=5,  # Low limit for testing
            blocked_tools=["python_exec"],
        )

        # Verify rate limiting works by calling directly

        results = []
        error_raised = False
        error_msg = ""

        for i in range(10):
            try:
                r = await tool_interface.call("test_tool", {"i": i})
                results.append(r)
            except Exception as e:
                error_raised = True
                error_msg = str(e).lower()
                break

        # Should have stopped after max_calls
        assert error_raised, "Should have raised error after max calls"
        assert len(results) <= 5, f"Should have stopped at 5 calls, got {len(results)}"
        assert (
            "rate" in error_msg
            or "limit" in error_msg
            or "exhausted" in error_msg
            or "max" in error_msg
            or "exceeded" in error_msg
        )


# =============================================================================
# Resource Limit Tests (SEC-010 to SEC-011)
# =============================================================================


class TestResourceLimits:
    """Tests for resource limit enforcement (SEC-010 to SEC-011)."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.timeout(20)
    async def test_sec_010_timeout_enforcement(
        self,
        sandbox_context_dict: dict,
    ):
        """
        SEC-010: Verify the wall-clock timeout HARD-KILLS a blocking infinite
        loop (CR-1 process isolation).

        Before CR-1 the sandbox ran code in-process via ``asyncio.wait_for``,
        which cannot interrupt ``while True: pass`` — the event loop never gets
        control, so the "timeout" never fires and the process hangs. With
        process isolation the parent SIGKILLs the child when the deadline
        passes. The ``@pytest.mark.timeout`` turns any regression to the old
        behaviour (a hang) into a hard failure rather than an infinite run.
        """
        check_imports()

        config = SandboxConfig(timeout=2, max_tool_calls=10)
        sandbox = PythonExecSandbox(
            tool_caller=None,
            allowed_imports=set(config.allowed_imports) if config.allowed_imports else None,
            timeout=config.timeout,
            max_output_size=1024 * 1024,
        )

        import time as _time

        code = "while True:\n    pass\n"
        start = _time.perf_counter()
        result = await sandbox.execute(code, context=sandbox_context_dict)
        elapsed = _time.perf_counter() - start

        assert result.success is False, "Infinite loop must be aborted, not succeed"
        assert result.error is not None
        assert "timeout" in result.error.lower()
        # Must abort within a few seconds of the 2s budget (i.e. be hard-killed).
        assert elapsed < 10, f"Took {elapsed:.1f}s — timeout did not hard-kill the child"

    @pytest.mark.asyncio
    @pytest.mark.timeout(20)
    async def test_sec_010b_cpu_intensive_timeout(
        self,
        sandbox_context_dict: dict,
    ):
        """
        SEC-010b: Verify a CPU-bound busy loop (no awaits) is interrupted by
        the wall-clock timeout via process isolation (CR-1).
        """
        check_imports()

        config = SandboxConfig(timeout=2, max_tool_calls=10)
        sandbox = PythonExecSandbox(
            tool_caller=None,
            allowed_imports=set(config.allowed_imports) if config.allowed_imports else None,
            timeout=config.timeout,
            max_output_size=1024 * 1024,
        )

        import time as _time

        # Heavy CPU loop with no opportunity for the event loop to preempt.
        code = "n = 0\nwhile n < 10**18:\n    n += 1\nresult = n\n"
        start = _time.perf_counter()
        result = await sandbox.execute(code, context=sandbox_context_dict)
        elapsed = _time.perf_counter() - start

        assert result.success is False, "CPU-bound loop must be aborted"
        assert result.error is not None
        assert "timeout" in result.error.lower()
        assert elapsed < 10, f"Took {elapsed:.1f}s — CPU loop was not interrupted"


# =============================================================================
# Recursion Prevention Tests (SEC-011)
# =============================================================================


class TestRecursionPrevention:
    """Tests for python_exec recursion prevention."""

    @pytest.mark.asyncio
    async def test_sec_011_python_exec_recursion_blocked(
        self,
        sandbox_context_dict: dict,
    ):
        """
        SEC-011: Verify python_exec cannot call itself.

        Security Requirement: Prevent infinite recursion attacks.

        Note: The sandbox uses exec() which doesn't support top-level await.
        This test verifies that python_exec is in the blocked_tools list
        of the ToolCallInterface.
        """
        check_imports()

        # Create a tool caller that would allow calls
        async def mock_caller(tool_name: str, params: dict[str, Any]) -> Any:
            return {"result": "called"}

        mock_tool_caller = MagicMock()
        mock_tool_caller.call = mock_caller

        # Create context with python_exec blocked
        tool_interface = ToolCallInterface(
            tool_caller=mock_tool_caller,
            max_calls=10,
            blocked_tools=["python_exec"],  # python_exec is blocked
        )

        # Verify python_exec is in blocked tools (using private attribute)
        assert "python_exec" in tool_interface._blocked_tools

        # The ToolCallInterface should reject python_exec calls
        error_raised = False
        error_msg = ""
        try:
            await tool_interface.call("python_exec", {"code": "result = 42"})
            # If we get here, the call wasn't blocked
            raise AssertionError("python_exec call should have been blocked")
        except Exception as e:
            error_raised = True
            error_msg = str(e).lower()

        assert error_raised, "Should have raised error for blocked tool"
        assert "blocked" in error_msg or "python_exec" in error_msg or "not allowed" in error_msg


# =============================================================================
# Code Validation Tests (SEC-012)
# =============================================================================


class TestCodeValidation:
    """Tests for code validation without execution."""

    def test_sec_012_validate_valid_code(self, sandbox: "PythonExecSandbox"):
        """
        SEC-012a: Verify valid code passes validation.
        """
        check_imports()

        code = """
import json
data = {"key": "value"}
result = json.dumps(data)
"""
        errors = sandbox.validate_code(code)
        assert len(errors) == 0, f"Valid code should pass validation, got errors: {errors}"

    def test_sec_012_validate_blocked_import(self, sandbox: "PythonExecSandbox"):
        """
        SEC-012b: Verify blocked import is caught in validation.
        """
        check_imports()

        code = """
import os
result = os.getcwd()
"""
        errors = sandbox.validate_code(code)
        assert len(errors) > 0, "Blocked import should be caught in validation"
        assert any("os" in err.lower() or "import" in err.lower() for err in errors)

    def test_sec_012_validate_syntax_error(self, sandbox: "PythonExecSandbox"):
        """
        SEC-012c: Verify syntax errors are caught in validation.
        """
        check_imports()

        code = """
def broken(
    # Missing closing paren and body
"""
        errors = sandbox.validate_code(code)
        assert len(errors) > 0, "Syntax error should be caught"

    @pytest.mark.parametrize(
        "injection_code",
        [
            # Real injected statements (not string literals): each attempts a
            # sandbox escape and MUST be blocked, either at static validation
            # (errors returned) or at execution (result.success is False).
            "import os\nresult = os.system('ls')\n",
            "result = __import__('os').system('ls')\n",
            "result = eval(\"__import__('os').system('ls')\")\n",
            "result = open('/etc/passwd').read()\n",
        ],
    )
    @pytest.mark.asyncio
    @pytest.mark.timeout(20)
    async def test_sec_012_injection_patterns(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_context_dict: dict,
        injection_code: str,
    ):
        """
        SEC-012d: Verify injection patterns are actually BLOCKED.

        Previously this test called ``validate_code`` and asserted nothing —
        a false green. We now assert each attack is rejected: blocked at
        static validation (non-empty errors) OR fails at execution time
        (``result.success is False``). Either way the escape never runs.
        """
        check_imports()

        # Static validation should flag most of these (os import, __import__,
        # eval, open). If it does, that alone proves the gate works.
        errors = sandbox.validate_code(injection_code)

        # And execution must never succeed regardless.
        result = await sandbox.execute(injection_code, context=sandbox_context_dict)

        assert errors or (result.success is False), (
            f"Injection must be blocked but slipped through: {injection_code!r} "
            f"(errors={errors}, success={result.success})"
        )


# =============================================================================
# Context Access Tests
# =============================================================================


class TestContextAccess:
    """Tests for secure context access."""

    @pytest.mark.asyncio
    async def test_context_inputs_accessible(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_context_dict: dict,
    ):
        """Verify inputs are accessible in code."""
        check_imports()

        code = """
result = context.inputs.get("test_input")
"""
        result = await sandbox.execute(code, sandbox_context_dict)

        assert result.success is True
        assert result.result == "test_value"

    @pytest.mark.asyncio
    async def test_context_config_accessible(
        self,
        sandbox: "PythonExecSandbox",
        sandbox_context_dict: dict,
    ):
        """Verify config is accessible in code."""
        check_imports()

        code = """
result = context.config.get("test_config")
"""
        result = await sandbox.execute(code, sandbox_context_dict)

        assert result.success is True
        assert result.result == "config_value"

    @pytest.mark.asyncio
    async def test_context_steps_accessible(
        self,
        sandbox: "PythonExecSandbox",
        mock_tool_caller,
    ):
        """Verify previous step outputs are accessible."""
        check_imports()

        # Create context with previous step output
        sandbox_context = SandboxContext(
            inputs={},
            steps={
                "previous_step": StepOutput(
                    output={"data": "from_previous"},
                    success=True,
                    duration_ms=100,
                    step_id="previous_step",
                ),
            },
            config={},
            tools=ToolCallInterface(
                tool_caller=mock_tool_caller,
                max_calls=10,
                blocked_tools=["python_exec"],
            ),
        )

        # Convert to dict for MVP implementation
        context_dict = {"context": sandbox_context}

        code = """
result = context.steps["previous_step"].output["data"]
"""
        result = await sandbox.execute(code, context=context_dict)

        assert result.success is True
        assert result.result == "from_previous"
