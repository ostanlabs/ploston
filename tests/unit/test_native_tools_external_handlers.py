"""Behavioral tests for native-tools handlers that talk to external services.

We never hit a real service. Instead we stub the *boundary* the core
implementation crosses (httpx for http_request / ml / firecrawl, the lazily
imported ``kafka`` package for the kafka tools) and then assert on the real
output envelope and the real request shaping the handler performs (URL,
payload, headers, method). This exercises the live server.py handler wiring
plus the ploston_core implementation glue without any network/broker.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from ploston.native_tools import server as srv

# --------------------------------------------------------------------------- #
# httpx test double
# --------------------------------------------------------------------------- #


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: Any = None,
        text: str = "",
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.headers = headers or {}
        self.content = (text or "").encode()

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeAsyncClient:
    """Records the last request and returns a queued response.

    ``calls`` is shared (class-level injection per test) so assertions can
    inspect exactly what the handler sent.
    """

    last_request: dict[str, Any] = {}
    response: _FakeResponse = _FakeResponse(json_data={"ok": True}, text="{}")

    def __init__(self, *args, **kwargs):
        type(self).last_request = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def request(self, method, url, headers=None, json=None, params=None):
        type(self).last_request = {
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
            "params": params,
        }
        return type(self).response

    async def post(self, url, headers=None, json=None):
        type(self).last_request = {
            "method": "POST",
            "url": url,
            "headers": headers,
            "json": json,
        }
        return type(self).response

    async def get(self, url, headers=None):
        type(self).last_request = {"method": "GET", "url": url, "headers": headers}
        return type(self).response


@pytest.fixture()
def fake_httpx(monkeypatch):
    """Install a fake ``httpx`` module visible to all importers in-process."""
    fake = types.ModuleType("httpx")
    fake.AsyncClient = _FakeAsyncClient

    class _TimeoutError(Exception):  # noqa: N818 - mirrors httpx.TimeoutException name
        pass

    class _RequestError(Exception):
        pass

    class _ConnectError(_RequestError):
        pass

    fake.TimeoutException = _TimeoutError
    fake.RequestError = _RequestError
    fake.ConnectError = _ConnectError
    monkeypatch.setitem(sys.modules, "httpx", fake)
    # firecrawl.py imported httpx at module load; rebind its reference too.
    import ploston_core.native_tools.firecrawl as fc

    monkeypatch.setattr(fc, "httpx", fake)
    # reset shared state
    _FakeAsyncClient.last_request = {}
    _FakeAsyncClient.response = _FakeResponse(json_data={"ok": True}, text="{}")
    return _FakeAsyncClient


# =============================================================================
# http_request handler — request shaping + error envelopes
# =============================================================================


class TestHttpRequest:
    @pytest.mark.asyncio
    async def test_get_request_shaping(self, fake_httpx, monkeypatch):
        import ploston_core.native_tools.network as net

        # Avoid real DNS + bypass the SSRF private-range block with a public IP.
        monkeypatch.setattr(net, "_resolve_host_ips", lambda host: ["93.184.216.34"])
        fake_httpx.response = _FakeResponse(
            status_code=200, json_data={"hello": "world"}, text='{"hello":"world"}'
        )

        result = await srv.http_request.fn(
            "http://example.com/api", method="get", params={"q": "x"}
        )
        assert result["success"] is True
        assert result["status_code"] == 200
        assert result["data"] == {"hello": "world"}
        # Method is upper-cased and params forwarded.
        assert fake_httpx.last_request["method"] == "GET"
        assert fake_httpx.last_request["params"] == {"q": "x"}
        assert fake_httpx.last_request["url"] == "http://example.com/api"

    @pytest.mark.asyncio
    async def test_post_sends_json_body(self, fake_httpx, monkeypatch):
        import ploston_core.native_tools.network as net

        monkeypatch.setattr(net, "_resolve_host_ips", lambda host: ["93.184.216.34"])
        fake_httpx.response = _FakeResponse(status_code=201, json_data={"id": 1}, text="{}")

        result = await srv.http_request.fn(
            "http://example.com/items", method="POST", data={"name": "n"}
        )
        assert result["success"] is True
        assert result["status_code"] == 201
        # POST body is forwarded as JSON.
        assert fake_httpx.last_request["json"] == {"name": "n"}

    @pytest.mark.asyncio
    async def test_empty_url_error_envelope(self, fake_httpx):
        result = await srv.http_request.fn("")
        assert result["success"] is False
        assert "URL is required" in result["error"]

    @pytest.mark.asyncio
    async def test_ssrf_block_for_loopback(self, fake_httpx):
        # No DNS monkeypatch: 127.0.0.1 is a literal loopback IP and must be
        # rejected by the SSRF guard before any send.
        result = await srv.http_request.fn("http://127.0.0.1/secret")
        assert result["success"] is False
        assert "SSRF" in result["error"]


# =============================================================================
# ML handlers backed by Ollama (httpx) — mock the embeddings endpoint
# =============================================================================


class TestMlOllamaBacked:
    @pytest.mark.asyncio
    async def test_embed_text_wires_model_and_host(self, fake_httpx):
        fake_httpx.response = _FakeResponse(
            status_code=200, json_data={"embedding": [0.1, 0.2, 0.3]}, text="{}"
        )
        result = await srv.ml_embed_text.fn("hello", model="custom-model")
        assert result["success"] is True
        assert result["embedding"] == [0.1, 0.2, 0.3]
        # Ollama embeddings endpoint + payload shaping.
        req = fake_httpx.last_request
        assert req["url"].endswith("/api/embeddings")
        assert req["json"]["model"] == "custom-model"
        assert req["json"]["prompt"] == "hello"

    @pytest.mark.asyncio
    async def test_embed_text_empty_input_error(self, fake_httpx):
        result = await srv.ml_embed_text.fn("")
        assert result["success"] is False
        assert "Text is required" in result["error"]

    @pytest.mark.asyncio
    async def test_cosine_similarity_uses_embeddings(self, fake_httpx):
        # Same embedding for both texts => cosine similarity ~1.0.
        fake_httpx.response = _FakeResponse(
            status_code=200, json_data={"embedding": [1.0, 0.0, 0.0]}, text="{}"
        )
        result = await srv.ml_text_similarity.fn("a", "b", method="cosine")
        assert result["success"] is True
        assert result["method"] == "cosine"
        assert result["similarity"] == pytest.approx(1.0, abs=1e-6)


class TestMlLocalMethods:
    """These don't require Ollama and run purely in-process."""

    @pytest.mark.asyncio
    async def test_jaccard_similarity(self):
        result = await srv.ml_text_similarity.fn(
            "hello world foo", "hello world bar", method="jaccard"
        )
        assert result["success"] is True
        assert result["method"] == "jaccard"
        assert result["similarity"] == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_unknown_method_error(self):
        result = await srv.ml_text_similarity.fn("a", "b", method="bogus")
        assert result["success"] is False
        assert "Unknown similarity method" in result["error"]

    @pytest.mark.asyncio
    async def test_sentiment_positive(self):
        result = await srv.ml_analyze_sentiment.fn("I love this wonderful happy great thing")
        assert result["success"] is True
        assert result["sentiment"] == "positive"

    @pytest.mark.asyncio
    async def test_sentiment_negative(self):
        result = await srv.ml_analyze_sentiment.fn("terrible awful horrible bad")
        assert result["success"] is True
        assert result["sentiment"] == "negative"

    @pytest.mark.asyncio
    async def test_sentiment_empty_error(self):
        result = await srv.ml_analyze_sentiment.fn("")
        assert result["success"] is False


