"""i3bar visibility."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..server import mcp, resolve_defaults


@mcp.tool(
    name="i3_bar",
    annotations={
        "title": "Control i3bar",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
@resolve_defaults
async def i3_bar(
    mode: Literal["dock", "hide", "invisible"] | None = Field(
        default=None,
        description="dock is always visible, hide shows on the modifier key, invisible never shows.",
    ),
    hidden_state: Literal["hide", "show"] | None = Field(
        default=None, description="With mode=hide, whether the bar is currently shown."
    ),
    bar_id: str | None = Field(
        default=None, description="Which bar. Omit to affect every bar. List ids with i3_query."
    ),
) -> str:
    """Set i3bar's display mode or its current hidden state.

    Give mode, hidden_state, or both.
    """
    parts = []
    if mode is not None:
        parts.append(f"bar mode {mode}" + (f" {bar_id}" if bar_id else ""))
    if hidden_state is not None:
        parts.append(f"bar hidden_state {hidden_state}" + (f" {bar_id}" if bar_id else ""))
    if not parts:
        return render.err("Specify mode, hidden_state, or both.")
    return render.run("; ".join(parts))
