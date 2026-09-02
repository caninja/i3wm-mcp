"""Workspace switching, renaming, and output assignment."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import ipc, render
from ..criteria import escape_value
from ..enums import WORKSPACE_KEYWORDS
from ..ipc import I3Error
from ..server import mcp


def _workspace_ref(name: str, by_number: bool, no_auto_back_and_forth: bool = False) -> str:
    flag = "--no-auto-back-and-forth " if no_auto_back_and_forth else ""
    if by_number:
        return f"workspace {flag}number {name}"
    return f'workspace {flag}"{escape_value(name)}"'


@mcp.tool(
    name="i3_workspace",
    annotations={
        "title": "Manage i3 Workspaces",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_workspace(
    action: Literal["switch", "navigate", "rename", "move_to_output", "bulk_move"] = Field(),
    name: str | None = Field(
        default=None,
        description="Name, or for switch one of next, prev, next_on_output, "
        "prev_on_output, back_and_forth, which ignore by_number. "
        "Omit on rename/move_to_output for the focused one.",
    ),
    by_number: bool = Field(default=False, description="For workspaces named like '3: web': match by leading number."),
    no_auto_back_and_forth: bool = Field(default=False, description="Suppress i3's automatic back_and_forth."),
    direction: Literal[
        "next", "prev", "next_on_output", "prev_on_output", "back_and_forth"
    ] | None = Field(default=None, description="navigate only."),
    new_name: str | None = Field(default=None, description="rename: the new name."),
    output: str | None = Field(
        default=None, description="move_to_output/bulk_move: target output."
    ),
    names: list[str] | None = Field(default=None, description="bulk_move: workspaces to move."),
    preserve: str | None = Field(
        default=None, description="bulk_move: one to leave where it is."
    ),
) -> str:
    """Switch, navigate, rename, or move workspaces between outputs."""
    if action == "switch":
        if name is None:
            return render.err("action=switch needs a name.")
        if name in WORKSPACE_KEYWORDS:
            return render.run(f"workspace {name}")
        return render.run(_workspace_ref(name, by_number, no_auto_back_and_forth))

    if action == "navigate":
        if direction is None:
            return render.err("action=navigate needs a direction.")
        return render.run(f"workspace {direction}")

    if action == "rename":
        if new_name is None:
            return render.err("action=rename needs new_name.")
        if name is None:
            return render.run(f'rename workspace to "{escape_value(new_name)}"')
        return render.run(
            f'rename workspace "{escape_value(name)}" to "{escape_value(new_name)}"'
        )

    if action == "move_to_output":
        if output is None:
            return render.err("action=move_to_output needs an output.")
        command = f"move workspace to output {output}"
        if name is not None:
            command = f"{_workspace_ref(name, by_number)}; {command}"
        return render.run(command)

    # bulk_move
    if not names or output is None:
        return render.err("action=bulk_move needs names and output.")
    try:
        existing = {ws["name"] for ws in ipc.get_connection().query(ipc.GET_WORKSPACES)}
    except I3Error as exc:
        return render.err(str(exc))

    moved: list[str] = []
    skipped: list[dict] = []
    for ws_name in names:
        if preserve is not None and ws_name == preserve:
            skipped.append({"name": ws_name, "reason": "preserved"})
            continue
        if ws_name not in existing:
            skipped.append({"name": ws_name, "reason": "does not exist"})
            continue
        command = f'{_workspace_ref(ws_name, False)}; move workspace to output {output}'
        try:
            ipc.get_connection().command(command)
        except I3Error as exc:
            skipped.append({"name": ws_name, "reason": str(exc)})
            continue
        moved.append(ws_name)

    return render.ok(moved=moved, skipped=skipped, output=output)
