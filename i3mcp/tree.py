"""Walk the i3 tree into flat window records carrying their context.

i3 4.25.1 puts every managed window in a node of type 'con' with a separate
'floating' field of 'auto_off' | 'auto_on' | 'user_off' | 'user_on'. A node of
type 'floating_con' is the wrapper, not the window, so testing node type for
floating never matches.

Records are compact: a key is omitted whenever its value is None, False, []
or {}. `parent_layout` carries the enclosing container's layout
(splith|splitv|tabbed|stacked|dockarea), or the string "floating" for a
window reached through `floating_nodes`. `rect` is `[x, y, width, height]`.

`scratchpad_state` lives on the enclosing `floating_con`, never on the window
con below it, so the walk carries it down the same way it carries `floating`;
the uninteresting "none" is dropped entirely.
"""

from __future__ import annotations

from typing import Any

SCRATCHPAD_WORKSPACE = "__i3_scratch"
_FLOATING_STATES = {"auto_on", "user_on"}


def _rect_list(rect: dict | None) -> list[int]:
    rect = rect or {}
    return [rect.get("x", 0), rect.get("y", 0), rect.get("width", 0), rect.get("height", 0)]


def _compact(record: dict) -> dict:
    """Drop keys whose value is None, False, [] or {}. (0 and "" are kept.)"""
    compacted = {}
    for key, value in record.items():
        if value is None or value is False:
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        compacted[key] = value
    return compacted


def _scratchpad_state(node: dict, inherited: str | None = None) -> str | None:
    """The window's scratchpad state, taken from its floating_con when needed."""
    state = node.get("scratchpad_state")
    if not state or state == "none":
        state = inherited
    return None if state == "none" else state


def _record(
    node: dict,
    workspace: dict | None,
    output: str | None,
    parent_layout: str | None,
    scratchpad_state: str | None = None,
) -> dict:
    props = node.get("window_properties") or {}
    workspace = workspace or {}
    workspace_num = workspace.get("num")
    if not isinstance(workspace_num, int) or workspace_num < 0:
        workspace_num = None
    record = {
        "con_id": node.get("id"),
        "window_id": node.get("window"),
        "name": node.get("name"),
        "window_class": props.get("class"),
        "instance": props.get("instance"),
        "window_role": props.get("window_role"),
        "window_type": node.get("window_type"),
        "marks": node.get("marks") or [],
        "workspace": workspace.get("name"),
        "workspace_num": workspace_num,
        "output": output,
        "floating": node.get("floating") in _FLOATING_STATES,
        "focused": bool(node.get("focused")),
        "urgent": bool(node.get("urgent")),
        "fullscreen": bool(node.get("fullscreen_mode")),
        "sticky": bool(node.get("sticky")),
        "scratchpad_state": _scratchpad_state(node, scratchpad_state),
        "parent_layout": parent_layout,
        "rect": _rect_list(node.get("rect")),
    }
    return _compact(record)


def walk_windows(tree: dict) -> list[dict]:
    """Flatten the tree into window records, tagged with workspace and output."""
    records: list[dict] = []

    def visit(
        node: dict,
        workspace: dict | None,
        output: str | None,
        parent_layout: str | None,
        floating: bool = False,
        scratchpad_state: str | None = None,
    ) -> None:
        node_type = node.get("type")
        if node_type == "output":
            output = node.get("name") or output
        elif node_type == "workspace":
            workspace = node
            output = node.get("output") or output

        window_id = node.get("window")
        if window_id:
            records.append(
                _record(
                    node,
                    workspace,
                    output,
                    "floating" if floating else parent_layout,
                    scratchpad_state,
                )
            )

        # A real floating_con carries its own (irrelevant) "layout"; once inside a
        # floating subtree, that stays "floating" all the way down, regardless.
        layout = node.get("layout") or parent_layout
        for child in node.get("nodes") or []:
            visit(child, workspace, output, layout, floating, scratchpad_state)
        for child in node.get("floating_nodes") or []:
            # The wrapper is where i3 records the scratchpad state.
            visit(child, workspace, output, layout, True, _scratchpad_state(child, scratchpad_state))

    visit(tree, None, None, None)
    return records


