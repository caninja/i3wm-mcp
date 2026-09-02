"""Response shaping. Every tool returns a JSON string."""

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
        ipc.get_connection().command(command)
    except I3Error as exc:
        payload: dict[str, Any] = {"command": command, **extra}
        if exc.replies is not None:
            payload["i3_replies"] = exc.replies
        return err(str(exc), **payload)
    return ok(command=command, **extra)


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
