"""Ploston OSS Server module.

This module provides the server startup functionality for the
open-source community tier.
"""

import asyncio

from ploston_core.extensions import FeatureFlagRegistry
from ploston_core.mcp_frontend import MCPFrontend, MCPServerConfig

from ploston.defaults import COMMUNITY_FEATURE_FLAGS

__all__ = [
    "MCPFrontend",
    "MCPServerConfig",
    "create_server",
    "main",
]


def create_server(config_path: str | None = None) -> MCPFrontend:
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

    from ploston_core.config import MCPHTTPConfig
    from ploston_core.types import MCPTransport

    parser = argparse.ArgumentParser(description="Ploston OSS Server")
    parser.add_argument("-c", "--config", help="Config file path")
    parser.add_argument("-p", "--port", type=int, default=8080, help="HTTP port")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host")
    args = parser.parse_args()

    # Set community feature flags
    FeatureFlagRegistry.set_flags(COMMUNITY_FEATURE_FLAGS)

    # Create HTTP config with CLI arguments
    http_config = MCPHTTPConfig(host=args.host, port=args.port)

    # Create server config
    config = MCPServerConfig()

    # Create and run server with HTTP transport
    server = MCPFrontend(
        workflow_engine=None,
        tool_registry=None,
        workflow_registry=None,
        tool_invoker=None,
        config=config,
        transport=MCPTransport.HTTP,
        http_config=http_config,
    )

    print(f"[Ploston] Starting server on http://{args.host}:{args.port}", flush=True)
    asyncio.run(server.start())


if __name__ == "__main__":
    main()
