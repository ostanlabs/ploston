# LangChain + Ploston Integration Example

Ploston workflows as peer tools to native LangChain tools. A LangChain agent
decides on each query whether to use a native tool (current UTC time) or a
Ploston-wrapped workflow (`hello_world`), treating both identically.

## What This Demonstrates

- A LangChain agent using `langchain-mcp-adapters` to load Ploston MCP tools
- Ploston workflows appearing as first-class LangChain tools alongside native ones
- The agent autonomously choosing which tool to call based on the user query

## Prerequisites

1. A running Ploston Control Plane with the `hello_world` workflow registered:

   ```bash
   ploston bootstrap --edge
   ```

2. An OpenAI API key (or swap to any LangChain-supported LLM):

   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Run

```bash
python agent.py
```

The agent receives two queries:
1. "What time is it?" → uses the native `get_current_time` tool
2. "Say hello to LangChain" → uses the Ploston `hello_world` workflow via MCP

## What to Look At After Running

- **Terminal output** — shows which tool the agent selected for each query
- **Ploston Inspector** — run `ploston inspector` and look for the `hello_world`
  execution in the Session Inspector. The MCP call and its wrapped workflow steps
  are visible in the execution trace.
- **Execution history** — `ploston executions list` shows the workflow run triggered
  by the LangChain agent
