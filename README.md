# i3wm MCP Server

> **Control i3 window manager with natural language through Claude and other AI assistants**

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server providing programmatic control of the [i3 window manager](https://i3wm.org/). This server exposes 13 tools covering i3 functionality, enabling AI assistants to manage windows, workspaces, layouts, gaps, and more through natural conversation.

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


## Install

Requires [`uv`](https://docs.astral.sh/uv/). No pipx, no manual venv.

```bash
git clone https://github.com/caninja/i3wm-mcp.git
cd i3wm-mcp
claude mcp add --transport stdio i3 -- uv run --directory /absolute/path/to/i3wm-mcp i3wm-mcp
```

Or edit `~/.claude.json` directly:

```json
{
  "mcpServers": {
    "i3": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/i3wm-mcp", "i3wm-mcp"]
    }
  }
}
```



## Requirements

- Python 3.10+
- i3 4.x (developed and verified against 4.25.1)
- `uv`

Runtime dependencies are `mcp>=2` and `pydantic>=2`, declared in `pyproject.toml`
and resolved automatically by `uv`. There is nothing else to install by hand.

## Tools

| Tool | Does |
|------|------|
| `i3_query` | Read i3 state: tree, focused window, scratchpad, workspaces, outputs, marks, version, config, bar config, binding modes/state. |
| `i3_focus` | Move keyboard focus by direction, container relationship, sibling, output, or criteria. |
| `i3_move` | Move a container to a workspace, output, position, mark, or the scratchpad; or swap two containers. |
| `i3_resize` | Grow, shrink, or set the size of a container, in px or ppt. |
| `i3_kill` | Close a window. Destructive. |
| `i3_window` | Set floating, sticky, fullscreen, border, and title properties. |
| `i3_layout` | Set a container's layout or split orientation. |
| `i3_workspace` | Switch, navigate, rename, or move workspaces between outputs. |
| `i3_mark` | Set or remove marks on a window. |
| `i3_scratchpad` | Show, hide, or move windows in the scratchpad, keyed by mark. |
| `i3_gaps` | Set or adjust inner/outer/edge gaps. |
| `i3_bar` | Set i3bar's display mode or hidden state. |
| `i3_wm` | Launch applications, reload/restart i3, switch binding mode, or control logging. |

## Criteria

Most mutating tools take an optional `criteria` object so a command can target
any window, not just the focused one. Leave it unset to act on the focused
window.

String fields (`window_class`, `title`, `instance`, ...) match **exactly** by
default. Set `match` to `substring` or `regex` for looser matching. `con_id`
(from `i3_query`) is the most precise and stable handle — prefer it once you
know it.

## Verification

```bash
uv run --with pytest --with pytest-asyncio pytest    # offline unit tests
uv run python scripts/smoke.py                        # live, drives real i3
```

The smoke test opens and closes a real window on a scratch workspace and
restores your previously focused workspace. Run it deliberately.

Try:
- "What workspaces do I have?"
- "Set inner gaps to 10 pixels"
- "Focus my Firefox window"


## Gotchas

- Use `by_number=true` on `i3_workspace`/`i3_move` for workspaces named like
  `"3: web"` — plain `workspace 3` would create a new workspace called `3`
  instead of switching to the existing one.
- `i3_wm(action="exec")` returns as soon as i3 accepts the command, before the
  new window exists. Poll `i3_query(what="tree")` for it rather than assuming
  it's there immediately.
- `exit` is not exposed on purpose — terminating the i3 session isn't
  something a tool call should be able to do by accident.
