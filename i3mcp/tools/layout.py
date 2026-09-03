"""Container layout and split orientation."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria
from ..server import mcp


@mcp.tool(
    name="i3_layout",
    annotations={
        "title": "Set i3 Layout or Split",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_layout(
    criteria: WindowCriteria | None = Field(default=None),
    layout: Literal[
        "default", "tabbed", "stacking", "splitv", "splith", "toggle split", "toggle all"
    ] | None = Field(default=None, description="Arrangement of the container's children."),
    split: Literal["horizontal", "vertical", "toggle"] | None = Field(
        default=None, description="Orientation for the next window opened here."
    ),
) -> str:
    """Set a container's layout, its split orientation, or both."""
    parts = []
    if layout is not None:
        parts.append(f"layout {layout}")
    if split is not None:
        parts.append(f"split {split}")
    if not parts:
        return render.err("Specify layout, split, or both.")
    return render.run_targeted(criteria, ", ".join(parts))
