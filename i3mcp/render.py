"""Response shaping. Every tool returns a JSON string."""

from __future__ import annotations

import json
from typing import Any

from . import ipc, tree
from .criteria import WindowCriteria, prefix_command
from .ipc import I3Error

CHARACTER_LIMIT = 25000
TARGET_LIMIT = 20


def _dump(payload: dict) -> str:
    return json.dumps(payload, indent=2)


def ok(**fields: Any) -> str:
    return _dump({"success": True, **fields})


def err(message: str, **fields: Any) -> str:
    return _dump({"success": False, "error": message, **fields})


def run(command: str, **extra: Any) -> str:
    """Run an i3 command and render the outcome."""
    try:
        ipc.get_connection().command(command)
    except I3Error as exc:
        payload: dict[str, Any] = {"command": command, **extra}
        if exc.replies is not None:
            payload["i3_replies"] = exc.replies
        return err(str(exc), **payload)
    return ok(command=command, **extra)


URGENT_NOTE = "i3 acts on one urgent window; these are the candidates."


def _target(record: dict) -> dict:
    """Identify one window, staying compact: a key the record lacks is left out."""
    fields = {
        "con_id": record.get("con_id"),
        "name": record.get("name"),
        "window_class": record.get("window_class"),
    }
    return {key: value for key, value in fields.items() if value is not None}


def run_targeted(criteria: WindowCriteria | None, command: str, **extra: Any) -> str:
    """Run a command against the windows it will actually hit, or refuse to run it.

    i3 answers success even when criteria match nothing, so resolve the targets
    from the tree first and report them alongside the command.
    """
    try:
        records = tree.walk_windows(ipc.get_connection().query(ipc.GET_TREE))
    except I3Error as exc:
        return err(str(exc))
    records = tree.filter_windows(records)

    if criteria is None or criteria.is_empty():
        focused = tree.find_focused(records)
        targets = [focused] if focused is not None else []
    else:
        try:
            criteria.validate_patterns()
            targets = [record for record in records if criteria.matches(record)]
        except ValueError as exc:
            return err(str(exc))
        if not targets:
            return err(
                "No window matches the criteria.",
                criteria=criteria.to_selector(),
                hint="List windows with i3_query; con_id is the most reliable selector.",
            )
        if criteria.urgent is not None and len(targets) > 1:
            # i3's cmd_criteria_match_windows keeps only the single most (or
            # least) recently urgent container, and the records carry no
            # urgency timestamp to reproduce that choice here.
            extra["note"] = URGENT_NOTE

    return run(
        prefix_command(criteria, command),
        targets=[_target(record) for record in targets[:TARGET_LIMIT]],
        target_count=len(targets),
        **extra,
    )


def json_list(key: str, items: list, limit: int = CHARACTER_LIMIT, **fields: Any) -> str:
    """Render a list, dropping whole entries rather than slicing mid-structure."""
    kept = list(items)
    while True:
        payload: dict[str, Any] = {"success": True, key: kept, "count": len(kept), **fields}
        if len(kept) < len(items):
            payload["truncated"] = True
            payload["omitted"] = len(items) - len(kept)
            payload["hint"] = "Narrow the filters to see the rest."
        out = _dump(payload)
        if len(out) <= limit or not kept:
            return out
        # Drop roughly the proportion that overflows, at least one entry.
        overflow = len(out) - limit
        drop = max(1, int(len(kept) * overflow / len(out)) + 1)
        kept = kept[: max(0, len(kept) - drop)]
