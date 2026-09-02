"""Walk the i3 tree into flat window records carrying their context.

i3 4.25.1 puts every managed window in a node of type 'con' with a separate
'floating' field of 'auto_off' | 'auto_on' | 'user_off' | 'user_on'. A node of
type 'floating_con' is the wrapper, not the window, so testing node type for
floating never matches.
"""

from __future__ import annotations

from typing import Any

SCRATCHPAD_WORKSPACE = "__i3_scratch"
_FLOATING_STATES = {"auto_on", "user_on"}


def _record(node: dict, workspace: str | None, output: str | None) -> dict:
    props = node.get("window_properties") or {}
    return {
        "con_id": node.get("id"),
        "window_id": node.get("window"),
        "name": node.get("name"),
        "window_class": props.get("class"),
        "instance": props.get("instance"),
        "window_role": props.get("window_role"),
        "window_type": node.get("window_type"),
        "marks": node.get("marks") or [],
        "workspace": workspace,
        "output": output,
        "floating": node.get("floating") in _FLOATING_STATES,
        "focused": bool(node.get("focused")),
        "urgent": bool(node.get("urgent")),
        "fullscreen": bool(node.get("fullscreen_mode")),
        "scratchpad_state": node.get("scratchpad_state"),
        "layout": node.get("layout"),
        "rect": node.get("rect") or {},
    }


def walk_windows(tree: dict) -> list[dict]:
    """Flatten the tree into window records, tagged with workspace and output."""
    records: list[dict] = []

    def visit(node: dict, workspace: str | None, output: str | None) -> None:
        node_type = node.get("type")
        if node_type == "output":
            output = node.get("name") or output
        elif node_type == "workspace":
            workspace = node.get("name") or workspace
            output = node.get("output") or output

        window_id = node.get("window")
        if window_id:
            records.append(_record(node, workspace, output))

        for child in list(node.get("nodes") or []) + list(node.get("floating_nodes") or []):
            visit(child, workspace, output)

    visit(tree, None, None)
    return records


def is_dock(record: dict) -> bool:
    """i3bar and other docked clients appear in the tree as ordinary windows."""
    return record.get("window_type") == "dock"


def _contains(haystack: Any, needle: str) -> bool:
    return needle.lower() in str(haystack or "").lower()


def filter_windows(
    records: list[dict],
    *,
    window_class: str | None = None,
    title: str | None = None,
    instance: str | None = None,
    window_type: str | None = None,
    workspace: str | None = None,
    mark: str | None = None,
    floating: bool | None = None,
    urgent: bool | None = None,
    focused: bool | None = None,
    scratchpad: bool | None = None,
    include_docks: bool = False,
) -> list[dict]:
    """Filter window records. String filters are case-insensitive substrings."""
    result = []
    for record in records:
        if not include_docks and is_dock(record):
            continue
        if window_class is not None and not _contains(record["window_class"], window_class):
            continue
        if title is not None and not _contains(record["name"], title):
            continue
        if instance is not None and not _contains(record["instance"], instance):
            continue
        if window_type is not None and record.get("window_type") != window_type:
            continue
        if workspace is not None and record.get("workspace") != workspace:
            continue
        if mark is not None and mark not in (record.get("marks") or []):
            continue
        if floating is not None and record["floating"] is not floating:
            continue
        if urgent is not None and record["urgent"] is not urgent:
            continue
        if focused is not None and record["focused"] is not focused:
            continue
        in_scratchpad = record.get("workspace") == SCRATCHPAD_WORKSPACE
        if scratchpad is not None and in_scratchpad is not scratchpad:
            continue
        result.append(record)
    return result


def find_focused(records: list[dict]) -> dict | None:
    for record in records:
        if record["focused"]:
            return record
    return None
