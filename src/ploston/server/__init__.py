"""Ploston OSS Server module.

This module provides the server startup functionality for the
open-source community tier.
"""

import asyncio

from ploston_core import PlostApplication
from ploston_core.extensions import FeatureFlagRegistry
from ploston_core.mcp_frontend import MCPFrontend, MCPServerConfig
from ploston_core.types import MCPTransport

from ploston.defaults import COMMUNITY_FEATURE_FLAGS

__all__ = [
    "MCPFrontend",
    "MCPServerConfig",
    "PlostApplication",
    "create_server",
    "main",
]


async def create_server(
    config_path: str | None = None,
    host: str = "0.0.0.0",
    port: int = 8080,
    with_rest_api: bool = True,
) -> PlostApplication:
    """Create OSS server with community defaults.

    Args:
        config_path: Optional path to configuration file.
        host: HTTP host (default: 0.0.0.0)
        port: HTTP port (default: 8080)
        with_rest_api: Enable REST API alongside MCP (default: True)

    Returns:
        Configured PlostApplication instance (initialized).
    """
    # Set community feature flags
    FeatureFlagRegistry.set_flags(COMMUNITY_FEATURE_FLAGS)

    # Create application with full component initialization
    app = PlostApplication(
        config_path=config_path,
        transport=MCPTransport.HTTP,
        http_host=host,
        http_port=port,
        with_rest_api=with_rest_api,
        rest_api_prefix="/api/v1",
        rest_api_docs=True,
    )
    await app.initialize()
    return app


def main():
    """CLI entrypoint for ploston-server."""
    import argparse

    parser = argparse.ArgumentParser(description="Ploston OSS Server")
    parser.add_argument("-c", "--config", help="Config file path")
    parser.add_argument("-p", "--port", type=int, default=8080, help="HTTP port")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host")
    parser.add_argument("--no-rest", action="store_true", help="Disable REST API (MCP only)")
    args = parser.parse_args()

    # Set community feature flags
    FeatureFlagRegistry.set_flags(COMMUNITY_FEATURE_FLAGS)

    async def run_server():
        """Run the server with full initialization."""
        app = PlostApplication(
            config_path=args.config,
            transport=MCPTransport.HTTP,
            http_host=args.host,
            http_port=args.port,
            with_rest_api=not args.no_rest,
            rest_api_prefix="/api/v1",
            rest_api_docs=True,
        )

        mode = "dual-mode (MCP + REST)" if not args.no_rest else "MCP only"
        print(
            f"[Ploston] Starting server on http://{args.host}:{args.port} ({mode})",
            flush=True,
        )

        try:
            await app.initialize()
            print("[Ploston] Server initialized successfully", flush=True)
            await app.start()
        except KeyboardInterrupt:
            print("\n[Ploston] Shutting down...", flush=True)
            await app.shutdown()
        except Exception as e:
            print(f"[Ploston] Error: {e}", flush=True)
            await app.shutdown()
            raise

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
