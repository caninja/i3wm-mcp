"""Window properties: floating, sticky, fullscreen, border, title."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria, escape_value
from ..server import mcp

Toggle = Literal["enable", "disable", "toggle"]


@mcp.tool(
    name="i3_window",
    annotations={
        "title": "Set i3 Window Properties",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_window(
    criteria: WindowCriteria | None = Field(default=None),
    floating: Toggle | None = Field(default=None),
    sticky: Toggle | None = Field(
        default=None, description="Floating window stays on every workspace."
    ),
    fullscreen: Toggle | None = Field(default=None),
    fullscreen_global: bool = Field(
        default=False, description="With fullscreen: span every output."
    ),
    border: Literal["normal", "pixel", "none", "toggle"] | None = Field(
        default=None, description="normal keeps the title bar, pixel drops it."
    ),
    border_width: int | None = Field(
        default=None, description="Pixels; normal and pixel borders only.", ge=0, le=50
    ),
    title_format: str | None = Field(
        default=None,
        description="Template, e.g. '%title (%class)'; also %instance, %machine, %shell.",
    ),
    title_window_icon: Literal["on", "off", "toggle"] | None = Field(
        default=None, description="Application icon in the title bar."
    ),
    title_window_icon_padding: int | None = Field(
        default=None,
        description="Pixels around the icon; valid on its own.",
        ge=0,
    ),
) -> str:
    """Set floating, sticky, fullscreen, border or title properties; several in
    one call run as a single chained i3 command."""
    parts: list[str] = []
    if floating is not None:
        parts.append(f"floating {floating}")
    if sticky is not None:
        parts.append(f"sticky {sticky}")
    if fullscreen is not None:
        parts.append(f"fullscreen {fullscreen}" + (" global" if fullscreen_global else ""))
    if border is not None:
        if border in ("normal", "pixel") and border_width is not None:
            parts.append(f"border {border} {border_width}")
        else:
            parts.append(f"border {border}")
    if title_format is not None:
        parts.append(f'title_format "{escape_value(title_format)}"')
    if title_window_icon is not None:
        parts.append(f"title_window_icon {title_window_icon}")
    if title_window_icon_padding is not None:
        parts.append(f"title_window_icon padding {title_window_icon_padding}px")

    if not parts:
        return render.err(
            "Specify at least one of: floating, sticky, fullscreen, border, "
            "title_format, or title_window_icon."
        )

    return render.run_targeted(criteria, ", ".join(parts))
