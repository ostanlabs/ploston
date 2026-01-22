"""
Workflow Engine Integration Tests for AEL.

Test IDs: WF-001 to WF-020
Priority: P0 (Critical)

These tests verify the workflow execution functionality:
- Linear workflow execution
- Code step execution
- Tool step execution
- Step dependencies
- Timeout handling
- Retry logic
- Output handling

Prerequisites:
- Components 6-10 must be implemented
- Run after Milestone M4
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

# These imports will work once components are implemented
try:
    from ploston_core.engine import WorkflowEngine
    from ploston_core.errors import AELError, ErrorCategory
    from ploston_core.invoker import ToolCallResult, ToolInvoker
    from ploston_core.template import TemplateEngine
    from ploston_core.types import (
        BackoffType,
        ExecutionStatus,
        OnError,
        RetryConfig,
        StepStatus,
    )
    from ploston_core.workflow import (
        InputDefinition,
        OutputDefinition,
        StepDefinition,
        WorkflowDefinition,
        WorkflowRegistry,
    )

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.workflow,
]


def check_imports():
    if not IMPORTS_AVAILABLE:
        pytest.skip("AEL workflow engine module not yet implemented")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_workflow_registry() -> MagicMock:
    """Create mock workflow registry."""
    check_imports()
    registry = MagicMock(spec=WorkflowRegistry)
    return registry


@pytest.fixture
def mock_tool_invoker() -> MagicMock:
    """Create mock tool invoker that executes python_exec with real sandbox.

    This fixture creates a smart mock that:
    - Uses real PythonExecSandbox for python_exec calls (code steps)
    - Returns mock output for other tool calls (tool steps)

    This allows integration tests to verify actual code execution while
    mocking external tool dependencies.
    """
    check_imports()
    from ploston_core.sandbox import PythonExecSandbox

    # Create real sandbox for code execution
    sandbox = PythonExecSandbox(
        tool_caller=None,
        allowed_imports=None,  # Use defaults
        timeout=30,
    )

    async def smart_invoke(
        tool_name: str,
        arguments: dict = None,
        params: dict = None,
        timeout_seconds: int = None,
        step_id: str = None,
        execution_id: str = None,
    ) -> ToolCallResult:
        """Smart invoke that routes python_exec to real sandbox."""
        # Handle both 'arguments' and 'params' parameter names
        actual_params = arguments or params or {}

        if tool_name == "python_exec":
            # Execute code in real sandbox
            code = actual_params.get("code", "")
            context = actual_params.get("context", {})

            # Convert SandboxContext to dict if needed
            if hasattr(context, "inputs"):
                context = {"context": context}

            result = await sandbox.execute(code, context=context)

            return ToolCallResult(
                success=result.success,
                output=result.result,
                duration_ms=int(result.execution_time * 1000),
                tool_name="python_exec",
                error=result.error if not result.success else None,
            )
        else:
            # Mock other tools
            return ToolCallResult(
                success=True,
                output={"result": "mock_output"},
                duration_ms=100,
                tool_name=tool_name,
            )

    invoker = MagicMock(spec=ToolInvoker)
    invoker.invoke = AsyncMock(side_effect=smart_invoke)
    return invoker


@pytest.fixture
def mock_template_engine() -> TemplateEngine:
    """Create real template engine for integration tests.

    Using real TemplateEngine instead of mock because:
    1. This is an integration test - we want to test real behavior
    2. Template rendering is critical for workflow outputs
    3. Static values like "constant" should pass through unchanged
    """
    check_imports()
    return TemplateEngine()


@pytest.fixture
def simple_workflow() -> "WorkflowDefinition":
    """Create simple test workflow."""
    check_imports()
    return WorkflowDefinition(
        name="simple-workflow",
        version="1.0",
        description="Simple test workflow",
        inputs=[],
        steps=[
            StepDefinition(
                id="step_1",
                code="result = 'hello'",
            ),
            StepDefinition(
                id="step_2",
                code="result = context.steps['step_1'].output + ' world'",
            ),
        ],
        outputs=[
            OutputDefinition(name="message", from_path="steps.step_2.output"),
        ],
    )


@pytest.fixture
def tool_workflow() -> "WorkflowDefinition":
    """Create workflow with tool step."""
    check_imports()
    return WorkflowDefinition(
        name="tool-workflow",
        version="1.0",
        description="Workflow with tool step",
        inputs=[
            InputDefinition(name="url", type="string", required=True),
        ],
        steps=[
            StepDefinition(
                id="fetch",
                tool="http_request",
                params={
                    "method": "GET",
                    "url": "{{ inputs.url }}",
                },
            ),
            StepDefinition(
                id="process",
                code="result = len(context.steps['fetch'].output.get('body', ''))",
            ),
        ],
        outputs=[
            OutputDefinition(name="length", from_path="steps.process.output"),
        ],
    )


@pytest.fixture
def workflow_engine(
    mock_workflow_registry,
    mock_tool_invoker,
    mock_template_engine,
) -> "WorkflowEngine":
    """Create workflow engine with mocks."""
    check_imports()

    config = MagicMock()
    config.step_timeout = 30
    config.workflow_timeout = 300

    return WorkflowEngine(
        workflow_registry=mock_workflow_registry,
        tool_invoker=mock_tool_invoker,
        template_engine=mock_template_engine,
        config=config,
    )


# =============================================================================
# Linear Workflow Execution Tests (WF-001 to WF-003)
# =============================================================================


class TestLinearWorkflowExecution:
    """Tests for basic linear workflow execution (WF-001 to WF-003)."""

    @pytest.mark.asyncio
    async def test_wf_001_simple_linear_workflow(
        self,
        workflow_engine: "WorkflowEngine",
        simple_workflow: "WorkflowDefinition",
    ):
        """
        WF-001: Verify simple linear workflow executes all steps in order.
        """
        check_imports()

        result = await workflow_engine.execute_workflow(
            workflow=simple_workflow,
            inputs={},
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert len(result.steps) == 2
        assert result.steps[0].step_id == "step_1"
        assert result.steps[1].step_id == "step_2"

        # Verify execution order (step_2 after step_1)
        assert result.steps[0].completed_at <= result.steps[1].started_at

    @pytest.mark.asyncio
    async def test_wf_002_workflow_with_inputs(
        self,
        workflow_engine: "WorkflowEngine",
        mock_workflow_registry: MagicMock,
    ):
        """
        WF-002: Verify workflow receives and uses inputs correctly.
        """
        check_imports()

        workflow = WorkflowDefinition(
            name="input-workflow",
            version="1.0",
            inputs=[
                InputDefinition(name="name", type="string", required=True),
            ],
            steps=[
                StepDefinition(
                    id="greet",
                    code="result = f\"Hello, {context.inputs['name']}!\"",
                ),
            ],
            outputs=[
                OutputDefinition(name="greeting", from_path="steps.greet.output"),
            ],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={"name": "Alice"},
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.outputs["greeting"] == "Hello, Alice!"

    @pytest.mark.asyncio
    async def test_wf_003_workflow_outputs(
        self,
        workflow_engine: "WorkflowEngine",
    ):
        """
        WF-003: Verify workflow outputs are collected correctly.
        """
        check_imports()

        workflow = WorkflowDefinition(
            name="output-workflow",
            version="1.0",
            inputs=[],
            steps=[
                StepDefinition(
                    id="compute",
                    code="result = {'value': 42, 'name': 'answer'}",
                ),
            ],
            outputs=[
                OutputDefinition(name="the_value", from_path="steps.compute.output.value"),
                OutputDefinition(name="static", value="constant"),
            ],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.outputs["the_value"] == 42
        assert result.outputs["static"] == "constant"


# =============================================================================
# Code Step Execution Tests (WF-004 to WF-006)
# =============================================================================


class TestCodeStepExecution:
    """Tests for code step execution (WF-004 to WF-006)."""

    @pytest.mark.asyncio
    async def test_wf_004_code_step_basic(
        self,
        workflow_engine: "WorkflowEngine",
    ):
        """
        WF-004: Verify code step executes Python code correctly.
        """
        check_imports()

        workflow = WorkflowDefinition(
            name="code-workflow",
            version="1.0",
            inputs=[],
            steps=[
                StepDefinition(
                    id="compute",
                    code="""
