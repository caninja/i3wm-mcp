"""Move keyboard focus."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria
from ..enums import Direction
from ..server import mcp


@mcp.tool(
    name="i3_focus",
    annotations={
        "title": "Focus i3 Window or Output",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_focus(
    direction: Direction | None = Field(
        default=None, description="Focus the neighbouring window: left, right, up, or down."
    ),
    target: Literal["parent", "child", "floating", "tiling", "mode_toggle"] | None = Field(
        default=None,
        description="Focus the parent or child container, or switch between floating and tiling.",
    ),
    sibling: Literal["next", "prev"] | None = Field(
        default=None, description="Focus the next or previous sibling container."
    ),
    cycle: Literal["next", "prev"] | None = Field(
        default=None, description="Focus the next or previous container in the tree."
    ),
    output: str | None = Field(
        default=None,
        description="Focus an output by name (e.g. 'HDMI-1') or relative position "
        "(left/right/up/down/current/primary/nonprimary/next).",
    ),
    criteria: WindowCriteria | None = Field(
        default=None, description="Focus the window matching these criteria."
    ),
    focus_workspace: bool = Field(
        default=False,
        description="With criteria: focus the matching window's workspace rather than the window.",
    ),
) -> str:
    """Focus a window by direction, container relationship, criteria, or output.

    Exactly one of direction, target, sibling, cycle, output or criteria.
    """
    chosen = [
        name
        for name, value in (
            ("direction", direction),
            ("target", target),
            ("sibling", sibling),
            ("cycle", cycle),
            ("output", output),
            ("criteria", criteria if criteria and not criteria.is_empty() else None),
        )
        if value is not None
    ]
    if not chosen:
        return render.err(
            "Specify one of: direction, target, sibling, cycle, output, or criteria."
        )
    if len(chosen) > 1:
        return render.err(f"Specify only one of these at a time, got: {', '.join(chosen)}.")

    if direction is not None:
        return render.run(f"focus {direction}")
    if target is not None:
        return render.run(f"focus {target}")
    if sibling is not None:
        return render.run(f"focus {sibling} sibling")
    if cycle is not None:
        return render.run(f"focus {cycle}")
    if output is not None:
        return render.run(f"focus output {output}")

    verb = "focus workspace" if focus_workspace else "focus"
    return render.run_targeted(criteria, verb)
