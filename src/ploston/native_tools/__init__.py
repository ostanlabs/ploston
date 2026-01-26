"""Native Tools MCP Server for Ploston.

This module provides the FastMCP server wrapper that exposes native tools
from ploston_core.native_tools via the Model Context Protocol (MCP).
"""

from .config_manager import ConfigManager, ToolConfig, get_config, get_config_manager
from .config_watcher import NativeToolsConfig, RedisConfigWatcher, RedisConfigWatcherOptions
from .server import mcp

__all__ = [
    "mcp",
    "ConfigManager",
    "ToolConfig",
    "get_config",
    "get_config_manager",
    "NativeToolsConfig",
    "RedisConfigWatcher",
    "RedisConfigWatcherOptions",
]
