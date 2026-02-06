#!/usr/bin/env python3
"""Wrapper script to run native_tools MCP server.

This script runs the native tools MCP server which exposes tool implementations
from ploston_core.native_tools via the Model Context Protocol (MCP).
"""

from ploston.native_tools.server import mcp

mcp.run()
