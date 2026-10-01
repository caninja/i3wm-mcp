"""The MCPServer instance. Tool modules import `mcp` and decorate it."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from .schema import compact


class I3Server(MCPServer):
    """MCPServer that publishes compact input schemas and text-only results.

    Every tool returns a JSON string. Left structured, the SDK would also wrap
    it as {"result": "<escaped JSON>"} and publish an output schema for that,
    roughly doubling what the model reads.
    """

    def tool(self, *args: Any, structured_output: bool | None = False, **kwargs: Any):
        return super().tool(*args, structured_output=structured_output, **kwargs)

    async def list_tools(self):
        return [
            tool.model_copy(update={"input_schema": compact(tool.input_schema)})
            for tool in await super().list_tools()
        ]


mcp = I3Server("i3_mcp")


def main() -> None:
    from . import tools  # noqa: F401  (importing registers every tool)

    mcp.run()
