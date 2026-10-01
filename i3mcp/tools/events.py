"""Read the background event log."""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import Field

from .. import events, render
from ..server import mcp

# How long a first call waits for the watcher's initial subscription.
CONNECT_GRACE = 1.0


@mcp.tool(
    name="i3_events",
    annotations={
        "title": "Read i3 Events",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_events(
    since: int | None = Field(
        default=None, description="cursor from a previous reply; omit for the latest events."
    ),
    wait_seconds: float | None = Field(
        default=None, ge=0.1, le=300, description="Block until a matching event or timeout."
    ),
    event: Literal["window", "workspace", "output", "mode"] | None = Field(default=None),
    change: str | None = Field(
        default=None, description="e.g. new, close, focus, title, urgent, mark, move, init."
    ),
    window_class: str | None = Field(default=None, description="Case-insensitive substring."),
    title: str | None = Field(default=None, description="Case-insensitive substring."),
    con_id: int | None = Field(default=None),
) -> str:
    """Window, workspace, output and mode events logged in the background since
    the server started. Pass the reply's cursor as `since` to get only newer
    ones; wait_seconds blocks until one matches (e.g. a window turns urgent)."""
    log = events.get_log()
    if not log.connected:
        await asyncio.to_thread(log.wait_connected, CONNECT_GRACE)
    filters = {
        "event": event,
        "change": change,
        "window_class": window_class,
        "title": title,
        "con_id": con_id,
    }
    if not log.connected and not log.read(since, filters)["events"]:
        return render.err(f"Not subscribed to i3 events: {log.last_error or 'connecting'}.")

    if wait_seconds is None:
        result = log.read(since, filters)
    else:
        result = await asyncio.to_thread(log.wait, since, filters, wait_seconds)
    if not log.connected:
        result["watcher"] = f"disconnected: {log.last_error}"
    return render.ok(**result)
