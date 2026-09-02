"""Scratchpad management, keyed consistently on marks."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import ipc, render, tree
from ..criteria import WindowCriteria, escape_value, prefix_command
from ..enums import MatchMode
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
        description="show toggles a window in or out; move sends one in; hide_all sends every visible one back."
    ),
    mark: str | None = Field(
        default=None,
        description="Named scratchpad. On move the mark is set; on show it is looked up. "
        "Use the same name for both.",
    ),
    criteria: WindowCriteria | None = Field(
        default=None,
        description="For show and move: which window to act on. Omit for the focused one.",
    ),
) -> str:
    """Show, hide, or populate the scratchpad. Named scratchpads are addressed by mark.

    List what is in the scratchpad with i3_query(what='scratchpad').
    """
    if action == "show":
        has_criteria = criteria is not None and not criteria.is_empty()
        if mark is not None and has_criteria:
            return render.err("Give mark or criteria for show, not both.")
        if mark is not None:
            selector = WindowCriteria(con_mark=mark, match=MatchMode.EXACT).to_selector()
            return render.run(f"{selector} scratchpad show")
        if has_criteria:
            return render.run(f"{criteria.to_selector()} scratchpad show")
        return render.run("scratchpad show")

    if action == "move":
        parts = []
        if mark is not None:
            parts.append(f'mark --replace "{escape_value(mark)}"')
        parts.append("move scratchpad")
        return render.run(prefix_command(criteria, ", ".join(parts)))

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
            failed.append({"con_id": record["con_id"], "name": record["name"], "error": str(exc)})
            continue
        hidden.append({"con_id": record["con_id"], "name": record["name"], "class": record["window_class"]})

    return render.ok(hidden_count=len(hidden), hidden=hidden, failed=failed)
