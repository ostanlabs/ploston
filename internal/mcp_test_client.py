#!/usr/bin/env python3
"""
MCP Test Client - Simulates an MCP client (like Claude Desktop) for testing AEL.

This utility spawns AEL as a subprocess and communicates via stdio using the
MCP protocol (JSON-RPC). Useful for:
- Testing AEL's MCP server functionality without Claude Desktop
- Faster iteration during development
- Automated integration testing

Usage:
    # Interactive mode
    python internal/mcp_test_client.py -c internal/ael-config.yaml

    # Run a single command
    python internal/mcp_test_client.py -c internal/ael-config.yaml --list-tools
    python internal/mcp_test_client.py -c internal/ael-config.yaml --call workflow:fetch-url '{"url": "https://httpbin.org/get"}'
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


class MCPTestClient:
    """MCP client that communicates with AEL via stdio."""

    def __init__(self, config_path: str, ael_command: str | None = None):
        self.config_path = Path(config_path).resolve()
        self.ael_command = ael_command or self._find_ael()
        self.process: subprocess.Popen | None = None
        self._msg_id = 0

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
        """Start AEL as a subprocess."""
        cmd = [self.ael_command, "-c", str(self.config_path), "serve"]
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            cwd=self.config_path.parent.parent,  # repo root
        )
        print(f"[CLIENT] Started AEL (PID: {self.process.pid})", file=sys.stderr)

    def stop(self) -> None:
        """Stop AEL subprocess."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            print(f"[CLIENT] Stopped AEL", file=sys.stderr)

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for response."""
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise RuntimeError("AEL not started")

        msg_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
        }
        if params:
            request["params"] = params

        # Send request
        request_line = json.dumps(request) + "\n"
        self.process.stdin.write(request_line)
        self.process.stdin.flush()
        print(f"[CLIENT] >>> {method}", file=sys.stderr)

        # Read response
        response_line = self.process.stdout.readline()
        if not response_line:
            raise RuntimeError("No response from AEL")

        response = json.loads(response_line)
        return response

    def initialize(self) -> dict[str, Any]:
        """Send initialize request."""
        return self.send("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "mcp-test-client", "version": "1.0.0"},
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


def interactive_mode(client: MCPTestClient) -> None:
    """Run interactive REPL."""
    print("\n=== MCP Test Client Interactive Mode ===")
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
            line = input("mcp> ").strip()
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
    parser = argparse.ArgumentParser(description="MCP Test Client for AEL")
    parser.add_argument("-c", "--config", required=True, help="Path to AEL config file")
    parser.add_argument("--ael", help="Path to ael command (auto-detected if not specified)")
    parser.add_argument("--list-tools", action="store_true", help="List tools and exit")
    parser.add_argument("--call", nargs=2, metavar=("TOOL", "ARGS"), help="Call a tool with JSON args")
    parser.add_argument("--workflow", nargs=2, metavar=("NAME", "INPUTS"), help="Run a workflow with JSON inputs")

    args = parser.parse_args()

    client = MCPTestClient(args.config, args.ael)

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
