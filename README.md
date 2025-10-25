# i3wm MCP Server

> **Control i3 window manager with natural language through Claude and other AI assistants**

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server providing programmatic control of the [i3 window manager](https://i3wm.org/). This server exposes different tools covering i3 functionality, enabling AI assistants to manage windows, workspaces, layouts, gaps, and more through natural conversation.

[![MCP](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io/)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![i3wm](https://img.shields.io/badge/i3wm-4.x-orange)](https://i3wm.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

### Vibecode alert
> Mostly vibed with claude



## Overview

The i3wm MCP Server bridges AI assistants with i3's powerful tiling window manager, enabling:

- **Natural language control**: "Move this window to workspace 2" → executed instantly
- **Complex automation**: Chain multiple window operations in a single request
- **Context awareness**: Query window states, binding modes, and configurations

**Example interactions:**
```
User: "Set 10px gaps between windows and make them look nice"
Claude: *Sets inner gaps to 10px, outer gaps to 5px*

User: "Move my Firefox to the right monitor and make it fullscreen"
Claude: *Identifies Firefox window, moves to specified output, enables fullscreen*

User: "What version of i3 am I running?"
Claude: *Returns: i3 version 4.23 (2023-10-29)*
```


## Quick Start

### Installation

**Prerequisites:** Python 3.8+, i3 window manager

1. **Clone the repository:**
```bash
git clone https://github.com/caninja/i3wm-mcp.git
cd i3wm-mcp
```

2. **Install dependencies:**
```bash
sudo pacman -Sy python-pydantic
pipx install mcp
pipx install fastmcp

# depending on setup, maybe the following is enough for you
python -m venv venv
./venv/bin/pip install fastmcp pydantic  
```

3. **Add to Claude:**

Using the MCP CLI (recommended):
```bash
# Add the server to Claude configuration
claude mcp add --transport stdio i3 /absolute/path/to/i3wm-mcp/venv/bin/python /absolute/path/to/i3wm-mcp/i3_mcp.py
```

Or manually edit `~/.claude.json`:
```json
{
  "mcpServers": {
    "i3": {
      "command": "python",
      "args": ["/absolute/path/to/i3wm-mcp/i3_mcp.py"]
    }
  }
}
```

4. **Restart Claude** and start using natural language to control i3!


### Verification

Test the server independently:
```bash
# Verify syntax
python -m py_compile i3_mcp.py

# Test server startup (will timeout after 5s - this is expected)
timeout 5s python i3_mcp.py || echo "✓ Server ready"
```

Try:
- "What workspaces do I have?"
- "Set inner gaps to 10 pixels"
- "Focus my Firefox window"

---

## TODO
* Add documentation for models for cleaner lookup
