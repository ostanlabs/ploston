#!/usr/bin/env python3
"""
MCP HTTP Test Client - Simulates an MCP client for testing Ploston over HTTP transport.

This utility connects to a Ploston server via HTTP and communicates using the
MCP protocol (JSON-RPC). Designed for use with docker-compose or any running server.

Usage:
    # Connect to docker-compose server (default: localhost:8082)
    python internal/mcp_http_test_client.py --list-tools

    # Connect to custom host/port
    python internal/mcp_http_test_client.py --host localhost --port 8080 --list-tools

    # Call a tool
    python internal/mcp_http_test_client.py --call http_request '{"url": "https://httpbin.org/get", "method": "GET"}'

    # Run a workflow
    python internal/mcp_http_test_client.py --workflow fetch-url '{"url": "https://httpbin.org/get"}'

Environment Variables:
    PLOSTON_HOST: Server host (default: 127.0.0.1)
    PLOSTON_PORT: Server port (default: 8082 for docker-compose test server)
"""

import argparse
import json
import os
import sys
import time
from typing import Any

import requests


class MCPHTTPTestClient:
    """MCP client that communicates with Ploston server via HTTP."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8082,
    ):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self._msg_id = 0
        self._session_id: str | None = None

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def wait_for_server(self, timeout: int = 30) -> bool:
        """Wait for the HTTP server to be ready.

        Returns:
            True if server is ready, False if timeout.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.base_url}/health", timeout=1)
                if response.status_code == 200:
                    print(f"[CLIENT] Server ready at {self.base_url}", file=sys.stderr)
                    return True
            except requests.exceptions.ConnectionError:
                pass
            time.sleep(0.5)
        return False

    def is_server_running(self) -> bool:
        """Check if the server is running."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            return response.status_code == 200
        except requests.exceptions.ConnectionError:
            return False

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a JSON-RPC request via HTTP."""
        msg_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
        }
        if params:
            request["params"] = params

        headers = {"Content-Type": "application/json"}
        if self._session_id:
            headers["X-MCP-Session-ID"] = self._session_id

        print(f"[CLIENT] >>> {method}", file=sys.stderr)

        response = requests.post(
            f"{self.base_url}/mcp",
            json=request,
            headers=headers,
            timeout=60,
        )

        if response.status_code == 204:
            return {"jsonrpc": "2.0", "id": msg_id, "result": None}

        return response.json()

    def initialize(self) -> dict[str, Any]:
        """Send initialize request."""
        return self.send(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "mcp-http-test-client", "version": "1.0.0"},
                "capabilities": {},
            },
        )

    def list_tools(self) -> list[dict[str, Any]]:
        """List available tools."""
        response = self.send("tools/list", {})
        if "error" in response:
            raise RuntimeError(f"Error: {response['error']}")
        return response.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool."""
        response = self.send("tools/call", {"name": name, "arguments": arguments})
        if "error" in response:
            raise RuntimeError(f"Error: {response['error']}")
        return response.get("result", {})

    def ping(self) -> bool:
        """Ping the server."""
        response = self.send("ping", {})
        return response.get("result", {}).get("pong", False)


def print_json(data: Any, indent: int = 2) -> None:
    """Pretty print JSON data."""
    print(json.dumps(data, indent=indent))


def interactive_mode(client: MCPHTTPTestClient) -> None:
    """Run interactive REPL."""
    print("\n=== MCP HTTP Test Client Interactive Mode ===")
    print("Commands:")
    print("  init                      - Send initialize request")
    print("  list                      - List available tools")
    print("  call <tool> [json_args]   - Call a tool")
    print("  workflow <name> [inputs]  - Run a workflow")
    print("  ping                      - Ping server")
    print("  raw <method> [json_params] - Send raw JSON-RPC")
    print("  quit                      - Exit")
    print()

    while True:
        try:
            line = input("mcp-http> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        parts = line.split(maxsplit=2)
        cmd = parts[0].lower()

        try:
            if cmd in ("quit", "exit", "q"):
                break
            elif cmd == "init":
                print_json(client.initialize())
            elif cmd == "list":
                tools = client.list_tools()
                print(f"\nFound {len(tools)} tools:\n")
                for t in sorted(tools, key=lambda x: x["name"]):
                    print(f"  {t['name']:<40} {t.get('description', '')[:40]}")
                print()
            elif cmd == "call" and len(parts) >= 2:
                tool_name = parts[1]
                args = json.loads(parts[2]) if len(parts) > 2 else {}
                result = client.call_tool(tool_name, args)
                print_json(result)
            elif cmd == "workflow" and len(parts) >= 2:
                workflow_name = parts[1]
                inputs = json.loads(parts[2]) if len(parts) > 2 else {}
                result = client.call_tool(f"workflow:{workflow_name}", inputs)
                print_json(result)
            elif cmd == "ping":
                print(f"Pong: {client.ping()}")
            elif cmd == "raw" and len(parts) >= 2:
                method = parts[1]
                params = json.loads(parts[2]) if len(parts) > 2 else None
                print_json(client.send(method, params))
            elif cmd == "help":
                print("Commands: init, list, call, workflow, ping, raw, quit")
            else:
                print(f"Unknown command: {cmd}. Type 'help' for commands.")
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)


def main():
    # Default port is 8082 (docker-compose test server)
    default_host = os.environ.get("PLOSTON_HOST", "127.0.0.1")
    default_port = int(os.environ.get("PLOSTON_PORT", "8082"))

    parser = argparse.ArgumentParser(
        description="MCP HTTP Test Client for Ploston",
        epilog="""
