"""Move containers and workspaces."""

from __future__ import annotations

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria, escape_value
from ..enums import Direction, Unit, WORKSPACE_KEYWORDS
from ..server import mcp

_RELATIVE_WORKSPACES = WORKSPACE_KEYWORDS | {"current"}


@mcp.tool(
    name="i3_move",
    annotations={
        "title": "Move i3 Container",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_move(
    criteria: WindowCriteria | None = Field(default=None),
    direction: Direction | None = Field(default=None, description="Step this way."),
    amount: int | None = Field(default=None, description="With direction: how far.", ge=1),
    unit: Unit = Field(
        default="px",
        description="For amount and position; ppt is percent of the output.",
    ),
    workspace: str | None = Field(
        default=None, description="Target name, or next/prev/current."
    ),
    by_number: bool = Field(
        default=False, description="For workspaces named like '3: web': match by leading number."
    ),
    follow: bool = Field(default=False, description="Switch to it after moving."),
    no_auto_back_and_forth: bool = Field(
        default=False, description="Suppress i3's automatic back_and_forth."
    ),
    output: str | None = Field(default=None, description="Target output name or position."),
    move_workspace: bool = Field(
        default=False, description="With output: move the whole workspace."
    ),
    position_x: int | None = Field(default=None, description="Floating window; give position_y too."),
    position_y: int | None = Field(default=None),
    center: bool = Field(default=False, description="Centre a floating window."),
    absolute: bool = Field(
        default=False, description="With center/position: coordinates span all outputs."
    ),
    to_mouse: bool = Field(default=False, description="To the mouse pointer (floating)."),
    to_mark: str | None = Field(default=None, description="Onto the container with this mark."),
    to_scratchpad: bool = Field(default=False),
    swap_with_mark: str | None = Field(default=None),
    swap_with_con_id: int | None = Field(default=None),
    swap_with_window_id: int | None = Field(default=None),
) -> str:
    """Move a container to a workspace, output, position, mark or the scratchpad,
    or swap it with another. Give exactly one destination."""
    has_position = position_x is not None or position_y is not None
    destinations = {
        "direction": direction is not None,
        "workspace": workspace is not None,
        "output": output is not None,
        "position": has_position,
        "center": center,
        "to_mouse": to_mouse,
        "to_mark": to_mark is not None,
        "to_scratchpad": to_scratchpad,
        "swap": swap_with_mark is not None
        or swap_with_con_id is not None
        or swap_with_window_id is not None,
    }
    chosen = [name for name, present in destinations.items() if present]
    if not chosen:
        return render.err(
            "Specify a destination: direction, workspace, output, position, center, "
            "to_mouse, to_mark, to_scratchpad, or a swap_with_* argument."
        )
    if len(chosen) > 1:
        return render.err(f"Specify only one destination, got: {', '.join(chosen)}.")

    if direction is not None:
        command = f"move {direction}"
        if amount is not None:
            command += f" {amount} {unit}"
    elif workspace is not None:
        flag = "--no-auto-back-and-forth " if no_auto_back_and_forth else ""
        if workspace in _RELATIVE_WORKSPACES:
            command = f"move container to workspace {workspace}"
        elif by_number:
            command = f"move {flag}container to workspace number {workspace}"
        else:
            command = f'move {flag}container to workspace "{escape_value(workspace)}"'
    elif output is not None:
        subject = "workspace" if move_workspace else "container"
        command = f"move {subject} to output {output}"
    elif has_position:
        if position_x is None or position_y is None:
            return render.err("Give both position_x and position_y, or neither.")
        prefix = "move absolute position" if absolute else "move position"
        command = f"{prefix} {position_x} {unit} {position_y} {unit}"
    elif center:
        command = "move absolute position center" if absolute else "move position center"
    elif to_mouse:
        command = "move position mouse"
    elif to_mark is not None:
        command = f'move container to mark "{escape_value(to_mark)}"'
    elif to_scratchpad:
        command = "move scratchpad"
    else:
        if swap_with_mark is not None:
            command = f'swap container with mark "{escape_value(swap_with_mark)}"'
        elif swap_with_con_id is not None:
            command = f"swap container with con_id {swap_with_con_id}"
        else:
            command = f"swap container with id {swap_with_window_id}"

    if follow and workspace is not None:
        if workspace in _RELATIVE_WORKSPACES:
            follow_cmd = f"workspace {workspace}"
        elif by_number:
            follow_cmd = f"workspace number {workspace}"
        else:
            follow_cmd = f'workspace "{escape_value(workspace)}"'
        # The ";" ends the criteria's scope in i3, so the follow-up switch runs
        # unconditionally -- exactly as it did when the prefix was applied here.
        command = f"{command}; {follow_cmd}"
    return render.run_targeted(criteria, command)
