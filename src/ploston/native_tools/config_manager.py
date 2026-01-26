"""Configuration Manager for Native Tools.

This module manages the global configuration state for native-tools,
integrating with the Redis config watcher for reactive updates.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ploston_core.native_tools.utils import (
    resolve_kafka_servers_for_docker,
    resolve_url_for_docker,
)

from .config_watcher import NativeToolsConfig, RedisConfigWatcher, RedisConfigWatcherOptions

logger = logging.getLogger(__name__)


@dataclass
class ToolConfig:
    """Current tool configuration values."""

    # Workspace
    workspace_dir: str = os.getcwd()

    # Firecrawl
    firecrawl_base_url: str = "http://localhost:3002"
    firecrawl_api_key: Optional[str] = None

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_client_id: str = "mcp-native-tools"
    kafka_security_protocol: str = "PLAINTEXT"
    kafka_sasl_mechanism: Optional[str] = None
    kafka_sasl_username: Optional[str] = None
    kafka_sasl_password: Optional[str] = None

    # Ollama
    ollama_host: str = "http://localhost:11434"
    default_embedding_model: str = "all-minilm:latest"


class ConfigManager:
    """Manages native-tools configuration with Redis integration.

    This class:
    - Loads initial config from environment variables
    - Optionally connects to Redis for reactive updates
    - Provides current config values to tools
    - Notifies registered callbacks on config changes
    """

    def __init__(self):
        """Initialize the config manager."""
        self._config = ToolConfig()
        self._watcher: Optional[RedisConfigWatcher] = None
        self._on_change_callbacks: list[Callable[[ToolConfig], None]] = []
        self._load_from_env()

    def _load_from_env(self) -> None:
        """Load configuration from environment variables."""
        self._config.workspace_dir = os.getenv("WORKSPACE_DIR", os.getcwd())

        # Firecrawl
        raw_firecrawl_url = os.getenv("FIRECRAWL_BASE_URL", "http://localhost:3002")
        self._config.firecrawl_base_url = resolve_url_for_docker(raw_firecrawl_url)
        self._config.firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")

        # Kafka
        raw_kafka_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self._config.kafka_bootstrap_servers = resolve_kafka_servers_for_docker(raw_kafka_servers)
        self._config.kafka_client_id = os.getenv("KAFKA_CLIENT_ID", "mcp-native-tools")
        self._config.kafka_security_protocol = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
        self._config.kafka_sasl_mechanism = os.getenv("KAFKA_SASL_MECHANISM")
        self._config.kafka_sasl_username = os.getenv("KAFKA_SASL_USERNAME")
        self._config.kafka_sasl_password = os.getenv("KAFKA_SASL_PASSWORD")

        # Ollama
        raw_ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self._config.ollama_host = resolve_url_for_docker(raw_ollama_host)
        self._config.default_embedding_model = os.getenv(
            "DEFAULT_EMBEDDING_MODEL", "all-minilm:latest"
        )

        logger.info("Loaded config from environment")

    @property
    def config(self) -> ToolConfig:
        """Get current configuration."""
        return self._config

    @property
    def redis_connected(self) -> bool:
        """Check if connected to Redis."""
        return self._watcher is not None and self._watcher.connected

    def on_change(self, callback: Callable[[ToolConfig], None]) -> None:
        """Register callback for config changes.

        Args:
            callback: Function to call when config changes
        """
        self._on_change_callbacks.append(callback)

    async def start_redis_watcher(self) -> bool:
        """Start watching Redis for config changes.

        Returns:
            True if started successfully, False otherwise.
        """
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logger.info("REDIS_URL not set, skipping Redis config watcher")
            return False

        options = RedisConfigWatcherOptions()
        self._watcher = RedisConfigWatcher(
            options=options,
            on_config_change=self._handle_config_change,
        )

        return await self._watcher.start()

    async def stop_redis_watcher(self) -> None:
        """Stop the Redis config watcher."""
        if self._watcher:
            await self._watcher.stop()
            self._watcher = None

    def _handle_config_change(self, new_config: NativeToolsConfig) -> None:
        """Handle config change from Redis.

        Args:
            new_config: New configuration from Redis
        """
        logger.info("Applying config update from Redis")

        # Update Firecrawl config
        if new_config.firecrawl.enabled:
            raw_url = new_config.firecrawl.base_url
            self._config.firecrawl_base_url = resolve_url_for_docker(raw_url)
            self._config.firecrawl_api_key = new_config.firecrawl.api_key

        # Update Kafka config
        if new_config.kafka.enabled:
            raw_servers = new_config.kafka.bootstrap_servers
            self._config.kafka_bootstrap_servers = resolve_kafka_servers_for_docker(raw_servers)
            self._config.kafka_security_protocol = new_config.kafka.security_protocol
            self._config.kafka_sasl_mechanism = new_config.kafka.sasl_mechanism
            self._config.kafka_sasl_username = new_config.kafka.sasl_username
            self._config.kafka_sasl_password = new_config.kafka.sasl_password

        # Update Ollama config
        if new_config.ollama.enabled:
            raw_host = new_config.ollama.host
            self._config.ollama_host = resolve_url_for_docker(raw_host)
            self._config.default_embedding_model = new_config.ollama.default_model

        # Update filesystem config
        if new_config.filesystem.enabled:
            self._config.workspace_dir = new_config.filesystem.workspace_dir

        # Notify callbacks
        for callback in self._on_change_callbacks:
            try:
                callback(self._config)
            except Exception as e:
                logger.error(f"Config change callback failed: {e}")

    def get_health_status(self) -> dict[str, Any]:
        """Get health status for health check endpoint.

        Returns:
            Health status dict
        """
        status: dict[str, Any] = {
            "config_source": "redis" if self.redis_connected else "environment",
        }

        if self._watcher:
            status.update(self._watcher.get_health_status())

        return status


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global config manager instance.

    Returns:
        ConfigManager instance
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def get_config() -> ToolConfig:
    """Get current tool configuration.

    Returns:
        Current ToolConfig
    """
    return get_config_manager().config
