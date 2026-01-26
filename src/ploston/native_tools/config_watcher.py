"""Redis Config Watcher for Native Tools.

This module provides reactive configuration updates from Redis pub/sub.
When ploston publishes config changes, native-tools receives them and
reinitializes affected tools.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class KafkaConfig(BaseModel):
    """Kafka configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    bootstrap_servers: str = ""
    producer: dict[str, Any] = Field(default_factory=lambda: {"acks": "all", "retries": 3})
    consumer: dict[str, Any] = Field(default_factory=lambda: {"auto_offset_reset": "earliest"})
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: Optional[str] = None
    sasl_username: Optional[str] = None
    sasl_password: Optional[str] = None


class FirecrawlConfig(BaseModel):
    """Firecrawl configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    base_url: str = ""
    api_key: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3


class OllamaConfig(BaseModel):
    """Ollama configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    host: str = "http://localhost:11434"
    default_model: str = "llama3.2"
    timeout: int = 120


class FilesystemConfig(BaseModel):
    """Filesystem configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    workspace_dir: str = "/workspace"
    allowed_paths: list[str] = Field(default_factory=list)
    denied_paths: list[str] = Field(default_factory=list)
    max_file_size: int = 10 * 1024 * 1024  # 10MB


class NetworkConfig(BaseModel):
    """Network configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    timeout: int = 30
    max_retries: int = 3
    allowed_hosts: list[str] = Field(default_factory=list)
    denied_hosts: list[str] = Field(default_factory=list)


