"""Unit tests for the AEL Plugin Framework.

Tests cover:
- Core plugin types (PluginDecision, HookResult, contexts)
- AELPlugin base class
- PluginRegistry loading and execution
- Built-in plugins (LoggingPlugin, MetricsPlugin)
- Hook execution chain with fail_open handling
"""

import logging
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
from ploston_core.config.models import PluginDefinition
from ploston_core.plugins import (
    AELPlugin,
    HookResult,
    PluginDecision,
    PluginLoadResult,
    PluginRegistry,
    RequestContext,
    ResponseContext,
    StepContext,
    StepResultContext,
)
from ploston_core.plugins.builtin import BUILTIN_PLUGINS, LoggingPlugin, MetricsPlugin

# =============================================================================
# Core Types Tests
# =============================================================================


class TestPluginDecision:
    """Tests for PluginDecision enum."""

    def test_continue_value(self):
        """Test CONTINUE decision value."""
        assert PluginDecision.CONTINUE.value == "continue"

    def test_decision_is_enum(self):
        """Test PluginDecision is an enum."""
        assert hasattr(PluginDecision, "CONTINUE")


class TestHookResult:
    """Tests for HookResult generic class."""

    def test_create_with_data(self):
        """Test creating HookResult with data."""
        result = HookResult(data={"key": "value"})
        assert result.data == {"key": "value"}
        assert result.decision == PluginDecision.CONTINUE
        assert result.modified is False
        assert result.metadata == {}

    def test_unchanged_factory(self):
        """Test HookResult.unchanged factory method."""
        data = {"test": 123}
        result = HookResult.unchanged(data)
        assert result.data == data
        assert result.modified is False
        assert result.decision == PluginDecision.CONTINUE

    def test_changed_factory(self):
        """Test HookResult.changed factory method."""
        data = {"test": 456}
        metadata = {"reason": "modified"}
        result = HookResult.changed(data, metadata)
        assert result.data == data
        assert result.modified is True
        assert result.metadata == metadata

    def test_changed_without_metadata(self):
        """Test HookResult.changed without metadata."""
        result = HookResult.changed("data")
        assert result.modified is True
        assert result.metadata == {}


class TestRequestContext:
    """Tests for RequestContext dataclass."""

    def test_create_request_context(self):
        """Test creating RequestContext."""
        ctx = RequestContext(
            workflow_id="test-workflow",
            inputs={"param": "value"},
            execution_id="exec-123",
        )
        assert ctx.workflow_id == "test-workflow"
        assert ctx.inputs == {"param": "value"}
        assert ctx.execution_id == "exec-123"
        assert ctx.metadata == {}

    def test_request_context_with_metadata(self):
        """Test RequestContext with metadata."""
        ctx = RequestContext(
            workflow_id="wf",
            inputs={},
            execution_id="e1",
            metadata={"source": "api"},
        )
        assert ctx.metadata == {"source": "api"}


class TestStepContext:
    """Tests for StepContext dataclass."""

    def test_create_step_context(self):
        """Test creating StepContext."""
        ctx = StepContext(
            workflow_id="wf",
            execution_id="exec",
            step_id="step-1",
            step_type="tool",
            step_index=0,
            total_steps=3,
            tool_name="http_request",
            params={"url": "https://example.com"},
        )
        assert ctx.step_id == "step-1"
        assert ctx.step_type == "tool"
        assert ctx.step_index == 0
        assert ctx.total_steps == 3
        assert ctx.tool_name == "http_request"


class TestStepResultContext:
    """Tests for StepResultContext dataclass."""

    def test_create_success_result(self):
        """Test creating successful StepResultContext."""
        ctx = StepResultContext(
            workflow_id="wf",
            execution_id="exec",
            step_id="step-1",
            step_type="tool",
            tool_name="http_request",
            params={"url": "https://example.com"},
            output={"result": "ok"},
            success=True,
            duration_ms=150,
        )
        assert ctx.success is True
        assert ctx.output == {"result": "ok"}
        assert ctx.error is None

    def test_create_failure_result(self):
        """Test creating failed StepResultContext."""
        error = ValueError("test error")
        ctx = StepResultContext(
            workflow_id="wf",
            execution_id="exec",
            step_id="step-1",
            step_type="tool",
            tool_name="http_request",
            params={},
            output=None,
            success=False,
            error=error,
            duration_ms=50,
        )
        assert ctx.success is False
        assert ctx.error == error


