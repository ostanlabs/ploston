"""Integration tests for AEL telemetry.

Tests telemetry integration with:
- HTTP transport /metrics endpoint
- Workflow execution metrics
- Tool invocation metrics
"""

import asyncio
import pytest
from httpx import AsyncClient
from starlette.testclient import TestClient

from ploston_core.mcp_frontend.http_transport import HTTPTransport
from ploston_core.telemetry import (
    MetricLabels,
    TelemetryConfig,
    get_telemetry,
    reset_telemetry,
    setup_telemetry,
)


class TestMetricsEndpoint:
    """Tests for /metrics endpoint in HTTP transport."""

    def setup_method(self):
        """Reset telemetry before each test."""
        reset_telemetry()

    def teardown_method(self):
        """Reset telemetry after each test."""
        reset_telemetry()

    def test_metrics_endpoint_without_telemetry(self):
        """Test /metrics endpoint when telemetry is not initialized."""
        async def mock_handler(msg):
            return {"jsonrpc": "2.0", "id": msg.get("id"), "result": {}}

        transport = HTTPTransport(message_handler=mock_handler)
        client = TestClient(transport.app)

        response = client.get("/metrics")
        assert response.status_code == 200
        assert "Telemetry not initialized" in response.text

    def test_metrics_endpoint_with_telemetry_enabled(self):
        """Test /metrics endpoint when telemetry is enabled."""
        # Initialize telemetry
        setup_telemetry()

        async def mock_handler(msg):
            return {"jsonrpc": "2.0", "id": msg.get("id"), "result": {}}

        transport = HTTPTransport(message_handler=mock_handler)
        client = TestClient(transport.app)

        response = client.get("/metrics")
        assert response.status_code == 200
        # Should return Prometheus format or OTEL metrics
        assert response.headers["content-type"].startswith("text/plain")

    def test_metrics_endpoint_with_telemetry_disabled(self):
        """Test /metrics endpoint when telemetry is disabled."""
        # Initialize telemetry with disabled config
        config = TelemetryConfig(enabled=False)
        setup_telemetry(config)

        async def mock_handler(msg):
            return {"jsonrpc": "2.0", "id": msg.get("id"), "result": {}}

        transport = HTTPTransport(message_handler=mock_handler)
        client = TestClient(transport.app)

        response = client.get("/metrics")
        assert response.status_code == 200
        assert "Metrics disabled" in response.text

    def test_metrics_endpoint_with_metrics_disabled(self):
        """Test /metrics endpoint when metrics specifically disabled."""
        # Initialize telemetry with metrics disabled
        config = TelemetryConfig(enabled=True, metrics_enabled=False)
        setup_telemetry(config)

        async def mock_handler(msg):
            return {"jsonrpc": "2.0", "id": msg.get("id"), "result": {}}

        transport = HTTPTransport(message_handler=mock_handler)
        client = TestClient(transport.app)

        response = client.get("/metrics")
        assert response.status_code == 200
        assert "Metrics disabled" in response.text


class TestTelemetryIntegration:
    """Tests for telemetry integration with AEL components."""

    def setup_method(self):
        """Reset telemetry before each test."""
        reset_telemetry()

    def teardown_method(self):
        """Reset telemetry after each test."""
        reset_telemetry()

    def test_telemetry_setup_creates_all_components(self):
        """Test that telemetry setup creates all required components."""
        telemetry = setup_telemetry()

        assert telemetry["meter"] is not None
        assert telemetry["tracer"] is not None
        assert telemetry["metrics"] is not None
        assert telemetry["config"] is not None

    def test_telemetry_config_from_ael_config(self):
        """Test creating TelemetryConfig from AEL config values."""
        # Simulate AEL config values
        config = TelemetryConfig(
            enabled=True,
            service_name="ael-test",
            service_version="1.0.0-test",
            metrics_enabled=True,
            traces_enabled=False,
        )

        telemetry = setup_telemetry(config)
        assert telemetry["config"].service_name == "ael-test"
        assert telemetry["config"].service_version == "1.0.0-test"

    @pytest.mark.asyncio
    async def test_metrics_recorded_during_instrumentation(self):
        """Test that metrics are recorded during instrumentation."""
        from ploston_core.telemetry import instrument_workflow, instrument_step, instrument_tool_call

        setup_telemetry()
        metrics = get_telemetry()["metrics"]

        # Record some metrics
        async with instrument_workflow("test-workflow"):
            async with instrument_step("test-workflow", "step-1"):
                async with instrument_tool_call("test-tool"):
                    pass

        # Metrics should have been recorded (no assertion on values,
        # just verify no errors occurred)
        assert metrics is not None


