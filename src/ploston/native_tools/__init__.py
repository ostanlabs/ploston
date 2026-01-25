"""Native Tools MCP Server for Ploston.

This module provides the FastMCP server wrapper that exposes native tools
from ploston_core.native_tools via the Model Context Protocol (MCP).
"""

from .server import mcp

__all__ = ["mcp"]