import math
result = math.sqrt(16)
""",
                ),
            ],
            outputs=[
                OutputDefinition(name="result", from_path="steps.compute.output"),
            ],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.outputs["result"] == 4.0

    @pytest.mark.asyncio
    async def test_wf_005_code_step_access_inputs(
        self,
        workflow_engine: "WorkflowEngine",
    ):
        """
        WF-005: Verify code step can access workflow inputs.
        """
        check_imports()

        workflow = WorkflowDefinition(
            name="inputs-workflow",
            version="1.0",
            inputs=[
                InputDefinition(name="multiplier", type="integer", required=True),
            ],
            steps=[
                StepDefinition(
                    id="multiply",
                    code="result = context.inputs['multiplier'] * 10",
                ),
            ],
            outputs=[
                OutputDefinition(name="product", from_path="steps.multiply.output"),
            ],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={"multiplier": 5},
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.outputs["product"] == 50

    @pytest.mark.asyncio
    async def test_wf_006_code_step_access_previous_steps(
        self,
        workflow_engine: "WorkflowEngine",
    ):
        """
        WF-006: Verify code step can access previous step outputs.
        """
        check_imports()

        workflow = WorkflowDefinition(
            name="chain-workflow",
            version="1.0",
            inputs=[],
            steps=[
                StepDefinition(
                    id="step_a",
                    code="result = {'items': [1, 2, 3]}",
                ),
                StepDefinition(
                    id="step_b",
                    code="result = sum(context.steps['step_a'].output['items'])",
                ),
            ],
            outputs=[
                OutputDefinition(name="total", from_path="steps.step_b.output"),
            ],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.outputs["total"] == 6


# =============================================================================
# Tool Step Execution Tests (WF-007 to WF-009)
# =============================================================================


class TestToolStepExecution:
    """Tests for tool step execution (WF-007 to WF-009)."""

    @pytest.mark.asyncio
    async def test_wf_007_tool_step_basic(
        self,
        workflow_engine: "WorkflowEngine",
        mock_tool_invoker: MagicMock,
    ):
        """
        WF-007: Verify tool step invokes MCP tool correctly.

        Uses real template engine for integration testing.
        """
        check_imports()

        # Override mock_tool_invoker for this specific test to return tool output
        # (the fixture's smart_invoke handles python_exec, but we need to handle http_request)
        original_invoke = mock_tool_invoker.invoke.side_effect

        async def tool_invoke(tool_name, **kwargs):
            if tool_name == "http_request":
                return ToolCallResult(
                    success=True,
                    output={"body": "response content", "status": 200},
                    duration_ms=150,
                    tool_name="http_request",
                )
            # Fall back to original smart_invoke for python_exec
            return await original_invoke(tool_name, **kwargs)

        mock_tool_invoker.invoke = AsyncMock(side_effect=tool_invoke)

        workflow = WorkflowDefinition(
            name="tool-workflow",
            version="1.0",
            inputs=[],
            steps=[
                StepDefinition(
                    id="fetch",
                    tool="http_request",
                    params={"method": "GET", "url": "https://example.com"},
                ),
            ],
            outputs=[
                OutputDefinition(name="status", from_path="steps.fetch.output.status"),
            ],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},
        )

        assert result.status == ExecutionStatus.COMPLETED
        mock_tool_invoker.invoke.assert_called_once()
        assert result.outputs["status"] == 200

    @pytest.mark.asyncio
    async def test_wf_008_tool_step_with_templates(
        self,
        workflow_engine: "WorkflowEngine",
        mock_tool_invoker: MagicMock,
    ):
        """
        WF-008: Verify tool step parameters support templates.

        Uses real template engine for integration testing.
        The template {{ inputs.url }} should be rendered to the actual input value.
        """
        check_imports()

        # Override mock_tool_invoker to capture the rendered params
        captured_params = {}
        original_invoke = mock_tool_invoker.invoke.side_effect

        async def capturing_invoke(tool_name, **kwargs):
            if tool_name == "http_request":
                # Capture the params that were passed (after template rendering)
                captured_params.update(kwargs.get("arguments", kwargs.get("params", {})))
                return ToolCallResult(
                    success=True,
                    output={"body": "content"},
                    duration_ms=100,
                    tool_name="http_request",
                )
            return await original_invoke(tool_name, **kwargs)

        mock_tool_invoker.invoke = AsyncMock(side_effect=capturing_invoke)

        workflow = WorkflowDefinition(
            name="template-workflow",
            version="1.0",
            inputs=[InputDefinition(name="url", type="string", required=True)],
            steps=[
                StepDefinition(
                    id="fetch",
                    tool="http_request",
                    params={"method": "GET", "url": "{{ inputs.url }}"},
                ),
            ],
            outputs=[],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={"url": "https://rendered-url.com"},
        )

        assert result.status == ExecutionStatus.COMPLETED
        # Verify template was rendered - the url should be the actual input value
        assert captured_params.get("url") == "https://rendered-url.com"

    @pytest.mark.asyncio
    async def test_wf_009_tool_step_error_handling(
        self,
        workflow_engine: "WorkflowEngine",
        mock_tool_invoker: MagicMock,
    ):
        """
        WF-009: Verify tool step handles tool errors correctly.
        """
        check_imports()

        # Setup mock to return error
        mock_tool_invoker.invoke = AsyncMock(
            return_value=ToolCallResult(
                success=False,
                output=None,
                duration_ms=50,
                tool_name="http_request",
                error=AELError(
                    code="TOOL_FAILED",
                    category=ErrorCategory.EXECUTION,
                    message="Connection refused",
                ),
            )
        )

        workflow = WorkflowDefinition(
            name="error-workflow",
            version="1.0",
            inputs=[],
            steps=[
                StepDefinition(
                    id="failing_step",
                    tool="http_request",
                    params={},
                    on_error=OnError.FAIL,
                ),
            ],
            outputs=[],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},
        )

        assert result.status == ExecutionStatus.FAILED
        assert result.error is not None


# =============================================================================
# Step Dependencies Tests (WF-010 to WF-011)
# =============================================================================


class TestStepDependencies:
    """Tests for step dependencies (WF-010 to WF-011)."""

    @pytest.mark.asyncio
    async def test_wf_010_implicit_dependencies(
        self,
        workflow_engine: "WorkflowEngine",
    ):
        """
        WF-010: Verify implicit dependencies (order-based) work.
        """
        check_imports()

        # We'll use code steps that record their execution
        workflow = WorkflowDefinition(
            name="order-workflow",
            version="1.0",
            inputs=[],
            steps=[
                StepDefinition(id="step_1", code="result = 1"),
                StepDefinition(id="step_2", code="result = 2"),
                StepDefinition(id="step_3", code="result = 3"),
            ],
            outputs=[],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},
        )

        assert result.status == ExecutionStatus.COMPLETED

        # Verify order from timestamps
        step_1 = result.steps[0]
        step_2 = result.steps[1]
        step_3 = result.steps[2]

        assert step_1.completed_at <= step_2.started_at
        assert step_2.completed_at <= step_3.started_at

    @pytest.mark.asyncio
    async def test_wf_011_explicit_dependencies(
        self,
        workflow_engine: "WorkflowEngine",
    ):
        """
        WF-011: Verify explicit depends_on works correctly.
        """
        check_imports()

        workflow = WorkflowDefinition(
            name="deps-workflow",
            version="1.0",
            inputs=[],
            steps=[
                StepDefinition(id="step_a", code="result = 'A'"),
                StepDefinition(id="step_b", code="result = 'B'"),
                StepDefinition(
                    id="step_c",
                    depends_on=["step_a", "step_b"],
                    code="result = context.steps['step_a'].output + context.steps['step_b'].output",
                ),
            ],
            outputs=[
                OutputDefinition(name="combined", from_path="steps.step_c.output"),
            ],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.outputs["combined"] == "AB"


# =============================================================================
# Timeout Handling Tests (WF-012)
# =============================================================================


class TestTimeoutHandling:
    """Tests for timeout handling (WF-012)."""

    @pytest.mark.asyncio
    async def test_wf_012_step_timeout(
        self,
        workflow_engine: "WorkflowEngine",
        mock_tool_invoker: MagicMock,
    ):
        """
        WF-012: Verify step timeout is enforced.

        Note: This test uses a mock that simulates timeout behavior because
        the sandbox's asyncio.wait_for cannot interrupt blocking code like
        time.sleep(). In production, timeouts would be enforced at the
        process level.
        """
        check_imports()

        # Mock tool invoker to simulate timeout
        mock_tool_invoker.invoke = AsyncMock(
            return_value=ToolCallResult(
                success=False,
                output=None,
                duration_ms=2000,
                tool_name="python_exec",
                error=AELError(
                    code="TIMEOUT",
                    category=ErrorCategory.EXECUTION,
                    message="Execution timeout after 2s",
                    retryable=True,
                ),
            )
        )

        workflow = WorkflowDefinition(
            name="timeout-workflow",
            version="1.0",
            inputs=[],
            steps=[
                StepDefinition(
                    id="slow_step",
                    code="result = 'done'",  # Code doesn't matter, mock handles it
                    timeout=2,  # 2 second timeout
                ),
            ],
            outputs=[],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},
        )

        assert result.status == ExecutionStatus.FAILED
        assert result.error is not None
        # Error should mention timeout
        error_msg = str(result.error).lower()
        assert "timeout" in error_msg


# =============================================================================
# Retry Logic Tests (WF-013 to WF-014)
# =============================================================================


class TestRetryLogic:
    """Tests for retry logic (WF-013 to WF-014)."""

    @pytest.mark.asyncio
    async def test_wf_013_step_retry_on_failure(
        self,
        workflow_engine: "WorkflowEngine",
        mock_tool_invoker: MagicMock,
    ):
        """
        WF-013: Verify step retry on failure.
        """
        check_imports()

        # First two calls fail, third succeeds
        call_count = 0

        async def failing_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return ToolCallResult(
                    success=False,
                    output=None,
                    duration_ms=50,
                    tool_name="flaky_tool",
                    error=AELError(
                        code="TOOL_FAILED",
                        category=ErrorCategory.EXECUTION,
                        message="Temporary failure",
                        retryable=True,
                    ),
                )
            return ToolCallResult(
                success=True,
                output={"result": "success"},
                duration_ms=100,
                tool_name="flaky_tool",
            )

        mock_tool_invoker.invoke = AsyncMock(side_effect=failing_then_success)

        workflow = WorkflowDefinition(
            name="retry-workflow",
            version="1.0",
            inputs=[],
            steps=[
                StepDefinition(
                    id="flaky_step",
                    tool="flaky_tool",
                    params={},
                    on_error=OnError.RETRY,
                    retry=RetryConfig(
                        max_attempts=5,
                        backoff=BackoffType.FIXED,
                        delay_seconds=0.1,
                    ),
                ),
            ],
            outputs=[
                OutputDefinition(name="result", from_path="steps.flaky_step.output.result"),
            ],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert call_count == 3  # Failed twice, succeeded on third

        # Step should show retry info
        step = result.steps[0]
        assert step.attempt == 3
        assert step.max_attempts == 5

    @pytest.mark.asyncio
    async def test_wf_014_retry_exhausted(
        self,
        workflow_engine: "WorkflowEngine",
        mock_tool_invoker: MagicMock,
    ):
        """
        WF-014: Verify workflow fails when retries are exhausted.
        """
        check_imports()

        # Always fail
        mock_tool_invoker.invoke = AsyncMock(
            return_value=ToolCallResult(
                success=False,
                output=None,
                duration_ms=50,
                tool_name="failing_tool",
                error=AELError(
                    code="TOOL_FAILED",
                    category=ErrorCategory.EXECUTION,
                    message="Always fails",
                    retryable=True,
                ),
            )
        )

        workflow = WorkflowDefinition(
            name="fail-workflow",
            version="1.0",
            inputs=[],
            steps=[
                StepDefinition(
                    id="always_fails",
                    tool="failing_tool",
                    params={},
                    on_error=OnError.RETRY,
                    retry=RetryConfig(
                        max_attempts=3,
                        backoff=BackoffType.FIXED,
                        delay_seconds=0.1,
                    ),
                ),
            ],
            outputs=[],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},
        )

        assert result.status == ExecutionStatus.FAILED
        assert mock_tool_invoker.invoke.call_count == 3


# =============================================================================
# Error Handling Tests (WF-015)
# =============================================================================


class TestErrorHandling:
    """Tests for error handling (WF-015)."""

    @pytest.mark.asyncio
    async def test_wf_015_on_error_skip(
        self,
        workflow_engine: "WorkflowEngine",
    ):
        """
        WF-015: Verify on_error: skip continues workflow.
        """
        check_imports()

        workflow = WorkflowDefinition(
            name="skip-workflow",
            version="1.0",
            inputs=[],
            steps=[
                StepDefinition(
                    id="failing_step",
                    code="raise ValueError('intentional error')",
                    on_error=OnError.SKIP,
                ),
                StepDefinition(
                    id="next_step",
                    code="result = 'continued'",
                ),
            ],
            outputs=[
                OutputDefinition(name="result", from_path="steps.next_step.output"),
            ],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},
        )

        # Workflow should complete (not fail)
        assert result.status == ExecutionStatus.COMPLETED

        # First step should be skipped
        assert result.steps[0].status == StepStatus.SKIPPED

        # Second step should complete
        assert result.steps[1].status == StepStatus.COMPLETED
        assert result.outputs["result"] == "continued"


# =============================================================================
# Input Validation Tests (WF-016 to WF-018)
# =============================================================================


class TestInputValidation:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_wf_016_missing_required_input(
        self,
        workflow_engine: "WorkflowEngine",
    ):
        """
        WF-016: Verify missing required input fails validation.

        Note: The workflow engine returns a FAILED result with error info
        rather than raising an exception. This allows callers to handle
        validation errors uniformly with execution errors.
        """
        check_imports()

        workflow = WorkflowDefinition(
            name="required-workflow",
            version="1.0",
            inputs=[
                InputDefinition(name="required_param", type="string", required=True),
            ],
            steps=[
                StepDefinition(id="step", code="result = 1"),
            ],
            outputs=[],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},  # Missing required_param
        )

        # Validation errors result in FAILED status with error info
        assert result.status == ExecutionStatus.FAILED
        assert result.error is not None
        error_str = str(result.error).lower()
        assert "input" in error_str or "required" in error_str

    @pytest.mark.asyncio
    async def test_wf_017_default_input_used(
        self,
        workflow_engine: "WorkflowEngine",
    ):
        """
        WF-017: Verify default input value is used when not provided.
        """
        check_imports()

        workflow = WorkflowDefinition(
            name="default-workflow",
            version="1.0",
            inputs=[
                InputDefinition(name="value", type="integer", required=False, default=42),
            ],
            steps=[
                StepDefinition(
                    id="use_default",
                    code="result = context.inputs.get('value', 0)",
                ),
            ],
            outputs=[
                OutputDefinition(name="value", from_path="steps.use_default.output"),
            ],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},  # Not providing 'value'
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.outputs["value"] == 42


# =============================================================================
# Execution Result Tests
# =============================================================================


class TestExecutionResult:
    """Tests for execution result structure."""

    @pytest.mark.asyncio
    async def test_execution_id_generated(
        self,
        workflow_engine: "WorkflowEngine",
        simple_workflow: "WorkflowDefinition",
    ):
        """Verify execution ID is generated."""
        check_imports()

        result = await workflow_engine.execute_workflow(
            workflow=simple_workflow,
            inputs={},
        )

        assert result.execution_id is not None
        assert result.execution_id.startswith("exec-")

    @pytest.mark.asyncio
    async def test_timing_captured(
        self,
        workflow_engine: "WorkflowEngine",
        simple_workflow: "WorkflowDefinition",
    ):
        """Verify timing information is captured."""
        check_imports()

        result = await workflow_engine.execute_workflow(
            workflow=simple_workflow,
            inputs={},
        )

        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.duration_ms is not None
        assert result.duration_ms >= 0
        assert result.completed_at >= result.started_at

    @pytest.mark.asyncio
    async def test_step_counts(
        self,
        workflow_engine: "WorkflowEngine",
    ):
        """Verify step counts are accurate."""
        check_imports()

        workflow = WorkflowDefinition(
            name="counts-workflow",
            version="1.0",
            inputs=[],
            steps=[
                StepDefinition(id="step_1", code="result = 1"),
                StepDefinition(id="step_2", code="raise ValueError('fail')", on_error=OnError.SKIP),
                StepDefinition(id="step_3", code="result = 3"),
            ],
            outputs=[],
        )

        result = await workflow_engine.execute_workflow(
            workflow=workflow,
            inputs={},
        )

        assert result.steps_completed == 2
        assert result.steps_skipped == 1
        assert result.steps_failed == 0  # Skipped, not failed
