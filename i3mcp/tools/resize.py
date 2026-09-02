"""Resize containers."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria, prefix_command
from ..enums import Unit
from ..server import mcp


@mcp.tool(
    name="i3_resize",
    annotations={
        "title": "Resize i3 Container",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_resize(
    mode: Literal["grow", "shrink", "set"] = Field(
        description="grow or shrink by an amount, or set an absolute size."
    ),
    criteria: WindowCriteria | None = Field(
        default=None, description="Which window to resize. Omit for the focused one."
    ),
    direction: Literal["width", "height", "left", "right", "up", "down"] | None = Field(
        default=None, description="Required for grow and shrink: which edge or dimension changes."
    ),
    amount: int = Field(default=10, description="How much to grow or shrink.", ge=1),
    width: int | None = Field(default=None, description="For mode=set: target width."),
    height: int | None = Field(default=None, description="For mode=set: target height."),
    unit: Unit = Field(
        default=Unit.PX,
        description="px for pixels, ppt for percent of the parent container.",
    ),
) -> str:
    """Grow, shrink, or set the size of a container.

    ppt works on tiled containers; px suits floating ones.
    """
    if mode == "set":
        if width is None and height is None:
            return render.err("mode=set needs width, height, or both.")
        parts = ["resize set"]
        if width is not None:
            parts.append(f"width {width} {unit.value}")
        if height is not None:
            parts.append(f"height {height} {unit.value}")
        command = " ".join(parts)
    else:
        if direction is None:
            return render.err(f"mode={mode} needs a direction.")
        if unit == Unit.PPT:
            # i3 4.25.1's grammar for resize grow/shrink requires a px amount;
            # ppt is only accepted as a fallback "or" clause (verified live:
            # a bare "resize grow right 1 ppt" is a parse error -- "Expected
            # one of these tokens: 'px', 'or', <end>"). resize set has no such
            # restriction. Re-using amount for both satisfies the grammar and
            # gives the intended ppt behaviour on a tiling container.
            command = f"resize {mode} {direction} {amount} px or {amount} ppt"
        else:
            command = f"resize {mode} {direction} {amount} {unit.value}"

    return render.run(prefix_command(criteria, command))
