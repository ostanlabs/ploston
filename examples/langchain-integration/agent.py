"""LangChain agent using Ploston workflows as MCP tools.

Demonstrates a LangChain agent that has two tools:
  1. get_current_time — a native LangChain tool (no MCP, no Ploston)
  2. hello_world     — a Ploston workflow exposed via the MCP bridge

The agent picks whichever tool fits the user's query. Ploston workflows
appear as first-class peers to native tools — the agent doesn't know or
care that hello_world is a deterministic workflow under the hood.

Prerequisites:
  - A running Ploston Control Plane: `ploston bootstrap --edge`
  - The hello_world workflow registered (ships by default with bootstrap)
  - OPENAI_API_KEY set in the environment
  - Dependencies installed: `pip install -r requirements.txt`
"""

import asyncio
import shutil
from datetime import UTC, datetime

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient

# --- Native LangChain tool (no Ploston involved) ---


@tool
def get_current_time() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


# --- Agent setup ---


async def run_agent():
    # Find the ploston binary
    ploston_bin = shutil.which("ploston")
    if ploston_bin is None:
        raise RuntimeError("ploston CLI not found. Install it with: pip install ploston-cli")

    # Connect to Ploston via the MCP bridge (stdio transport).
    # The bridge exposes all registered workflows as MCP tools.
    client = MultiServerMCPClient(
        {
            "ploston": {
                "command": ploston_bin,
                "args": ["bridge", "--url", "http://localhost:8022"],
                "transport": "stdio",
            },
        }
    )

    # Load Ploston MCP tools and combine with native tools
    mcp_tools = await client.get_tools()
    all_tools = [get_current_time] + mcp_tools

    print(f"Loaded {len(all_tools)} tools:")
    for t in all_tools:
        print(f"  - {t.name}")
    print()

    # Create a LangChain agent with all tools
    agent = create_agent("openai:gpt-4.1", all_tools)

    # --- Query 1: should use the native get_current_time tool ---
    print("=" * 60)
    print("Query: What time is it?")
    print("=" * 60)
    response = await agent.ainvoke({"messages": "What time is it right now?"})
    last_msg = response["messages"][-1]
    print(f"Answer: {last_msg.content}\n")

    # --- Query 2: should use the Ploston hello_world workflow ---
    print("=" * 60)
    print("Query: Say hello to LangChain")
    print("=" * 60)
    response = await agent.ainvoke({"messages": "Say hello to LangChain using the hello tool"})
    last_msg = response["messages"][-1]
    print(f"Answer: {last_msg.content}\n")


if __name__ == "__main__":
    asyncio.run(run_agent())
