"""Ploston OSS Server module.

This module provides the server startup functionality for the
open-source community tier.
"""

import asyncio
from typing import Optional

from ploston_core.mcp_frontend import MCPFrontend, MCPServerConfig
from ploston_core.extensions import FeatureFlagRegistry

from ploston.defaults import COMMUNITY_FEATURE_FLAGS


__all__ = [
    "MCPFrontend",
    "MCPServerConfig",
    "create_server",
    "main",
]


def create_server(config_path: Optional[str] = None) -> MCPFrontend:
    """Create OSS server with community defaults.

    Args:
        config_path: Optional path to configuration file.

    Returns:
        Configured MCPFrontend server instance.
    """
    # Set community feature flags
    FeatureFlagRegistry.set_flags(COMMUNITY_FEATURE_FLAGS)

    # Create server with default config
    config = MCPServerConfig()
    return MCPFrontend(config)


def main():
    """CLI entrypoint for ploston-server."""
    import argparse

    parser = argparse.ArgumentParser(description="Ploston OSS Server")
    parser.add_argument("-c", "--config", help="Config file path")
    parser.add_argument("-p", "--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    server = create_server(args.config)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
