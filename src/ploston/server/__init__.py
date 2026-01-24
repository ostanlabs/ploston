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

    from ploston_core.api.app import create_rest_app
    from ploston_core.api.config import RESTConfig
    from ploston_core.config import MCPHTTPConfig
    from ploston_core.engine import WorkflowEngine
    from ploston_core.invoker import ToolInvoker
    from ploston_core.registry import ToolRegistry
    from ploston_core.types import MCPTransport

    from ploston.workflow import WorkflowRegistry

    parser = argparse.ArgumentParser(description="Ploston OSS Server")
    parser.add_argument("-c", "--config", help="Config file path")
    parser.add_argument("-p", "--port", type=int, default=8080, help="HTTP port")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host")
    parser.add_argument(
        "--no-rest", action="store_true", help="Disable REST API (MCP only)"
    )
    args = parser.parse_args()

    # Set community feature flags
    FeatureFlagRegistry.set_flags(COMMUNITY_FEATURE_FLAGS)

    # Create core components
    tool_registry = ToolRegistry()
    tool_invoker = ToolInvoker(tool_registry)
    workflow_registry = WorkflowRegistry()
    workflow_engine = WorkflowEngine(tool_invoker)

    # Create HTTP config with CLI arguments
    http_config = MCPHTTPConfig(host=args.host, port=args.port)

    # Create REST API app for dual-mode (unless disabled)
    rest_app = None
    if not args.no_rest:
        rest_config = RESTConfig(
            host=args.host,
            port=args.port,
            prefix="",  # No prefix - will be mounted at /api/v1
            title="Ploston REST API",
            version="1.0.0",
        )
        rest_app = create_rest_app(
            workflow_registry=workflow_registry,
            workflow_engine=workflow_engine,
            tool_registry=tool_registry,
            tool_invoker=tool_invoker,
            config=rest_config,
        )

    # Create server config
    config = MCPServerConfig()

    # Create and run server with HTTP transport (dual-mode: MCP + REST)
    server = MCPFrontend(
        workflow_engine=workflow_engine,
        tool_registry=tool_registry,
        workflow_registry=workflow_registry,
        tool_invoker=tool_invoker,
        config=config,
        transport=MCPTransport.HTTP,
        http_config=http_config,
        rest_app=rest_app,
        rest_prefix="/api/v1",
    )

    mode = "dual-mode (MCP + REST)" if rest_app else "MCP only"
    print(f"[Ploston] Starting server on http://{args.host}:{args.port} ({mode})", flush=True)
    asyncio.run(server.start())


if __name__ == "__main__":
    main()