def is_dock(record: dict) -> bool:
    """i3bar and other docked clients appear in the tree as ordinary windows.

    On i3 4.25.1 the i3bar window reports window_type "unknown"; what marks it
    is the enclosing node of type/layout "dockarea", carried into records as
    parent_layout. Raw tree nodes are accepted too, hence the "layout" check.
    """
    return (
        record.get("window_type") == "dock"
        or record.get("parent_layout") == "dockarea"
        or record.get("layout") == "dockarea"
    )


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
        if window_class is not None and not _contains(record.get("window_class"), window_class):
            continue
        if title is not None and not _contains(record.get("name"), title):
            continue
        if instance is not None and not _contains(record.get("instance"), instance):
            continue
        if window_type is not None and record.get("window_type") != window_type:
            continue
        if workspace is not None:
            matches_name = record.get("workspace") == workspace
            matches_num = workspace.isdigit() and record.get("workspace_num") == int(workspace)
            if not (matches_name or matches_num):
                continue
        if mark is not None and mark not in (record.get("marks") or []):
            continue
        if floating is not None and record.get("floating", False) is not floating:
            continue
        if urgent is not None and record.get("urgent", False) is not urgent:
            continue
        if focused is not None and record.get("focused", False) is not focused:
            continue
        in_scratchpad = record.get("workspace") == SCRATCHPAD_WORKSPACE
        if scratchpad is not None and in_scratchpad is not scratchpad:
            continue
        result.append(record)
    return result


def find_focused(records: list[dict]) -> dict | None:
    for record in records:
        if record.get("focused"):
            return record
    return None


def _percent(node: dict) -> float | None:
    percent = node.get("percent")
    return round(percent, 2) if isinstance(percent, (int, float)) else None


def _outline_leaf(node: dict) -> dict:
    props = node.get("window_properties") or {}
    return _compact(
        {
            "con_id": node.get("id"),
            "name": node.get("name"),
            "window_class": props.get("class"),
            "percent": _percent(node),
            "focused": bool(node.get("focused")),
            "marks": node.get("marks") or [],
        }
    )


def _outline_node(node: dict) -> dict:
    """Render one node (leaf or container) of a workspace's tree, skipping docks."""
    if node.get("window"):
        return _outline_leaf(node)
    children = [_outline_node(child) for child in node.get("nodes") or [] if not is_dock(child)]
    record = _compact(
        {
            "con_id": node.get("id"),
            "layout": node.get("layout"),
            "percent": _percent(node),
        }
    )
    record["nodes"] = children  # always present, even empty; never compacted away
    return record


def _find_workspace_by_name_or_num(tree_root: dict, workspace: str) -> dict | None:
    def visit(node: dict) -> dict | None:
        if node.get("type") == "workspace":
            if node.get("name") == workspace:
                return node
            if workspace.isdigit() and node.get("num") == int(workspace):
                return node
        for child in node.get("nodes") or []:
            found = visit(child)
            if found is not None:
                return found
        return None

    return visit(tree_root)


def _find_focused_workspace(tree_root: dict) -> dict | None:
    def visit(node: dict, workspace: dict | None) -> dict | None:
        if node.get("type") == "workspace":
            workspace = node
            # An empty workspace is itself the focused container.
            if node.get("focused"):
                return node
        if node.get("window") and node.get("focused"):
            return workspace
        for child in node.get("nodes") or []:
            found = visit(child, workspace)
            if found is not None:
                return found
        for child in node.get("floating_nodes") or []:
            found = visit(child, workspace)
            if found is not None:
                return found
        return None

    return visit(tree_root, None)


def outline(tree_root: dict, workspace: str | None) -> dict | None:
    """Render one workspace's container structure, con_ids and all.

    Returns None when the requested workspace (by name or number) does not
    exist, or, when `workspace` is None, no window in the whole tree is
    focused.
    """
    if workspace is None:
        workspace_node = _find_focused_workspace(tree_root)
    else:
        workspace_node = _find_workspace_by_name_or_num(tree_root, workspace)
    if workspace_node is None:
        return None

    nodes = [_outline_node(child) for child in workspace_node.get("nodes") or [] if not is_dock(child)]
    floating: list[dict] = []
    for wrapper in workspace_node.get("floating_nodes") or []:
        for inner in wrapper.get("nodes") or []:
            if not is_dock(inner):
                floating.append(_outline_leaf(inner))

    workspace_num = workspace_node.get("num")
    if not isinstance(workspace_num, int) or workspace_num < 0:
        workspace_num = None

    record = _compact(
        {
            "con_id": workspace_node.get("id"),
            "workspace": workspace_node.get("name"),
            "workspace_num": workspace_num,
            "layout": workspace_node.get("layout"),
        }
    )
    record["nodes"] = nodes  # always present, even empty; never compacted away
    if floating:
        record["floating"] = floating
    return record
