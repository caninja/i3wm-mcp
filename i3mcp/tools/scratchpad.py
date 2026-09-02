"""Scratchpad management, keyed consistently on marks."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import ipc, render, tree
from ..criteria import WindowCriteria, escape_value
from ..ipc import I3Error
from ..server import mcp


@mcp.tool(
    name="i3_scratchpad",
    annotations={
        "title": "Manage i3 Scratchpad",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_scratchpad(
    action: Literal["show", "move", "hide_all"] = Field(
        description="show toggles one in or out; move sends one in; hide_all sends all back."
    ),
    mark: str | None = Field(
        default=None,
        description="Named scratchpad: set on move, looked up on show; "
        "use the same name for both.",
    ),
    criteria: WindowCriteria | None = Field(default=None, description="show/move only."),
) -> str:
    """Show, hide or populate the scratchpad; named ones are addressed by mark.
    List its contents with i3_query(what='scratchpad')."""
    if action == "show":
        has_criteria = criteria is not None and not criteria.is_empty()
        if mark is not None and has_criteria:
            return render.err("Give mark or criteria for show, not both.")
        if mark is not None:
            by_mark = WindowCriteria(con_mark=mark, match="exact")
            return render.run_targeted(by_mark, "scratchpad show")
        if has_criteria:
            return render.run_targeted(criteria, "scratchpad show")
        return render.run("scratchpad show")

    if action == "move":
        parts = []
        if mark is not None:
            parts.append(f'mark --replace "{escape_value(mark)}"')
        parts.append("move scratchpad")
        return render.run_targeted(criteria, ", ".join(parts))

    # hide_all: a scratchpad window is visible when it sits on a real workspace.
    try:
        records = tree.walk_windows(ipc.get_connection().query(ipc.GET_TREE))
    except I3Error as exc:
        return render.err(str(exc))

    visible = [
        record
        for record in records
        if record.get("scratchpad_state")
        and record["scratchpad_state"] != "none"
        and record.get("workspace") != tree.SCRATCHPAD_WORKSPACE
    ]

    hidden: list[dict] = []
    failed: list[dict] = []
    for record in visible:
        try:
            ipc.get_connection().command(f"[con_id={record['con_id']}] move scratchpad")
        except I3Error as exc:
            failed.append({"con_id": record["con_id"], "name": record.get("name"), "error": str(exc)})
            continue
        hidden.append(
            {
                "con_id": record["con_id"],
                "name": record.get("name"),
                "class": record.get("window_class"),
            }
        )

    return render.ok(hidden_count=len(hidden), hidden=hidden, failed=failed)
