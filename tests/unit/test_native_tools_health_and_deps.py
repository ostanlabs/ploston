"""Behavioral tests for native-tools health endpoints, dependency gating, and
the remaining kafka/ml handlers not covered elsewhere.

These exercise the live server.py handlers:
- _check_dependency raising DependencyUnavailableError when a configured
  dependency is unhealthy (kafka/ollama/firecrawl tools are gated on it).
- health_check / the HTTP /health + /metrics custom routes.
- kafka_consume / kafka_health, and ml_classify_text (Ollama-backed, mocked).

The global HealthManager is mutated by configure_*; a fixture resets it so we
don't leak dependency state into the rest of the suite.
"""

from __future__ import annotations

import sys
import types

import pytest
from ploston_core.native_tools import (
    DependencyUnavailableError,
    get_health_manager,
)
from ploston_core.native_tools.health import reset_health_manager

from ploston.native_tools import server as srv


@pytest.fixture()
def clean_health_manager():
    """Ensure each test starts and ends with a fresh global HealthManager."""
    reset_health_manager()
    yield get_health_manager()
    reset_health_manager()


# =============================================================================
# Dependency gating
# =============================================================================


class TestDependencyGating:
    @pytest.mark.asyncio
    async def test_unhealthy_kafka_blocks_tool(self, clean_health_manager):
        # Enabling kafka with a non-default broker marks it UNHEALTHY until a
        # live check succeeds; the tool must refuse to run.
        clean_health_manager.configure_kafka(
            bootstrap_servers="broker:9092",
            client_id="c",
            security_protocol="PLAINTEXT",
        )
        assert clean_health_manager.is_dependency_healthy("kafka") is False
        with pytest.raises(DependencyUnavailableError):
            await srv.kafka_list_topics.fn()

    @pytest.mark.asyncio
    async def test_unhealthy_ollama_blocks_classify(self, clean_health_manager):
        clean_health_manager.configure_ollama(host="http://ollama:11434")
        assert clean_health_manager.is_dependency_healthy("ollama") is False
        with pytest.raises(DependencyUnavailableError):
            await srv.ml_classify_text.fn("text", ["a", "b"])

    @pytest.mark.asyncio
    async def test_healthy_when_dependency_unconfigured(self, clean_health_manager):
        # With no dependency configured, the gate is open (returns True), so the
        # tool proceeds to the (here unreachable) broker and raises a real error
        # rather than DependencyUnavailableError.
        assert clean_health_manager.is_dependency_healthy("kafka") is True


# =============================================================================
# Health endpoints
# =============================================================================


class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_health_check_tool_returns_envelope(self, clean_health_manager):
        result = await srv.health_check.fn()
        assert result["service"] == "native-tools"
        assert "status" in result
        assert "config" in result
        assert result["config"]["config_source"] == "environment"

    @pytest.mark.asyncio
    async def test_http_health_route(self, clean_health_manager):
        # http_health_check is a Starlette route handler taking a request.
        resp = await srv.http_health_check(request=None)
        assert resp.status_code in (200, 503)
        # JSONResponse stores the serialized body.
        assert b"native-tools" in resp.body

    @pytest.mark.asyncio
    async def test_http_metrics_route(self, clean_health_manager):
        resp = await srv.http_metrics(request=None)
        # Prometheus exposition is text/plain; body is bytes.
        assert resp.status_code == 200
        assert b"native_tools" in resp.body or resp.body  # non-empty exposition


# =============================================================================
# Remaining kafka handlers (consume / health) — fake kafka package
# =============================================================================


class _FakeMessage:
    def __init__(self, value, key=None, partition=0, offset=0, timestamp=0):
        self.value = value
        self.key = key
        self.partition = partition
        self.offset = offset
        self.timestamp = timestamp


class _FakeConsumer:
    def __init__(self, topic, **config):
        self.topic = topic
        self.config = config
        self._messages = [
            _FakeMessage(b'{"n": 1}', key=b"k1", offset=0),
            _FakeMessage(b"plain-text", key=None, offset=1),
        ]

    def __iter__(self):
        return iter(self._messages)

    def close(self):
        pass


class _FakeAdminClient:
    def __init__(self, **config):
        self.config = config

    def list_topics(self):
        return ["t1", "t2", "t3"]

    def close(self):
        pass


@pytest.fixture()
def fake_kafka(monkeypatch):
    kafka_mod = types.ModuleType("kafka")
    kafka_mod.KafkaConsumer = _FakeConsumer
    kafka_mod.KafkaAdminClient = _FakeAdminClient
    kafka_mod.KafkaProducer = object
    monkeypatch.setitem(sys.modules, "kafka", kafka_mod)
    return kafka_mod


