"""The MCPServer instance. Tool modules import `mcp` and decorate it."""

from __future__ import annotations

from typing import Callable, TypeVar

from mcp.server.mcpserver import MCPServer
from pydantic import validate_call

mcp = MCPServer("i3_mcp")

_F = TypeVar("_F", bound=Callable)


def resolve_defaults(fn: _F) -> _F:
    """Make a direct call to a tool coroutine behave like an MCP-dispatched one.

    Two things only happen when MCPServer builds a pydantic model from the
    function signature and calls it with every argument resolved explicitly
    (mcp 2.1.1, verified: FuncMetadata.validate_arguments() / call_fn()):

    1. A parameter written `x: T | None = Field(default=None, ...)` gets its
       real default substituted for an omitted argument. At the plain-Python
       level the literal default is the FieldInfo object itself, so a direct
       call leaves an omitted argument bound to that FieldInfo rather than
       None/False/etc, and `if x is not None` then misbehaves.
    2. A plain value like the string "left" gets coerced to its declared
       type, e.g. Direction.LEFT, before the tool body runs. A direct call
       with a plain string leaves it as a plain str, and `direction.value`
       then fails -- Direction is a (str, Enum), so the string is never
       wrongly rejected, just never converted to the enum member either.

    Every tool here is unit tested by importing and calling the coroutine
    directly, bypassing that dispatch path entirely. `pydantic.validate_call`
    reproduces both behaviours for a direct call while leaving the MCP call
    path and schema generation unaffected (verified against a live
    call_tool() round trip and a list_tools() schema dump).
    """
    return validate_call(validate_return=False)(fn)


def main() -> None:
    from . import tools  # noqa: F401  (importing registers every tool)

    mcp.run()
