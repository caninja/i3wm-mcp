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


class SubscribeFailed(Exception):
    """ipc.subscribe failed, so the command was never sent."""


def _is_wanted(container: dict, wait_match: str | None) -> bool:
    """Without wait_match any new window counts; with it, class or title must contain it."""
    if wait_match is None:
        return True
    props = container.get("window_properties") or {}
    haystack = f"{props.get('class') or ''}\n{container.get('name') or ''}".lower()
    return wait_match.lower() in haystack


def _launch_and_wait(
    cmd: str, wait_seconds: float, wait_match: str | None = None
) -> tuple[dict | None, float]:
    """Run cmd and return i3's first wanted 'new' window container, plus seconds waited.

    Subscribing before the command runs is what makes this reliable: the window
    appears within milliseconds, so a stream opened afterwards can miss it. The
    handshake is itself a round-trip to i3, so the clock starts only once it is
    done -- otherwise setup eats the caller's wait_seconds.
    """
    try:
        stream = ipc.subscribe(["window"])
    except (I3Error, OSError) as exc:
        raise SubscribeFailed(str(exc)) from exc
    started = time.monotonic()
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
            container = event.get("container") or {}
            if event.get("change") == "new" and _is_wanted(container, wait_match):
                return container, time.monotonic() - started
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
    ] = Field(),
    command: str | None = Field(
        default=None, description="exec: the shell command to launch.", max_length=500
    ),
    workspace: str | None = Field(
        default=None,
        description="exec: switch here first; new windows land on the focused workspace.",
    ),
    mode_name: str | None = Field(
        default=None, description="mode: which mode to enter, e.g. 'resize'."
    ),
    comment: str | None = Field(default=None, description="nop: text to log."),
    toggle: Literal["on", "off", "toggle"] | None = Field(
        default=None, description="For shmlog and debuglog."
    ),
    path: str | None = Field(
        default=None, description="append_layout: a saved layout JSON file."
    ),
    wait_seconds: float | None = Field(
        default=None,
        ge=0.1,
        le=60,
        description=(
            "exec: wait up to this long for a new window; returns it "
            "(con_id, class, name) or timed_out=true."
        ),
    ),
    wait_match: str | None = Field(
        default=None,
        description="exec: only a new window whose class or title contains this counts.",
    ),
) -> str:
    """Launch an app, reload or restart i3, switch binding mode, or control logging."""
    if action == "exec":
        if not command:
            return render.err("action=exec needs a command.")
        cmd = f'exec --no-startup-id "{escape_value(command)}"'
        if workspace:
            cmd = f'workspace "{escape_value(workspace)}"; {cmd}'
        if wait_seconds is None:
            return render.run(cmd)
        try:
            container, waited = await asyncio.to_thread(_launch_and_wait, cmd, wait_seconds, wait_match)
        except SubscribeFailed as exc:
            return render.err(f"Cannot subscribe to i3 events: {exc}", command=cmd)
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
        return render.run(f'nop "{escape_value(comment)}"' if comment else "nop")

    if action in ("shmlog", "debuglog"):
        if toggle is None:
            return render.err(f"action={action} needs toggle=on, off, or toggle.")
        return render.run(f"{action} {toggle}")

    if not path:
        return render.err("action=append_layout needs a path.")
    return render.run(f'append_layout "{escape_value(path)}"')