class TestTelemetryConfigModels:
    """Tests for telemetry configuration models."""

    def test_telemetry_metrics_config_defaults(self):
        """Test TelemetryMetricsConfig default values."""
        from ploston_core.config import TelemetryMetricsConfig

        config = TelemetryMetricsConfig()
        assert config.enabled is True
        assert config.prometheus_enabled is True

    def test_telemetry_tracing_config_defaults(self):
        """Test TelemetryTracingConfig default values."""
        from ploston_core.config import TelemetryTracingConfig

        config = TelemetryTracingConfig()
        assert config.enabled is False  # Phase 2

    def test_telemetry_config_with_new_fields(self):
        """Test TelemetryConfig with new metrics/tracing fields."""
        from ploston_core.config import TelemetryConfig as AELTelemetryConfig

        config = AELTelemetryConfig()
        assert config.enabled is True
        assert config.service_name == "ael"
        assert config.service_version == "1.0.0"
        assert config.metrics.enabled is True
        assert config.tracing.enabled is False


class TestTraceContextPropagation:
    """Tests for trace context propagation (T-149)."""

    def setup_method(self):
        """Reset telemetry before each test."""
        reset_telemetry()

    def teardown_method(self):
        """Reset telemetry after each test."""
        reset_telemetry()

    @pytest.mark.asyncio
    async def test_trace_spans_created_for_workflow(self):
        """Test that trace spans are created for workflow execution."""
        from opentelemetry import trace
        from ploston_core.telemetry import instrument_workflow

        config = TelemetryConfig(traces_enabled=True)
        setup_telemetry(config)

        tracer = trace.get_tracer("test")

        with tracer.start_as_current_span("parent") as parent_span:
            async with instrument_workflow("test-workflow") as result:
                # Verify parent span context is preserved
                current_span = trace.get_current_span()
                assert current_span.is_recording()

                # Verify parent context is valid
                ctx = current_span.get_span_context()
                assert ctx.is_valid

    @pytest.mark.asyncio
    async def test_instrumentation_creates_spans(self):
        """Test that instrumentation creates spans (not as current)."""
        from opentelemetry import trace
        from ploston_core.telemetry import instrument_workflow, instrument_step, instrument_tool_call

        config = TelemetryConfig(traces_enabled=True)
        setup_telemetry(config)

        # Instrumentation creates spans but doesn't set them as current
        # This is by design - the spans are created and ended within the context
        async with instrument_workflow("wf-1") as wf_result:
            async with instrument_step("wf-1", "step-1") as step_result:
                async with instrument_tool_call("tool-1") as tool_result:
                    # Verify result dicts are yielded
                    assert wf_result["status"] == "success"
                    assert step_result["status"] == "success"
                    assert tool_result["status"] == "success"

    @pytest.mark.asyncio
    async def test_parent_span_context_preserved(self):
        """Test that parent span context is preserved during instrumentation."""
        from opentelemetry import trace
        from ploston_core.telemetry import instrument_workflow

        config = TelemetryConfig(traces_enabled=True)
        setup_telemetry(config)

        tracer = trace.get_tracer("test")

        with tracer.start_as_current_span("parent") as parent_span:
            parent_ctx = parent_span.get_span_context()

            async with instrument_workflow("test-workflow"):
                # Current span should still be the parent
                current = trace.get_current_span()
                current_ctx = current.get_span_context()

                # Same trace_id and span_id as parent
                assert current_ctx.trace_id == parent_ctx.trace_id
                assert current_ctx.span_id == parent_ctx.span_id


