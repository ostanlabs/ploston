"""Behavioral tests for native-tools config manager + Redis config watcher.

Covers reload/notification logic that the existing security-wiring test
(test_native_tools_config_security.py) does not: the full ConfigManager
_handle_config_change for firecrawl/kafka/ollama/data sections, on_change
callbacks, env-var resolution in config payloads, and the RedisConfigWatcher
start/fetch/notify/health flow driven by a fake redis.asyncio client.

We never connect to a real Redis. We install a fake ``redis.asyncio`` module
and assert on the real config objects the watcher produces and the real
callbacks it fires.
"""

from __future__ import annotations

import json
import sys
import types

import pytest
from ploston.native_tools import config_manager as cm
from ploston.native_tools.config_watcher import (
    DataConfig,
    FirecrawlConfig,
    KafkaConfig,
    NativeToolsConfig,
    OllamaConfig,
    RedisConfigWatcher,
    RedisConfigWatcherOptions,
    resolve_config_env_vars,
    resolve_env_vars,
)

# =============================================================================
# Env-var resolution
# =============================================================================


class TestEnvVarResolution:
    def test_simple_var_substituted(self, monkeypatch):
        monkeypatch.setenv("MY_HOST", "redis.internal")
        assert resolve_env_vars("${MY_HOST}") == "redis.internal"

    def test_default_used_when_unset(self, monkeypatch):
        monkeypatch.delenv("NOPE_VAR", raising=False)
        assert resolve_env_vars("${NOPE_VAR:-fallback}") == "fallback"

    def test_set_var_overrides_default(self, monkeypatch):
        monkeypatch.setenv("SET_VAR", "real")
        assert resolve_env_vars("${SET_VAR:-fallback}") == "real"

    def test_unset_no_default_becomes_empty(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        assert resolve_env_vars("x${MISSING_VAR}y") == "xy"

    def test_recursive_resolution_in_nested_structure(self, monkeypatch):
        monkeypatch.setenv("BROKER", "k:9092")
        config = {
            "kafka": {"bootstrap_servers": "${BROKER}", "list": ["${BROKER}", "static"]},
            "n": 5,
            "flag": True,
        }
        resolved = resolve_config_env_vars(config)
        assert resolved["kafka"]["bootstrap_servers"] == "k:9092"
        assert resolved["kafka"]["list"] == ["k:9092", "static"]
        # Non-string values pass through unchanged.
        assert resolved["n"] == 5
        assert resolved["flag"] is True


# =============================================================================
# ConfigManager._handle_config_change — all dependency sections
# =============================================================================


def _fresh_manager(monkeypatch):
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    return cm.ConfigManager()


class TestHandleConfigChange:
    def test_firecrawl_section_applied(self, monkeypatch):
        mgr = _fresh_manager(monkeypatch)
        new = NativeToolsConfig(
            firecrawl=FirecrawlConfig(enabled=True, base_url="http://fc:3002", api_key="abc")
        )
        mgr._handle_config_change(new)
        assert mgr.config.firecrawl_base_url == "http://fc:3002"
        assert mgr.config.firecrawl_api_key == "abc"

    def test_kafka_section_applied(self, monkeypatch):
        mgr = _fresh_manager(monkeypatch)
        new = NativeToolsConfig(
            kafka=KafkaConfig(
                enabled=True,
                bootstrap_servers="broker:9092",
                security_protocol="SASL_PLAINTEXT",
                sasl_mechanism="PLAIN",
                sasl_username="u",
                sasl_password="p",
            )
        )
        mgr._handle_config_change(new)
        assert mgr.config.kafka_bootstrap_servers == "broker:9092"
        assert mgr.config.kafka_security_protocol == "SASL_PLAINTEXT"
        assert mgr.config.kafka_sasl_mechanism == "PLAIN"
        assert mgr.config.kafka_sasl_username == "u"
        assert mgr.config.kafka_sasl_password == "p"

    def test_ollama_section_applied(self, monkeypatch):
        mgr = _fresh_manager(monkeypatch)
        new = NativeToolsConfig(
            ollama=OllamaConfig(enabled=True, host="http://ollama:11434", default_model="mxbai")
        )
        mgr._handle_config_change(new)
        assert mgr.config.ollama_host == "http://ollama:11434"
        assert mgr.config.default_embedding_model == "mxbai"

    def test_data_section_applied(self, monkeypatch):
        mgr = _fresh_manager(monkeypatch)
        new = NativeToolsConfig(data=DataConfig(enabled=True, max_data_size=999))
        mgr._handle_config_change(new)
        assert mgr.config.max_data_size == 999

    def test_disabled_section_is_ignored(self, monkeypatch):
        mgr = _fresh_manager(monkeypatch)
        before = mgr.config.firecrawl_base_url
        new = NativeToolsConfig(
            firecrawl=FirecrawlConfig(enabled=False, base_url="http://should-not-apply")
        )
        mgr._handle_config_change(new)
        assert mgr.config.firecrawl_base_url == before

    def test_on_change_callback_invoked(self, monkeypatch):
        mgr = _fresh_manager(monkeypatch)
        seen = []
        mgr.on_change(lambda cfg: seen.append(cfg.max_data_size))
        mgr._handle_config_change(
            NativeToolsConfig(data=DataConfig(enabled=True, max_data_size=123))
        )
        assert seen == [123]

    def test_failing_callback_does_not_break_others(self, monkeypatch):
        mgr = _fresh_manager(monkeypatch)
        seen = []

        def boom(cfg):
            raise RuntimeError("callback failed")

        mgr.on_change(boom)
        mgr.on_change(lambda cfg: seen.append("ok"))
        # Should swallow the first callback's error and still run the second.
        mgr._handle_config_change(NativeToolsConfig(data=DataConfig(enabled=True, max_data_size=1)))
        assert seen == ["ok"]


# =============================================================================
# ConfigManager health status + Redis gating
# =============================================================================


class TestConfigManagerRedisGating:
    @pytest.mark.asyncio
    async def test_start_redis_watcher_no_url_returns_false(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        mgr = _fresh_manager(monkeypatch)
        assert await mgr.start_redis_watcher() is False
        assert mgr.redis_connected is False

    def test_health_status_environment_source(self, monkeypatch):
        mgr = _fresh_manager(monkeypatch)
        status = mgr.get_health_status()
        assert status["config_source"] == "environment"


# =============================================================================
# RedisConfigWatcher driven by a fake redis.asyncio client
# =============================================================================


class _FakePubSub:
    def __init__(self, messages=None):
        self._messages = messages or []
        self.subscribed = None
        self.closed = False

    async def subscribe(self, channel):
        self.subscribed = channel

    async def listen(self):
        for m in self._messages:
            yield m

    async def unsubscribe(self):
        pass

    async def aclose(self):
        self.closed = True


class _FakeRedisClient:
    def __init__(self, *, store=None, pubsub_messages=None, ping_ok=True):
        self._store = store or {}
        self._pubsub_messages = pubsub_messages or []
        self._ping_ok = ping_ok
        self.closed = False

    async def ping(self):
        if not self._ping_ok:
            raise ConnectionError("no redis")
        return True

    async def get(self, key):
        return self._store.get(key)

    def pubsub(self):
        return _FakePubSub(self._pubsub_messages)

    async def aclose(self):
        self.closed = True


def _install_fake_redis(monkeypatch, client):
    """Install a fake ``redis.asyncio`` module returning ``client``."""
    redis_pkg = types.ModuleType("redis")
    redis_async = types.ModuleType("redis.asyncio")

    def from_url(url, decode_responses=True):
        return client

    redis_async.from_url = from_url
    redis_pkg.asyncio = redis_async
    monkeypatch.setitem(sys.modules, "redis", redis_pkg)
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_async)


def _config_payload(version, *, base_url="http://fc:3002"):
    return json.dumps(
        {
            "version": version,
            "config": {"firecrawl": {"enabled": True, "base_url": base_url}},
        }
    )


class TestRedisConfigWatcher:
    @pytest.mark.asyncio
    async def test_start_fetches_initial_config_and_fires_callback(self, monkeypatch):
        received = []
        opts = RedisConfigWatcherOptions(
            redis_url="redis://x", key_prefix="ploston:config", service_name="native-tools"
        )
        key = "ploston:config:native-tools"
        client = _FakeRedisClient(store={key: _config_payload(1)})
        _install_fake_redis(monkeypatch, client)

        watcher = RedisConfigWatcher(options=opts, on_config_change=lambda c: received.append(c))
        started = await watcher.start()
        try:
            assert started is True
            assert watcher.connected is True
            # Initial fetch parsed + applied + callback fired.
            assert len(received) == 1
            assert received[0].firecrawl.base_url == "http://fc:3002"
            assert watcher.current_config is not None
        finally:
            await watcher.stop()
        assert watcher.connected is False

    @pytest.mark.asyncio
    async def test_start_returns_false_when_ping_fails(self, monkeypatch):
        client = _FakeRedisClient(ping_ok=False)
        _install_fake_redis(monkeypatch, client)
        watcher = RedisConfigWatcher(options=RedisConfigWatcherOptions(redis_url="redis://x"))
        assert await watcher.start() is False
        assert watcher.connected is False
        # offline_since recorded => offline_duration available.
        assert watcher.offline_duration_seconds is not None

    @pytest.mark.asyncio
    async def test_fetch_ignores_stale_version(self, monkeypatch):
        received = []
        key = "ploston:config:native-tools"
        client = _FakeRedisClient(store={key: _config_payload(5)})
        _install_fake_redis(monkeypatch, client)
        watcher = RedisConfigWatcher(
            options=RedisConfigWatcherOptions(redis_url="redis://x"),
            on_config_change=lambda c: received.append(c),
        )
        await watcher.start()
        try:
            assert len(received) == 1
            # Re-point store to an older version; fetch must ignore it.
            client._store[key] = _config_payload(2, base_url="http://stale")
            await watcher._fetch_config()
            assert len(received) == 1
            assert watcher.current_config.firecrawl.base_url == "http://fc:3002"
        finally:
            await watcher.stop()

    @pytest.mark.asyncio
    async def test_handle_notification_for_other_service_ignored(self, monkeypatch):
        received = []
        client = _FakeRedisClient()
        _install_fake_redis(monkeypatch, client)
        watcher = RedisConfigWatcher(
            options=RedisConfigWatcherOptions(redis_url="redis://x"),
            on_config_change=lambda c: received.append(c),
        )
        await watcher.start()
        try:
            await watcher._handle_notification(
                json.dumps({"service": "some-other-service", "version": 99})
            )
            assert received == []
        finally:
            await watcher.stop()

    @pytest.mark.asyncio
    async def test_handle_notification_triggers_refetch(self, monkeypatch):
        received = []
        key = "ploston:config:native-tools"
        client = _FakeRedisClient(store={})
        _install_fake_redis(monkeypatch, client)
        watcher = RedisConfigWatcher(
            options=RedisConfigWatcherOptions(redis_url="redis://x"),
            on_config_change=lambda c: received.append(c),
        )
        await watcher.start()
        try:
            # Now publish a config + a matching notification.
            client._store[key] = _config_payload(1)
            await watcher._handle_notification(
                json.dumps({"service": "native-tools", "version": 1})
            )
            assert len(received) == 1
            assert received[0].firecrawl.base_url == "http://fc:3002"
        finally:
            await watcher.stop()

    @pytest.mark.asyncio
    async def test_health_status_reports_version_and_connection(self, monkeypatch):
        key = "ploston:config:native-tools"
        client = _FakeRedisClient(store={key: _config_payload(7)})
        _install_fake_redis(monkeypatch, client)
        watcher = RedisConfigWatcher(options=RedisConfigWatcherOptions(redis_url="redis://x"))
        await watcher.start()
        try:
            status = watcher.get_health_status()
            assert status["redis_connected"] is True
            assert status["config_version"] == 7
        finally:
            await watcher.stop()

    def test_health_status_offline_message(self):
        watcher = RedisConfigWatcher(options=RedisConfigWatcherOptions(redis_url="redis://x"))
        from datetime import datetime, timedelta, timezone

        watcher._connected = False
        watcher._offline_since = datetime.now(timezone.utc) - timedelta(seconds=10)
        status = watcher.get_health_status()
        assert status["redis_connected"] is False
        assert "offline_message" in status
        assert "seconds" in status["offline_message"]
