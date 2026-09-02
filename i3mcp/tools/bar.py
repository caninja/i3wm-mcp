"""i3bar visibility."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import escape_value
from ..server import mcp


@mcp.tool(
    name="i3_bar",
    annotations={
        "title": "Control i3bar",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_bar(
    mode: Literal["dock", "hide", "invisible"] | None = Field(
        default=None,
        description="dock: always visible; hide: on the modifier key; invisible: never.",
    ),
    hidden_state: Literal["hide", "show"] | None = Field(
        default=None, description="With mode=hide: show or hide it now."
    ),
    bar_id: str | None = Field(
        default=None, description="Omit for every bar; ids from i3_query."
    ),
) -> str:
    """Set i3bar's display mode or hidden state. Give mode, hidden_state, or both."""
    # Verified on i3 4.25.1: a quoted bar id parses, and `bar` takes no
    # criteria prefix, so an unquoted one would let ";" inject a command.
    suffix = f' "{escape_value(bar_id)}"' if bar_id else ""
    parts = []
    if mode is not None:
        parts.append(f"bar mode {mode}{suffix}")
    if hidden_state is not None:
        parts.append(f"bar hidden_state {hidden_state}{suffix}")
    if not parts:
        return render.err("Specify mode, hidden_state, or both.")
    return render.run("; ".join(parts))