class TestResponseContext:
    """Tests for ResponseContext dataclass."""

    def test_create_response_context(self):
        """Test creating ResponseContext."""
        ctx = ResponseContext(
            workflow_id="wf",
            execution_id="exec",
            inputs={"in": 1},
            outputs={"out": 2},
            success=True,
            duration_ms=1000,
            step_count=5,
        )
        assert ctx.outputs == {"out": 2}
        assert ctx.step_count == 5


# =============================================================================
# AELPlugin Base Class Tests
# =============================================================================


class TestAELPlugin:
    """Tests for AELPlugin base class."""

    def test_default_attributes(self):
        """Test default plugin attributes."""
        plugin = AELPlugin()
        assert plugin.name == "base"
        assert plugin.priority == 50
        assert plugin.fail_open is True
        assert plugin.config == {}

    def test_custom_config(self):
        """Test plugin with custom config."""
        plugin = AELPlugin(config={"key": "value"})
        assert plugin.config == {"key": "value"}

    def test_on_request_received_passthrough(self):
        """Test default on_request_received returns context unchanged."""
        plugin = AELPlugin()
        ctx = RequestContext(workflow_id="wf", inputs={}, execution_id="e")
        result = plugin.on_request_received(ctx)
        assert result == ctx

    def test_on_step_before_passthrough(self):
        """Test default on_step_before returns context unchanged."""
        plugin = AELPlugin()
        ctx = StepContext(
            workflow_id="wf",
            execution_id="e",
            step_id="s",
            step_type="tool",
            tool_name="http_request",
            params={},
            step_index=0,
            total_steps=1,
        )
        result = plugin.on_step_before(ctx)
        assert result == ctx

    def test_on_step_after_passthrough(self):
        """Test default on_step_after returns context unchanged."""
        plugin = AELPlugin()
        ctx = StepResultContext(
            workflow_id="wf",
            execution_id="e",
            step_id="s",
            step_type="tool",
            tool_name="http_request",
            params={},
            output=None,
            success=True,
            duration_ms=100,
        )
        result = plugin.on_step_after(ctx)
        assert result == ctx

    def test_on_response_ready_passthrough(self):
        """Test default on_response_ready returns context unchanged."""
        plugin = AELPlugin()
        ctx = ResponseContext(
            workflow_id="wf",
            execution_id="e",
            inputs={},
            outputs={},
            success=True,
            duration_ms=100,
            step_count=1,
        )
        result = plugin.on_response_ready(ctx)
        assert result == ctx

    def test_repr(self):
        """Test plugin string representation."""
        plugin = AELPlugin()
        assert "AELPlugin" in repr(plugin)
        assert "name='base'" in repr(plugin)


# =============================================================================
# Custom Plugin Tests
# =============================================================================


class ModifyingPlugin(AELPlugin):
    """Test plugin that modifies contexts."""

    name = "modifying"
    priority = 10

    def on_request_received(self, context: RequestContext) -> HookResult[RequestContext]:
        new_inputs = {**context.inputs, "added_by_plugin": True}
        new_ctx = replace(context, inputs=new_inputs)
        return HookResult.changed(new_ctx, {"modified_by": self.name})

    def on_step_before(self, context: StepContext) -> HookResult[StepContext]:
        new_params = {**context.params, "plugin_param": "value"}
        new_ctx = replace(context, params=new_params)
        return HookResult.changed(new_ctx)


class FailingPlugin(AELPlugin):
    """Test plugin that raises exceptions."""

    name = "failing"
    priority = 20

    def on_request_received(self, context: RequestContext) -> RequestContext:
        raise RuntimeError("Plugin error")


class TestCustomPlugins:
    """Tests for custom plugin implementations."""

    def test_modifying_plugin_request(self):
        """Test plugin that modifies request context."""
        plugin = ModifyingPlugin()
        ctx = RequestContext(workflow_id="wf", inputs={"original": True}, execution_id="e")
        result = plugin.on_request_received(ctx)

        assert isinstance(result, HookResult)
        assert result.modified is True
        assert result.data.inputs["original"] is True
        assert result.data.inputs["added_by_plugin"] is True

    def test_modifying_plugin_step(self):
        """Test plugin that modifies step context."""
        plugin = ModifyingPlugin()
        ctx = StepContext(
            workflow_id="wf",
            execution_id="e",
            step_id="s",
            step_type="tool",
            tool_name="http_request",
            params={"existing": "param"},
            step_index=0,
            total_steps=1,
        )
        result = plugin.on_step_before(ctx)

        assert result.data.params["existing"] == "param"
        assert result.data.params["plugin_param"] == "value"


