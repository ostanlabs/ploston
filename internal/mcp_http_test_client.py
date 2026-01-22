#!/usr/bin/env python3
"""
MCP HTTP Test Client - Simulates an MCP client for testing AEL over HTTP transport.

This utility starts AEL with HTTP transport and communicates via HTTP using the
MCP protocol (JSON-RPC). Useful for:
- Testing AEL's HTTP transport functionality
- Faster iteration during development
- Automated integration testing with HTTP

Usage:
    # Interactive mode
    python internal/mcp_http_test_client.py -c internal/ael-config.yaml

    # Run a single command
    python internal/mcp_http_test_client.py -c internal/ael-config.yaml --list-tools
    python internal/mcp_http_test_client.py -c internal/ael-config.yaml --call workflow:fetch-url '{"url": "https://httpbin.org/get"}'
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests


class MCPHTTPTestClient:
    """MCP client that communicates with AEL via HTTP."""

    def __init__(
        self,
        config_path: str,
        ael_command: str | None = None,
        host: str = "127.0.0.1",
        port: int = 8080,
    ):
        self.config_path = Path(config_path).resolve()
        self.ael_command = ael_command or self._find_ael()
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.process: subprocess.Popen | None = None
        self._msg_id = 0
        self._session_id: str | None = None

    def _find_ael(self) -> str:
        """Find the ploston command in the virtualenv."""
        # Try common locations - check for both ploston and ael
        candidates = [
            Path(__file__).parent.parent / ".venv" / "bin" / "ploston",
            Path(sys.executable).parent / "ploston",
            Path(__file__).parent.parent / ".venv" / "bin" / "ael",
            Path(sys.executable).parent / "ael",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        # Fall back to PATH - prefer ploston
        return "ploston"

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def start(self) -> None:
        """Start AEL as a subprocess with HTTP transport."""
        cmd = [
            self.ael_command,
            "-c", str(self.config_path),
            "serve",
            "--transport", "http",
            "--host", self.host,
            "--port", str(self.port),
        ]
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.config_path.parent.parent,
        )
        print(f"[CLIENT] Started AEL HTTP server (PID: {self.process.pid})", file=sys.stderr)

        # Wait for server to be ready
        self._wait_for_server()

    def _wait_for_server(self, timeout: int = 30) -> None:
        """Wait for the HTTP server to be ready."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.base_url}/health", timeout=1)
                if response.status_code == 200:
                    print(f"[CLIENT] Server ready at {self.base_url}", file=sys.stderr)
                    return
            except requests.exceptions.ConnectionError:
                pass
            time.sleep(0.5)
        raise RuntimeError(f"Server did not start within {timeout} seconds")

    def stop(self) -> None:
        """Stop AEL subprocess."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            print("[CLIENT] Stopped AEL", file=sys.stderr)

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
        return self.send("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "mcp-http-test-client", "version": "1.0.0"},
            "capabilities": {},
        })

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
    parser = argparse.ArgumentParser(description="MCP HTTP Test Client for AEL")
    parser.add_argument("-c", "--config", required=True, help="Path to AEL config file")
    parser.add_argument("--ael", help="Path to ael command (auto-detected if not specified)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to connect to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port to connect to (default: 8080)")
    parser.add_argument("--list-tools", action="store_true", help="List tools and exit")
    parser.add_argument("--call", nargs=2, metavar=("TOOL", "ARGS"), help="Call a tool with JSON args")
    parser.add_argument("--workflow", nargs=2, metavar=("NAME", "INPUTS"), help="Run a workflow with JSON inputs")

    args = parser.parse_args()

    client = MCPHTTPTestClient(args.config, args.ael, args.host, args.port)

    try:
        client.start()

        # Always initialize first
        init_response = client.initialize()
        print(f"[CLIENT] Connected to: {init_response.get('result', {}).get('serverInfo', {})}", file=sys.stderr)

        if args.list_tools:
            tools = client.list_tools()
            print(f"\n{'='*60}")
            print(f"Available Tools ({len(tools)})")
            print(f"{'='*60}\n")
            for t in sorted(tools, key=lambda x: x["name"]):
                desc = t.get("description", "")[:50]
                print(f"  {t['name']:<40} {desc}")
            print()

        elif args.call:
            tool_name, args_json = args.call
            arguments = json.loads(args_json)
            result = client.call_tool(tool_name, arguments)
            print(f"\n{'='*60}")
            print(f"Tool: {tool_name}")
            print(f"{'='*60}")
            print_json(result)

        elif args.workflow:
            workflow_name, inputs_json = args.workflow
            inputs = json.loads(inputs_json)
            result = client.call_tool(f"workflow:{workflow_name}", inputs)
            print(f"\n{'='*60}")
            print(f"Workflow: {workflow_name}")
            print(f"{'='*60}")
            print_json(result)

        else:
            # Interactive mode
            interactive_mode(client)

    finally:
        client.stop()


if __name__ == "__main__":
    main()