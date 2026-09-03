"""Gap control.

The runtime syntax is `gaps <type> <current|all> <operation> <px>`. i3 4.25.1
rejects 'workspace' and 'global' as the scope token.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..server import mcp


@mcp.tool(
    name="i3_gaps",
    annotations={
        "title": "Adjust i3 Gaps",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_gaps(
    amount: int = Field(description="Pixels; 0 removes the gap.", ge=0, le=500),
    gap: Literal[
        "inner", "outer", "horizontal", "vertical", "top", "right", "bottom", "left"
    ] = Field(default="inner"),
    operation: Literal["set", "plus", "minus", "toggle"] = Field(
        default="set", description="toggle flips between the amount and 0."
    ),
    scope: Literal["current", "all"] = Field(
        default="current", description="Which workspaces."
    ),
) -> str:
    """Set or adjust gaps between windows (inner) or at workspace edges (outer)."""
    return render.run(f"gaps {gap} {scope} {operation} {amount}")