class TestStructuredLoggingIntegration:
    """Integration tests for structured logging with trace context."""

    def setup_method(self):
        """Reset telemetry and loggers before each test."""
        reset_telemetry()
        from ploston_core.telemetry.logging import reset_loggers
        reset_loggers()

    def teardown_method(self):
        """Reset telemetry and loggers after each test."""
        reset_telemetry()
        from ploston_core.telemetry.logging import reset_loggers
        reset_loggers()

    def test_logger_includes_trace_context_in_span(self):
        """Test that logger includes trace context when in active span."""
        import json
        import logging
        from io import StringIO
        from opentelemetry import trace
        from ploston_core.telemetry.logging import StructuredLogFormatter, get_logger

        config = TelemetryConfig(traces_enabled=True)
        setup_telemetry(config)

        tracer = trace.get_tracer("test")

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredLogFormatter())

        logger = get_logger("test_integration")
        logger._logger.handlers = [handler]

        with tracer.start_as_current_span("test_span"):
            logger.info("Test message in span")

        output = stream.getvalue()
        data = json.loads(output)

        assert "trace_id" in data
        assert "span_id" in data
        assert len(data["trace_id"]) == 32
        assert len(data["span_id"]) == 16

    @pytest.mark.asyncio
    async def test_logs_correlated_with_workflow_traces(self):
        """Test that logs are correlated with workflow traces when in active span."""
        import json
        import logging
        from io import StringIO
        from opentelemetry import trace
        from ploston_core.telemetry import instrument_workflow
        from ploston_core.telemetry.logging import StructuredLogFormatter, get_logger

        config = TelemetryConfig(traces_enabled=True)
        setup_telemetry(config)

        tracer = trace.get_tracer("test")

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredLogFormatter())

        logger = get_logger("workflow_test2")
        logger._logger.handlers = [handler]

        # Log within an active span to get trace context
        with tracer.start_as_current_span("workflow_span"):
            async with instrument_workflow("test-workflow"):
                logger.info("Processing workflow")

        output = stream.getvalue()
        data = json.loads(output)

        # Log should have trace context from the active span
        assert "trace_id" in data
        assert "span_id" in data


class TestOTLPExporterIntegration:
    """Integration tests for OTLP exporter configuration."""

    def setup_method(self):
        """Reset telemetry before each test."""
        reset_telemetry()

    def teardown_method(self):
        """Reset telemetry after each test."""
        reset_telemetry()

    def test_telemetry_setup_with_otlp_config(self):
        """Test telemetry setup with OTLP exporter configuration."""
        from ploston_core.telemetry import OTLPExporterConfig

        config = TelemetryConfig(
            traces_enabled=True,
            logs_enabled=True,
            otlp=OTLPExporterConfig(
                enabled=False,  # Don't actually connect
                endpoint="http://localhost:4317",
                protocol="grpc",
            ),
        )

        telemetry = setup_telemetry(config)

        assert telemetry["tracer"] is not None
        assert telemetry["tracer_provider"] is not None
        assert telemetry["config"].otlp.endpoint == "http://localhost:4317"

    def test_telemetry_config_supports_http_protocol(self):
        """Test OTLP config supports HTTP protocol."""
        from ploston_core.telemetry import OTLPExporterConfig

        config = TelemetryConfig(
            traces_enabled=True,
            otlp=OTLPExporterConfig(
                enabled=False,
                endpoint="http://localhost:4318",
                protocol="http",
            ),
        )

        telemetry = setup_telemetry(config)
        assert telemetry["config"].otlp.protocol == "http"
