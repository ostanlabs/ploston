#!/usr/bin/env python3
"""Wrapper script to run native_tools MCP server."""

import os
import sys
from pathlib import Path

# Add agent/src to path - look for it relative to this script or via env var
script_dir = Path(__file__).parent.resolve()
# Try multiple locations for agent/src
agent_src_candidates = [
    script_dir.parent.parent / "agent" / "src",  # meta-repo: packages/ploston/../agent/src
    script_dir.parent / "agent" / "src",  # if agent is sibling to internal
    Path(os.environ.get("AGENT_SRC", "")) if os.environ.get("AGENT_SRC") else None,
]

for candidate in agent_src_candidates:
    if candidate and candidate.exists():
        sys.path.insert(0, str(candidate))
        break

from native_tools.server import mcp

mcp.run()

