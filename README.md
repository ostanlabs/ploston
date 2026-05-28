# Ploston

Ploston is a deterministic execution layer for AI agents. It sits between your agent (Claude, Cursor, Codex, or any MCP-capable client) and the tools your agent calls, turning conversational tool-use into repeatable, auditable workflows. Every tool call passes through the Control Plane, which records inputs, outputs, and timing into a structured execution log — so when a workflow fails at step 4, you can re-run steps 1–3 from cache and debug step 4 in isolation.

<!-- TODO: embed T-685 hero GIF -->

## Quick Start

```bash
# 1. Install the CLI
pip install ploston-cli

# 2. Bootstrap the Control Plane (Docker Compose by default)
ploston bootstrap

# 3. Inject Ploston into your agent's MCP config
#    Supports: Claude Desktop, Cursor, Claude Code, Windsurf,
#              Gemini CLI, Cline, VS Code Copilot, Codex, Zed
ploston inject

# 4. Restart your agent — Ploston MCP servers appear automatically

# 5. Start building workflows conversationally, or run an existing one:
ploston run my-workflow
```

`ploston bootstrap` deploys the Control Plane, MCP bridge, and (optionally) a full observability stack locally:

```bash
# Include Grafana dashboards, ClickHouse, and OTEL Collector
ploston bootstrap --with-observability
```

For the full walkthrough, see [`docs/QUICK_START.md`](docs/QUICK_START.md).

## What the CLI Does

| Command | Purpose |
|---------|---------|
| `ploston bootstrap` | Deploy Control Plane (Docker or Kubernetes) |
| `ploston inject` | Inject Ploston MCP servers into agent configs |
| `ploston inspector` | Start/stop the local Session Inspector web UI |
| `ploston server add/list/remove` | Register upstream MCP servers |
| `ploston workflows` | List and manage workflows |
| `ploston run` | Execute a workflow |
| `ploston executions` | Inspect execution history |
| `ploston init` | Initialize configuration |
| `ploston bridge` | Start MCP bridge to Control Plane |
| `ploston runner` | Manage local tool-execution runners |
| `ploston validate` | Validate workflow YAML |
| `ploston tools` | List available tools |
| `ploston config` | Manage CLI and server configuration |

## Examples

| Example | Description |
|---------|-------------|
| [`examples/ploston-config.yaml`](examples/ploston-config.yaml) | Reference configuration file |
| [`examples/workflows/`](examples/workflows/) | Sample workflow definitions |

## Architecture

<!-- TODO: embed T-1074 architecture diagram -->

```
┌─────────────────┐     MCP (stdio)      ┌──────────────────────┐
│  Claude Desktop │◄────────────────────►│   MCP Bridge         │
│  Cursor / Codex │                      │   (ploston bridge)   │
│  Claude Code    │                      └──────────┬───────────┘
└─────────────────┘                                 │ HTTP
                                                    ▼
                                          ┌──────────────────────┐
                                          │   Control Plane      │
                                          │   (ploston-core)     │
                                          │                      │
                                          │  • Workflow engine   │
                                          │  • Execution log     │
                                          │  • Tool registry     │
                                          │  • Auth + routing    │
                                          └──────────┬───────────┘
                                                     │ MCP / HTTP
                                          ┌──────────┴───────────┐
                                          │   Upstream MCP       │
                                          │   Servers            │
                                          │   (your tools)       │
                                          └──────────────────────┘
```

## Configuration

Ploston reads configuration from (in priority order):

1. `ploston-config.yaml` in the current directory
2. `~/.ploston/config.yaml` (user scope)
3. Environment variables (`PLOSTON_HOST`, `PLOSTON_PORT`, etc.)
4. CLI flags

See [`examples/ploston-config.yaml`](examples/ploston-config.yaml) for all available options.

## Docker

```bash
# Pull and run the Control Plane directly
docker pull ostanlabs/ploston:latest
docker run -d --name ploston -p 8022:8022 ostanlabs/ploston:latest
```

Or use `ploston bootstrap` which handles Docker Compose setup automatically.

## Development

```bash
git clone https://github.com/ostanlabs/ploston.git
cd ploston
make install    # requires Python 3.12+ and uv
make test       # run all tests
make check      # lint + tests
make serve      # start server locally
```

## Related Packages

- [`ploston-cli`](https://github.com/ostanlabs/ploston-cli) — CLI client and local runner ([PyPI](https://pypi.org/project/ploston-cli/))
- [`ploston-core`](https://github.com/ostanlabs/ploston-core) — Control Plane server and workflow engine

## License

Apache-2.0

## Disclaimer

This project is developed independently in a personal capacity and is not affiliated with, endorsed by, or connected to any employer.
No proprietary or confidential information from any employer has been used in this project.