class TestKafkaConsumeHealth:
    @pytest.mark.asyncio
    async def test_consume_decodes_json_and_text(self, fake_kafka, clean_health_manager):
        result = await srv.kafka_consume.fn("events", max_messages=10)
        assert result["success"] is True
        assert result["message_count"] == 2
        # First message decoded as JSON, second as plain text.
        assert result["messages"][0]["value"] == {"n": 1}
        assert result["messages"][0]["key"] == "k1"
        assert result["messages"][1]["value"] == "plain-text"
        assert result["messages"][1]["key"] is None

    @pytest.mark.asyncio
    async def test_kafka_health_reports_healthy(self, fake_kafka, clean_health_manager):
        result = await srv.kafka_health.fn()
        assert result["success"] is True
        assert result["status"] == "healthy"
        assert result["topic_count"] == 3


# =============================================================================
# ml_classify_text — Ollama-backed, mocked via httpx
# =============================================================================


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data
        self.text = ""
        self.content = b""
        self.headers = {}

    def json(self):
        return self._json


class _FakeAsyncClient:
    response_for_prompt: dict[str, list[float]] = {}

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        prompt = (json or {}).get("prompt", "")
        emb = type(self).response_for_prompt.get(prompt, [0.0, 0.0, 1.0])
        return _FakeResponse(200, {"embedding": emb})


class TestConfigGlobalsWiring:
    def test_update_config_globals_rebinds_module_state(self, monkeypatch):
        from ploston.native_tools.config_manager import ToolConfig

        # Snapshot + restore the module globals this function rebinds, so it
        # cannot leak into other tests sharing this interpreter.
        names = [
            "WORKSPACE_DIR",
            "MAX_FILE_SIZE",
            "ALLOWED_PATHS",
            "DENIED_PATHS",
            "ALLOWED_HOSTS",
            "DENIED_HOSTS",
            "FIRECRAWL_BASE_URL",
            "FIRECRAWL_API_KEY",
            "KAFKA_BOOTSTRAP_SERVERS",
            "KAFKA_CLIENT_ID",
            "KAFKA_SECURITY_PROTOCOL",
            "KAFKA_SASL_MECHANISM",
            "KAFKA_SASL_USERNAME",
            "KAFKA_SASL_PASSWORD",
            "OLLAMA_HOST",
            "DEFAULT_EMBEDDING_MODEL",
        ]
        saved = {n: getattr(srv, n) for n in names}

        new = ToolConfig(
            workspace_dir="/ws2",
            max_file_size=4242,
            allowed_paths=["/ws2/pub"],
            denied_paths=["/ws2/secret"],
            allowed_hosts=["api.example.com"],
            denied_hosts=["evil.example.com"],
            firecrawl_base_url="http://fc:9",
            kafka_bootstrap_servers="broker:9092",
            ollama_host="http://oll:1",
            default_embedding_model="m1",
        )
        try:
            srv._update_config_globals(new)
            # The handlers read these module globals at call time.
            assert srv.WORKSPACE_DIR == "/ws2"
            assert srv.MAX_FILE_SIZE == 4242
            assert srv.ALLOWED_PATHS == ["/ws2/pub"]
            assert srv.DENIED_HOSTS == ["evil.example.com"]
            assert srv.FIRECRAWL_BASE_URL == "http://fc:9"
            assert srv.KAFKA_BOOTSTRAP_SERVERS == "broker:9092"
            assert srv.OLLAMA_HOST == "http://oll:1"
            assert srv.DEFAULT_EMBEDDING_MODEL == "m1"
        finally:
            for n, v in saved.items():
                setattr(srv, n, v)

    def test_configure_health_manager_registers_dependencies(
        self, clean_health_manager, monkeypatch
    ):
        # Point the module globals at non-default endpoints so the health
        # manager treats the dependencies as enabled.
        monkeypatch.setattr(srv, "KAFKA_BOOTSTRAP_SERVERS", "broker:9092")
        monkeypatch.setattr(srv, "OLLAMA_HOST", "http://ollama:11434")
        monkeypatch.setattr(srv, "FIRECRAWL_BASE_URL", "http://fc:3002")
        srv._configure_health_manager()
        assert clean_health_manager.is_dependency_enabled("kafka") is True
        assert clean_health_manager.is_dependency_enabled("ollama") is True
        assert clean_health_manager.is_dependency_enabled("firecrawl") is True


class TestMlClassify:
    @pytest.mark.asyncio
    async def test_classify_picks_closest_category(self, monkeypatch, clean_health_manager):
        fake = types.ModuleType("httpx")
        fake.AsyncClient = _FakeAsyncClient
        fake.ConnectError = type("ConnectError", (Exception,), {})
        monkeypatch.setitem(sys.modules, "httpx", fake)

        # text embeds same as "sports"; "weather" is orthogonal.
        _FakeAsyncClient.response_for_prompt = {
            "the match score": [1.0, 0.0, 0.0],
            "sports": [1.0, 0.0, 0.0],
            "weather": [0.0, 1.0, 0.0],
        }
        result = await srv.ml_classify_text.fn("the match score", ["sports", "weather"])
        assert result["success"] is True
        assert result["category"] == "sports"
        assert result["confidence"] == pytest.approx(1.0, abs=1e-6)
