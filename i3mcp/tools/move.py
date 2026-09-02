"""Move containers and workspaces."""

from __future__ import annotations

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria, escape_value, prefix_command
from ..enums import Direction, Unit
from ..server import mcp, resolve_defaults

_RELATIVE_WORKSPACES = {"next", "prev", "current", "next_on_output", "prev_on_output"}


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
@resolve_defaults
async def i3_move(
    criteria: WindowCriteria | None = Field(
        default=None, description="Which window to move. Omit to move the focused one."
    ),
    direction: Direction | None = Field(default=None, description="Move one step in this direction."),
    amount: int | None = Field(default=None, description="With direction: how far to move.", ge=1),
    unit: Unit = Field(default=Unit.PX, description="Unit for amount and position: px or ppt."),
    workspace: str | None = Field(
        default=None,
        description="Target workspace name, or next/prev/current for a relative move.",
    ),
    by_number: bool = Field(
        default=False,
        description="Treat workspace as a number. Use this with named workspaces like '3: web', "
        "where plain 'workspace 3' would create a new one instead of switching.",
    ),
    follow: bool = Field(default=False, description="Switch to the workspace after moving."),
    no_auto_back_and_forth: bool = Field(
        default=False, description="Suppress i3's automatic back_and_forth behaviour."
    ),
    output: str | None = Field(
        default=None, description="Target output name or relative position."
    ),
    move_workspace: bool = Field(
        default=False, description="With output: move the whole workspace instead of the container."
    ),
    position_x: int | None = Field(default=None, description="Absolute X for a floating window."),
    position_y: int | None = Field(default=None, description="Absolute Y for a floating window."),
    center: bool = Field(default=False, description="Centre a floating window on its output."),
    to_mouse: bool = Field(default=False, description="Move a floating window to the pointer."),
    to_mark: str | None = Field(default=None, description="Move onto the container with this mark."),
    to_scratchpad: bool = Field(default=False, description="Move the container to the scratchpad."),
    swap_with_mark: str | None = Field(default=None, description="Swap with the container holding this mark."),
    swap_with_con_id: int | None = Field(default=None, description="Swap with this container id."),
    swap_with_window_id: int | None = Field(default=None, description="Swap with this X11 window id."),
) -> str:
    """Move a container to a workspace, output, position, mark, or the scratchpad; or swap two containers.

    Pick exactly one destination. Without `criteria` the focused container moves.
    """
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
        command = f"move {direction.value}"
        if amount is not None:
            command += f" {amount} {unit.value}"
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
        command = (
            f"move absolute position {position_x} {unit.value} {position_y} {unit.value}"
        )
    elif center:
        command = "move absolute position center"
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

    full = prefix_command(criteria, command)
    if follow and workspace is not None:
        if workspace in _RELATIVE_WORKSPACES:
            follow_cmd = f"workspace {workspace}"
        elif by_number:
            follow_cmd = f"workspace number {workspace}"
        else:
            follow_cmd = f'workspace "{escape_value(workspace)}"'
        full = f"{full}; {follow_cmd}"
    return render.run(full)
