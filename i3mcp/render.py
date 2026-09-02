"""Response shaping. Every tool returns a JSON string unless asked for markdown."""

from __future__ import annotations

import json
from typing import Any

from . import ipc
from .ipc import I3Error

CHARACTER_LIMIT = 25000


def _dump(payload: dict) -> str:
    return json.dumps(payload, indent=2)


def ok(**fields: Any) -> str:
    return _dump({"success": True, **fields})


def err(message: str, **fields: Any) -> str:
    return _dump({"success": False, "error": message, **fields})


def run(command: str, **extra: Any) -> str:
    """Run an i3 command and render the outcome."""
    try:
        replies = ipc.get_connection().command(command)
    except I3Error as exc:
        payload: dict[str, Any] = {"command": command, **extra}
        if exc.replies is not None:
            payload["i3_replies"] = exc.replies
        return err(str(exc), **payload)
    return ok(command=command, replies=replies, **extra)


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


def markdown(text: str, limit: int = CHARACTER_LIMIT) -> str:
    if len(text) <= limit:
        return text
    notice = (
        f"\n\n---\n**Response truncated** (exceeded {limit} characters). "
        "Narrow the filters to see the rest."
    )
    return text[:limit] + notice


def window_lines(records: list[dict]) -> str:
    """Render window records as a compact markdown list."""
    if not records:
        return "No windows match.\n"
    lines = []
    for record in records:
        flags = []
        if record.get("focused"):
            flags.append("focused")
        if record.get("floating"):
            flags.append("floating")
        if record.get("urgent"):
            flags.append("urgent")
        if record.get("fullscreen"):
            flags.append("fullscreen")
        marks = record.get("marks") or []
        if marks:
            flags.append("marks: " + ", ".join(marks))
        suffix = f" [{'; '.join(flags)}]" if flags else ""
        lines.append(
            f"- **{record.get('name') or 'Untitled'}**{suffix}\n"
            f"  - class: `{record.get('window_class')}`  instance: `{record.get('instance')}`\n"
            f"  - workspace: `{record.get('workspace')}`  output: `{record.get('output')}`\n"
            f"  - con_id: `{record.get('con_id')}`  window_id: `{record.get('window_id')}`\n"
        )
    return "".join(lines)
