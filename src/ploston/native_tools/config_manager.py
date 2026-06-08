"""Configuration Manager for Native Tools.

This module manages the global configuration state for native-tools,
integrating with the Redis config watcher for reactive updates.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ploston_core.native_tools.utils import (
    resolve_kafka_servers_for_docker,
    resolve_url_for_docker,
)

from .config_watcher import NativeToolsConfig, RedisConfigWatcher, RedisConfigWatcherOptions

logger = logging.getLogger(__name__)

# Safe, dedicated default workspace used when WORKSPACE_DIR is not set.
# Importantly this is NOT the process CWD (which is /app, the code tree, in the
# native-tools Docker image) — see PL-C3.
DEFAULT_WORKSPACE_DIR = "/workspace"

# Default filesystem / network limits (mirrors config_watcher schema defaults).
DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_MAX_DATA_SIZE = 50 * 1024 * 1024  # 50MB


def _default_workspace_dir() -> str:
    """Resolve the default workspace, failing closed away from CWD (PL-C3).

    In Docker, ``os.getcwd()`` is ``/app`` (the code tree); silently using it
    as the writable/readable workspace would expose the application source to
    fs tools. We instead use a dedicated DEFAULT_WORKSPACE_DIR and warn so the
    misconfiguration is visible.
    """
    logger.warning(
        "WORKSPACE_DIR is not set; defaulting to safe workspace %s instead of "
        "the current working directory. Set WORKSPACE_DIR explicitly.",
        DEFAULT_WORKSPACE_DIR,
    )
    return DEFAULT_WORKSPACE_DIR


@dataclass
class ToolConfig:
    """Current tool configuration values."""

    # Workspace
    workspace_dir: str = DEFAULT_WORKSPACE_DIR

    # Filesystem security (PL-C5) — enforced by fs tools.
    max_file_size: int = DEFAULT_MAX_FILE_SIZE
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=list)

    # Network security (PL-C5) — enforced by http_request.
    allowed_hosts: list[str] = field(default_factory=list)
    denied_hosts: list[str] = field(default_factory=list)

    # Data limit (PL-C5). NOTE: not yet enforced by the data transform tools;
    # wired into config so it can be consumed once those tools accept a limit.
    # TODO(PL-C5): thread max_data_size into data transform tools.
    max_data_size: int = DEFAULT_MAX_DATA_SIZE

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
        workspace_env = os.getenv("WORKSPACE_DIR")
        self._config.workspace_dir = workspace_env or _default_workspace_dir()

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

        # Update filesystem config (PL-C5): wire through the security fields so
        # they are actually enforced by the fs tools, not just decorative.
        if new_config.filesystem.enabled:
            self._config.workspace_dir = new_config.filesystem.workspace_dir
            self._config.allowed_paths = list(new_config.filesystem.allowed_paths)
            self._config.denied_paths = list(new_config.filesystem.denied_paths)
            self._config.max_file_size = new_config.filesystem.max_file_size

        # Update network config (PL-C5): wire allow/deny hosts through to
        # http_request's SSRF guard.
        if new_config.network.enabled:
            self._config.allowed_hosts = list(new_config.network.allowed_hosts)
            self._config.denied_hosts = list(new_config.network.denied_hosts)

        # Update data config (PL-C5).
        if new_config.data.enabled:
            self._config.max_data_size = new_config.data.max_data_size

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
