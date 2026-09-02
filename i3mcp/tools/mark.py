"""Set and remove i3 marks."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria, escape_value, prefix_command
from ..server import mcp


@mcp.tool(
    name="i3_mark",
    annotations={
        "title": "Mark or Unmark i3 Window",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_mark(
    criteria: WindowCriteria | None = Field(
        default=None, description="Which window to mark. Omit for the focused one."
    ),
    mark: str | None = Field(
        default=None, description="Mark to set. Marks are the stable way to address a window later."
    ),
    mode: Literal["replace", "add", "toggle"] = Field(
        default="replace",
        description="replace clears other marks, add keeps them, toggle flips this one.",
    ),
    unmark: str | None = Field(default=None, description="Mark to remove."),
    unmark_all: bool = Field(default=False, description="Remove every mark from the target."),
) -> str:
    """Set or remove a mark on a window. Marks survive moves and are the best criteria handle.

    Give one of: mark, unmark, or unmark_all.
    """
    chosen = [
        name
        for name, present in (("mark", mark is not None), ("unmark", unmark is not None), ("unmark_all", unmark_all))
        if present
    ]
    if not chosen:
        return render.err("Specify one of: mark, unmark, or unmark_all.")
    if len(chosen) > 1:
        return render.err(f"Specify only one of these at a time, got: {', '.join(chosen)}.")

    if mark is not None:
        command = f'mark --{mode} "{escape_value(mark)}"'
    elif unmark is not None:
        command = f'unmark "{escape_value(unmark)}"'
    else:
        command = "unmark"

    return render.run(prefix_command(criteria, command))
