"""Close windows."""

from __future__ import annotations

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria
from ..server import mcp


@mcp.tool(
    name="i3_kill",
    annotations={
        "title": "Close i3 Window",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_kill(
    criteria: WindowCriteria | None = Field(default=None),
) -> str:
    """Close a window (the focused one without criteria); the app may prompt to
    save. Destructive: confirm the target first."""
    return render.run_targeted(criteria, "kill")
