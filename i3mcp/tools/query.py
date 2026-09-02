"""Read-only inspection of i3 state."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import Field

from .. import ipc, render, tree
from ..ipc import I3Error
from ..server import mcp

_SIMPLE_QUERIES = {
    "workspaces": (ipc.GET_WORKSPACES, "workspaces"),
    "outputs": (ipc.GET_OUTPUTS, "outputs"),
    "marks": (ipc.GET_MARKS, "marks"),
    "version": (ipc.GET_VERSION, "version"),
    "binding_modes": (ipc.GET_BINDING_MODES, "binding_modes"),
    "binding_state": (ipc.GET_BINDING_STATE, "binding_state"),
}


@mcp.tool(
    name="i3_query",
    annotations={
        "title": "Query i3 State",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def i3_query(
    what: Literal[
        "tree",
        "focused",
        "scratchpad",
        "layout",
        "workspaces",
        "outputs",
        "marks",
        "version",
        "config",
        "bar_config",
        "binding_modes",
        "binding_state",
    ] = Field(default="tree", description="Which piece of i3 state to read."),
    window_class: str | None = Field(
        default=None, description="tree/scratchpad: case-insensitive substring of the window class."
    ),
    title: str | None = Field(
        default=None, description="tree/scratchpad: case-insensitive substring of the window title."
    ),
    instance: str | None = Field(default=None, description="tree/scratchpad: substring of the instance."),
    window_type: str | None = Field(default=None, description="tree: exact window type, e.g. 'dialog'."),
    workspace: str | None = Field(
        default=None, description="tree/layout: workspace name, or its bare number."
    ),
    mark: str | None = Field(default=None, description="tree: exact mark on the container."),
    floating: bool | None = Field(default=None, description="tree: restrict to floating or tiling windows."),
    urgent: bool | None = Field(default=None, description="tree: restrict to urgent windows."),
    include_docks: bool = Field(default=False, description="tree: include i3bar and other dock windows."),
    bar_id: str | None = Field(
        default=None, description="bar_config: which bar. Omit to list bar ids."
    ),
    include_config_body: bool = Field(
        default=False, description="config: include the full config text, which can be large."
    ),
) -> str:
    """Read i3 state: the window tree, workspaces, outputs, marks, config, bars, or binding modes.

    Window records carry con_id, workspace and output, which the other tools'
    `criteria` argument expects. Absent booleans mean false; `rect` is `[x, y, width, height]`; `workspace` accepts a name or a bare number.
    layout: nested containers of one workspace, with con_ids that i3_layout can target.
    """
    conn = ipc.get_connection()
    try:
        if what in ("tree", "focused", "scratchpad"):
            records = tree.walk_windows(conn.query(ipc.GET_TREE))
            if what == "focused":
                found = tree.find_focused(records)
                return render.ok(window=found)
            filtered = tree.filter_windows(
                records,
                window_class=window_class,
                title=title,
                instance=instance,
                window_type=window_type,
                workspace=workspace,
                mark=mark,
                floating=floating,
                urgent=urgent,
                scratchpad=True if what == "scratchpad" else None,
                include_docks=include_docks,
            )
            return render.json_list("windows", filtered)

        if what == "layout":
            result = tree.outline(conn.query(ipc.GET_TREE), workspace)
            if result is None:
                if workspace is None:
                    return render.err("No focused window; pass workspace explicitly.")
                return render.err(
                    f"No workspace named or numbered {workspace!r}.",
                    hint="List them with i3_query(what='workspaces').",
                )
            return render.ok(**result)

        if what == "config":
            data = conn.query(ipc.GET_CONFIG)
            body = data.get("config", "")
            if include_config_body:
                return render.ok(config=body, included_configs=data.get("included_configs", []))
            return render.ok(
                config_length=len(body),
                config_preview=body[:500],
                included_configs=data.get("included_configs", []),
                hint="Pass include_config_body=true for the full text.",
            )

        if what == "bar_config":
            payload = bar_id or ""
            data = conn.query(ipc.GET_BAR_CONFIG, payload)
            if bar_id:
                return render.ok(bar_config=data)
            return render.ok(bar_ids=data, hint="Pass bar_id to read one bar's configuration.")

        msg_type, key = _SIMPLE_QUERIES[what]
        data = conn.query(msg_type)
        if isinstance(data, list):
            return render.json_list(key, data)
        return render.ok(**{key: data})
    except I3Error as exc:
        return render.err(str(exc), what=what)
