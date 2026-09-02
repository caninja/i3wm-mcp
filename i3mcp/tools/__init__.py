"""Importing this package registers every tool on the server."""

from . import (  # noqa: F401
    bar,
    focus,
    gaps,
    kill,
    layout,
    mark,
    move,
    query,
    resize,
    scratchpad,
    window,
    wm,
    workspace,
)
from ..schema import compact
from ..server import mcp

# mcp 2.1.1 builds each tool's schema once, at registration, and MCPServer.list_tools()
# re-reads Tool.parameters on every call -- so compacting it in place here is what
# clients see. _tool_manager is the only handle mcp 2.1.1 offers onto the Tool objects.
for _tool in mcp._tool_manager.list_tools():
    _tool.parameters = compact(_tool.parameters)
