# Ploston Internal Validation

This directory contains configuration and workflows for validating Ploston with the native_tools MCP server from the agent submodule.

## Prerequisites

### Required

- Ploston server package installed
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

3. **Start Ploston:**
   ```bash
   ploston-server -c internal/ploston-config.yaml
   ```

## Testing Workflows

### Via CLI

```bash
# Simple URL fetch
ploston run fetch-url --input url=https://httpbin.org/get

# File operations (no external services needed)
ploston run file-operations --input filename=test.txt --input content="Hello Ploston!"

# Python exec modes
ploston run python-exec-explicit --input numbers='[1,2,3,4,5]'

# Fetch and publish to Kafka (requires Kafka)
ploston run fetch-and-publish --input url=https://httpbin.org/get --input topic=events
```

### Via MCP Test Client

The `mcp_http_test_client.py` utility simulates an MCP client (like Claude Desktop) for faster testing:

```bash
# List all available tools
python internal/mcp_http_test_client.py --list-tools

# Call a tool directly
python internal/mcp_http_test_client.py \
  --call http_request '{"url": "https://httpbin.org/get", "method": "GET"}'

# Run a workflow
python internal/mcp_http_test_client.py \
  --workflow fetch-url '{"url": "https://httpbin.org/get"}'

# Interactive mode (REPL)
python internal/mcp_http_test_client.py
# Then use: init, list, call <tool> <json>, workflow <name> <json>, ping, quit
```

### Via Claude Desktop

1. Run `ploston bootstrap` to deploy the Control Plane
2. Run `ploston inject` to inject MCP bridge config into Claude Desktop
3. Ask Claude: "Run the fetch-url workflow with url https://httpbin.org/get"

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

Ensure you're running from the repository root directory.
