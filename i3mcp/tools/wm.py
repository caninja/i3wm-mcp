"""Window-manager level operations: launching, reloading, modes, logging."""

from __future__ import annotations

import asyncio
import time
from typing import Literal

from pydantic import Field

from .. import ipc, render, tree
from ..criteria import escape_value
from ..ipc import I3Error
from ..server import mcp

TIMEOUT_HINT = "The command was accepted but no new window appeared in time; check i3_query."


def _launch_and_wait(cmd: str, wait_seconds: float) -> tuple[dict | None, float]:
    """Run cmd and return i3's first 'new' window container, plus seconds waited.

    Subscribing before the command runs is what makes this reliable: the window
    appears within milliseconds, so a stream opened afterwards can miss it.
    """
    started = time.monotonic()
    stream = ipc.subscribe(["window"])
    try:
        ipc.get_connection().command(cmd)
        deadline = started + wait_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None, time.monotonic() - started
            event = stream.next_event(remaining)
            if event is None:
                return None, time.monotonic() - started
            if event.get("change") == "new":
                return event.get("container") or {}, time.monotonic() - started
    finally:
        stream.close()


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
    wait_seconds: float | None = Field(
        default=None,
        ge=0.1,
        le=60,
        description=(
            "For action=exec: wait up to this long for a new window and return it "
            "(con_id, class, name)."
        ),
    ),
) -> str:
    """Launch an application, reload or restart i3, switch binding mode, or control logging.

    New windows land on the focused workspace, so exec switches there first when asked.
    """
    if action == "exec":
        if not command:
            return render.err("action=exec needs a command.")
        cmd = f'exec --no-startup-id "{escape_value(command)}"'
        if workspace:
            cmd = f'workspace "{escape_value(workspace)}"; {cmd}'
        if wait_seconds is None:
            return render.run(cmd)
        try:
            container, waited = await asyncio.to_thread(_launch_and_wait, cmd, wait_seconds)
        except I3Error as exc:
            return render.command_error(cmd, exc)
        if container is None:
            return render.ok(command=cmd, window=None, timed_out=True, hint=TIMEOUT_HINT)
        record = tree._record(
            container, workspace=None, output=container.get("output"), parent_layout=None
        )
        return render.ok(command=cmd, window=record, waited_seconds=round(waited, 2))

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
        return render.run(f"{action} {toggle}")

    if not path:
        return render.err("action=append_layout needs a path.")
    return render.run(f'append_layout "{escape_value(path)}"')
