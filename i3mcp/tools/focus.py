"""Move keyboard focus."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria, escape_value
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
        default=None, description="Focus the neighbouring window."
    ),
    target: Literal["parent", "child", "floating", "tiling", "mode_toggle"] | None = Field(
        default=None,
        description="parent/child walk the tree; mode_toggle swaps floating and tiling.",
    ),
    sibling: Literal["next", "prev"] | None = Field(
        default=None, description="Within the same parent."
    ),
    cycle: Literal["next", "prev"] | None = Field(
        default=None, description="Across the whole tree."
    ),
    output: str | None = Field(
        default=None,
        description="Output name, e.g. 'HDMI-1', or left/right/up/down/primary/next.",
    ),
    criteria: WindowCriteria | None = Field(default=None),
    focus_workspace: bool = Field(
        default=False,
        description="With criteria: focus its workspace, not the window.",
    ),
) -> str:
    """Focus a window or an output. Give exactly one of direction, target,
    sibling, cycle, output, criteria."""
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
        return render.run(f'focus output "{escape_value(output)}"')

    verb = "focus workspace" if focus_workspace else "focus"
    return render.run_targeted(criteria, verb)
