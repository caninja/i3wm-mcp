"""The MCPServer instance. Tool modules import `mcp` and decorate it."""

from __future__ import annotations

import functools
import inspect
from typing import Callable, TypeVar

from mcp.server.mcpserver import MCPServer
from pydantic.fields import FieldInfo

mcp = MCPServer("i3_mcp")

_F = TypeVar("_F", bound=Callable)


def resolve_defaults(fn: _F) -> _F:
    """Make a direct call to a tool coroutine behave like an MCP-dispatched one.

    A parameter written `x: T | None = Field(default=None, ...)` has, at the
    plain-Python level, a literal default of the FieldInfo object itself --
    Field() is only resolved to its real default when MCPServer builds a
    pydantic model from the function signature and calls the function with
    every argument passed explicitly, which is what happens on the real MCP
    call path (mcp 2.1.1, verified: FuncMetadata.validate_arguments() /
    call_fn()). A direct Python call -- which is how every tool is unit
    tested here -- leaves any omitted argument bound to the raw FieldInfo
    object rather than None/False/etc, and things like `if x is not None`
    then misbehave since a FieldInfo is never None.

    This decorator resolves those defaults before the tool body runs, so a
    tool behaves identically whether invoked through the MCP protocol or
    directly. It preserves the original signature (via functools.wraps, and
    inspect.signature's own __wrapped__ following) so MCPServer's schema
    generation is unaffected.
    """
    sig = inspect.signature(fn)

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        for name, value in list(bound.arguments.items()):
            if isinstance(value, FieldInfo):
                bound.arguments[name] = (
                    value.default_factory() if value.default_factory is not None else value.default
                )
        return await fn(*bound.args, **bound.kwargs)

    return wrapper


def main() -> None:
    from . import tools  # noqa: F401  (importing registers every tool)

    mcp.run()