class DataConfig(BaseModel):
    """Data transformation configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    max_data_size: int = 50 * 1024 * 1024  # 50MB


class NativeToolsConfig(BaseModel):
    """Configuration model for native-tools.

    Uses extra="ignore" for forward compatibility - new fields from
    ploston won't break older native-tools versions.
    """

    model_config = ConfigDict(extra="ignore")

    kafka: KafkaConfig = Field(default_factory=KafkaConfig)
    firecrawl: FirecrawlConfig = Field(default_factory=FirecrawlConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    filesystem: FilesystemConfig = Field(default_factory=FilesystemConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    data: DataConfig = Field(default_factory=DataConfig)


def resolve_env_vars(value: str) -> str:
    """Resolve environment variable references in string.

    Supports:
    - ${VAR} - Required, returns empty string if not set
    - ${VAR:-default} - With default value

    Args:
        value: String with potential env var references

    Returns:
        String with env vars resolved
    """
    pattern = r"\$\{([^}:]+)(?::(-?)([^}]*))?\}"

    def replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        operator = match.group(2)  # '-' or None
        operand = match.group(3)  # default value

        env_value = os.environ.get(var_name)

        if env_value is not None:
            return env_value

        # Variable not set
        if operator == "-":
            return operand or ""
        else:
            # Return empty string for unset vars (don't fail)
            return ""

    return re.sub(pattern, replacer, value)


def resolve_config_env_vars(config: dict[str, Any]) -> dict[str, Any]:
    """Recursively resolve env vars in config dict.

    Args:
        config: Configuration dictionary

    Returns:
        Config with env vars resolved
    """
    if isinstance(config, dict):
        return {k: resolve_config_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [resolve_config_env_vars(item) for item in config]
    elif isinstance(config, str):
        return resolve_env_vars(config)
    else:
        return config


@dataclass
class RedisConfigWatcherOptions:
    """Options for RedisConfigWatcher."""

    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    key_prefix: str = field(
        default_factory=lambda: os.getenv("REDIS_CONFIG_PREFIX", "ploston:config")
    )
    channel: str = field(
        default_factory=lambda: os.getenv("REDIS_CONFIG_CHANNEL", "ploston:config:changed")
    )
    service_name: str = field(
        default_factory=lambda: os.getenv("REDIS_SERVICE_NAME", "native-tools")
    )
    reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 0  # 0 = infinite


class RedisConfigWatcher:
    """Watches Redis for configuration changes and triggers callbacks.

    This class:
    - Subscribes to the config change channel
    - Fetches initial config on startup
    - Calls registered callbacks when config changes
    - Handles reconnection on Redis failures
    """

    def __init__(
        self,
        options: Optional[RedisConfigWatcherOptions] = None,
        on_config_change: Optional[Callable[[NativeToolsConfig], None]] = None,
    ):
        """Initialize the config watcher.

        Args:
            options: Configuration options
            on_config_change: Callback when config changes
        """
        self._options = options or RedisConfigWatcherOptions()
        self._on_config_change = on_config_change
        self._client: Optional[Any] = None  # redis.asyncio.Redis
        self._pubsub: Optional[Any] = None  # redis.asyncio.PubSub
        self._running = False
        self._current_config: Optional[NativeToolsConfig] = None
        self._last_version: int = 0
        self._connected = False
        self._offline_since: Optional[datetime] = None
        self._watch_task: Optional[asyncio.Task[None]] = None

    @property
    def connected(self) -> bool:
        """Return whether connected to Redis."""
        return self._connected

    @property
    def current_config(self) -> Optional[NativeToolsConfig]:
        """Return current configuration."""
        return self._current_config

    @property
    def offline_duration_seconds(self) -> Optional[float]:
        """Return how long we've been offline, or None if connected."""
        if self._connected or self._offline_since is None:
            return None
        return (datetime.now(timezone.utc) - self._offline_since).total_seconds()

    async def start(self) -> bool:
        """Start watching for config changes.

        Returns:
            True if started successfully, False otherwise.
        """
        if self._running:
            return True

        try:
            import redis.asyncio as redis

            self._client = redis.from_url(
                self._options.redis_url,
                decode_responses=True,
            )

            # Test connection
            await self._client.ping()
            self._connected = True
            self._offline_since = None
            logger.info(f"Connected to Redis at {self._options.redis_url}")

            # Fetch initial config
            await self._fetch_config()

            # Start watching
            self._running = True
            self._watch_task = asyncio.create_task(self._watch_loop())

            return True

        except ImportError:
            logger.error("redis package not installed")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            self._offline_since = datetime.now(timezone.utc)
            return False

    async def stop(self) -> None:
        """Stop watching for config changes."""
        self._running = False

        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            self._watch_task = None

        if self._pubsub:
            try:
                await self._pubsub.unsubscribe()
                await self._pubsub.aclose()
            except Exception:
                pass
            self._pubsub = None

        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

        self._connected = False
        logger.info("Stopped config watcher")

    async def _fetch_config(self) -> None:
        """Fetch current config from Redis."""
        if not self._client:
            return

        try:
            key = f"{self._options.key_prefix}:{self._options.service_name}"
            data = await self._client.get(key)

            if data:
                import json

                payload = json.loads(data)
                version = payload.get("version", 0)

                if version > self._last_version:
                    config_dict = payload.get("config", {})
                    # Resolve env vars
                    resolved = resolve_config_env_vars(config_dict)
                    self._current_config = NativeToolsConfig.model_validate(resolved)
                    self._last_version = version

                    logger.info(f"Loaded config version {version}")

                    if self._on_config_change:
                        self._on_config_change(self._current_config)

        except Exception as e:
            logger.error(f"Failed to fetch config: {e}")

    async def _watch_loop(self) -> None:
        """Main loop for watching config changes."""
        reconnect_attempts = 0

        while self._running:
            try:
                if not self._client:
                    raise ConnectionError("No Redis client")

                self._pubsub = self._client.pubsub()
                await self._pubsub.subscribe(self._options.channel)

                self._connected = True
                self._offline_since = None
                reconnect_attempts = 0

                async for message in self._pubsub.listen():
                    if not self._running:
                        break

                    if message["type"] == "message":
                        await self._handle_notification(message["data"])

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Config watcher error: {e}")
                self._connected = False
                if self._offline_since is None:
                    self._offline_since = datetime.now(timezone.utc)

                reconnect_attempts += 1
                max_attempts = self._options.max_reconnect_attempts
                if max_attempts > 0 and reconnect_attempts >= max_attempts:
                    logger.error("Max reconnect attempts reached")
                    break

                await asyncio.sleep(self._options.reconnect_delay)

                # Try to reconnect
                try:
                    import redis.asyncio as redis

                    self._client = redis.from_url(
                        self._options.redis_url,
                        decode_responses=True,
                    )
                    await self._client.ping()
                except Exception:
                    pass

    async def _handle_notification(self, data: str) -> None:
        """Handle a config change notification.

        Args:
            data: JSON notification data
        """
        try:
            import json

            notification = json.loads(data)
            service = notification.get("service")
            version = notification.get("version", 0)

            # Only process notifications for our service
            if service != self._options.service_name:
                return

            # Only process if version is newer
            if version <= self._last_version:
                return

            logger.info(f"Received config update notification (version {version})")
            await self._fetch_config()

        except Exception as e:
            logger.error(f"Failed to handle notification: {e}")

    def get_health_status(self) -> dict[str, Any]:
        """Get health status for health check endpoint.

        Returns:
            Health status dict
        """
        status: dict[str, Any] = {
            "redis_connected": self._connected,
            "config_version": self._last_version,
        }

        if not self._connected and self._offline_since:
            duration = self.offline_duration_seconds
            status["offline_since"] = self._offline_since.isoformat()
            status["offline_duration_seconds"] = duration
            if duration:
                if duration < 60:
                    status["offline_message"] = f"Redis offline for {int(duration)} seconds"
                elif duration < 3600:
                    status["offline_message"] = f"Redis offline for {int(duration / 60)} minutes"
                else:
                    status["offline_message"] = f"Redis offline for {duration / 3600:.1f} hours"

        return status
