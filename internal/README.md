# AEL Internal Validation

This directory contains configuration and workflows for validating AEL with the native_tools MCP server from the agent submodule.

## Prerequisites

### Required

- AEL MVP complete (all 13 components)
- Agent submodule initialized:
  ```bash
  git submodule update --init
  ```

### Optional Services

For full tool coverage, you may need:

| Service | Tools | Setup |
|---------|-------|-------|
| Firecrawl | `firecrawl_search`, `firecrawl_map`, `firecrawl_extract` | `docker-compose up firecrawl` |
| Kafka | `kafka_publish`, `kafka_list_topics`, `kafka_create_topic`, `kafka_consume` | `docker-compose up kafka` |
| Ollama | `ml_embed_text`, `ml_text_similarity`, `ml_classify_text` | [ollama.ai](https://ollama.ai) |

## Setup

1. **Copy environment file:**
   ```bash
   cp internal/.env.example internal/.env
   ```

2. **Edit values in `internal/.env`** (optional - defaults work for local services)

3. **Start AEL:**
   ```bash
   ael -c internal/ael-config.yaml serve
   ```

## Testing Workflows

### Via CLI

```bash
# Simple URL fetch
ael run fetch-url --input url=https://httpbin.org/get

# File operations (no external services needed)
ael run file-operations --input filename=test.txt --input content="Hello AEL!"

# Python exec modes
ael run python-exec-explicit --input numbers='[1,2,3,4,5]'

# Fetch and publish to Kafka (requires Kafka)
ael run fetch-and-publish --input url=https://httpbin.org/get --input topic=events
```

### Via MCP Test Client

The `mcp_test_client.py` utility simulates an MCP client (like Claude Desktop) for faster testing:

```bash
# List all available tools
python internal/mcp_test_client.py -c internal/ael-config.yaml --list-tools

# Call a tool directly
python internal/mcp_test_client.py -c internal/ael-config.yaml \
  --call http_request '{"url": "https://httpbin.org/get", "method": "GET"}'

# Run a workflow
python internal/mcp_test_client.py -c internal/ael-config.yaml \
  --workflow fetch-url '{"url": "https://httpbin.org/get"}'

# Interactive mode (REPL)
python internal/mcp_test_client.py -c internal/ael-config.yaml
# Then use: init, list, call <tool> <json>, workflow <name> <json>, ping, quit
```

### Via Claude Desktop

1. Add AEL to Claude Desktop config (see below)
2. Ask Claude: "Call workflow:fetch-url with url https://httpbin.org/get"

## Claude Desktop Integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ael": {
      "command": "/path/to/agent-execution-layer/.venv/bin/ael",
      "args": ["-c", "internal/ael-config.yaml", "serve"],
      "cwd": "/path/to/agent-execution-layer"
    }
  }
}
```

Replace `/path/to/agent-execution-layer` with your actual path (e.g., `/Users/yourname/code/agent-execution-layer`).

## Available Workflows

| Workflow | Description | Required Services |
|----------|-------------|-------------------|
| `fetch-url` | Fetch a URL via HTTP | None |
| `fetch-and-publish` | Fetch URL → transform → publish to Kafka | Kafka |
| `file-operations` | Write, read, list files | None |
| `python-exec-explicit` | Demo implicit vs explicit python_exec | None |

## Available Tools (from native_tools)

| Category | Tools |
|----------|-------|
| Filesystem | `fs_read`, `fs_write`, `fs_list`, `fs_delete` |
| Network | `http_request`, `network_ping`, `network_dns_lookup`, `network_port_check` |
| Kafka | `kafka_publish`, `kafka_list_topics`, `kafka_create_topic`, `kafka_consume` |
| Firecrawl | `firecrawl_search`, `firecrawl_map`, `firecrawl_extract` |
| Data | `data_validate`, `data_json_to_csv`, `data_csv_to_json` |
| Extraction | `extract_text`, `extract_structured`, `extract_file_metadata` |
| ML | `ml_embed_text`, `ml_text_similarity`, `ml_classify_text` |

## Troubleshooting

### "Tool not found" errors

Ensure the agent submodule is initialized:
```bash
git submodule update --init
```

### Kafka connection errors

Start Kafka locally:
```bash
docker-compose up -d kafka
```

### Firecrawl errors

Start Firecrawl locally:
```bash
docker-compose up -d firecrawl
```

Or set `FIRECRAWL_API_KEY` for cloud Firecrawl.

### Python import errors

Ensure you're running from the `agent-execution-layer` root directory.

