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
    criteria: WindowCriteria | None = Field(
        default=None,
        description="Which window to close. Omit to close the focused one.",
    ),
) -> str:
    """Close a window. The application may prompt to save first.

    Destructive: confirm the target before calling without criteria.
    """
    return render.run_targeted(criteria, "kill")
