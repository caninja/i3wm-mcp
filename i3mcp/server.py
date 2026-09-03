"""The MCPServer instance. Tool modules import `mcp` and decorate it."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("i3_mcp")


def main() -> None:
    from . import tools  # noqa: F401  (importing registers every tool)

    mcp.run()