Examples:
  # Start docker-compose first:
  docker compose -f docker-compose.test.yml up -d

  # Then run tests:
  python internal/mcp_http_test_client.py --list-tools
  python internal/mcp_http_test_client.py --call http_request '{"url": "https://httpbin.org/get", "method": "GET"}'
  python internal/mcp_http_test_client.py --workflow fetch-url '{"url": "https://httpbin.org/get"}'
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default=default_host,
        help=f"Server host (default: {default_host}, or PLOSTON_HOST env var)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help=f"Server port (default: {default_port}, or PLOSTON_PORT env var)",
    )
    parser.add_argument("--list-tools", action="store_true", help="List tools and exit")
    parser.add_argument(
        "--call",
        nargs=2,
        metavar=("TOOL", "ARGS"),
        help="Call a tool with JSON args",
    )
    parser.add_argument(
        "--workflow",
        nargs=2,
        metavar=("NAME", "INPUTS"),
        help="Run a workflow with JSON inputs",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=0,
        metavar="SECONDS",
        help="Wait up to N seconds for server to be ready (default: 0, fail immediately if not ready)",
    )

    args = parser.parse_args()

    client = MCPHTTPTestClient(args.host, args.port)

    # Check if server is running
    if args.wait > 0:
        if not client.wait_for_server(timeout=args.wait):
            print(
                f"[ERROR] Server not ready at {client.base_url} after {args.wait}s",
                file=sys.stderr,
            )
            print(
                "[ERROR] Start the server with: docker compose -f docker-compose.test.yml up -d",
                file=sys.stderr,
            )
            sys.exit(1)
    elif not client.is_server_running():
        print(f"[ERROR] Server not running at {client.base_url}", file=sys.stderr)
        print(
            "[ERROR] Start the server with: docker compose -f docker-compose.test.yml up -d",
            file=sys.stderr,
        )
        sys.exit(1)

    # Initialize MCP session
    init_response = client.initialize()
    print(
        f"[CLIENT] Connected to: {init_response.get('result', {}).get('serverInfo', {})}",
        file=sys.stderr,
    )

    if args.list_tools:
        tools = client.list_tools()
        print(f"\n{'=' * 60}")
        print(f"Available Tools ({len(tools)})")
        print(f"{'=' * 60}\n")
        for t in sorted(tools, key=lambda x: x["name"]):
            desc = t.get("description", "")[:50]
            print(f"  {t['name']:<40} {desc}")
        print()

    elif args.call:
        tool_name, args_json = args.call
        arguments = json.loads(args_json)
        result = client.call_tool(tool_name, arguments)
        print(f"\n{'=' * 60}")
        print(f"Tool: {tool_name}")
        print(f"{'=' * 60}")
        print_json(result)

    elif args.workflow:
        workflow_name, inputs_json = args.workflow
        inputs = json.loads(inputs_json)
        result = client.call_tool(f"workflow:{workflow_name}", inputs)
        print(f"\n{'=' * 60}")
        print(f"Workflow: {workflow_name}")
        print(f"{'=' * 60}")
        print_json(result)

    else:
        # Interactive mode
        interactive_mode(client)


if __name__ == "__main__":
    main()
