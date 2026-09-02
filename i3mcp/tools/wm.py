"""Window-manager level operations: launching, reloading, modes, logging."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import escape_value
from ..server import mcp


@mcp.tool(
    name="i3_wm",
    annotations={
        "title": "Control i3 Itself",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def i3_wm(
    action: Literal[
        "exec", "reload", "restart", "mode", "nop", "shmlog", "debuglog", "append_layout"
    ] = Field(description="Which window-manager operation to run."),
    command: str | None = Field(
        default=None, description="For action=exec: the shell command to launch.", max_length=500
    ),
    workspace: str | None = Field(
        default=None, description="For action=exec: switch to this workspace before launching."
    ),
    mode_name: str | None = Field(
        default=None, description="For action=mode: the binding mode to enter, e.g. 'resize'."
    ),
    comment: str | None = Field(default=None, description="For action=nop: a comment to log."),
    toggle: Literal["on", "off", "toggle"] | None = Field(
        default=None, description="For shmlog and debuglog."
    ),
    path: str | None = Field(
        default=None, description="For action=append_layout: path to a saved layout JSON file."
    ),
) -> str:
    """Launch an application, reload or restart i3, switch binding mode, or control logging.

    New windows land on the focused workspace, so exec switches there first when asked.
    """
    if action == "exec":
        if not command:
            return render.err("action=exec needs a command.")
        cmd = f"exec --no-startup-id {command}"
        if workspace:
            cmd = f'workspace "{escape_value(workspace)}"; {cmd}'
        return render.run(cmd)

    if action in ("reload", "restart"):
        return render.run(action)

    if action == "mode":
        if not mode_name:
            return render.err("action=mode needs mode_name.")
        return render.run(f'mode "{escape_value(mode_name)}"')

    if action == "nop":
        return render.run(f"nop {comment}" if comment else "nop")

    if action in ("shmlog", "debuglog"):
        if toggle is None:
            return render.err(f"action={action} needs toggle=on, off, or toggle.")
        if action == "debuglog" and toggle == "toggle":
            return render.err("debuglog accepts only on or off.")
        return render.run(f"{action} {toggle}")

    if not path:
        return render.err("action=append_layout needs a path.")
    return render.run(f'append_layout "{escape_value(path)}"')