# =============================================================================
# Firecrawl handlers — mock httpx, assert endpoint + payload + envelope
# =============================================================================


class TestFirecrawl:
    @pytest.mark.asyncio
    async def test_search_shapes_request_and_envelope(self, fake_httpx, monkeypatch):
        monkeypatch.setattr(srv, "FIRECRAWL_BASE_URL", "http://fc:3002")
        monkeypatch.setattr(srv, "FIRECRAWL_API_KEY", "secret-key")
        fake_httpx.response = _FakeResponse(
            status_code=200,
            json_data={"success": True, "data": [{"url": "https://a"}, {"url": "https://b"}]},
            text="{}",
        )
        result = await srv.firecrawl_search.fn("python", limit=5)
        assert result["success"] is True
        assert result["result_count"] == 2
        assert result["query"] == "python"
        req = fake_httpx.last_request
        assert req["url"] == "http://fc:3002/v1/search"
        assert req["json"] == {"query": "python", "limit": 5}
        assert req["headers"]["Authorization"] == "Bearer secret-key"

    @pytest.mark.asyncio
    async def test_map_filters_excluded_and_returns_urls(self, fake_httpx, monkeypatch):
        monkeypatch.setattr(srv, "FIRECRAWL_BASE_URL", "http://fc:3002")
        monkeypatch.setattr(srv, "FIRECRAWL_API_KEY", None)
        fake_httpx.response = _FakeResponse(
            status_code=200,
            json_data={
                "success": True,
                "links": ["https://x.com/a", "https://x.com/b"],
            },
            text="{}",
        )
        result = await srv.firecrawl_map.fn("https://x.com")
        assert result["success"] is True
        assert result["total_urls"] == 2
        assert fake_httpx.last_request["url"] == "http://fc:3002/v1/map"
        # No API key => no Authorization header.
        assert "Authorization" not in fake_httpx.last_request["headers"]

    @pytest.mark.asyncio
    async def test_extract_passes_schema_and_prompt(self, fake_httpx, monkeypatch):
        monkeypatch.setattr(srv, "FIRECRAWL_BASE_URL", "http://fc:3002")
        monkeypatch.setattr(srv, "FIRECRAWL_API_KEY", None)
        fake_httpx.response = _FakeResponse(
            status_code=200,
            json_data={"success": True, "data": {"title": "T"}},
            text="{}",
        )
        result = await srv.firecrawl_extract.fn(
            ["https://x.com"], schema={"type": "object"}, prompt="get title"
        )
        assert result["success"] is True
        assert result["data"] == {"title": "T"}
        req = fake_httpx.last_request
        assert req["url"] == "http://fc:3002/v1/extract"
        assert req["json"]["urls"] == ["https://x.com"]
        assert req["json"]["schema"] == {"type": "object"}
        assert req["json"]["prompt"] == "get title"

    @pytest.mark.asyncio
    async def test_health_reports_healthy(self, fake_httpx, monkeypatch):
        monkeypatch.setattr(srv, "FIRECRAWL_BASE_URL", "http://fc:3002")
        fake_httpx.response = _FakeResponse(status_code=200, text="ok")
        result = await srv.firecrawl_health.fn()
        assert result["success"] is True
        assert result["status"] == "healthy"
        assert result["response_code"] == 200