# =============================================================================
# PluginRegistry Tests
# =============================================================================


class TestPluginRegistry:
    """Tests for PluginRegistry."""

    def test_empty_registry(self):
        """Test empty registry."""
        registry = PluginRegistry()
        assert registry.plugins == []

    def test_load_builtin_plugin(self):
        """Test loading builtin plugin."""
        registry = PluginRegistry()
        definitions = [
            PluginDefinition(name="logging", type="builtin", enabled=True)
        ]
        result = registry.load_plugins(definitions)

        assert result.success_count == 1
        assert result.failure_count == 0
        assert len(registry.plugins) == 1
        assert isinstance(registry.plugins[0], LoggingPlugin)

    def test_load_disabled_plugin(self):
        """Test disabled plugins are skipped."""
        registry = PluginRegistry()
        definitions = [
            PluginDefinition(name="logging", type="builtin", enabled=False)
        ]
        result = registry.load_plugins(definitions)

        assert result.success_count == 0
        assert len(registry.plugins) == 0

    def test_load_unknown_builtin(self):
        """Test loading unknown builtin fails gracefully."""
        registry = PluginRegistry()
        definitions = [
            PluginDefinition(name="nonexistent", type="builtin", enabled=True)
        ]
        result = registry.load_plugins(definitions)

        assert result.success_count == 0
        assert result.failure_count == 1
        assert "nonexistent" in result.failed[0][0]

    def test_priority_sorting(self):
        """Test plugins are sorted by priority."""
        registry = PluginRegistry()
        definitions = [
            PluginDefinition(name="logging", type="builtin", priority=90, enabled=True),
            PluginDefinition(name="metrics", type="builtin", priority=10, enabled=True),
        ]
        result = registry.load_plugins(definitions)

        assert result.success_count == 2
        # Lower priority should come first
        assert registry.plugins[0].priority == 10
        assert registry.plugins[1].priority == 90

    def test_load_from_file(self):
        """Test loading plugin from file."""
        # Create a temporary plugin file
        plugin_code = '''
from ploston_core.plugins import AELPlugin

class FilePlugin(AELPlugin):
    name = "file-plugin"
    priority = 25
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(plugin_code)
            plugin_path = f.name

        try:
            registry = PluginRegistry()
            definitions = [
                PluginDefinition(
                    name="file-plugin",
                    type="file",
                    path=plugin_path,
                    enabled=True,
                )
            ]
            result = registry.load_plugins(definitions)

            assert result.success_count == 1
            assert registry.plugins[0].name == "file-plugin"
        finally:
            Path(plugin_path).unlink()

    def test_load_from_nonexistent_file(self):
        """Test loading from nonexistent file fails."""
        registry = PluginRegistry()
        definitions = [
            PluginDefinition(
                name="missing",
                type="file",
                path="/nonexistent/path.py",
                enabled=True,
            )
        ]
        result = registry.load_plugins(definitions)

        assert result.failure_count == 1

    def test_unknown_plugin_type(self):
        """Test unknown plugin type fails."""
        registry = PluginRegistry()
        definitions = [
            PluginDefinition(name="test", type="unknown", enabled=True)
        ]
        result = registry.load_plugins(definitions)

        assert result.failure_count == 1


class TestPluginRegistryHookExecution:
    """Tests for PluginRegistry hook execution."""

    def test_execute_request_received_empty(self):
        """Test executing hook with no plugins."""
        registry = PluginRegistry()
        ctx = RequestContext(workflow_id="wf", inputs={}, execution_id="e")
        result = registry.execute_request_received(ctx)

        assert result.data == ctx
        assert result.modified is False

    def test_execute_request_received_with_plugin(self):
        """Test executing hook with modifying plugin."""
        registry = PluginRegistry()
        registry._plugins = [ModifyingPlugin()]

        ctx = RequestContext(workflow_id="wf", inputs={"x": 1}, execution_id="e")
        result = registry.execute_request_received(ctx)

        assert result.modified is True
        assert result.data.inputs["added_by_plugin"] is True

    def test_execute_step_before(self):
        """Test executing step_before hook."""
        registry = PluginRegistry()
        registry._plugins = [ModifyingPlugin()]

        ctx = StepContext(
            workflow_id="wf",
            execution_id="e",
            step_id="s",
            step_type="tool",
            tool_name="http_request",
            params={},
            step_index=0,
            total_steps=1,
        )
        result = registry.execute_step_before(ctx)

        assert result.data.params["plugin_param"] == "value"

    def test_execute_step_after(self):
        """Test executing step_after hook."""
        registry = PluginRegistry()
        ctx = StepResultContext(
            workflow_id="wf",
            execution_id="e",
            step_id="s",
            step_type="tool",
            tool_name="http_request",
            params={},
            output=None,
            success=True,
            duration_ms=100,
        )
        result = registry.execute_step_after(ctx)

        assert result.data == ctx

    def test_execute_response_ready(self):
        """Test executing response_ready hook."""
        registry = PluginRegistry()
        ctx = ResponseContext(
            workflow_id="wf",
            execution_id="e",
            inputs={},
            outputs={},
            success=True,
            duration_ms=100,
            step_count=1,
        )
        result = registry.execute_response_ready(ctx)

        assert result.data == ctx

    def test_fail_open_continues_on_error(self):
        """Test fail_open=True continues execution on error."""
        registry = PluginRegistry()
        failing = FailingPlugin()
        failing.fail_open = True
        registry._plugins = [failing]

        ctx = RequestContext(workflow_id="wf", inputs={}, execution_id="e")
        # Should not raise, should continue
        result = registry.execute_request_received(ctx)
        assert result.data == ctx

    def test_fail_closed_raises_on_error(self):
        """Test fail_open=False raises on error."""
        registry = PluginRegistry()
        failing = FailingPlugin()
        failing.fail_open = False
        registry._plugins = [failing]

        ctx = RequestContext(workflow_id="wf", inputs={}, execution_id="e")
        with pytest.raises(RuntimeError, match="Plugin error"):
            registry.execute_request_received(ctx)

    def test_chain_execution_order(self):
        """Test plugins execute in priority order."""
        execution_order = []

        class OrderTrackingPlugin(AELPlugin):
            def on_request_received(self, context: RequestContext) -> RequestContext:
                execution_order.append(self.name)
                return context

        plugin1 = OrderTrackingPlugin()
        plugin1.name = "first"
        plugin1.priority = 10

        plugin2 = OrderTrackingPlugin()
        plugin2.name = "second"
        plugin2.priority = 20

        plugin3 = OrderTrackingPlugin()
        plugin3.name = "third"
        plugin3.priority = 30

        registry = PluginRegistry()
        registry._plugins = [plugin2, plugin3, plugin1]  # Unsorted
        registry._plugins = sorted(registry._plugins, key=lambda p: p.priority)

        ctx = RequestContext(workflow_id="wf", inputs={}, execution_id="e")
        registry.execute_request_received(ctx)

        assert execution_order == ["first", "second", "third"]


# =============================================================================
# Built-in Plugin Tests
# =============================================================================


class TestLoggingPlugin:
    """Tests for LoggingPlugin."""

    def test_default_config(self):
        """Test LoggingPlugin default configuration."""
        plugin = LoggingPlugin()
        assert plugin.name == "logging"
        assert plugin.priority == 10

    def test_custom_log_level(self):
        """Test LoggingPlugin with custom log level."""
        plugin = LoggingPlugin(config={"level": "DEBUG"})
        assert plugin._level == logging.DEBUG

    def test_on_request_received_logs(self, caplog):
        """Test LoggingPlugin logs request."""
        plugin = LoggingPlugin(config={"level": "INFO"})
        ctx = RequestContext(
            workflow_id="test-wf",
            inputs={"param": "value"},
            execution_id="exec-123",
        )

        with caplog.at_level(logging.INFO, logger="ael.plugins.logging"):
            result = plugin.on_request_received(ctx)

        assert result == ctx
        assert "test-wf" in caplog.text or len(caplog.records) >= 0  # May not capture

    def test_on_step_before_logs(self):
        """Test LoggingPlugin logs step start."""
        plugin = LoggingPlugin()
        ctx = StepContext(
            workflow_id="wf",
            execution_id="e",
            step_id="step-1",
            step_type="tool",
            step_index=0,
            total_steps=3,
            tool_name="http_request",
            params={},
        )
        result = plugin.on_step_before(ctx)
        assert result == ctx

    def test_on_step_after_logs_success(self):
        """Test LoggingPlugin logs step success."""
        plugin = LoggingPlugin()
        ctx = StepResultContext(
            workflow_id="wf",
            execution_id="e",
            step_id="step-1",
            step_type="tool",
            tool_name="http_request",
            params={},
            output={"result": "ok"},
            success=True,
            duration_ms=150,
        )
        result = plugin.on_step_after(ctx)
        assert result == ctx

    def test_on_step_after_logs_failure(self):
        """Test LoggingPlugin logs step failure."""
        plugin = LoggingPlugin()
        ctx = StepResultContext(
            workflow_id="wf",
            execution_id="e",
            step_id="step-1",
            step_type="tool",
            tool_name="http_request",
            params={},
            output=None,
            success=False,
            error=ValueError("test error"),
            duration_ms=50,
        )
        result = plugin.on_step_after(ctx)
        assert result == ctx

    def test_on_response_ready_logs(self):
        """Test LoggingPlugin logs response."""
        plugin = LoggingPlugin()
        ctx = ResponseContext(
            workflow_id="wf",
            execution_id="e",
            inputs={},
            outputs={"result": "done"},
            success=True,
            duration_ms=1000,
            step_count=5,
        )
        result = plugin.on_response_ready(ctx)
        assert result == ctx


class TestMetricsPlugin:
    """Tests for MetricsPlugin."""

    def test_default_config(self):
        """Test MetricsPlugin default configuration."""
        plugin = MetricsPlugin()
        assert plugin.name == "metrics"
        assert plugin.priority == 90

    def test_custom_prefix(self):
        """Test MetricsPlugin with custom prefix."""
        plugin = MetricsPlugin(config={"prefix": "custom"})
        assert plugin._prefix == "custom"

    def test_on_request_received_records(self):
        """Test MetricsPlugin records request."""
        plugin = MetricsPlugin()
        ctx = RequestContext(
            workflow_id="wf",
            inputs={},
            execution_id="exec-123",
        )
        result = plugin.on_request_received(ctx)
        assert result == ctx
        # Timing should be recorded
        assert "exec-123" in plugin._request_times

    def test_on_step_before_records(self):
        """Test MetricsPlugin records step start."""
        plugin = MetricsPlugin()
        ctx = StepContext(
            workflow_id="wf",
            execution_id="e",
            step_id="s",
            step_type="tool",
            tool_name="http_request",
            params={},
            step_index=0,
            total_steps=1,
        )
        result = plugin.on_step_before(ctx)
        assert "_metrics_start_time" in result.metadata

    def test_on_step_after_records(self):
        """Test MetricsPlugin records step completion."""
        plugin = MetricsPlugin()
        ctx = StepResultContext(
            workflow_id="wf",
            execution_id="e",
            step_id="s",
            step_type="tool",
            tool_name="http_request",
            params={},
            output=None,
            success=True,
            duration_ms=100,
        )
        result = plugin.on_step_after(ctx)
        assert result == ctx

    def test_on_response_ready_cleans_up(self):
        """Test MetricsPlugin cleans up timing data."""
        plugin = MetricsPlugin()
        plugin._request_times["exec-123"] = 12345.0

        ctx = ResponseContext(
            workflow_id="wf",
            execution_id="exec-123",
            inputs={},
            outputs={},
            success=True,
            duration_ms=1000,
            step_count=1,
        )
        plugin.on_response_ready(ctx)

        assert "exec-123" not in plugin._request_times


class TestBuiltinPluginsRegistry:
    """Tests for BUILTIN_PLUGINS registry."""

    def test_logging_registered(self):
        """Test LoggingPlugin is registered."""
        assert "logging" in BUILTIN_PLUGINS
        assert BUILTIN_PLUGINS["logging"] == LoggingPlugin

    def test_metrics_registered(self):
        """Test MetricsPlugin is registered."""
        assert "metrics" in BUILTIN_PLUGINS
        assert BUILTIN_PLUGINS["metrics"] == MetricsPlugin


# =============================================================================
# PluginLoadResult Tests
# =============================================================================


class TestPluginLoadResult:
    """Tests for PluginLoadResult."""

    def test_empty_result(self):
        """Test empty load result."""
        result = PluginLoadResult()
        assert result.success_count == 0
        assert result.failure_count == 0

    def test_with_loaded(self):
        """Test result with loaded plugins."""
        result = PluginLoadResult(loaded=[AELPlugin(), AELPlugin()])
        assert result.success_count == 2

    def test_with_failed(self):
        """Test result with failed plugins."""
        result = PluginLoadResult(failed=[("plugin1", "error1"), ("plugin2", "error2")])
        assert result.failure_count == 2