# --------------------------------------------------------------------------- #
# Kafka test double — inject a fake ``kafka`` package
# --------------------------------------------------------------------------- #


class _FakeRecordMeta:
    partition = 0
    offset = 42
    timestamp = 1234567890


class _FakeFuture:
    def get(self, timeout=None):
        return _FakeRecordMeta()


class _FakeProducer:
    instances: list["_FakeProducer"] = []

    def __init__(self, **config):
        self.config = config
        self.sent: list[tuple] = []
        _FakeProducer.instances.append(self)

    def send(self, topic, value=None, key=None):
        self.sent.append((topic, value, key))
        return _FakeFuture()

    def flush(self):
        pass

    def close(self):
        pass


class _FakeAdminClient:
    def __init__(self, **config):
        self.config = config

    def list_topics(self):
        return ["topic-a", "topic-b"]

    def create_topics(self, new_topics, **kw):
        return None

    def close(self):
        pass


@pytest.fixture()
def fake_kafka(monkeypatch):
    _FakeProducer.instances = []
    kafka_mod = types.ModuleType("kafka")
    kafka_mod.KafkaProducer = _FakeProducer
    kafka_mod.KafkaAdminClient = _FakeAdminClient
    kafka_mod.KafkaConsumer = object  # not exercised here

    admin_mod = types.ModuleType("kafka.admin")

    class _NewTopic:
        def __init__(self, name, num_partitions=1, replication_factor=1):
            self.name = name
            self.num_partitions = num_partitions
            self.replication_factor = replication_factor

    admin_mod.NewTopic = _NewTopic

    monkeypatch.setitem(sys.modules, "kafka", kafka_mod)
    monkeypatch.setitem(sys.modules, "kafka.admin", admin_mod)
    return kafka_mod


class TestKafka:
    @pytest.mark.asyncio
    async def test_publish_wires_config_and_returns_metadata(self, fake_kafka, monkeypatch):
        monkeypatch.setattr(srv, "KAFKA_BOOTSTRAP_SERVERS", "broker:9092")
        monkeypatch.setattr(srv, "KAFKA_CLIENT_ID", "cid")
        result = await srv.kafka_publish.fn("events", {"x": 1}, key="k1")
        assert result["success"] is True
        assert result["topic"] == "events"
        assert result["partition"] == 0
        assert result["offset"] == 42
        # Producer was built with our config + the message/key were sent.
        producer = _FakeProducer.instances[-1]
        assert producer.config["bootstrap_servers"] == "broker:9092"
        assert producer.config["client_id"] == "cid"
        topic, value, key = producer.sent[0]
        assert topic == "events"
        assert key == b"k1"
        assert b'"x": 1' in value

    @pytest.mark.asyncio
    async def test_list_topics_returns_sorted(self, fake_kafka):
        result = await srv.kafka_list_topics.fn()
        assert result["success"] is True
        assert result["topics"] == ["topic-a", "topic-b"]
        assert result["topic_count"] == 2

    @pytest.mark.asyncio
    async def test_create_topic(self, fake_kafka):
        result = await srv.kafka_create_topic.fn("new-topic", num_partitions=3)
        assert result["success"] is True
        assert result["topic"] == "new-topic"

    @pytest.mark.asyncio
    async def test_publish_missing_library_raises(self, monkeypatch):
        # No fake_kafka fixture: ensure the lazy import fails => ImportError.
        monkeypatch.setitem(sys.modules, "kafka", None)
        with pytest.raises(ImportError):
            await srv.kafka_publish.fn("t", "m")
